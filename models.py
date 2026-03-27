from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

Side = Literal["YES", "NO", "BOTH"]


@dataclass(frozen=True)
class SegmentWindow:
    label: str
    start_min: int
    stop_min: int

    @property
    def freeze_threshold_sec(self) -> int:
        return self.stop_min * 60


@dataclass
class SegmentSnapshot:
    label: str
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    signed_range: float


@dataclass
class RangeMetrics:
    segments: tuple[SegmentSnapshot, ...]
    average_1: Optional[float]
    average_2: Optional[float]
    range_1_low: Optional[float]
    range_1_high: Optional[float]
    range_2_low: Optional[float]
    range_2_high: Optional[float]


@dataclass
class Market:
    slug: str
    symbol: str
    market_id: str
    question: str
    target_price: float
    timer_left: int
    current_price: float
    yes_percentage: float
    no_percentage: float
    total_pool: float
    yes_pool: float
    no_pool: float
    range_metrics: Optional[RangeMetrics] = None
    reference_price: Optional[float] = None

    @property
    def target_delta(self) -> float:
        return self.current_price - self.target_price


@dataclass
class Signal:
    market_slug: str
    market_id: str
    side: Side
    stake: float
    delta: float
    reason: str
    signal_id: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RoundState:
    market_slug: str
    reference_price: Optional[float] = None
    last_price: float = 0.0
    triggered_both: bool = False
    triggered_yes: bool = False
    triggered_no: bool = False
    execution_blocked: bool = False
    last_error: Optional[str] = None
    pending_settlement_logged: bool = False
    frozen_range_metrics: Optional[RangeMetrics] = None
    frozen_segments: list[Optional[SegmentSnapshot]] = field(default_factory=list)
    completed: bool = False
