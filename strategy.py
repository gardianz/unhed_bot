from __future__ import annotations

from config import config
from state import BotState
from strategy_1 import Strategy1
from strategy_2 import Strategy2
from strategy_base import BaseStrategy

STRATEGY_REGISTRY: dict[str, type[BaseStrategy]] = {
    "1": Strategy1,
    "2": Strategy2,
}


def build_strategy(state: BotState) -> BaseStrategy:
    strategy_cls = STRATEGY_REGISTRY[config.SELECT_STRATEGY]
    return strategy_cls(state)
