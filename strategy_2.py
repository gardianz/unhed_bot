from __future__ import annotations

from models import SegmentSnapshot, SegmentWindow
from strategy_base import BaseStrategy


class Strategy2(BaseStrategy):
    strategy_id = "2"
    name = "Absolute M5 Segment"
    segment_windows = (
        SegmentWindow("seg_1", 30, 25),
        SegmentWindow("seg_2", 25, 20),
        SegmentWindow("seg_3", 20, 15),
        SegmentWindow("seg_4", 15, 10),
        SegmentWindow("seg_5", 10, 5),
        SegmentWindow("seg_akhir", 5, 1),
    )

    def minimum_average_1(self, symbol: str) -> float | None:
        # Strategy 2 intentionally does not use per-symbol avg_1 minimum filters.
        return None

    def compute_segment_value(
        self,
        open_price: float,
        close_price: float,
        high_price: float,
        low_price: float,
    ) -> float:
        return abs(high_price - low_price)

    def compute_averages(
        self,
        segments: tuple[SegmentSnapshot, ...],
    ) -> tuple[float, float]:
        absolute_segments = [abs(segment.signed_range) for segment in segments]
        average_1 = sum(absolute_segments) / len(absolute_segments)
        average_2 = average_1 / 4
        return average_1, average_2
