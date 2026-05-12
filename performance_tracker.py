"""
Performance Tracker — Records trade outcomes for Head Advisor briefing.
Captures advisor votes at execution time and syncs closed positions from Alpaca.
"""

import json
import logging
import requests
from collections import defaultdict
from config import ALPACA_BASE_URL, ALPACA_HEADERS, PERFORMANCE_LOG_FILE
from market_data import get_positions

logger = logging.getLogger(__name__)


def load_performance_log() -> list:
    """Load performance_log.json; return empty list if missing or corrupt."""
    try:
        with open(PERFORMANCE_LOG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Performance log unreadable ({e}), starting fresh")
        return []


def save_performance_log(log: list) -> None:
    """Overwrite performance_log.json with the given list."""
    with open(PERFORMANCE_LOG_FILE, "w") as f:
        json.dump(log, f, indent=2)


def append_performance_entry(
    order_id: str,
    symbol: str,
    side: str,
    qty: int,
    entry_price: float,
    entry_date: str,
    advisor_votes: list,
) -> None:
    """
    Phase 1: write a new open entry to the performance log at trade execution.
    advisor_votes: list of dicts with keys advisor, recommendation, confidence.
    """
    log = load_performance_log()
    entry = {
        "order_id": order_id,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "entry_price": entry_price,
        "entry_date": entry_date,
        "advisor_votes": {
            op["advisor"]: {
                "recommendation": op["recommendation"],
                "confidence": op["confidence"],
            }
            for op in advisor_votes
        },
        "status": "open",
        "exit_price": None,
        "exit_date": None,
        "pnl_pct": None,
        "outcome": None,
    }
    log.append(entry)
    save_performance_log(log)
    logger.debug(f"Performance entry written: {symbol} order {order_id}")


def sync_closed_trades() -> int:
    """
    Phase 2: check Alpaca for positions that were closed since last sync.
    Updates matching open entries with exit price, P&L, and outcome.
    Returns count of entries newly marked closed.
    """
    log = load_performance_log()
    open_entries = [e for e in log if e["status"] == "open"]
    if not open_entries:
        return 0

    try:
        positions = get_positions()
    except Exception as e:
        logger.error(f"sync_closed_trades: failed to fetch positions: {e}")
        return 0

    open_symbols = {p["symbol"] for p in positions}

    by_symbol = defaultdict(list)
    for entry in open_entries:
        by_symbol[entry["symbol"]].append(entry)
    for entries in by_symbol.values():
        entries.sort(key=lambda e: e["entry_date"])

    newly_closed = 0
    for symbol, entries in by_symbol.items():
        if symbol in open_symbols:
            continue

        fills = _fetch_sell_fills(symbol, entries[0]["entry_date"])
        for i, entry in enumerate(entries):
            if i >= len(fills):
                break
            exit_price, exit_date = fills[i]
            entry["exit_price"] = exit_price
            entry["exit_date"] = exit_date
            entry["pnl_pct"] = round(
                (exit_price - entry["entry_price"]) / entry["entry_price"] * 100, 2
            )
            entry["outcome"] = "win" if entry["pnl_pct"] > 0 else "loss"
            entry["status"] = "closed"
            newly_closed += 1
            sign = "+" if entry["pnl_pct"] > 0 else ""
            logger.info(
                f"Synced closed trade: {symbol} {entry['outcome'].upper()} "
                f"{sign}{entry['pnl_pct']}%"
            )

    save_performance_log(log)
    return newly_closed


def _fetch_sell_fills(symbol: str, after_date: str) -> list:
    """
    Fetch sell fill activities for symbol from Alpaca after after_date.
    Returns list of (exit_price, exit_date) tuples sorted by time ascending.
    """
    try:
        resp = requests.get(
            f"{ALPACA_BASE_URL}/v2/account/activities/FILL",
            headers=ALPACA_HEADERS,
            params={
                "after": f"{after_date}T00:00:00Z",
                "direction": "asc",
                "page_size": 100,
            },
        )
        resp.raise_for_status()
        activities = resp.json()
        return [
            (float(act["price"]), act["transaction_time"][:10])
            for act in activities
            if act.get("symbol") == symbol and act.get("side") == "sell"
        ]
    except Exception as e:
        logger.warning(f"_fetch_sell_fills({symbol}): {e}")
        return []
