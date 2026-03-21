from __future__ import annotations

from dataclasses import asdict
from typing import Any

from models import RoundState, Signal


class BotState:
    def __init__(self) -> None:
        self.rounds: dict[str, RoundState] = {}
        self.recent_activity: list[dict[str, Any]] = []
        self.last_bets: dict[str, str] = {}
        self.total_bet_cc: float = 0.0
        self.starting_balance: float | None = None
        self.current_balance: float | None = None
        self.events: list[str] = []

    def get_or_create(self, slug: str) -> RoundState:
        if slug not in self.rounds or self.rounds[slug].completed:
            self.rounds[slug] = RoundState(market_slug=slug)
        return self.rounds[slug]

    def reset_round(self, slug: str) -> None:
        if slug in self.rounds:
            self.rounds[slug].completed = True

    def record_signal(self, signal: Signal) -> None:
        payload = asdict(signal)
        payload["timestamp"] = signal.timestamp.isoformat()
        self.recent_activity.append(payload)
        self.recent_activity = self.recent_activity[-50:]

    def record_bet(self, market_slug: str, bet_summary: str) -> None:
        self.last_bets[market_slug] = bet_summary

    def get_last_bet(self, market_slug: str) -> str:
        return self.last_bets.get(market_slug, "-")

    def get_market_status(self, market_slug: str) -> str:
        round_state = self.rounds.get(market_slug)
        if round_state is None or round_state.completed:
            return "WAITING"
        if round_state.triggered_yes:
            return "YES SENT"
        if round_state.triggered_no:
            return "NO SENT"
        if round_state.triggered_both:
            return "BOTH SENT"
        return "MONITORING"

    def record_total_bet(self, amount: float) -> None:
        self.total_bet_cc += amount

    def set_balances(
        self,
        *,
        starting_balance: float | None = None,
        current_balance: float | None = None,
    ) -> None:
        if starting_balance is not None and self.starting_balance is None:
            self.starting_balance = starting_balance
        if current_balance is not None:
            self.current_balance = current_balance

    def get_pnl(self) -> float | None:
        if self.starting_balance is None or self.current_balance is None:
            return None
        return self.current_balance - self.starting_balance

    def add_event(self, message: str) -> None:
        self.events.append(message)
        self.events = self.events[-8:]
