from __future__ import annotations

import uuid
from typing import Optional

from config import config
from logger import logger
from models import Market, Signal
from state import BotState


class Strategy:
    def __init__(self, state: BotState):
        self.state = state

    def evaluate(self, market: Market) -> Optional[Signal]:
        if market.timer_left > 60 or market.timer_left <= 0:
            return None

        state = self.state.get_or_create(market.slug)
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
        minimum_average_1 = config.minimum_average_1(market.symbol)

        if metrics.range_2_low <= current_price <= metrics.range_2_high and not state.triggered_both:
            signal = Signal(
                market_slug=market.slug,
                market_id=market.market_id,
                side="BOTH",
                stake=config.STAKE_CC,
                delta=market.target_delta,
                reason=(
                    f"Current price inside range_2 "
                    f"[{metrics.range_2_low:.4f}, {metrics.range_2_high:.4f}]"
                ),
                signal_id=uuid.uuid4().hex,
            )
            state.triggered_both = True
            state.last_price = market.current_price
            self.state.record_signal(signal)
            return signal

        if abs(metrics.average_1) < minimum_average_1:
            return None

        if current_price > metrics.range_1_high and not (
            state.triggered_yes or state.triggered_no
        ):
            signal = Signal(
                market_slug=market.slug,
                market_id=market.market_id,
                side="YES",
                stake=config.STAKE_CC,
                delta=market.target_delta,
                reason=f"Current price above range_1_high {metrics.range_1_high:.4f}",
                signal_id=uuid.uuid4().hex,
            )
            state.triggered_yes = True
            state.last_price = market.current_price
            self.state.record_signal(signal)
            return signal

        if current_price < metrics.range_1_low and not (
            state.triggered_yes or state.triggered_no
        ):
            signal = Signal(
                market_slug=market.slug,
                market_id=market.market_id,
                side="NO",
                stake=config.STAKE_CC,
                delta=market.target_delta,
                reason=f"Current price below range_1_low {metrics.range_1_low:.4f}",
                signal_id=uuid.uuid4().hex,
            )
            state.triggered_no = True
            state.last_price = market.current_price
            self.state.record_signal(signal)
            return signal

        state.last_price = market.current_price
        return None
