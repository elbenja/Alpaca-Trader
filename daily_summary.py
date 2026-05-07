"""
Daily Summary Generator — GPT-4o powered end-of-day report.
Analyzes trades, P&L, and advisor performance from the day.
"""

import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from openai import OpenAI
from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    OPENAI_TEMPERATURE,
    TRADES_FILE,
    SUMMARIES_DIR,
)

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)

ACCOUNT_START_DATE = date(2026, 4, 13)
ACCOUNT_START_EQUITY = 10000.00

# Ensure summaries directory exists
os.makedirs(SUMMARIES_DIR, exist_ok=True)


def get_todays_trades() -> list:
    """Load trades from today and return as list."""
    try:
        with open(TRADES_FILE, "r") as f:
            all_trades = json.load(f)
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.warning(f"Failed to load trades: {e}")
        return []

    # Filter for today's trades
    today = datetime.now().date()
    todays_trades = []

    for trade in all_trades:
        try:
            trade_date = datetime.fromisoformat(trade["timestamp"]).date()
            if trade_date == today:
                todays_trades.append(trade)
        except Exception:
            continue

    return todays_trades


def generate_summary(trades: list, portfolio_snapshot: dict) -> str:
    """
    Use GPT-4o to generate a professional end-of-day summary.

    Args:
        trades: List of today's trade records
        portfolio_snapshot: Dict with current positions, account equity, etc.

    Returns:
        Markdown-formatted summary
    """

    # Format trades for the prompt
    trades_summary = ""
    if trades:
        for i, trade in enumerate(trades, 1):
            trades_summary += f"""
{i}. **{trade['side'].upper()} {trade['qty']} {trade['symbol']}** @ ${trade['entry_price']:.2f}
   - SL: ${trade['stop_loss']:.2f} | TP: ${trade['take_profit']:.2f}
   - Reasoning: {trade.get('reasoning', 'N/A')[:150]}
"""
    else:
        trades_summary = "No trades executed today."

    # Build prompt
    prompt = f"""
You are a financial analyst summarizing a day of algorithmic trading on a multi-agent wealth advisor system.

**Today's Trading Activity:**
{trades_summary}

**Portfolio Snapshot:**
- Account Equity: ${portfolio_snapshot.get('equity', 0):,.2f}
- Buying Power: ${portfolio_snapshot.get('buying_power', 0):,.2f}
- Open Positions: {len(portfolio_snapshot.get('positions', []))}
- Max Allowed: {portfolio_snapshot.get('max_positions', 10)}

**Your Task:**
Generate a concise, professional end-of-day summary (3-4 paragraphs) that:
1. Summarizes the trading activity and rationale
2. Notes any patterns in advisor recommendations
3. Highlights risk management actions taken
4. Provides brief outlook for tomorrow

Write in markdown format with headers. Be data-driven and analytical.
"""

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=OPENAI_TEMPERATURE,
            messages=[
                {
                    "role": "system",
                    "content": "You are a financial analyst. Provide clear, concise market analysis.",
                },
                {"role": "user", "content": prompt},
            ],
            max_tokens=800,
        )

        summary_text = response.choices[0].message.content.strip()
        return summary_text

    except Exception as e:
        logger.error(f"Failed to generate GPT summary: {e}")
        return f"# Summary Generation Failed\n\nError: {str(e)}\n\nSee trades.json for details."


def parse_account_equity(summary_text: str) -> float | None:
    """Extract account equity from an existing summary file."""
    match = re.search(r"account equity[^$]*\$([0-9,]+\.\d{2})", summary_text, re.IGNORECASE)
    if not match:
        return None

    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def get_summary_equity(summary_date: date, summaries_dir: str = SUMMARIES_DIR) -> float | None:
    """Read ending equity from a previously saved daily summary."""
    filepath = os.path.join(summaries_dir, f"{summary_date.strftime('%Y-%m-%d')}.md")

    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, "r") as f:
            return parse_account_equity(f.read())
    except Exception as e:
        logger.warning(f"Failed to read prior summary equity from {filepath}: {e}")
        return None


def calculate_gain_pct(current_equity: float, baseline_equity: float) -> float:
    """Calculate percentage gain or loss from a baseline equity."""
    if baseline_equity <= 0:
        return 0.0
    return ((current_equity - baseline_equity) / baseline_equity) * 100


def build_performance_footer(
    current_equity: float,
    summary_date: date,
    summaries_dir: str = SUMMARIES_DIR,
) -> str:
    """Build a stable footer with daily and since-inception percentage gains."""
    if summary_date <= ACCOUNT_START_DATE:
        daily_baseline = ACCOUNT_START_EQUITY
    else:
        previous_equity = get_summary_equity(summary_date - timedelta(days=1), summaries_dir)
        daily_baseline = previous_equity if previous_equity is not None else ACCOUNT_START_EQUITY

    daily_gain_pct = calculate_gain_pct(current_equity, daily_baseline)
    gain_since_start_pct = calculate_gain_pct(current_equity, ACCOUNT_START_EQUITY)

    return (
        "\n\n---\n\n"
        f"Daily gain: {daily_gain_pct:+.2f}%\n"
        f"Gain since April 13, 2026: {gain_since_start_pct:+.2f}%"
    )


def save_summary(
    summary_text: str,
    portfolio_snapshot: dict | None = None,
    summary_date: date | None = None,
    summaries_dir: str = SUMMARIES_DIR,
) -> str:
    """
    Save summary to YYYY-MM-DD.md file in summaries/ directory.

    Returns:
        File path of saved summary
    """
    now = datetime.now()
    summary_date = summary_date or now.date()
    today = summary_date.strftime("%Y-%m-%d")
    filepath = os.path.join(summaries_dir, f"{today}.md")

    header = f"""# Daily Summary — {today}

Generated: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}

---

"""

    full_summary = header + summary_text
    if portfolio_snapshot and "equity" in portfolio_snapshot:
        full_summary += build_performance_footer(
            current_equity=float(portfolio_snapshot["equity"]),
            summary_date=summary_date,
            summaries_dir=summaries_dir,
        )

    try:
        with open(filepath, "w") as f:
            f.write(full_summary)
        logger.info(f"✅ Daily summary saved: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Failed to save summary: {e}")
        return None


def run_daily_summary(portfolio_snapshot: dict) -> str:
    """
    Main entry point: collect trades, generate summary, save to file.

    Args:
        portfolio_snapshot: Current account state

    Returns:
        Path to saved summary file, or None if failed
    """
    logger.info("Generating daily summary...")

    trades = get_todays_trades()
    logger.info(f"Found {len(trades)} trades from today")

    summary_text = generate_summary(trades, portfolio_snapshot)
    filepath = save_summary(summary_text, portfolio_snapshot=portfolio_snapshot)

    return filepath
