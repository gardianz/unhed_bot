from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from config import config
from models import Market, RangeMetrics, SegmentSnapshot, SegmentWindow, Signal
from state import BotState


class BaseStrategy(ABC):
    strategy_id: str = ""
    name: str = ""
    segment_windows: tuple[SegmentWindow, ...] = ()

    def __init__(self, state: BotState):
        self.state = state

    @property
    def segment_count(self) -> int:
        return len(self.segment_windows)

    def ensure_round_state(self, market_slug: str):
        return self.state.get_or_create(market_slug, segment_count=self.segment_count)

    def minimum_average_1(self, symbol: str) -> float | None:
        return None

    def build_range_metrics(
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
        for window in self.segment_windows:
            start_ms = end_ms - window.start_min * 60 * 1000
            stop_ms = end_ms - window.stop_min * 60 * 1000
            segment_points = [
                price for timestamp, price in points if start_ms <= timestamp <= stop_ms
            ]
            if not segment_points:
                break
            segment_snapshots.append(
                self._build_segment_snapshot(window.label, segment_points)
            )

        if not segment_snapshots:
            return None

        if len(segment_snapshots) < self.segment_count:
            return RangeMetrics(
                segments=tuple(segment_snapshots),
                average_1=None,
                average_2=None,
                range_1_low=None,
                range_1_high=None,
                range_2_low=None,
                range_2_high=None,
            )

        return self.rebuild_range_metrics(tuple(segment_snapshots), target_price)

    def rebuild_range_metrics(
        self,
        segments: tuple[SegmentSnapshot, ...],
        target_price: float,
    ) -> RangeMetrics:
        average_1, average_2 = self.compute_averages(segments)
        width_1 = abs(average_1)
        width_2 = abs(average_2)
        return RangeMetrics(
            segments=segments,
            average_1=average_1,
            average_2=average_2,
            range_1_low=target_price - width_1,
            range_1_high=target_price + width_1,
            range_2_low=target_price - width_2,
            range_2_high=target_price + width_2,
        )

    def evaluate(self, market: Market) -> Optional[Signal]:
        if market.timer_left > config.DECISION_WINDOW_SEC or market.timer_left <= 0:
            return None

        state = self.ensure_round_state(market.slug)
        if state.execution_blocked:
            return None
        metrics = state.frozen_range_metrics or market.range_metrics
        if (
            metrics is None
            or metrics.average_1 is None
            or metrics.range_1_low is None
            or metrics.range_1_high is None
            or metrics.range_2_low is None
            or metrics.range_2_high is None
        ):
            return None

        current_price = market.current_price
        if metrics.range_2_low <= current_price <= metrics.range_2_high and not state.triggered_both:
            signal = self._create_signal(
                market,
                side="BOTH",
                reason=(
                    f"Current price inside range_2 "
                    f"[{metrics.range_2_low:.4f}, {metrics.range_2_high:.4f}]"
                ),
            )
            state.last_price = current_price
            return signal

        minimum_average_1 = self.minimum_average_1(market.symbol)
        if minimum_average_1 is not None and abs(metrics.average_1) < minimum_average_1:
            return None

        if current_price > metrics.range_1_high and not (state.triggered_yes or state.triggered_no):
            signal = self._create_signal(
                market,
                side="YES",
                reason=f"Current price above range_1_high {metrics.range_1_high:.4f}",
            )
            state.last_price = current_price
            return signal

        if current_price < metrics.range_1_low and not (state.triggered_yes or state.triggered_no):
            signal = self._create_signal(
                market,
                side="NO",
                reason=f"Current price below range_1_low {metrics.range_1_low:.4f}",
            )
            state.last_price = current_price
            return signal

        state.last_price = current_price
        return None

    def _create_signal(self, market: Market, side: str, reason: str) -> Signal:
        return Signal(
            market_slug=market.slug,
            market_id=market.market_id,
            side=side,
            stake=config.stake_for_side(side),
            delta=market.target_delta,
            reason=reason,
            signal_id=uuid.uuid4().hex,
        )

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

    def _build_segment_snapshot(
        self,
        label: str,
        segment_points: list[float],
    ) -> SegmentSnapshot:
        open_price = segment_points[0]
        close_price = segment_points[-1]
        high_price = max(segment_points)
        low_price = min(segment_points)
        return SegmentSnapshot(
            label=label,
            open_price=open_price,
            close_price=close_price,
            high_price=high_price,
            low_price=low_price,
            signed_range=self.compute_segment_value(
                open_price,
                close_price,
                high_price,
                low_price,
            ),
        )

    @abstractmethod
    def compute_segment_value(
        self,
        open_price: float,
        close_price: float,
        high_price: float,
        low_price: float,
    ) -> float:
        raise NotImplementedError

    @abstractmethod
    def compute_averages(
        self,
        segments: tuple[SegmentSnapshot, ...],
    ) -> tuple[float, float]:
        raise NotImplementedError
