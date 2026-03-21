from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional

from config import ThresholdConfig

Side = Literal["YES", "NO", "BOTH"]


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
    segments: tuple[SegmentSnapshot, SegmentSnapshot, SegmentSnapshot, SegmentSnapshot]
    average_1: float
    average_2: float
    range_1_low: float
    range_1_high: float
    range_2_low: float
    range_2_high: float


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
    thresholds: ThresholdConfig
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
    frozen_range_metrics: Optional[RangeMetrics] = None
    frozen_segments: list[Optional[SegmentSnapshot]] = field(
        default_factory=lambda: [None, None, None, None]
    )
    completed: bool = False
