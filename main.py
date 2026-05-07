"""
Main Orchestrator — Wealth Advisor Trading Bot
Runs hourly during market hours, coordinates all advisors, executes trades.
"""

import logging
import time
import os
import sys
from datetime import datetime, time as dt_time
import pytz
from config import (
    MARKET_OPEN,
    MARKET_CLOSE,
    RUN_INTERVAL_MINUTES,
    TIMEZONE,
    STOCK_UNIVERSE,
    MAX_POSITIONS,
)
from market_data import (
    get_account,
    get_positions,
    get_bars,
    get_momentum_candidates,
    build_portfolio_context,
    build_force_added_candidates,
)
from trade_executor import TradeExecutor
from daily_summary import run_daily_summary
from form4_fetcher import get_qualifying_form4_buys

# Import advisors
from advisors.momentum_analyst import MomentumAnalyst
from advisors.sentiment_analyst import SentimentAnalyst
from advisors.risk_manager import RiskManager
from advisors.portfolio_strategist import PortfolioStrategist
from advisors.head_advisor import HeadAdvisor
from advisors.form4_analyst import Form4Analyst

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


class WealthAdvisorBot:
    """Multi-agent trading bot orchestrator."""

    def __init__(self):
        """Initialize bot and all advisors."""
        logger.info("=" * 70)
        logger.info("🤖 WEALTH ADVISOR BOT — Starting Up")
        logger.info("=" * 70)

        # Initialize advisors
        self.momentum_analyst = MomentumAnalyst()
        self.sentiment_analyst = SentimentAnalyst()
        self.risk_manager = RiskManager()
        self.portfolio_strategist = PortfolioStrategist()
        self.head_advisor = HeadAdvisor()
        self.form4_analyst = Form4Analyst()

        # Trade executor
        self.executor = TradeExecutor()

        # Timezone for market hours
        self.tz = pytz.timezone(TIMEZONE)

        # Form 4 state (resets per calendar day)
        self.form4_briefing = None          # Result dict from Form4Analyst.generate_briefing
        self.form4_prep_date = None         # date() the briefing was generated for
        self.first_post_open_done_date = None  # date() the first post-open cycle ran

        logger.info("✅ All advisors initialized")
        logger.info(f"✅ Trading universe: {len(STOCK_UNIVERSE)} stocks")
        logger.info(f"✅ Max positions: {MAX_POSITIONS}")

    def is_market_open(self) -> bool:
        """Check if market is currently open (US Eastern time)."""
        now = datetime.now(self.tz).time()
        return MARKET_OPEN <= now < MARKET_CLOSE

    def is_pre_market(self) -> bool:
        """Check if we're before the open (same calendar day, any time before 9:30 ET)."""
        now = datetime.now(self.tz).time()
        return now < MARKET_OPEN

    def should_run(self) -> bool:
        """Check if we're in market hours and ready to run."""
        if not self.is_market_open():
            logger.debug("Market is closed, skipping run")
            return False
        return True

    def run_form4_prep(self):
        """
        Pre-market Form 4 briefing generation. Fetches OpenInsider + S&P 500,
        runs the Form 4 Analyst to produce the markdown briefing, and stores
        the result on self.form4_briefing for use in the first post-open cycle.
        Idempotent within a calendar day — regenerates each time it's called
        so the briefing reflects the latest filings.
        """
        today = datetime.now(self.tz).date()
        logger.info("=" * 70)
        logger.info(f"🕵️ FORM 4 PREP — {today.isoformat()}")
        logger.info("=" * 70)

        try:
            buys = get_qualifying_form4_buys()
            briefing = self.form4_analyst.generate_briefing(
                buys, datetime.now(self.tz)
            )
            self.form4_briefing = briefing
            self.form4_prep_date = today

            if briefing["qualifying_tickers"]:
                logger.info(
                    f"   Qualifying tickers: {', '.join(briefing['qualifying_tickers'])}"
                )
                logger.info(f"   Saved briefing: {briefing.get('summary_path', '(unsaved)')}")
            else:
                logger.info("   No qualifying buys today.")
        except Exception as e:
            logger.error(f"❌ Form 4 prep failed: {e}", exc_info=True)
            # Store an empty briefing so first post-open cycle doesn't retry indefinitely
            self.form4_briefing = {
                "briefing_markdown": "",
                "per_ticker_notes": {},
                "recommended_action": f"Form 4 prep failed: {e}",
                "qualifying_tickers": [],
                "summary_path": None,
            }
            self.form4_prep_date = today

    def run_analysis_cycle(self, inject_form4: bool = False):
        """
        Single trading cycle:
        1. Fetch market data
        2. Get momentum candidates (+ force-add Form 4 tickers if inject_form4)
        3. Run all advisors on each candidate
        4. Head advisor makes final decision (with Form 4 context if present)
        5. Execute approved trades
        """
        logger.info("-" * 70)
        header = f"🔄 Analysis Cycle Starting ({datetime.now(self.tz).strftime('%I:%M %p %Z')})"
        if inject_form4:
            header += " 🕵️ [FIRST POST-OPEN — Form 4 injection ON]"
        logger.info(header)
        logger.info("-" * 70)

        try:
            # Step 1: Get market data
            logger.info("📊 Fetching market data...")
            account = get_account()
            positions = get_positions()
            bars_data = get_bars(STOCK_UNIVERSE, limit=50, timeframe="15Min")

            # Step 2: Get momentum candidates
            logger.info("🔍 Pre-filtering momentum candidates...")
            candidates = get_momentum_candidates(bars_data)
            logger.info(f"   Found {len(candidates)} momentum candidates")

            # Step 2b: Force-add Form 4 tickers (first post-open cycle only)
            forced_symbols = set()
            if inject_form4 and self.form4_briefing:
                f4_tickers = self.form4_briefing.get("qualifying_tickers", [])
                existing = {c["symbol"] for c in candidates}
                extra = [t for t in f4_tickers if t not in existing]
                if extra:
                    logger.info(f"   🕵️ Force-adding Form 4 tickers: {', '.join(extra)}")
                    forced = build_force_added_candidates(extra)
                    forced_symbols = {c["symbol"] for c in forced}
                    candidates = candidates + forced

            if not candidates:
                logger.info("   No candidates met criteria, skipping cycle")
                return

            # Step 3: Build portfolio context
            portfolio_context = build_portfolio_context(account, positions)
            logger.info(
                f"   Portfolio: ${portfolio_context['equity']:,.2f} equity | "
                f"{len(positions)}/{MAX_POSITIONS} positions"
            )

            # Step 4: Analyze each candidate with all advisors
            decisions_made = 0
            for candidate in candidates:
                symbol = candidate["symbol"]
                logger.info(f"\n📈 Analyzing {symbol} (RSI: {candidate['rsi']:.1f}, "
                           f"Momentum: {candidate['momentum']:.2f}%)")

                # Get specialist opinions
                logger.info(f"  Gathering advisor opinions...")
                momentum_opinion = self.momentum_analyst.analyze(candidate, portfolio_context)
                sentiment_opinion = self.sentiment_analyst.analyze(candidate, portfolio_context)
                risk_opinion = self.risk_manager.analyze(candidate, portfolio_context)
                portfolio_opinion = self.portfolio_strategist.analyze(candidate, portfolio_context)

                opinions = [momentum_opinion, sentiment_opinion, risk_opinion, portfolio_opinion]

                # Build Form 4 context for this ticker (only on first post-open cycle)
                form4_ctx = None
                if inject_form4 and self.form4_briefing:
                    per_ticker = self.form4_briefing.get("per_ticker_notes", {}) or {}
                    if symbol in per_ticker or symbol in forced_symbols:
                        form4_ctx = {
                            "ticker_note": per_ticker.get(symbol, ""),
                            "overall_action": self.form4_briefing.get("recommended_action", ""),
                            "is_force_added": symbol in forced_symbols,
                        }

                # Head advisor synthesizes
                logger.info(f"  Head Advisor synthesizing...")
                decision = self.head_advisor.decide(
                    candidate, opinions, portfolio_context, form4_context=form4_ctx
                )

                # Execute if approved
                if decision.get("decision") == "BUY" and decision.get("shares", 0) > 0:
                    self._execute_decision(decision, candidate)
                    decisions_made += 1
                elif decision.get("decision") == "SELL" and decision.get("shares", 0) > 0:
                    self._execute_decision(decision, candidate)
                    decisions_made += 1

            logger.info(f"\n✅ Cycle complete: {decisions_made} trades executed")

        except Exception as e:
            logger.error(f"❌ Cycle failed: {e}", exc_info=True)

    def _execute_decision(self, decision: dict, stock_data: dict):
        """Execute a trade decision from Head Advisor."""
        symbol = decision.get("symbol")
        side = decision.get("decision", "PASS").lower()
        shares = decision.get("shares", 0)

        if side == "pass" or shares == 0:
            return

        entry_price = stock_data["price"]
        stop_loss = decision.get("stop_loss", 0)
        take_profit = decision.get("take_profit", 0)
        reasoning = decision.get("reasoning", "Advisor consensus")

        result = self.executor.execute_trade(
            symbol=symbol,
            qty=shares,
            side=side,
            entry_price=entry_price,
            stop_loss_price=stop_loss,
            take_profit_price=take_profit,
            reasoning=reasoning,
        )

        if result.get("status") == "success":
            logger.info(f"✅ Trade executed: {side.upper()} {shares} {symbol}")
        else:
            logger.error(f"❌ Trade failed: {result.get('reason')}")

    def run_daily_close(self):
        """Run at market close: generate end-of-day summary."""
        logger.info("=" * 70)
        logger.info("📋 MARKET CLOSE — Generating Daily Summary")
        logger.info("=" * 70)

        try:
            account = get_account()
            positions = get_positions()
            portfolio_snapshot = build_portfolio_context(account, positions)

            summary_path = run_daily_summary(portfolio_snapshot)
            if summary_path:
                logger.info(f"✅ Daily summary saved: {summary_path}")
            else:
                logger.warning("⚠️ Failed to save daily summary")

        except Exception as e:
            logger.error(f"❌ Daily close failed: {e}", exc_info=True)

    def run_forever(self):
        """Main loop: runs hourly during market hours."""
        logger.info(f"\n🚀 Bot starting main loop (interval: {RUN_INTERVAL_MINUTES} min)")
        logger.info(f"   Market hours: {MARKET_OPEN.strftime('%I:%M %p')} – "
                   f"{MARKET_CLOSE.strftime('%I:%M %p')} {TIMEZONE}\n")

        last_close_run = None
        interval_seconds = RUN_INTERVAL_MINUTES * 60

        try:
            while True:
                current_time = datetime.now(self.tz)
                today = current_time.date()

                # Pre-market: run Form 4 prep every cycle (regenerates briefing with latest filings)
                if self.is_pre_market():
                    self.run_form4_prep()

                # Market-open cycles
                if self.should_run():
                    # Catch-up: if bot started after market open and briefing is stale/missing
                    if self.form4_prep_date != today:
                        logger.info("🕵️ Catching up Form 4 prep (bot started post-open)")
                        self.run_form4_prep()

                    # First post-open cycle of the day gets Form 4 injection
                    inject_form4 = (self.first_post_open_done_date != today)
                    self.run_analysis_cycle(inject_form4=inject_form4)
                    if inject_form4:
                        self.first_post_open_done_date = today

                # Run daily close at market close time (once per day)
                current_time_str = current_time.strftime("%Y-%m-%d %H:%M")
                close_time_str = current_time.replace(
                    hour=MARKET_CLOSE.hour,
                    minute=MARKET_CLOSE.minute,
                    second=0,
                    microsecond=0
                ).strftime("%Y-%m-%d %H:%M")

                if (current_time_str >= close_time_str and
                    (last_close_run is None or last_close_run != current_time.date())):
                    self.run_daily_close()
                    last_close_run = current_time.date()

                # Sleep until next cycle
                logger.info(f"💤 Sleeping for {RUN_INTERVAL_MINUTES} minutes...")
                time.sleep(interval_seconds)

        except KeyboardInterrupt:
            logger.info("\n⏹️  Bot shutting down (Ctrl+C)")
        except Exception as e:
            logger.error(f"\n❌ Fatal error: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    try:
        bot = WealthAdvisorBot()
        bot.run_forever()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}", exc_info=True)
        sys.exit(1)
