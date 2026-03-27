from __future__ import annotations

import copy
import time

from dotenv import load_dotenv
from rich.console import Group
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.text import Text
import re

load_dotenv()

from config import config
from execution import BetExecutionError, LiveExecutionAdapter
from logger import logger
from market_feed import MarketFeed
from models import RangeMetrics, SegmentSnapshot
from state import BotState
from strategy import build_strategy
from telegram_notifier import telegram_notifier
from utils import export_signal_history, load_json_list, save_json_list

console = Console()


def format_time_left(total_seconds: int) -> str:
    minutes, seconds = divmod(max(total_seconds, 0), 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}h {minutes}m {seconds}s"
    return f"{minutes}m {seconds}s"


def format_delta(delta: float) -> str:
    return f"{delta:+,.4f}"


def format_cc(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.4f} CC"


def parse_bet_summary(summary: str) -> tuple[float, float]:
    if summary.startswith("BOTH "):
        match = re.match(r"BOTH\s+([0-9.]+)\s+CC\s+x2", summary)
        if match:
            stake = float(match.group(1))
            return stake, stake
        match = re.match(r"BOTH YES\s+([0-9.]+)\s*/\s*NO\s+([0-9.]+)\s+CC", summary)
        if match:
            return float(match.group(1)), float(match.group(2))
        return 0.0, 0.0
    if summary.startswith("YES "):
        match = re.match(r"YES\s+([0-9.]+)\s+CC", summary)
        return (float(match.group(1)), 0.0) if match else (0.0, 0.0)
    if summary.startswith("NO "):
        match = re.match(r"NO\s+([0-9.]+)\s+CC", summary)
        return (0.0, float(match.group(1))) if match else (0.0, 0.0)
    return 0.0, 0.0


def estimate_resolution_outcomes(market, bet_summary: str) -> tuple[str, str]:
    yes_stake, no_stake = parse_bet_summary(bet_summary)
    total_stake = yes_stake + no_stake
    if total_stake <= 0:
        return "-", "-"

    yes_gross = (yes_stake / market.yes_pool) * market.total_pool if market.yes_pool > 0 else 0.0
    no_gross = (no_stake / market.no_pool) * market.total_pool if market.no_pool > 0 else 0.0
    yes_net = yes_gross - total_stake
    no_net = no_gross - total_stake
    return format_cc(yes_net), format_cc(no_net)


def build_pending_event_message(market, bet_summary: str) -> str:
    position_label = (
        "ABOVE"
        if market.target_delta > 0
        else "BELOW"
        if market.target_delta < 0
        else "ON TARGET"
    )
    estimate_yes, estimate_no = estimate_resolution_outcomes(market, bet_summary)
    return (
        f"{market.symbol} pending settlement | {bet_summary} | "
        f"pool={market.total_pool:,.4f} CC | "
        f"{position_label} {market.target_delta:+.4f} | "
        f"est YES {estimate_yes} / NO {estimate_no}"
    )


def send_telegram_pending_message(
    market,
    bet_summary: str,
    balance: float | None,
    *,
    restored: bool = False,
) -> None:
    if not telegram_notifier.enabled:
        return
    position_label = (
        "ABOVE"
        if market.target_delta > 0
        else "BELOW"
        if market.target_delta < 0
        else "ON TARGET"
    )
    estimate_yes, estimate_no = estimate_resolution_outcomes(market, bet_summary)
    telegram_notifier.send_lines(
        "PENDING SETTLEMENT" if not restored else "RESTORED PENDING SETTLEMENT",
        f"balance: {format_cc(balance)}",
        f"nama market: {market.question}",
        f"position: {position_label}",
        f"bet: {bet_summary}",
        f"pool: {format_cc(market.total_pool)}",
        f"estimasi: YES {estimate_yes} | NO {estimate_no}",
        f"delta: {format_delta(market.target_delta)}",
    )


def build_event_panel(message: str) -> Panel:
    border_style = "bright_black"
    title = "EVENT"
    lines: list[Text] = []

    if message.startswith("Restored pending settlement: "):
        payload = message.removeprefix("Restored pending settlement: ")
        bet_summary, _, label = payload.partition(" | ")
        title = "RESTORED"
        border_style = "yellow"
        line = Text()
        line.append("position: ", style="white")
        line.append(bet_summary or "-", style="bold green")
        lines.append(line)
        if label:
            detail = Text()
            detail.append("market: ", style="white")
            detail.append(label, style="bright_black")
            lines.append(detail)
    elif " pending settlement | " in message:
        symbol, _, payload = message.partition(" pending settlement | ")
        parts = payload.split(" | ")
        title = f"{symbol} PENDING"
        border_style = "yellow"
        bet_summary = parts[0] if len(parts) > 0 else "-"
        pool = parts[1].removeprefix("pool=") if len(parts) > 1 else "-"
        position = parts[2] if len(parts) > 2 else "-"
        estimate = parts[3].removeprefix("est ") if len(parts) > 3 else "-"

        line1 = Text()
        line1.append("bet: ", style="white")
        line1.append(bet_summary, style="bold green")
        line1.append("   pool: ", style="white")
        line1.append(pool, style="cyan")
        lines.append(line1)

        line2 = Text()
        line2.append("position: ", style="white")
        line2.append(position, style="magenta")
        lines.append(line2)

        line3 = Text()
        line3.append("estimate: ", style="white")
        line3.append(estimate, style="bright_black")
        lines.append(line3)
    elif match := re.match(
        r"^(?P<symbol>[A-Z]{3}) (?P<bet>.+) delta=(?P<delta>[+-]?\d+(?:\.\d+)?) balance=(?P<balance>[\d.]+) CC$",
        message,
    ):
        title = f"{match.group('symbol')} BET"
        border_style = "green"
        line1 = Text()
        line1.append("bet: ", style="white")
        line1.append(match.group("bet"), style="bold green")
        lines.append(line1)

        line2 = Text()
        line2.append("delta: ", style="white")
        delta = float(match.group("delta"))
        line2.append(format_delta(delta), style="green" if delta >= 0 else "red")
        line2.append("   balance: ", style="white")
        line2.append(f"{float(match.group('balance')):,.4f} CC", style="cyan")
        lines.append(line2)
    elif match := re.match(r"^(?P<symbol>[A-Z]{3}) (?P<bet>.+) pending settlement$", message):
        title = f"{match.group('symbol')} PENDING"
        border_style = "yellow"
        line = Text()
        line.append("bet: ", style="white")
        line.append(match.group("bet"), style="bold green")
        lines.append(line)
    elif match := re.match(r"^(?P<symbol>[A-Z]{3}) round completed$", message):
        title = f"{match.group('symbol')} COMPLETE"
        border_style = "blue"
        line = Text()
        line.append("status: ", style="white")
        line.append("round completed", style="bright_black")
        lines.append(line)
    else:
        lines.append(Text(message, style="bright_black"))

    return Panel(Group(*lines), title=title, border_style=border_style, padding=(0, 1))


def rebuild_range_metrics(
    strategy,
    segments: tuple[SegmentSnapshot, ...],
    target_price: float,
) -> RangeMetrics:
    return strategy.rebuild_range_metrics(segments, target_price)


def display_metrics(state: BotState, strategy, market):
    round_state = state.get_or_create(market.slug, strategy.segment_count)
    if round_state.frozen_range_metrics is not None:
        return round_state.frozen_range_metrics

    metrics = market.range_metrics
    if metrics is None:
        merged_segments = tuple(
            copy.deepcopy(segment)
            for segment in round_state.frozen_segments
            if segment is not None
        )
        if not merged_segments:
            return None
        return RangeMetrics(
            segments=merged_segments,
            average_1=None,
            average_2=None,
            range_1_low=None,
            range_1_high=None,
            range_2_low=None,
            range_2_high=None,
        )

    merged_segments = list(metrics.segments)
    changed = False
    for idx, frozen_segment in enumerate(round_state.frozen_segments):
        if frozen_segment is None or idx >= len(merged_segments):
            continue
        merged_segments[idx] = copy.deepcopy(frozen_segment)
        changed = True

    if not changed:
        return metrics
    if (
        metrics.average_1 is None
        or metrics.average_2 is None
        or metrics.range_1_low is None
        or metrics.range_1_high is None
        or metrics.range_2_low is None
        or metrics.range_2_high is None
    ):
        return RangeMetrics(
            segments=tuple(merged_segments),
            average_1=None,
            average_2=None,
            range_1_low=None,
            range_1_high=None,
            range_2_low=None,
            range_2_high=None,
        )
    return rebuild_range_metrics(strategy, tuple(merged_segments), market.target_price)


def build_lines(markets, state, strategy):
    pnl = state.get_pnl()
    pnl_style = "green" if pnl is not None and pnl >= 0 else "red"
    decision_window_label = format_time_left(config.DECISION_WINDOW_SEC)

    title = Text(f"Unhedged FULL AUTO BOT | Strategy {config.SELECT_STRATEGY}", style="bold white")
    summary = Text()
    summary.append("balance: ", style="white")
    summary.append(format_cc(state.current_balance), style="green")
    summary.append("   ", style="white")
    summary.append("total bet: ", style="white")
    summary.append(format_cc(state.total_bet_cc), style="yellow")
    summary.append("   pnl: ", style="white")
    summary.append(format_cc(pnl), style=pnl_style if pnl is not None else "bright_black")

    blocks = [title, summary]

    for slug in sorted(markets):
        market = markets[slug]
        round_state = state.get_or_create(slug, strategy.segment_count)
        metrics = display_metrics(state, strategy, market)
        target_delta = market.target_delta
        min_avg1 = strategy.minimum_average_1(market.symbol)
        base_status = state.get_market_status(slug)

        if metrics is None:
            delta_style = "white"
            status_style = "bright_black"
            zone_label = "BUILDING RANGE"
        elif (
            metrics.range_2_low is not None
            and metrics.range_2_high is not None
            and metrics.range_2_low <= market.current_price <= metrics.range_2_high
        ):
            delta_style = "bold yellow"
            status_style = "yellow"
            zone_label = "BOTH ZONE"
        elif (
            min_avg1 is not None
            and metrics.average_1 is not None
            and abs(metrics.average_1) < min_avg1
        ):
            delta_style = "white"
            status_style = "bright_black"
            zone_label = "AVG1 TOO SMALL"
        elif metrics.range_1_high is not None and market.current_price > metrics.range_1_high:
            delta_style = "bold green"
            status_style = "green"
            zone_label = "YES ZONE"
        elif metrics.range_1_low is not None and market.current_price < metrics.range_1_low:
            delta_style = "bold red"
            status_style = "red"
            zone_label = "NO ZONE"
        else:
            delta_style = "white"
            status_style = "white"
            zone_label = "NO BET ZONE"

        if base_status == "BET FAILED":
            status_style = "red"

        status_label = base_status
        if (
            base_status in {"YES SENT", "NO SENT", "BOTH SENT"}
            and market.timer_left > 0
        ):
            status_label = f"{base_status} | PENDING"
        elif (
            base_status == "MONITORING"
            and state.get_last_bet(slug) != "-"
            and state.get_pending_bet(market.market_id) is not None
        ):
            status_label = "RESTORED | PENDING"
        if base_status == "MONITORING":
            if (
                state.get_last_bet(slug) != "-"
                and state.get_pending_bet(market.market_id) is not None
            ):
                status_label = "RESTORED | PENDING"
            elif metrics is None:
                status_label = "BUILDING RANGE"
            elif market.timer_left > config.DECISION_WINDOW_SEC:
                if zone_label == "YES ZONE":
                    status_label = f"WAIT {decision_window_label}: YES"
                elif zone_label == "NO ZONE":
                    status_label = f"WAIT {decision_window_label}: NO"
                elif zone_label == "BOTH ZONE":
                    status_label = f"WAIT {decision_window_label}: BOTH"
                elif zone_label == "AVG1 TOO SMALL":
                    status_label = "AVG1 TOO SMALL"
                else:
                    status_label = f"WAIT {decision_window_label}"
            else:
                if zone_label == "YES ZONE":
                    status_label = "READY YES"
                elif zone_label == "NO ZONE":
                    status_label = "READY NO"
                elif zone_label == "BOTH ZONE":
                    status_label = "READY BOTH"
                elif zone_label == "AVG1 TOO SMALL":
                    status_label = "AVG1 TOO SMALL"
                else:
                    status_label = "NO SIGNAL"
        if base_status == "BET FAILED" and round_state.last_error:
            status_label = f"BET FAILED | {round_state.last_error}"

        header = Text()
        header.append(f"{market.symbol}", style="bold cyan")
        header.append(f"  {market.question}", style="bold white")

        price_line = Text()
        price_line.append("target: ", style="white")
        price_line.append(f"{market.target_price:,.4f}", style="yellow")
        price_line.append("   current: ", style="white")
        price_line.append(f"{market.current_price:,.4f}", style="green")
        price_line.append("   left: ", style="white")
        price_line.append(format_time_left(market.timer_left), style="magenta")

        delta_line = Text()
        delta_line.append("delta target-current: ", style="white")
        delta_line.append(f"{format_delta(target_delta)}", style=delta_style)
        delta_line.append("   zone: ", style="white")
        delta_line.append(zone_label, style=status_style)

        outcome_line = Text()
        outcome_line.append("outcome: ", style="white")
        outcome_line.append(
            f"YES {market.yes_percentage:.0f}% / NO {market.no_percentage:.0f}%",
            style="blue",
        )
        outcome_line.append("   your bet: ", style="white")
        bet_summary = state.get_last_bet(slug)
        outcome_line.append(bet_summary, style="bold green")
        outcome_line.append("   status: ", style="white")
        outcome_line.append(status_label, style=status_style)

        pool_line = Text()
        position_label = "ABOVE TARGET" if target_delta > 0 else "BELOW TARGET" if target_delta < 0 else "ON TARGET"
        position_style = "green" if target_delta > 0 else "red" if target_delta < 0 else "yellow"
        pool_line.append("total pool: ", style="white")
        pool_line.append(format_cc(market.total_pool), style="cyan")
        pool_line.append("   position: ", style="white")
        pool_line.append(position_label, style=position_style)
        pool_line.append("   gap: ", style="white")
        pool_line.append(format_delta(target_delta), style=position_style)

        estimate_yes, estimate_no = estimate_resolution_outcomes(market, bet_summary)
        estimate_line = Text()
        estimate_line.append("est resolve: ", style="white")
        estimate_line.append(f"YES {estimate_yes}", style="green")
        estimate_line.append("   |   ", style="white")
        estimate_line.append(f"NO {estimate_no}", style="red")

        threshold_line = Text()
        if (
            metrics is None
            or metrics.average_1 is None
            or metrics.average_2 is None
            or metrics.range_1_low is None
            or metrics.range_1_high is None
            or metrics.range_2_low is None
            or metrics.range_2_high is None
        ):
            ready_segments = len(metrics.segments) if metrics is not None else 0
            threshold_line.append(
                f"ranges: waiting for enough history ({ready_segments}/{strategy.segment_count} segments ready)",
                style="bright_black",
            )
        else:
            threshold_line.append("avg_1: ", style="white")
            threshold_line.append(f"{metrics.average_1:+.4f}", style="cyan")
            if min_avg1 is not None:
                threshold_line.append("   min avg_1: ", style="white")
                threshold_line.append(f"{min_avg1:+.4f}", style="bright_black")
            threshold_line.append("   avg_2: ", style="white")
            threshold_line.append(f"{metrics.average_2:+.4f}", style="cyan")
            threshold_line.append("   range_1: ", style="white")
            threshold_line.append(
                f"{metrics.range_1_low:.4f} ~ {metrics.range_1_high:.4f}",
                style="bright_black",
            )
            threshold_line.append("   range_2: ", style="white")
            threshold_line.append(
                f"{metrics.range_2_low:.4f} ~ {metrics.range_2_high:.4f}",
                style="bright_black",
            )

        segment_line = Text()
        if metrics is None or not metrics.segments:
            segment_line.append("segments: waiting for enough history", style="bright_black")
        else:
            segment_line.append("segments: ", style="white")
            segment_line.append(
                " | ".join(
                    f"{segment.label} {segment.signed_range:+.4f}"
                    for segment in metrics.segments
                ),
                style="bright_black",
            )

        high_low_line = Text()
        if metrics is None or not metrics.segments:
            high_low_line.append("high-low: waiting for enough history", style="bright_black")
        else:
            high_low_line.append("high-low: ", style="white")
            high_low_line.append(
                " | ".join(
                    f"{segment.label} {segment.high_price:.4f}-{segment.low_price:.4f}"
                    for segment in metrics.segments
                ),
                style="bright_black",
            )

        blocks.append(
            Panel(
                Group(
                    header,
                    price_line,
                    delta_line,
                    outcome_line,
                    pool_line,
                    estimate_line,
                    threshold_line,
                    segment_line,
                    high_low_line,
                ),
                border_style="bright_black",
                padding=(0, 1),
            )
        )

    if len(blocks) == 2:
        blocks.append(Text("Menunggu market BTC/SOL/ETH above aktif...", style="yellow"))

    if state.events:
        blocks.append(Text("Events", style="bold white"))
        for item in state.events[-6:]:
            blocks.append(build_event_panel(item))

    return Group(*blocks)


def persist_pending_bets(state: BotState) -> None:
    items = []
    for market_id, summary in state.pending_bets_by_market_id.items():
        items.append({"market_id": market_id, "summary": summary})
    save_json_list(items, config.PENDING_BETS_PATH)


def freeze_segment_metrics(state: BotState, strategy, market) -> None:
    round_state = state.get_or_create(market.slug, strategy.segment_count)
    metrics = market.range_metrics
    if metrics is None:
        return

    freeze_thresholds = tuple(
        segment.freeze_threshold_sec for segment in strategy.segment_windows
    )
    for idx, threshold in enumerate(freeze_thresholds):
        if (
            idx < len(metrics.segments)
            and market.timer_left <= threshold
            and round_state.frozen_segments[idx] is None
        ):
            round_state.frozen_segments[idx] = copy.deepcopy(metrics.segments[idx])

    frozen_segments = round_state.frozen_segments[: len(metrics.segments)]
    if (
        round_state.frozen_range_metrics is None
        and len(metrics.segments) == len(freeze_thresholds)
        and all(frozen_segments)
    ):
        round_state.frozen_range_metrics = rebuild_range_metrics(
            strategy,
            tuple(segment for segment in frozen_segments if segment is not None),
            market.target_price,
        )


def main() -> None:
    config.validate_runtime()
    logger.success("UNHEDGED FULL AUTO STARTED")
    state = BotState()
    strategy = build_strategy(state)
    feed = MarketFeed(strategy)
    executor = LiveExecutionAdapter()
    latest_markets = {}
    state.set_balances(
        starting_balance=executor.starting_balance,
        current_balance=executor.starting_balance,
    )
    state.add_event(f"Start balance {executor.starting_balance:.4f} CC")
    try:
        restored_bets = executor.fetch_pending_settlement_bets()
    except Exception:
        logger.exception("Failed to restore pending settlement bets at startup.")
        restored_bets = []

    if not restored_bets:
        restored_bets = load_json_list(config.PENDING_BETS_PATH)

    for item in restored_bets:
        market_id = item.get("market_id")
        summary = item.get("summary")
        if not isinstance(market_id, str) or not isinstance(summary, str):
            continue
        question = item.get("question", market_id)
        state.restore_pending_bet(market_id, summary)
        state.add_event(f"Restored pending settlement: {summary} | {question}")
    persist_pending_bets(state)

    with Live(build_lines(latest_markets, state, strategy), console=console, auto_refresh=False, screen=True) as live:
        for market in feed.stream():
            if market.timer_left <= 0 and state.was_market_closed(market.slug, market.market_id):
                latest_markets.pop(market.slug, None)
                feed.drop_market(market.slug)
                live.update(build_lines(latest_markets, state, strategy), refresh=True)
                continue

            latest_markets[market.slug] = market
            restored_summary = state.get_pending_bet(market.market_id)
            if restored_summary is not None and state.get_last_bet(market.slug) == "-":
                state.record_bet(market.slug, restored_summary)
            if (
                restored_summary is not None
                and state.should_log_pending_details(market.market_id)
            ):
                state.add_event(build_pending_event_message(market, restored_summary))
                state.mark_pending_details_logged(market.market_id)
            if (
                restored_summary is not None
                and state.should_send_pending_telegram_update(
                    market.market_id,
                    config.TELEGRAM_POSITION_UPDATE_SEC,
                )
            ):
                send_telegram_pending_message(
                    market,
                    restored_summary,
                    state.current_balance,
                    restored=True,
                )
            freeze_segment_metrics(state, strategy, market)

            signal = strategy.evaluate(market)

            if signal:
                try:
                    placed_bets = executor.execute(signal)
                except BetExecutionError as exc:
                    logger.warning("Signal execution failed: %s", exc)
                    if not exc.retryable:
                        state.block_round_execution(
                            market.slug,
                            "API REJECTED",
                            segment_count=strategy.segment_count,
                        )
                    state.add_event(
                        f"{market.symbol} bet failed | {signal.side} | {exc}"
                    )
                    live.update(build_lines(latest_markets, state, strategy), refresh=True)
                    continue

                state.mark_signal_sent(
                    market.slug,
                    signal.side,
                    segment_count=strategy.segment_count,
                )
                state.record_signal(signal)
                summary = executor.summarize_bets(signal, placed_bets)
                state.record_bet(market.slug, summary)
                state.restore_pending_bet(market.market_id, summary)
                state.record_total_bet(executor.total_stake(signal))
                current_balance = executor.fetch_balance()
                state.set_balances(current_balance=current_balance)
                state.add_event(
                    f"{market.symbol} {summary} delta={signal.delta:+.4f} balance={current_balance:.4f} CC"
                )
                telegram_notifier.send_lines(
                    "BET TERKIRIM",
                    f"balance: {format_cc(current_balance)}",
                    f"nama market: {market.question}",
                    f"position: {'ABOVE' if market.target_delta > 0 else 'BELOW' if market.target_delta < 0 else 'ON TARGET'}",
                    f"bet: {summary}",
                    f"pool: {format_cc(market.total_pool)}",
                    f"estimasi: YES {estimate_resolution_outcomes(market, summary)[0]} | NO {estimate_resolution_outcomes(market, summary)[1]}",
                    f"delta: {format_delta(signal.delta)}",
                )
                round_state = state.get_or_create(market.slug, strategy.segment_count)
                if not round_state.pending_settlement_logged:
                    state.add_event(build_pending_event_message(market, summary))
                    state.mark_pending_details_logged(market.market_id)
                    state.pending_telegram_update_at[market.market_id] = time.monotonic()
                    round_state.pending_settlement_logged = True
                persist_pending_bets(state)
                export_signal_history(state.recent_activity, config.SIGNAL_HISTORY_PATH)

            if market.timer_left <= 0:
                state.add_event(f"{market.symbol} round completed")
                state.mark_closed_market(market.slug, market.market_id)
                state.reset_round(market.slug)
                state.record_bet(market.slug, "-")
                latest_markets.pop(market.slug, None)
                feed.drop_market(market.slug)
                try:
                    feed.refresh_market_ids()
                except Exception:
                    logger.exception("Failed to refresh market ids after round completion.")
                export_signal_history(state.recent_activity, config.SIGNAL_HISTORY_PATH)

            live.update(build_lines(latest_markets, state, strategy), refresh=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")
    except Exception:
        logger.exception("Fatal error in main loop.")
        raise
