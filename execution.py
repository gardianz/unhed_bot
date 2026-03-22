from __future__ import annotations

from collections import defaultdict

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

    def fetch_pending_settlement_bets(self) -> list[dict]:
        grouped: dict[str, dict] = {}
        limit = 100
        offset = 0

        while True:
            response = self._session.get(
                f"{self.base}/api/v1/bets",
                params={"limit": limit, "offset": offset},
                timeout=config.HTTP_TIMEOUT_SEC,
            )
            response.raise_for_status()
            payload = response.json()
            bets = payload.get("bets", [])
            if not isinstance(bets, list) or not bets:
                break

            for bet in bets:
                if not isinstance(bet, dict):
                    continue
                bet_status = str(bet.get("status", "")).upper()
                if bet_status in {"WON", "LOST", "REFUNDED", "VOIDED", "CANCELED", "CANCELLED"}:
                    continue

                market = bet.get("market")
                market_status = ""
                question = None
                if isinstance(market, dict):
                    market_status = str(market.get("status", "")).upper()
                    question = market.get("question")
                if market_status in {"RESOLVED", "VOIDED"}:
                    continue

                market_id = bet.get("marketId")
                if not isinstance(market_id, str) or not market_id:
                    continue

                entry = grouped.setdefault(
                    market_id,
                    {
                        "market_id": market_id,
                        "question": question or market_id,
                        "amounts": defaultdict(float),
                    },
                )

                outcome_index = bet.get("outcomeIndex")
                try:
                    amount = float(bet.get("amount", 0.0))
                except (TypeError, ValueError):
                    amount = 0.0
                if isinstance(outcome_index, int):
                    entry["amounts"][outcome_index] += amount

            if len(bets) < limit:
                break
            offset += limit

        restored: list[dict] = []
        for entry in grouped.values():
            amounts = entry["amounts"]
            yes_amount = amounts.get(0, 0.0)
            no_amount = amounts.get(1, 0.0)
            if yes_amount > 0 and no_amount > 0:
                if abs(yes_amount - no_amount) < 1e-9:
                    summary = f"BOTH {yes_amount:.2f} CC x2"
                else:
                    summary = f"BOTH YES {yes_amount:.2f} / NO {no_amount:.2f} CC"
            elif yes_amount > 0:
                summary = f"YES {yes_amount:.2f} CC"
            elif no_amount > 0:
                summary = f"NO {no_amount:.2f} CC"
            else:
                continue

            restored.append(
                {
                    "market_id": entry["market_id"],
                    "question": entry["question"],
                    "summary": summary,
                }
            )

        return restored

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
