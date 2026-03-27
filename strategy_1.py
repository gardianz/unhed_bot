from __future__ import annotations

from config import config
from models import SegmentSnapshot, SegmentWindow
from strategy_base import BaseStrategy


class Strategy1(BaseStrategy):
    strategy_id = "1"
    name = "Signed Range Legacy"
    segment_windows = (
        SegmentWindow("seg1", 30, 25),
        SegmentWindow("seg2", 25, 20),
        SegmentWindow("seg3", 20, 15),
        SegmentWindow("seg4", 15, 10),
        SegmentWindow("seg5", 10, 5),
        SegmentWindow("seg6", 5, 2),
    )

    def minimum_average_1(self, symbol: str) -> float | None:
        return config.minimum_average_1(symbol)

    def compute_segment_value(
        self,
        open_price: float,
        close_price: float,
        high_price: float,
        low_price: float,
    ) -> float:
        direction = close_price - open_price
        if direction > 0:
            return high_price - low_price
        if direction < 0:
            return -(high_price - low_price)
        return 0.0

    def compute_averages(
        self,
        segments: tuple[SegmentSnapshot, ...],
    ) -> tuple[float, float]:
        signed_ranges = [segment.signed_range for segment in segments]
        average_1 = sum(signed_ranges) / 2
        average_2 = average_1 / 3
        return average_1, average_2
