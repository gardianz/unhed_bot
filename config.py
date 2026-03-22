from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ThresholdConfig:
    both: float
    directional: float


@dataclass(frozen=True)
class MarketSpec:
    slug: str
    symbol: str
    search_terms: tuple[str, ...]
    thresholds: ThresholdConfig
    market_id: str = ""
    price_paths: tuple[str, ...] = ()


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
        self.WATCH_THRESHOLD_MIN = _env_int("WATCH_THRESHOLD_MIN", 2)
        self.HTTP_TIMEOUT_SEC = _env_float("HTTP_TIMEOUT_SEC", 10.0)
        self.POLL_INTERVAL_SEC = _env_float("POLL_INTERVAL_SEC", 1.0)
        self.SIGNAL_HISTORY_PATH = _env_str("SIGNAL_HISTORY_PATH", "signal_history.jsonl")
        self.PENDING_BETS_PATH = _env_str("PENDING_BETS_PATH", "pending_bets.json")

        self.BTC_MARKET_ID = _env_str("BTC_MARKET_ID")
        self.SOL_MARKET_ID = _env_str("SOL_MARKET_ID")
        self.ETH_MARKET_ID = _env_str("ETH_MARKET_ID")

        self.BTC_BOTH_DELTA = _env_float("BTC_BOTH_DELTA", 100.0)
        self.BTC_DIRECTIONAL_DELTA = _env_float("BTC_DIRECTIONAL_DELTA", 300.0)
        self.SOL_BOTH_DELTA = _env_float("SOL_BOTH_DELTA", 0.15)
        self.SOL_DIRECTIONAL_DELTA = _env_float("SOL_DIRECTIONAL_DELTA", 0.5)
        self.ETH_BOTH_DELTA = _env_float("ETH_BOTH_DELTA", 3.0)
        self.ETH_DIRECTIONAL_DELTA = _env_float("ETH_DIRECTIONAL_DELTA", 10.0)
        self.BTC_AVG1_MIN = _env_float("BTC_AVG1_MIN", 70.0)
        self.SOL_AVG1_MIN = _env_float("SOL_AVG1_MIN", 0.25)
        self.ETH_AVG1_MIN = _env_float("ETH_AVG1_MIN", 2.55)

    def validate_runtime(self) -> None:
        if self.STAKE_CC <= 0:
            raise ValueError("STAKE_CC must be greater than 0.")
        if self.WATCH_THRESHOLD_MIN <= 0:
            raise ValueError("WATCH_THRESHOLD_MIN must be greater than 0.")
        if self.HTTP_TIMEOUT_SEC <= 0:
            raise ValueError("HTTP_TIMEOUT_SEC must be greater than 0.")
        if self.POLL_INTERVAL_SEC <= 0:
            raise ValueError("POLL_INTERVAL_SEC must be greater than 0.")

    @property
    def market_specs(self) -> dict[str, MarketSpec]:
        return {
            "bitcoin_above": MarketSpec(
                slug="bitcoin_above",
                symbol="BTC",
                search_terms=("btc", "bitcoin"),
                market_id=self.BTC_MARKET_ID,
                thresholds=ThresholdConfig(
                    both=self.BTC_BOTH_DELTA,
                    directional=self.BTC_DIRECTIONAL_DELTA,
                ),
            ),
            "solana_above": MarketSpec(
                slug="solana_above",
                symbol="SOL",
                search_terms=("sol", "solana"),
                market_id=self.SOL_MARKET_ID,
                thresholds=ThresholdConfig(
                    both=self.SOL_BOTH_DELTA,
                    directional=self.SOL_DIRECTIONAL_DELTA,
                ),
            ),
            "ethereum_above": MarketSpec(
                slug="ethereum_above",
                symbol="ETH",
                search_terms=("eth", "ethereum"),
                market_id=self.ETH_MARKET_ID,
                thresholds=ThresholdConfig(
                    both=self.ETH_BOTH_DELTA,
                    directional=self.ETH_DIRECTIONAL_DELTA,
                ),
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
