from __future__ import annotations

from dotenv import load_dotenv
from rich.console import Group
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

load_dotenv()

from config import config
from execution import LiveExecutionAdapter
from logger import logger
from market_feed import MarketFeed
from state import BotState
from strategy import Strategy
from utils import export_signal_history

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


def build_lines(markets, state):
    pnl = state.get_pnl()
    pnl_style = "green" if pnl is not None and pnl >= 0 else "red"

    title = Text("Unhedged FULL AUTO BOT", style="bold white")
    summary = Text()
    summary.append("total bet: ", style="white")
    summary.append(format_cc(state.total_bet_cc), style="yellow")
    summary.append("   pnl: ", style="white")
    summary.append(format_cc(pnl), style=pnl_style if pnl is not None else "bright_black")

    blocks = [title, summary]

    for slug in sorted(markets):
        market = markets[slug]
        round_state = state.get_or_create(slug)
        metrics = round_state.frozen_range_metrics or market.range_metrics
        target_delta = market.target_delta
        min_avg1 = config.minimum_average_1(market.symbol)

        if metrics is None:
            delta_style = "white"
            status_style = "bright_black"
            zone_label = "BUILDING RANGE"
        elif metrics.range_2_low <= market.current_price <= metrics.range_2_high:
            delta_style = "bold yellow"
            status_style = "yellow"
            zone_label = "BOTH ZONE"
        elif abs(metrics.average_1) < min_avg1:
            delta_style = "white"
            status_style = "bright_black"
            zone_label = "AVG1 TOO SMALL"
        elif market.current_price > metrics.range_1_high:
            delta_style = "bold green"
            status_style = "green"
            zone_label = "YES ZONE"
        elif market.current_price < metrics.range_1_low:
            delta_style = "bold red"
            status_style = "red"
            zone_label = "NO ZONE"
        else:
            delta_style = "white"
            status_style = "white"
            zone_label = "NO BET ZONE"

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
        outcome_line.append(state.get_last_bet(slug), style="bold green")
        outcome_line.append("   status: ", style="white")
        outcome_line.append(state.get_market_status(slug), style=status_style)

        threshold_line = Text()
        if metrics is None:
            threshold_line.append("ranges: waiting for enough history", style="bright_black")
        else:
            threshold_line.append("avg_1: ", style="white")
            threshold_line.append(f"{metrics.average_1:+.4f}", style="cyan")
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
        if metrics is None:
            segment_line.append("segments: waiting for enough history", style="bright_black")
        else:
            moves = ", ".join(f"{value:+.4f}" for value in metrics.segment_moves)
            segment_line.append("segment m5/m5/m5/m3: ", style="white")
            segment_line.append(moves, style="bright_black")

        blocks.append(
            Panel(
                Group(header, price_line, delta_line, outcome_line, threshold_line, segment_line),
                border_style="bright_black",
                padding=(0, 1),
            )
        )

    if len(blocks) == 2:
        blocks.append(Text("Menunggu market BTC/SOL/ETH above aktif...", style="yellow"))

    return Group(*blocks)


def main() -> None:
    config.validate_runtime()
    logger.success("UNHEDGED FULL AUTO STARTED")
    state = BotState()
    strategy = Strategy(state)
    feed = MarketFeed()
    executor = LiveExecutionAdapter()
    latest_markets = {}
    state.set_balances(
        starting_balance=executor.starting_balance,
        current_balance=executor.starting_balance,
    )

    for market in feed.stream():
        latest_markets[market.slug] = market
        round_state = state.get_or_create(market.slug)
        if (
            round_state.frozen_range_metrics is None
            and market.range_metrics is not None
            and market.timer_left <= 120
        ):
            round_state.frozen_range_metrics = market.range_metrics

        signal = strategy.evaluate(market)

        if signal:
            logger.warning(
                "SIGNAL side=%s market=%s delta=%.4f reason=%s",
                signal.side,
                signal.market_slug,
                signal.delta,
                signal.reason,
            )
            placed_bets = executor.execute(signal)
            state.record_bet(
                market.slug,
                executor.summarize_bets(signal, placed_bets),
            )
            state.record_total_bet(executor.total_stake(signal))
            state.set_balances(current_balance=executor.fetch_balance())
            export_signal_history(state.recent_activity, config.SIGNAL_HISTORY_PATH)

        if market.timer_left <= 0:
            logger.info("Round completed for %s", market.slug)
            state.reset_round(market.slug)
            state.record_bet(market.slug, "-")
            latest_markets.pop(market.slug, None)
            feed.drop_market(market.slug)
            try:
                feed.refresh_market_ids()
            except Exception:
                logger.exception("Failed to refresh market ids after round completion.")
            export_signal_history(state.recent_activity, config.SIGNAL_HISTORY_PATH)

        console.clear()
        console.print(build_lines(latest_markets, state))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user.")
    except Exception:
        logger.exception("Fatal error in main loop.")
        raise
