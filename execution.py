from __future__ import annotations

from collections import defaultdict
from typing import Any

import requests
from requests import HTTPError, RequestException

from config import config
from logger import logger
from models import Signal


class BetExecutionError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        partial: bool = False,
        response_body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable
        self.partial = partial
        self.response_body = response_body


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
        logger.info("Fetching starting balance...")
        self._starting_balance = self._check_balance(log_message=True)

    @property
    def request_timeout(self) -> tuple[float, float]:
        return (config.HTTP_CONNECT_TIMEOUT_SEC, config.HTTP_TIMEOUT_SEC)

    @staticmethod
    def _format_error_body(response: requests.Response | None) -> str | None:
        if response is None:
            return None
        try:
            payload: Any = response.json()
        except ValueError:
            payload = response.text.strip()
        if isinstance(payload, dict):
            for key in ("message", "error", "details"):
                value = payload.get(key)
                if value:
                    return str(value)
            return str(payload)
        if payload:
            return str(payload)
        return None

    def _check_balance(self, *, log_message: bool) -> float:
        response = self._session.get(
            f"{self.base}/api/v1/balance",
            timeout=self.request_timeout,
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
                timeout=self.request_timeout,
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
        amount_per_outcome = (
            signal.stake / len(outcomes) if signal.side == "BOTH" else signal.stake
        )

        placed_bets: list[dict] = []
        for idx in outcomes:
            payload = {
                "marketId": signal.market_id,
                "outcomeIndex": idx,
                "amount": amount_per_outcome,
                "idempotencyKey": f"{signal.signal_id}-{idx}",
            }
            try:
                response = self._session.post(
                    f"{self.base}/api/v1/bets",
                    json=payload,
                    timeout=self.request_timeout,
                )
                response.raise_for_status()
                data = response.json()
                placed_bets.append(data)
            except HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                response_body = self._format_error_body(exc.response)
                message = (
                    f"Bet placement failed for signal_id={signal.signal_id} "
                    f"outcome_index={idx} status={status_code}"
                )
                if response_body:
                    message = f"{message} body={response_body}"
                logger.error(message)
                if placed_bets:
                    raise BetExecutionError(
                        f"Partial execution detected for signal_id={signal.signal_id}.",
                        status_code=status_code,
                        retryable=False,
                        partial=True,
                        response_body=response_body,
                    ) from None
                raise BetExecutionError(
                    message,
                    status_code=status_code,
                    retryable=bool(status_code and status_code >= 500),
                    partial=False,
                    response_body=response_body,
                ) from None
            except RequestException as exc:
                message = (
                    f"Bet placement request failed for signal_id={signal.signal_id} "
                    f"outcome_index={idx}: {exc}"
                )
                logger.error(message)
                if placed_bets:
                    raise BetExecutionError(
                        f"Partial execution detected for signal_id={signal.signal_id}.",
                        retryable=False,
                        partial=True,
                    ) from None
                raise BetExecutionError(
                    message,
                    retryable=True,
                    partial=False,
                ) from None

        return placed_bets

    @staticmethod
    def summarize_bets(signal: Signal, placed_bets: list[dict]) -> str:
        if signal.side == "BOTH":
            half_stake = signal.stake / 2
            return f"BOTH YES {half_stake:.2f} / NO {half_stake:.2f} CC"
        if not placed_bets:
            return f"{signal.side} {signal.stake:.2f} CC"
        return f"{signal.side} {signal.stake:.2f} CC"

    @staticmethod
    def total_stake(signal: Signal) -> float:
        return signal.stake
