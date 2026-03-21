from __future__ import annotations

import requests

from config import config
from logger import logger
from models import Signal


class LiveExecutionAdapter:
    def __init__(self):
        self.base = config.UNHEDGED_API_BASE
        self.key = config.UNHEDGED_API_KEY
        if not self.key:
            raise RuntimeError("UNHEDGED_API_KEY is required for live execution.")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        )
        self._starting_balance = self._check_balance(log_message=True)

    def _check_balance(self, *, log_message: bool) -> float:
        response = self._session.get(
            f"{self.base}/api/v1/balance",
            timeout=config.HTTP_TIMEOUT_SEC,
        )
        response.raise_for_status()
        available = float(response.json()["balance"]["available"])
        if log_message:
            logger.info("Balance available: %s CC", available)
        return available

    @property
    def starting_balance(self) -> float:
        return self._starting_balance

    def fetch_balance(self) -> float:
        return self._check_balance(log_message=False)

    def execute(self, signal: Signal) -> list[dict]:
        outcomes = (
            [config.outcome_index("YES"), config.outcome_index("NO")]
            if signal.side == "BOTH"
            else [config.outcome_index(signal.side)]
        )

        placed_bets: list[dict] = []
        for idx in outcomes:
            payload = {
                "marketId": signal.market_id,
                "outcomeIndex": idx,
                "amount": signal.stake,
                "idempotencyKey": f"{signal.signal_id}-{idx}",
            }
            try:
                response = self._session.post(
                    f"{self.base}/api/v1/bets",
                    json=payload,
                    timeout=config.HTTP_TIMEOUT_SEC,
                )
                response.raise_for_status()
                data = response.json()
                placed_bets.append(data)
            except Exception:
                logger.exception(
                    "Bet placement failed for signal_id=%s outcome_index=%s",
                    signal.signal_id,
                    idx,
                )
                if placed_bets:
                    raise RuntimeError(
                        f"Partial execution detected for signal_id={signal.signal_id}."
                    ) from None
                raise

        return placed_bets

    @staticmethod
    def summarize_bets(signal: Signal, placed_bets: list[dict]) -> str:
        if signal.side == "BOTH":
            return f"BOTH {signal.stake:.2f} CC x2"
        if not placed_bets:
            return f"{signal.side} {signal.stake:.2f} CC"
        return f"{signal.side} {signal.stake:.2f} CC"

    @staticmethod
    def total_stake(signal: Signal) -> float:
        return signal.stake * (2 if signal.side == "BOTH" else 1)
