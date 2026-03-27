from __future__ import annotations

from dataclasses import asdict
import time
from typing import Any

from models import RoundState, Signal


class BotState:
    def __init__(self) -> None:
        self.rounds: dict[str, RoundState] = {}
        self.recent_activity: list[dict[str, Any]] = []
        self.last_bets: dict[str, str] = {}
        self.pending_bets_by_market_id: dict[str, str] = {}
        self.pending_event_details_logged: set[str] = set()
        self.pending_telegram_update_at: dict[str, float] = {}
        self.total_bet_cc: float = 0.0
        self.starting_balance: float | None = None
        self.current_balance: float | None = None
        self.events: list[str] = []
        self.closed_market_ids: dict[str, str] = {}

    def get_or_create(self, slug: str, segment_count: int | None = None) -> RoundState:
        if slug not in self.rounds or self.rounds[slug].completed:
            self.rounds[slug] = RoundState(market_slug=slug)
        if segment_count is not None:
            frozen_segments = self.rounds[slug].frozen_segments
            if len(frozen_segments) < segment_count:
                frozen_segments.extend([None] * (segment_count - len(frozen_segments)))
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

    def restore_pending_bet(self, market_id: str, bet_summary: str) -> None:
        self.pending_bets_by_market_id[market_id] = bet_summary

    def get_pending_bet(self, market_id: str) -> str | None:
        return self.pending_bets_by_market_id.get(market_id)

    def should_log_pending_details(self, market_id: str) -> bool:
        return market_id not in self.pending_event_details_logged

    def mark_pending_details_logged(self, market_id: str) -> None:
        self.pending_event_details_logged.add(market_id)

    def get_market_status(self, market_slug: str) -> str:
        round_state = self.rounds.get(market_slug)
        if round_state is None or round_state.completed:
            return "WAITING"
        if round_state.execution_blocked:
            return "BET FAILED"
        if round_state.triggered_yes:
            return "YES SENT"
        if round_state.triggered_no:
            return "NO SENT"
        if round_state.triggered_both:
            return "BOTH SENT"
        return "MONITORING"

    def mark_signal_sent(self, market_slug: str, side: str, segment_count: int | None = None) -> None:
        round_state = self.get_or_create(market_slug, segment_count=segment_count)
        round_state.execution_blocked = False
        round_state.last_error = None
        if side == "YES":
            round_state.triggered_yes = True
        elif side == "NO":
            round_state.triggered_no = True
        elif side == "BOTH":
            round_state.triggered_both = True
        else:
            raise ValueError(f"Unsupported signal side: {side}")

    def block_round_execution(
        self,
        market_slug: str,
        reason: str,
        segment_count: int | None = None,
    ) -> None:
        round_state = self.get_or_create(market_slug, segment_count=segment_count)
        round_state.execution_blocked = True
        round_state.last_error = reason

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
        self.events = self.events[-20:]

    def mark_closed_market(self, market_slug: str, market_id: str) -> None:
        self.closed_market_ids[market_slug] = market_id

    def was_market_closed(self, market_slug: str, market_id: str) -> bool:
        return self.closed_market_ids.get(market_slug) == market_id

    def should_send_pending_telegram_update(
        self,
        market_id: str,
        interval_sec: float,
    ) -> bool:
        now = time.monotonic()
        last_sent = self.pending_telegram_update_at.get(market_id)
        if last_sent is None or now - last_sent >= interval_sec:
            self.pending_telegram_update_at[market_id] = now
            return True
        return False
