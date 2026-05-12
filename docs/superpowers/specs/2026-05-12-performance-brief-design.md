# Performance Brief — Design Spec
Date: 2026-05-12

## Goal

Give the Head Advisor a performance brief at every decision point so it can reason about its own track record. The brief is injected into the prompt — the system prompt itself does not change. Advisors other than the Head Advisor are not modified.

## What We Are Not Building

- No changes to specialist advisor prompts or logic
- No per-stock contextual memory (future enhancement)
- No real-time trade close detection (daily sync is sufficient)
- No monthly cadence (daily + weekly covers the signal)

---

## Architecture

```
Pre-market loop
  → run_form4_prep()           (existing)
  → run_performance_prep()     (new)
      → sync_closed_trades()   fetches Alpaca closes, updates performance_log.json
      → build_performance_brief()  builds brief text, caches to performance_brief_cache.json

Analysis cycle
  → advisors analyze           (unchanged)
  → head_advisor.decide(
        ...,
        performance_brief=self.performance_brief   (new param)
    )
  → _execute_decision()        (also saves advisor votes to performance_log.json)
```

---

## Data Model

### `performance_log.json`

Array of trade entries. Each entry is written in two phases.

**Phase 1 — at execution:**
```json
{
  "order_id": "46df3fff-...",
  "symbol": "MU",
  "side": "buy",
  "qty": 9,
  "entry_price": 417.58,
  "entry_date": "2026-04-13",
  "advisor_votes": {
    "📈 Momentum Analyst":     {"recommendation": "BUY",  "confidence": 85},
    "📰 Sentiment Analyst":    {"recommendation": "PASS", "confidence": 40},
    "🛡️ Risk Manager":         {"recommendation": "BUY",  "confidence": 75},
    "🏗️ Portfolio Strategist": {"recommendation": "BUY",  "confidence": 70}
  },
  "status": "open",
  "exit_price": null,
  "exit_date": null,
  "pnl_pct": null,
  "outcome": null
}
```

**Phase 2 — after Alpaca sync:**
```json
{
  "...": "same fields above",
  "status": "closed",
  "exit_price": 438.20,
  "exit_date": "2026-04-15",
  "pnl_pct": 4.93,
  "outcome": "win"
}
```

`outcome` is `"win"` when `pnl_pct > 0`, `"loss"` otherwise.

### `performance_brief_cache.json`

```json
{
  "date": "2026-05-12",
  "type": "weekly",
  "brief_text": "..."
}
```

`type` is `"weekly"` on Mondays, `"daily"` all other days. Brief is regenerated each pre-market run; cache avoids rebuilding mid-session.

---

## New Files

### `performance_tracker.py`

Single public function: `sync_closed_trades() -> int`

Logic:
1. Load `performance_log.json` (create empty array if missing)
2. Fetch current open positions from Alpaca (`get_positions()`)
3. For each entry with `status == "open"`:
   - If symbol is NOT in current Alpaca positions → position was closed
   - Fetch sell fill from Alpaca activities API (`activity_type=FILL`, side=sell, symbol match, after `entry_date`)
   - Write `exit_price`, `exit_date`, `pnl_pct`, `outcome`, `status=closed`
4. Save updated log
5. Return count of newly closed trades synced

Edge cases:
- Symbol appears in multiple open log entries (bought twice): match sell fills in chronological order — earliest open entry gets matched to earliest sell fill for that symbol, by `entry_date` ascending
- No sell fill found (position may have been stopped out via bracket order) — use Alpaca order history as fallback, match by symbol + date range after `entry_date`
- Log file missing or corrupt — recreate empty, log warning
- Historical trades in `trades.json` (before this feature) are not backfilled into `performance_log.json` — only trades executed after this feature ships will have advisor votes and be tracked

### `performance_brief.py`

Single public function: `build_performance_brief(today: date) -> str`

Logic:
1. Check `performance_brief_cache.json` — if `date` matches today, return cached `brief_text`
2. Load `performance_log.json`, filter `status == "closed"`
3. Build **Recent section** (every day): last 10 closed trades, sorted by `exit_date` desc
4. If `today.weekday() == 0` (Monday): also build **Patterns section** from last 30 days of closed trades
5. Write cache, return brief text

**Recent section format:**
```
--- Performance Brief (2026-05-12) ---
Recent Trades (last 10 closed):
  ✅ NVDA +5.2%  (4/4 advisors agreed BUY)
  ✅ MSFT +3.1%  (3/4 agreed — Sentiment Analyst dissented)
  ❌ CAG  -2.8%  (3/4 agreed — Risk Manager dissented)
  ...
Track record: 7W / 3L | Avg win: +4.1% | Avg loss: -2.2%
```

**Patterns section format (Mondays only):**
```
--- 30-Day Patterns ---
Advisor combo win rates (min 3 trades to report):
  All 4 agree BUY             → 82% win (11 trades)
  3/4 agree, Sentiment out    → 71% win  (7 trades)
  3/4 agree, Risk Manager out → 38% win  (8 trades) ⚠️
  Momentum + Risk both BUY    → 74% win overall
Notable symbols:
  Best:  NVDA avg +5.2% (3 trades), MSFT avg +3.8% (4 trades)
  Worst: CAG avg -1.9%  (2 trades)
```

If fewer than 5 closed trades exist, brief says: `"Insufficient history — fewer than 5 closed trades recorded."` and skips pattern analysis entirely.

---

## Changes to Existing Files

### `main.py`

1. **`__init__`**: add `self.performance_brief = None`

2. **New method `run_performance_prep()`**:
   ```python
   def run_performance_prep(self):
       synced = sync_closed_trades()
       self.performance_brief = build_performance_brief(datetime.now(self.tz).date())
   ```
   Called in `run_forever()` pre-market, after `run_form4_prep()`. Also called as catch-up if bot starts post-open and `self.performance_brief is None`.

3. **`_execute_decision()`**: after a successful trade, append to `performance_log.json`:
   - Requires passing `opinions` list into `_execute_decision()` — add as parameter
   - Write Phase 1 entry (status=open, advisor_votes from opinions list)

4. **`run_analysis_cycle()`**: pass `self.performance_brief` to `head_advisor.decide()`

### `advisors/head_advisor.py`

1. `decide()` signature: add `performance_brief: str = None`
2. `_build_decision_prompt()`: add `performance_brief` param; if not None, inject as a block before `--- Your Decision ---`

---

## Brief Cadence

| When | What runs | Brief type |
|------|-----------|------------|
| Pre-market, Tue–Fri | `sync_closed_trades()` + `build_performance_brief()` | daily (Recent only) |
| Pre-market, Monday | `sync_closed_trades()` + `build_performance_brief()` | weekly (Recent + Patterns) |
| Mid-session | brief already cached, no rebuild | — |
| Bot starts post-open | `run_performance_prep()` called as catch-up | daily or weekly per weekday |

---

## Success Criteria

- Head Advisor receives a performance brief on every `decide()` call once at least 1 closed trade exists
- `performance_log.json` accurately reflects advisor votes for all trades going forward
- Brief text is deterministic for a given date (cached, not regenerated per-decision)
- Zero changes to specialist advisor behavior
- Backwards compatible: if `performance_brief` is None, `decide()` behaves identically to today
