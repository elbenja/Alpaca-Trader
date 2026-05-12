# Performance Brief Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject a daily/weekly performance brief (recent trade outcomes + advisor combo win rates) into the Head Advisor's decision prompt so it reasons from its own track record.

**Architecture:** A `performance_tracker.py` module syncs closed Alpaca positions to `performance_log.json` and captures advisor votes at execution time. A `performance_brief.py` module builds a formatted text brief from the log — recent 10 trades daily, plus 30-day advisor combo patterns on Mondays. The brief is generated once pre-market and injected as an optional param into `HeadAdvisor.decide()`.

**Tech Stack:** Python 3, `requests` (Alpaca REST API — same pattern as existing code), `unittest` + `pytest`, `json` (existing storage pattern)

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `config.py` | Modify | Add `PERFORMANCE_LOG_FILE`, `PERFORMANCE_BRIEF_CACHE_FILE` constants |
| `performance_tracker.py` | Create | Load/save log, capture votes at execution, sync closes from Alpaca |
| `performance_brief.py` | Create | Build Recent + Patterns text brief from log, cache to disk |
| `main.py` | Modify | Add `run_performance_prep()`, save votes in `_execute_decision()`, pass brief to Head Advisor |
| `advisors/head_advisor.py` | Modify | Accept `performance_brief` param, inject into decision prompt |
| `tests/__init__.py` | Create | Empty — marks tests/ as a package |
| `tests/test_performance_tracker.py` | Create | Unit tests for tracker functions |
| `tests/test_performance_brief.py` | Create | Unit tests for brief builder |
| `requirements.txt` | Modify | Add `pytest` |

---

## Task 1: Scaffold — config constants, test directory, pytest

**Files:**
- Modify: `config.py`
- Modify: `requirements.txt`
- Create: `tests/__init__.py`

- [ ] **Step 1: Add constants to `config.py`**

At the bottom of `config.py`, after the `TRADES_FILE` line, add:

```python
PERFORMANCE_LOG_FILE = os.path.join(OUTPUT_DIR, "performance_log.json")
PERFORMANCE_BRIEF_CACHE_FILE = os.path.join(OUTPUT_DIR, "performance_brief_cache.json")
```

- [ ] **Step 2: Add pytest to `requirements.txt`**

Add this line to `requirements.txt`:
```
pytest>=7.0.0
```

- [ ] **Step 3: Create `tests/__init__.py`**

Create an empty file at `tests/__init__.py`.

- [ ] **Step 4: Install pytest**

```bash
cd "/Users/benjaminsaravia/Library/CloudStorage/GoogleDrive-elbenja@gmail.com/My Drive/Projects/Alpaca-Trader"
source venv/bin/activate && pip install pytest
```

Expected: `Successfully installed pytest-...`

- [ ] **Step 5: Verify config imports work**

```bash
source venv/bin/activate && python -c "from config import PERFORMANCE_LOG_FILE, PERFORMANCE_BRIEF_CACHE_FILE; print(PERFORMANCE_LOG_FILE)"
```

Expected: prints the full path ending in `performance_log.json`

- [ ] **Step 6: Commit**

```bash
git add config.py requirements.txt tests/__init__.py
git commit -m "feat: add performance brief file path constants and test scaffold"
```

---

## Task 2: `performance_tracker.py` — load, save, append (TDD)

**Files:**
- Create: `performance_tracker.py`
- Create: `tests/test_performance_tracker.py`

- [ ] **Step 1: Write failing tests for load/save/append**

Create `tests/test_performance_tracker.py`:

```python
import json
import os
import tempfile
import unittest
from unittest.mock import patch


class TestLoadPerformanceLog(unittest.TestCase):
    def test_returns_empty_list_when_file_missing(self):
        with patch("performance_tracker.PERFORMANCE_LOG_FILE", "/nonexistent/path.json"):
            from performance_tracker import load_performance_log
            result = load_performance_log()
        self.assertEqual(result, [])

    def test_returns_empty_list_on_corrupt_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json{{{")
            tmp = f.name
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp):
                from performance_tracker import load_performance_log
                result = load_performance_log()
            self.assertEqual(result, [])
        finally:
            os.unlink(tmp)


class TestSaveLoadRoundtrip(unittest.TestCase):
    def test_save_and_load_returns_same_data(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp = f.name
        try:
            sample = [{"order_id": "abc", "symbol": "NVDA", "status": "open"}]
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp):
                from performance_tracker import save_performance_log, load_performance_log
                save_performance_log(sample)
                result = load_performance_log()
            self.assertEqual(result, sample)
        finally:
            os.unlink(tmp)


class TestAppendPerformanceEntry(unittest.TestCase):
    def test_appends_phase1_entry_with_correct_fields(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([], f)
            tmp = f.name
        try:
            opinions = [
                {"advisor": "📈 Momentum Analyst", "recommendation": "BUY", "confidence": 80},
                {"advisor": "🛡️ Risk Manager", "recommendation": "PASS", "confidence": 60},
            ]
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp):
                from performance_tracker import append_performance_entry, load_performance_log
                append_performance_entry(
                    order_id="ord-123",
                    symbol="NVDA",
                    side="buy",
                    qty=5,
                    entry_price=450.00,
                    entry_date="2026-05-12",
                    advisor_votes=opinions,
                )
                log = load_performance_log()
            self.assertEqual(len(log), 1)
            entry = log[0]
            self.assertEqual(entry["order_id"], "ord-123")
            self.assertEqual(entry["symbol"], "NVDA")
            self.assertEqual(entry["status"], "open")
            self.assertIsNone(entry["exit_price"])
            self.assertIsNone(entry["outcome"])
            self.assertIn("📈 Momentum Analyst", entry["advisor_votes"])
            self.assertEqual(
                entry["advisor_votes"]["📈 Momentum Analyst"]["recommendation"], "BUY"
            )
            self.assertEqual(
                entry["advisor_votes"]["🛡️ Risk Manager"]["recommendation"], "PASS"
            )
        finally:
            os.unlink(tmp)

    def test_appends_to_existing_entries(self):
        existing = [{"order_id": "old-1", "symbol": "MSFT", "status": "closed"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(existing, f)
            tmp = f.name
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp):
                from performance_tracker import append_performance_entry, load_performance_log
                append_performance_entry(
                    order_id="ord-2",
                    symbol="AAPL",
                    side="buy",
                    qty=3,
                    entry_price=200.0,
                    entry_date="2026-05-12",
                    advisor_votes=[],
                )
                log = load_performance_log()
            self.assertEqual(len(log), 2)
            self.assertEqual(log[0]["order_id"], "old-1")
            self.assertEqual(log[1]["order_id"], "ord-2")
        finally:
            os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd "/Users/benjaminsaravia/Library/CloudStorage/GoogleDrive-elbenja@gmail.com/My Drive/Projects/Alpaca-Trader"
source venv/bin/activate && python -m pytest tests/test_performance_tracker.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'performance_tracker'`

- [ ] **Step 3: Create `performance_tracker.py` with load/save/append**

Create `performance_tracker.py`:

```python
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
```

- [ ] **Step 4: Run load/save/append tests**

```bash
source venv/bin/activate && python -m pytest tests/test_performance_tracker.py::TestLoadPerformanceLog tests/test_performance_tracker.py::TestSaveLoadRoundtrip tests/test_performance_tracker.py::TestAppendPerformanceEntry -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add performance_tracker.py tests/test_performance_tracker.py requirements.txt
git commit -m "feat: add performance_tracker load/save/append functions"
```

---

## Task 3: `performance_tracker.py` — sync_closed_trades (TDD)

**Files:**
- Modify: `tests/test_performance_tracker.py` (add sync tests)
- No changes to `performance_tracker.py` — sync is already written; these tests verify it

- [ ] **Step 1: Add sync tests to `tests/test_performance_tracker.py`**

Append this class to the end of `tests/test_performance_tracker.py` (before `if __name__ == "__main__":`):

```python
class TestSyncClosedTrades(unittest.TestCase):
    def test_returns_zero_when_log_is_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([], f)
            tmp = f.name
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp):
                from performance_tracker import sync_closed_trades
                result = sync_closed_trades()
            self.assertEqual(result, 0)
        finally:
            os.unlink(tmp)

    def test_does_not_close_entry_when_position_still_open(self):
        entry = {
            "order_id": "ord-1", "symbol": "NVDA", "side": "buy",
            "qty": 5, "entry_price": 450.0, "entry_date": "2026-05-01",
            "advisor_votes": {}, "status": "open",
            "exit_price": None, "exit_date": None, "pnl_pct": None, "outcome": None,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([entry], f)
            tmp = f.name
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp), \
                 patch("performance_tracker.get_positions", return_value=[{"symbol": "NVDA"}]):
                from performance_tracker import sync_closed_trades, load_performance_log
                result = sync_closed_trades()
                log = load_performance_log()
            self.assertEqual(result, 0)
            self.assertEqual(log[0]["status"], "open")
        finally:
            os.unlink(tmp)

    def test_closes_entry_and_computes_win(self):
        entry = {
            "order_id": "ord-2", "symbol": "MSFT", "side": "buy",
            "qty": 10, "entry_price": 380.0, "entry_date": "2026-04-13",
            "advisor_votes": {}, "status": "open",
            "exit_price": None, "exit_date": None, "pnl_pct": None, "outcome": None,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([entry], f)
            tmp = f.name
        from unittest.mock import MagicMock
        fill_resp = MagicMock()
        fill_resp.raise_for_status = MagicMock()
        fill_resp.json.return_value = [
            {
                "symbol": "MSFT", "side": "sell",
                "price": "399.0",
                "transaction_time": "2026-04-15T14:00:00Z",
            }
        ]
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp), \
                 patch("performance_tracker.get_positions", return_value=[]), \
                 patch("performance_tracker.requests.get", return_value=fill_resp):
                from performance_tracker import sync_closed_trades, load_performance_log
                result = sync_closed_trades()
                log = load_performance_log()
            self.assertEqual(result, 1)
            closed = log[0]
            self.assertEqual(closed["status"], "closed")
            self.assertAlmostEqual(closed["exit_price"], 399.0)
            self.assertEqual(closed["exit_date"], "2026-04-15")
            self.assertAlmostEqual(closed["pnl_pct"], 5.0, places=1)
            self.assertEqual(closed["outcome"], "win")
        finally:
            os.unlink(tmp)

    def test_closes_entry_and_computes_loss(self):
        entry = {
            "order_id": "ord-3", "symbol": "AMD", "side": "buy",
            "qty": 8, "entry_price": 200.0, "entry_date": "2026-04-20",
            "advisor_votes": {}, "status": "open",
            "exit_price": None, "exit_date": None, "pnl_pct": None, "outcome": None,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([entry], f)
            tmp = f.name
        from unittest.mock import MagicMock
        fill_resp = MagicMock()
        fill_resp.raise_for_status = MagicMock()
        fill_resp.json.return_value = [
            {
                "symbol": "AMD", "side": "sell",
                "price": "196.0",
                "transaction_time": "2026-04-21T10:00:00Z",
            }
        ]
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp), \
                 patch("performance_tracker.get_positions", return_value=[]), \
                 patch("performance_tracker.requests.get", return_value=fill_resp):
                from performance_tracker import sync_closed_trades, load_performance_log
                result = sync_closed_trades()
                log = load_performance_log()
            self.assertEqual(result, 1)
            self.assertEqual(log[0]["outcome"], "loss")
            self.assertAlmostEqual(log[0]["pnl_pct"], -2.0, places=1)
        finally:
            os.unlink(tmp)
```

- [ ] **Step 2: Run all tracker tests**

```bash
source venv/bin/activate && python -m pytest tests/test_performance_tracker.py -v
```

Expected: `9 passed`

- [ ] **Step 3: Commit**

```bash
git add tests/test_performance_tracker.py
git commit -m "test: add sync_closed_trades tests for performance tracker"
```

---

## Task 4: `performance_brief.py` — build brief and cache (TDD)

**Files:**
- Create: `performance_brief.py`
- Create: `tests/test_performance_brief.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_performance_brief.py`:

```python
import json
import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

SAMPLE_CLOSED = [
    {
        "order_id": f"ord-{i}",
        "symbol": sym,
        "side": "buy",
        "qty": 10,
        "entry_price": 100.0,
        "entry_date": "2026-04-13",
        "exit_date": f"2026-04-{13 + i}",
        "exit_price": price,
        "pnl_pct": round((price - 100.0) / 100.0 * 100, 2),
        "outcome": "win" if price > 100 else "loss",
        "status": "closed",
        "advisor_votes": {
            "📈 Momentum Analyst":     {"recommendation": "BUY",  "confidence": 80},
            "📰 Sentiment Analyst":    {"recommendation": "PASS", "confidence": 40},
            "🛡️ Risk Manager":         {"recommendation": "BUY",  "confidence": 75},
            "🏗️ Portfolio Strategist": {"recommendation": "BUY",  "confidence": 70},
        },
    }
    for i, (sym, price) in enumerate([
        ("NVDA", 105.0), ("MSFT", 103.0), ("AAPL", 98.0),
        ("AMZN", 106.0), ("AMD",  97.0),
    ])
]


class TestBuildPerformanceBrief(unittest.TestCase):
    def setUp(self):
        self.cache_file = tempfile.mktemp(suffix=".json")

    def tearDown(self):
        if os.path.exists(self.cache_file):
            os.unlink(self.cache_file)

    def test_insufficient_history_when_fewer_than_5_trades(self):
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED[:3]):
            from performance_brief import build_performance_brief
            result = build_performance_brief(date(2026, 5, 12))
        self.assertIn("Insufficient history", result)
        self.assertNotIn("Recent Trades", result)

    def test_recent_section_present_on_non_monday(self):
        tuesday = date(2026, 5, 12)
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED):
            from performance_brief import build_performance_brief
            result = build_performance_brief(tuesday)
        self.assertIn("Performance Brief (2026-05-12)", result)
        self.assertIn("Recent Trades", result)
        self.assertIn("Track record:", result)
        self.assertIn("3W / 2L", result)

    def test_patterns_section_absent_on_non_monday(self):
        tuesday = date(2026, 5, 12)
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED):
            from performance_brief import build_performance_brief
            result = build_performance_brief(tuesday)
        self.assertNotIn("30-Day Patterns", result)

    def test_patterns_section_present_on_monday(self):
        monday = date(2026, 5, 11)
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED):
            from performance_brief import build_performance_brief
            result = build_performance_brief(monday)
        self.assertIn("30-Day Patterns", result)
        self.assertIn("Sentiment Analyst out", result)

    def test_caching_avoids_second_log_load(self):
        tuesday = date(2026, 5, 12)
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED) as mock_load:
            from performance_brief import build_performance_brief
            first = build_performance_brief(tuesday)
            second = build_performance_brief(tuesday)
        self.assertEqual(first, second)
        self.assertEqual(mock_load.call_count, 1)

    def test_brief_shows_win_loss_symbols(self):
        tuesday = date(2026, 5, 12)
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED):
            from performance_brief import build_performance_brief
            result = build_performance_brief(tuesday)
        self.assertIn("NVDA", result)
        self.assertIn("+5.0%", result)
        self.assertIn("AAPL", result)
        self.assertIn("-2.0%", result)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
source venv/bin/activate && python -m pytest tests/test_performance_brief.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'performance_brief'`

- [ ] **Step 3: Create `performance_brief.py`**

Create `performance_brief.py`:

```python
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
```

- [ ] **Step 4: Run brief tests**

```bash
source venv/bin/activate && python -m pytest tests/test_performance_brief.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Run full test suite**

```bash
source venv/bin/activate && python -m pytest tests/ -v
```

Expected: `15 passed`

- [ ] **Step 6: Commit**

```bash
git add performance_brief.py tests/test_performance_brief.py
git commit -m "feat: add performance_brief builder with daily and weekly sections"
```

---

## Task 5: Wire up `main.py`

**Files:**
- Modify: `main.py`

- [ ] **Step 1: Add imports at the top of `main.py`**

After the existing imports block (after `from advisors.form4_analyst import Form4Analyst`), add:

```python
from performance_tracker import sync_closed_trades, append_performance_entry
from performance_brief import build_performance_brief
```

- [ ] **Step 2: Add `self.performance_brief = None` to `__init__`**

In `WealthAdvisorBot.__init__`, after `self.first_post_open_done_date = None`, add:

```python
self.performance_brief = None     # Built pre-market, injected into Head Advisor
```

- [ ] **Step 3: Add `run_performance_prep()` method**

Add this method to `WealthAdvisorBot`, after `run_form4_prep()`:

```python
def run_performance_prep(self):
    """Pre-market: sync closed trades from Alpaca and build today's performance brief."""
    today = datetime.now(self.tz).date()
    logger.info("=" * 70)
    logger.info(f"📊 PERFORMANCE PREP — {today.isoformat()}")
    logger.info("=" * 70)
    try:
        synced = sync_closed_trades()
        if synced:
            logger.info(f"   Synced {synced} newly closed trade(s)")
        self.performance_brief = build_performance_brief(today)
        logger.info("   Performance brief ready")
    except Exception as e:
        logger.error(f"❌ Performance prep failed: {e}", exc_info=True)
        self.performance_brief = None
```

- [ ] **Step 4: Modify `_execute_decision()` to accept and save `opinions`**

Change the signature of `_execute_decision` from:
```python
def _execute_decision(self, decision: dict, stock_data: dict):
```
to:
```python
def _execute_decision(self, decision: dict, stock_data: dict, opinions: list = None):
```

Then, inside `_execute_decision`, after `if result.get("status") == "success":` and the existing `logger.info(...)` line, add:

```python
        if opinions:
            append_performance_entry(
                order_id=result["order_id"],
                symbol=symbol,
                side=side,
                qty=shares,
                entry_price=entry_price,
                entry_date=datetime.now().date().isoformat(),
                advisor_votes=opinions,
            )
```

The full updated `_execute_decision` method should read:

```python
def _execute_decision(self, decision: dict, stock_data: dict, opinions: list = None):
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
        if opinions:
            append_performance_entry(
                order_id=result["order_id"],
                symbol=symbol,
                side=side,
                qty=shares,
                entry_price=entry_price,
                entry_date=datetime.now().date().isoformat(),
                advisor_votes=opinions,
            )
    else:
        logger.error(f"❌ Trade failed: {result.get('reason')}")
```

- [ ] **Step 5: Pass `opinions` and `performance_brief` in `run_analysis_cycle()`**

In `run_analysis_cycle()`, find the two `self._execute_decision(decision, candidate)` calls and change both to:

```python
self._execute_decision(decision, candidate, opinions)
```

Also find the `self.head_advisor.decide(...)` call and change it from:

```python
decision = self.head_advisor.decide(
    candidate, opinions, portfolio_context, form4_context=form4_ctx
)
```

to:

```python
decision = self.head_advisor.decide(
    candidate, opinions, portfolio_context,
    form4_context=form4_ctx,
    performance_brief=self.performance_brief,
)
```

- [ ] **Step 6: Call `run_performance_prep()` in `run_forever()`**

In `run_forever()`, in the pre-market block, add the call after `run_form4_prep()`:

```python
if self.is_pre_market():
    self.run_form4_prep()
    self.run_performance_prep()
```

Also add a catch-up call in the market-open block. After the existing catch-up block:

```python
if self.form4_prep_date != today:
    logger.info("🕵️ Catching up Form 4 prep (bot started post-open)")
    self.run_form4_prep()
```

Add:

```python
if self.performance_brief is None:
    self.run_performance_prep()
```

- [ ] **Step 7: Verify the file parses cleanly**

```bash
source venv/bin/activate && python -c "import main; print('OK')"
```

Expected: `OK` (no import errors)

- [ ] **Step 8: Run full test suite**

```bash
source venv/bin/activate && python -m pytest tests/ -v
```

Expected: `15 passed`

- [ ] **Step 9: Commit**

```bash
git add main.py
git commit -m "feat: wire performance brief and vote capture into main trading loop"
```

---

## Task 6: Modify `advisors/head_advisor.py` — inject brief into prompt

**Files:**
- Modify: `advisors/head_advisor.py`

- [ ] **Step 1: Update `decide()` signature**

Change the `decide()` method signature from:

```python
def decide(
    self,
    stock_data: dict,
    advisor_opinions: list,
    portfolio_context: dict,
    form4_context: dict = None,
) -> dict:
```

to:

```python
def decide(
    self,
    stock_data: dict,
    advisor_opinions: list,
    portfolio_context: dict,
    form4_context: dict = None,
    performance_brief: str = None,
) -> dict:
```

- [ ] **Step 2: Pass `performance_brief` through to prompt builder**

Inside `decide()`, change:

```python
user_message = self._build_decision_prompt(
    stock_data, advisor_opinions, portfolio_context, form4_context
)
```

to:

```python
user_message = self._build_decision_prompt(
    stock_data, advisor_opinions, portfolio_context, form4_context, performance_brief
)
```

- [ ] **Step 3: Update `_build_decision_prompt()` signature and inject brief**

Change the signature from:

```python
def _build_decision_prompt(
    self,
    stock_data: dict,
    advisor_opinions: list,
    portfolio_context: dict,
    form4_context: dict = None,
) -> str:
```

to:

```python
def _build_decision_prompt(
    self,
    stock_data: dict,
    advisor_opinions: list,
    portfolio_context: dict,
    form4_context: dict = None,
    performance_brief: str = None,
) -> str:
```

Then, inside `_build_decision_prompt()`, add this variable just before the `return f"""` statement:

```python
perf_block = f"\n{performance_brief}\n" if performance_brief else ""
```

And insert `{perf_block}` into the return string just before `--- Your Decision ---`:

```python
    return f"""
TRADE DECISION REQUIRED: {stock_data['symbol']}

--- Stock Data ---
Price: ${price:.2f}
RSI: {stock_data['rsi']:.1f}
Momentum: {stock_data['momentum']:.2f}%
Volume: {stock_data['volume']:,.0f}

--- Advisor Opinions ---
{opinions_text}
{form4_block}
--- Position Sizing Parameters ---
Buying Power Available: ${buying_power:,.2f}
Portfolio Equity: ${equity:,.2f}

Max Shares by Buying Power: {max_shares_by_power} shares (${max_shares_by_power * price:,.2f})
Max Shares by Concentration (40% limit): {max_shares_by_concentration} shares (${max_shares_by_concentration * price:,.2f})
Max Shares by Risk (7.5% per trade): {max_shares_by_risk} shares (${max_shares_by_risk * price:,.2f})
Suggested Shares (most conservative): {suggested_shares} shares (${position_value:,.2f}, {portfolio_concentration:.1f}% of portfolio)

Suggested Stop Loss (2%): ${stop_loss_price:.2f}
Suggested Take Profit (5%): ${take_profit_price:.2f}
Current Positions: {len(portfolio_context.get('positions', []))}/{portfolio_context.get('max_positions', 10)}
{perf_block}
--- Your Decision ---
Review all advisor opinions and the position sizing constraints.
Make the final BUY, SELL, or PASS decision.
If BUY: use the suggested shares above (or lower if you want to be more conservative).
IMPORTANT: Do NOT exceed the suggested shares — respect the buying power and concentration limits.
"""
```

- [ ] **Step 4: Verify the file parses cleanly**

```bash
source venv/bin/activate && python -c "from advisors.head_advisor import HeadAdvisor; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Smoke-test the full import chain**

```bash
source venv/bin/activate && python -c "
from advisors.head_advisor import HeadAdvisor
from performance_brief import build_performance_brief
from performance_tracker import sync_closed_trades, append_performance_entry
from datetime import date
brief = build_performance_brief(date.today())
print(brief[:80])
"
```

Expected: prints either `--- Performance Brief ---\nInsufficient history...` or the Recent Trades header (depending on whether `performance_log.json` exists yet).

- [ ] **Step 6: Run full test suite one final time**

```bash
source venv/bin/activate && python -m pytest tests/ -v
```

Expected: `15 passed`

- [ ] **Step 7: Final commit**

```bash
git add advisors/head_advisor.py
git commit -m "feat: inject performance brief into Head Advisor decision prompt"
```
