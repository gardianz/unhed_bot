from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Generator

import requests
from requests import HTTPError

from config import config
from logger import logger
from models import Market
from strategy_base import BaseStrategy


class MarketFeed:
    def __init__(self, strategy: BaseStrategy) -> None:
        self._strategy = strategy
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        logger.info("Resolving active market ids...")
        self._market_ids = self._resolve_market_ids()
        self._waiting_for_markets_logged = False
        self._market_payload_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._price_history_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._price_history_phase_cache: dict[str, int] = {}
        self._decision_window_history_locked: set[str] = set()
        self._rate_limited_until: dict[str, float] = {}

    @property
    def request_timeout(self) -> tuple[float, float]:
        return (config.HTTP_CONNECT_TIMEOUT_SEC, config.HTTP_TIMEOUT_SEC)

    def refresh_market_ids(self) -> None:
        self._market_ids = self._resolve_market_ids()
        if self._market_ids:
            self._waiting_for_markets_logged = False

    def drop_market(self, slug: str) -> None:
        market_id = self._market_ids.pop(slug, None)
        if not market_id:
            return
        self._market_payload_cache.pop(market_id, None)
        self._price_history_cache.pop(market_id, None)
        self._price_history_phase_cache.pop(market_id, None)
        self._decision_window_history_locked.discard(market_id)
        self._rate_limited_until.pop(f"market:{market_id}", None)
        self._rate_limited_until.pop(f"history:{market_id}", None)

    def _resolve_market_ids(self) -> dict[str, str]:
        specs = config.market_specs
        market_ids = {
            slug: spec.market_id
            for slug, spec in specs.items()
            if spec.market_id
        }
        missing = [slug for slug, spec in specs.items() if not spec.market_id]
        if not missing:
            return market_ids

        response = self._session.get(
            f"{config.UNHEDGED_API_BASE}/api/v1/markets",
            params={"category": "Crypto", "status": "ACTIVE", "limit": 100},
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        markets = response.json().get("markets", [])

        for slug in missing:
            spec = specs[slug]
            candidates = [
                item
                for item in markets
                if self._is_matching_above_market(item, spec.search_terms)
            ]
            candidates.sort(key=lambda item: item.get("endTime", ""))
            matched = candidates[0] if candidates else None
            if matched is not None:
                market_ids[slug] = matched["id"]

        return market_ids

    def _fetch_market_payload(self, market_id: str) -> dict[str, Any]:
        cache_key = f"market:{market_id}"
        now = time.monotonic()
        cached = self._market_payload_cache.get(market_id)
        if cached and (
            now - cached[0] < config.MARKET_DETAIL_REFRESH_SEC
            or now < self._rate_limited_until.get(cache_key, 0.0)
        ):
            return cached[1]

        response = self._session.get(
            f"{config.UNHEDGED_API_BASE}/api/v1/markets/{market_id}",
            timeout=self.request_timeout,
        )
        if response.status_code == 429 and cached:
            self._rate_limited_until[cache_key] = now + config.RATE_LIMIT_BACKOFF_SEC
            return cached[1]
        response.raise_for_status()
        payload = response.json().get("market")
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected market payload for market_id={market_id}")
        self._market_payload_cache[market_id] = (now, payload)
        self._rate_limited_until.pop(cache_key, None)
        return payload

    def _completed_segment_count(self, timer_left: int) -> int:
        segment_end_thresholds = [
            segment.freeze_threshold_sec for segment in self._strategy.segment_windows
        ]
        return sum(1 for threshold in segment_end_thresholds if timer_left <= threshold)

    def _fetch_price_history(self, market_id: str, timer_left: int) -> dict[str, Any]:
        cache_key = f"history:{market_id}"
        now = time.monotonic()
        cached = self._price_history_cache.get(market_id)
        current_phase = self._completed_segment_count(timer_left)
        last_phase = self._price_history_phase_cache.get(market_id, -1)
        if cached:
            if now < self._rate_limited_until.get(cache_key, 0.0):
                return cached[1]
            if timer_left <= config.DECISION_WINDOW_SEC:
                if market_id in self._decision_window_history_locked:
                    return cached[1]
            elif current_phase == last_phase:
                return cached[1]

        response = self._session.get(
            f"{config.UNHEDGED_API_BASE}/api/v1/markets/{market_id}/price-history",
            timeout=self.request_timeout,
        )
        if response.status_code == 429 and cached:
            self._rate_limited_until[cache_key] = now + config.RATE_LIMIT_BACKOFF_SEC
            return cached[1]
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Unexpected price-history payload for market_id={market_id}"
            )
        self._price_history_cache[market_id] = (now, payload)
        self._price_history_phase_cache[market_id] = current_phase
        if timer_left <= config.DECISION_WINDOW_SEC:
            self._decision_window_history_locked.add(market_id)
        else:
            self._decision_window_history_locked.discard(market_id)
        self._rate_limited_until.pop(cache_key, None)
        return payload

    @staticmethod
    def _extract_target_price(payload: dict[str, Any], question: str) -> float:
        resolver = payload.get("autoResolution") or {}
        resolver_config = resolver.get("resolverConfig") or {}
        threshold = resolver_config.get("threshold")
        if threshold is not None:
            return float(threshold)

        match = re.search(r"\$([0-9,]+(?:\.[0-9]+)?)", question)
        if match:
            return float(match.group(1).replace(",", ""))
        raise RuntimeError("Target price could not be determined from market payload.")

    @staticmethod
    def _extract_outcome_data(payload: dict[str, Any]) -> tuple[float, float, float, float, float]:
        outcome_stats = payload.get("outcomeStats")
        if not isinstance(outcome_stats, list) or len(outcome_stats) < 2:
            return 50.0, 50.0, 0.0, 0.0, 0.0

        totals: dict[int, float] = {}
        total_pool = 0.0
        for item in outcome_stats:
            outcome_index = item.get("outcomeIndex")
            amount = float(item.get("totalAmount", 0.0))
            if isinstance(outcome_index, int):
                totals[outcome_index] = amount
                total_pool += amount

        if total_pool <= 0:
            return 50.0, 50.0, totals.get(0, 0.0), totals.get(1, 0.0), 0.0

        yes_pct = totals.get(0, 0.0) / total_pool * 100
        no_pct = totals.get(1, 0.0) / total_pool * 100
        return yes_pct, no_pct, totals.get(0, 0.0), totals.get(1, 0.0), total_pool

    @staticmethod
    def _is_matching_above_market(
        item: dict[str, Any],
        search_terms: tuple[str, ...],
    ) -> bool:
        question = item.get("question", "").lower()
        if "above" not in question:
            return False
        return any(term in question for term in search_terms)

    @staticmethod
    def _extract_latest_price(history_payload: dict[str, Any]) -> float:
        prices = history_payload.get("prices")
        if not isinstance(prices, list) or not prices:
            raise RuntimeError("Price history payload does not contain any prices.")
        latest = prices[-1]
        if not isinstance(latest, dict) or "price" not in latest:
            raise RuntimeError("Latest price point is missing the 'price' field.")
        try:
            return float(latest["price"])
        except (TypeError, ValueError):
            raise RuntimeError(f"Latest price is not numeric: {latest['price']!r}") from None

    @staticmethod
    def _compute_timer_left(payload: dict[str, Any]) -> int:
        end_time = payload.get("endTime")
        if not end_time:
            raise RuntimeError("Market payload is missing endTime.")
        normalized = end_time.replace("Z", "+00:00")
        expires_at = datetime.fromisoformat(normalized)
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        remaining = expires_at - datetime.now(timezone.utc)
        return max(0, int(remaining.total_seconds()))

    def stream(self) -> Generator[Market, None, None]:
        while True:
            if not self._market_ids:
                if not self._waiting_for_markets_logged:
                    logger.warning("No active BTC/SOL/ETH above markets found. Retrying.")
                    self._waiting_for_markets_logged = True
                try:
                    self.refresh_market_ids()
                except Exception:
                    logger.exception("Failed to refresh market ids.")
                time.sleep(config.POLL_INTERVAL_SEC)
                continue

            for slug, market_id in list(self._market_ids.items()):
                spec = config.get_market_spec(slug)
                try:
                    payload = self._fetch_market_payload(market_id)
                    if payload.get("status") != "ACTIVE":
                        self.drop_market(slug)
                        continue
                    timer_left = self._compute_timer_left(payload)
                    history_payload = self._fetch_price_history(market_id, timer_left)
                    question = payload.get("question", slug)
                    yes_pct, no_pct, yes_pool, no_pool, total_pool = self._extract_outcome_data(payload)
                    target_price = self._extract_target_price(payload, question)
                    end_time = payload.get("endTime")
                    if not isinstance(end_time, str):
                        raise RuntimeError("Market payload is missing endTime.")
                    market = Market(
                        slug=slug,
                        symbol=spec.symbol,
                        market_id=market_id,
                        question=question,
                        target_price=target_price,
                        timer_left=timer_left,
                        current_price=self._extract_latest_price(history_payload),
                        yes_percentage=yes_pct,
                        no_percentage=no_pct,
                        total_pool=total_pool,
                        yes_pool=yes_pool,
                        no_pool=no_pool,
                        range_metrics=self._strategy.build_range_metrics(
                            history_payload,
                            end_time,
                            target_price,
                        ),
                    )
                    yield market
                except HTTPError as exc:
                    status_code = exc.response.status_code if exc.response is not None else None
                    if status_code in (404, 410):
                        logger.warning("Market %s is no longer available.", slug)
                        self.drop_market(slug)
                        continue
                    if status_code == 504:
                        logger.warning("Market %s timed out upstream. Will retry.", slug)
                        continue
                    if status_code == 429:
                        logger.warning("Market %s rate limited upstream. Using next cycle.", slug)
                        continue
                    logger.exception("Failed to refresh market %s", slug)
                except Exception:
                    logger.exception("Failed to refresh market %s", slug)
            time.sleep(config.POLL_INTERVAL_SEC)
