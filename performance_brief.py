"""
Performance Brief — Builds Head Advisor context from trade history.
Daily: last 10 closed trades. Monday: adds 30-day advisor combo patterns.
"""

import json
import logging
from datetime import date, timedelta
from performance_tracker import load_performance_log
from config import PERFORMANCE_BRIEF_CACHE_FILE

logger = logging.getLogger(__name__)


def build_performance_brief(today: date) -> str:
    """
    Build (or load cached) performance brief for the Head Advisor.
    Monday: includes 30-day advisor combo patterns. Other days: recent trades only.
    """
    cache = _load_cache()
    if cache and cache.get("date") == today.isoformat():
        return cache["brief_text"]

    log = load_performance_log()
    closed = [e for e in log if e["status"] == "closed"]

    if len(closed) < 5:
        brief = (
            "--- Performance Brief ---\n"
            "Insufficient history — fewer than 5 closed trades recorded."
        )
        _save_cache(today, "daily", brief)
        return brief

    recent = sorted(closed, key=lambda e: e["exit_date"], reverse=True)[:10]
    brief = _build_recent_section(recent, today)

    if today.weekday() == 0:  # Monday
        cutoff = (today - timedelta(days=30)).isoformat()
        monthly = [e for e in closed if e.get("exit_date", "") >= cutoff]
        if len(monthly) >= 3:
            brief += "\n" + _build_patterns_section(monthly)

    _save_cache(today, "weekly" if today.weekday() == 0 else "daily", brief)
    return brief


def _build_recent_section(trades: list, today: date) -> str:
    lines = [f"--- Performance Brief ({today.isoformat()}) ---",
             "Recent Trades (last 10 closed):"]

    for t in trades:
        icon = "✅" if t["outcome"] == "win" else "❌"
        votes = t.get("advisor_votes", {})
        buy_count = sum(1 for v in votes.values() if v["recommendation"] == "BUY")
        total = len(votes)
        dissenters = [_short_name(n) for n, v in votes.items() if v["recommendation"] != "BUY"]

        if not votes:
            vote_str = "(no advisor data)"
        elif dissenters:
            vote_str = f"({buy_count}/{total} agreed — {dissenters[0]} dissented)"
        else:
            vote_str = f"({buy_count}/{total} advisors agreed BUY)"

        pnl = t["pnl_pct"]
        sign = "+" if pnl > 0 else ""
        lines.append(f"  {icon} {t['symbol']:6} {sign}{pnl:.1f}%  {vote_str}")

    wins = [t for t in trades if t["outcome"] == "win"]
    losses = [t for t in trades if t["outcome"] == "loss"]
    avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0.0
    avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0.0
    lines.append(
        f"Track record: {len(wins)}W / {len(losses)}L | "
        f"Avg win: +{avg_win:.1f}% | Avg loss: {avg_loss:.1f}%"
    )
    return "\n".join(lines)


def _build_patterns_section(trades: list) -> str:
    lines = ["--- 30-Day Patterns ---",
             "Advisor combo win rates (min 3 trades to report):"]

    combos = {}
    for t in trades:
        votes = t.get("advisor_votes", {})
        if not votes:
            continue
        dissenters = sorted(n for n, v in votes.items() if v["recommendation"] != "BUY")
        sig = "all_agree" if not dissenters else "no_" + "_".join(_short_name(d) for d in dissenters)
        if sig not in combos:
            combos[sig] = {"wins": 0, "total": 0, "label": _combo_label(votes)}
        combos[sig]["total"] += 1
        if t["outcome"] == "win":
            combos[sig]["wins"] += 1

    for sig, data in sorted(combos.items(), key=lambda x: -x[1]["total"]):
        if data["total"] < 3:
            continue
        win_rate = data["wins"] / data["total"] * 100
        flag = " ⚠️" if win_rate < 50 else ""
        lines.append(
            f"  {data['label']:<42} → {win_rate:.0f}% win ({data['total']} trades){flag}"
        )

    symbol_stats: dict = {}
    for t in trades:
        symbol_stats.setdefault(t["symbol"], []).append(t["pnl_pct"])

    symbol_avgs = {s: sum(v) / len(v) for s, v in symbol_stats.items() if len(v) >= 2}
    if symbol_avgs:
        lines.append("Notable symbols:")
        best = sorted(symbol_avgs.items(), key=lambda x: -x[1])[:2]
        worst = sorted(symbol_avgs.items(), key=lambda x: x[1])[:2]
        lines.append(
            "  Best:  " + ", ".join(
                f"{s} avg +{v:.1f}% ({len(symbol_stats[s])} trades)" for s, v in best
            )
        )
        lines.append(
            "  Worst: " + ", ".join(
                f"{s} avg {v:.1f}% ({len(symbol_stats[s])} trades)" for s, v in worst
            )
        )

    return "\n".join(lines)


def _short_name(advisor_name: str) -> str:
    """'📈 Momentum Analyst' → 'Momentum Analyst'"""
    parts = advisor_name.strip().split(" ", 1)
    return parts[1] if len(parts) > 1 else advisor_name


def _combo_label(votes: dict) -> str:
    total = len(votes)
    pass_advisors = [_short_name(n) for n, v in votes.items() if v["recommendation"] != "BUY"]
    if not pass_advisors:
        return f"All {total} agree BUY"
    buy_count = total - len(pass_advisors)
    return f"{buy_count}/{total} agree, {pass_advisors[0]} out"


def _load_cache() -> dict:
    try:
        with open(PERFORMANCE_BRIEF_CACHE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_cache(today: date, brief_type: str, brief_text: str) -> None:
    try:
        with open(PERFORMANCE_BRIEF_CACHE_FILE, "w") as f:
            json.dump(
                {"date": today.isoformat(), "type": brief_type, "brief_text": brief_text},
                f, indent=2,
            )
    except Exception as e:
        logger.warning(f"Failed to save performance brief cache: {e}")
