from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MarketSpec:
    slug: str
    symbol: str
    search_terms: tuple[str, ...]
    market_id: str = ""


def _env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value if value is not None else default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return int(raw)


def _env_tuple(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    return tuple(part.strip() for part in raw.split(",") if part.strip())


class Config:
    def __init__(self) -> None:
        self.UNHEDGED_API_KEY = _env_str("UNHEDGED_API_KEY")
        self.UNHEDGED_API_BASE = _env_str("UNHEDGED_API_BASE", "https://api.unhedged.gg")
        self.STAKE_CC = _env_float("STAKE_CC", 5.0)
        self.HTTP_TIMEOUT_SEC = _env_float("HTTP_TIMEOUT_SEC", 10.0)
        self.POLL_INTERVAL_SEC = _env_float("POLL_INTERVAL_SEC", 1.0)
        self.DECISION_WINDOW_SEC = _env_int("DECISION_WINDOW_SEC", 10)
        self.MARKET_DETAIL_REFRESH_SEC = _env_float("MARKET_DETAIL_REFRESH_SEC", 3.0)
        self.PRICE_HISTORY_REFRESH_SEC = _env_float("PRICE_HISTORY_REFRESH_SEC", 1.0)
        self.RATE_LIMIT_BACKOFF_SEC = _env_float("RATE_LIMIT_BACKOFF_SEC", 10.0)
        self.SIGNAL_HISTORY_PATH = _env_str("SIGNAL_HISTORY_PATH", "signal_history.jsonl")
        self.PENDING_BETS_PATH = _env_str("PENDING_BETS_PATH", "pending_bets.json")
        self.TELEGRAM_POSITION_UPDATE_SEC = _env_float("TELEGRAM_POSITION_UPDATE_SEC", 10.0)

        self.BTC_MARKET_ID = _env_str("BTC_MARKET_ID")
        self.SOL_MARKET_ID = _env_str("SOL_MARKET_ID")
        self.ETH_MARKET_ID = _env_str("ETH_MARKET_ID")

        self.BTC_AVG1_MIN = _env_float("BTC_AVG1_MIN", 70.0)
        self.SOL_AVG1_MIN = _env_float("SOL_AVG1_MIN", 0.25)
        self.ETH_AVG1_MIN = _env_float("ETH_AVG1_MIN", 2.55)

    def validate_runtime(self) -> None:
        if self.STAKE_CC <= 0:
            raise ValueError("STAKE_CC must be greater than 0.")
        if self.HTTP_TIMEOUT_SEC <= 0:
            raise ValueError("HTTP_TIMEOUT_SEC must be greater than 0.")
        if self.POLL_INTERVAL_SEC <= 0:
            raise ValueError("POLL_INTERVAL_SEC must be greater than 0.")
        if self.DECISION_WINDOW_SEC <= 0:
            raise ValueError("DECISION_WINDOW_SEC must be greater than 0.")
        if self.MARKET_DETAIL_REFRESH_SEC <= 0:
            raise ValueError("MARKET_DETAIL_REFRESH_SEC must be greater than 0.")
        if self.PRICE_HISTORY_REFRESH_SEC <= 0:
            raise ValueError("PRICE_HISTORY_REFRESH_SEC must be greater than 0.")
        if self.RATE_LIMIT_BACKOFF_SEC <= 0:
            raise ValueError("RATE_LIMIT_BACKOFF_SEC must be greater than 0.")
        if self.TELEGRAM_POSITION_UPDATE_SEC <= 0:
            raise ValueError("TELEGRAM_POSITION_UPDATE_SEC must be greater than 0.")

    @property
    def market_specs(self) -> dict[str, MarketSpec]:
        return {
            "bitcoin_above": MarketSpec(
                slug="bitcoin_above",
                symbol="BTC",
                search_terms=("btc", "bitcoin"),
                market_id=self.BTC_MARKET_ID,
            ),
            "solana_above": MarketSpec(
                slug="solana_above",
                symbol="SOL",
                search_terms=("sol", "solana"),
                market_id=self.SOL_MARKET_ID,
            ),
            "ethereum_above": MarketSpec(
                slug="ethereum_above",
                symbol="ETH",
                search_terms=("eth", "ethereum"),
                market_id=self.ETH_MARKET_ID,
            ),
        }

    def get_market_spec(self, slug: str) -> MarketSpec:
        try:
            return self.market_specs[slug]
        except KeyError as exc:
            raise KeyError(f"Unknown market slug: {slug}") from exc

    def outcome_index(self, side: str) -> int:
        mapping: dict[str, int] = {"YES": 0, "NO": 1}
        try:
            return mapping[side]
        except KeyError as exc:
            raise ValueError(f"Unsupported side: {side}") from exc

    def minimum_average_1(self, symbol: str) -> float:
        mapping = {
            "BTC": self.BTC_AVG1_MIN,
            "SOL": self.SOL_AVG1_MIN,
            "ETH": self.ETH_AVG1_MIN,
        }
        try:
            return mapping[symbol.upper()]
        except KeyError as exc:
            raise ValueError(f"Unsupported symbol for minimum average_1: {symbol}") from exc

config = Config()
