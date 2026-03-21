from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Generator

import requests
from requests import HTTPError

from config import config
from logger import logger
from models import Market, RangeMetrics, SegmentSnapshot


class MarketFeed:
    SEGMENT_WINDOWS = (
        ("m5-1", 21, 16),
        ("m5-2", 16, 11),
        ("m5-3", 11, 6),
        ("m3-4", 6, 3),
    )

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})
        self._market_ids = self._resolve_market_ids()

    def refresh_market_ids(self) -> None:
        self._market_ids = self._resolve_market_ids()

    def drop_market(self, slug: str) -> None:
        self._market_ids.pop(slug, None)

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
            timeout=config.HTTP_TIMEOUT_SEC,
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
        response = self._session.get(
            f"{config.UNHEDGED_API_BASE}/api/v1/markets/{market_id}",
            timeout=config.HTTP_TIMEOUT_SEC,
        )
        response.raise_for_status()
        payload = response.json().get("market")
        if not isinstance(payload, dict):
            raise RuntimeError(f"Unexpected market payload for market_id={market_id}")
        return payload

    def _fetch_price_history(self, market_id: str) -> dict[str, Any]:
        response = self._session.get(
            f"{config.UNHEDGED_API_BASE}/api/v1/markets/{market_id}/price-history",
            timeout=config.HTTP_TIMEOUT_SEC,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Unexpected price-history payload for market_id={market_id}"
            )
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
    def _extract_outcome_percentages(payload: dict[str, Any]) -> tuple[float, float]:
        outcome_stats = payload.get("outcomeStats")
        if not isinstance(outcome_stats, list) or len(outcome_stats) < 2:
            return 50.0, 50.0

        totals: dict[int, float] = {}
        total_pool = 0.0
        for item in outcome_stats:
            outcome_index = item.get("outcomeIndex")
            amount = float(item.get("totalAmount", 0.0))
            if isinstance(outcome_index, int):
                totals[outcome_index] = amount
                total_pool += amount

        if total_pool <= 0:
            return 50.0, 50.0

        yes_pct = totals.get(0, 0.0) / total_pool * 100
        no_pct = totals.get(1, 0.0) / total_pool * 100
        return yes_pct, no_pct

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
    def _extract_price_points(history_payload: dict[str, Any]) -> list[tuple[int, float]]:
        prices = history_payload.get("prices")
        if not isinstance(prices, list) or not prices:
            raise RuntimeError("Price history payload does not contain any prices.")

        points: list[tuple[int, float]] = []
        for item in prices:
            if not isinstance(item, dict):
                continue
            timestamp = item.get("timestamp")
            price = item.get("price")
            if not isinstance(timestamp, (int, float)):
                continue
            try:
                points.append((int(timestamp), float(price)))
            except (TypeError, ValueError):
                continue

        if not points:
            raise RuntimeError("Price history payload does not contain valid price points.")

        points.sort(key=lambda point: point[0])
        return points

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

    def _build_range_metrics(
        self,
        history_payload: dict[str, Any],
        end_time: str,
        target_price: float,
    ) -> RangeMetrics | None:
        points = self._extract_price_points(history_payload)
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
        if end_dt.tzinfo is None:
            end_dt = end_dt.replace(tzinfo=timezone.utc)
        end_ms = int(end_dt.timestamp() * 1000)

        segment_snapshots: list[SegmentSnapshot] = []

        for label, start_min, stop_min in self.SEGMENT_WINDOWS:
            start_ms = end_ms - start_min * 60 * 1000
            stop_ms = end_ms - stop_min * 60 * 1000
            segment_points = [
                price
                for timestamp, price in points
                if start_ms <= timestamp <= stop_ms
            ]
            if not segment_points:
                return None
            open_price = segment_points[0]
            close_price = segment_points[-1]
            high_price = max(segment_points)
            low_price = min(segment_points)
            direction = close_price - open_price
            if direction > 0:
                signed_range = high_price - low_price
            elif direction < 0:
                signed_range = -(high_price - low_price)
            else:
                signed_range = 0.0
            segment_snapshots.append(
                SegmentSnapshot(
                    label=label,
                    open_price=open_price,
                    close_price=close_price,
                    high_price=high_price,
                    low_price=low_price,
                    signed_range=signed_range,
                )
            )

        segment_moves = [segment.signed_range for segment in segment_snapshots]
        average_1 = sum(segment_moves) / 2
        average_2 = average_1 / 3
        width_1 = abs(average_1)
        width_2 = abs(average_2)

        return RangeMetrics(
            segments=(
                segment_snapshots[0],
                segment_snapshots[1],
                segment_snapshots[2],
                segment_snapshots[3],
            ),
            average_1=average_1,
            average_2=average_2,
            range_1_low=target_price - width_1,
            range_1_high=target_price + width_1,
            range_2_low=target_price - width_2,
            range_2_high=target_price + width_2,
        )

    def stream(self) -> Generator[Market, None, None]:
        while True:
            if not self._market_ids:
                logger.warning("No active BTC/SOL/ETH above markets found. Retrying.")
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
                    history_payload = self._fetch_price_history(market_id)
                    question = payload.get("question", slug)
                    yes_pct, no_pct = self._extract_outcome_percentages(payload)
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
                        timer_left=self._compute_timer_left(payload),
                        current_price=self._extract_latest_price(history_payload),
                        yes_percentage=yes_pct,
                        no_percentage=no_pct,
                        thresholds=spec.thresholds,
                        range_metrics=self._build_range_metrics(
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
                    logger.exception("Failed to refresh market %s", slug)
                except Exception:
                    logger.exception("Failed to refresh market %s", slug)
            time.sleep(config.POLL_INTERVAL_SEC)
