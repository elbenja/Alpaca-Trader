# Prompt: Build `alpaca-trader-claude` from Scratch

## Context

This is a **parallel implementation** of an existing GPT-4o–based trading bot
([`Alpaca-Trader`](../)), rebuilt with the Anthropic SDK to compare cost, token
usage, and decision quality. The new project lives in a sibling folder called
`alpaca-trader-claude/`.

The existing bot:
- Uses `gpt-4o` at temperature 0.3 via OpenAI
- Makes **5 separate API calls per stock per cycle** (4 specialist advisors +
  1 head advisor), with no caching
- Relies on fragile JSON-in-markdown parsing
- Spends ~300 tokens output per advisor call, ×5 = ~1,500 output tokens per stock

The Claude version must be a **drop-in functional equivalent** — same trading
logic, same Alpaca integration, same file outputs — while demonstrating the
token-saving patterns described below.

---

## Model Recommendation

| Task | Model | Why |
|---|---|---|
| Advisor Panel (4 specialist opinions, structured) | `claude-haiku-4-5` | Simple classification × high volume |
| Head Advisor (final decision, position sizing) | `claude-sonnet-4-6` | Nuanced synthesis, math, context awareness |
| Form 4 pre-market analysis (async) | `claude-haiku-4-5` via **Batches API** | Non-realtime, 50% cost reduction |
| Daily summary (async) | `claude-sonnet-4-6` via **Batches API** | Non-realtime, 50% cost reduction |

**Primary model: `claude-sonnet-4-6`** for the main trading loop.
Use `claude-haiku-4-5` wherever the task is a structured classification with no
deep reasoning required.

---

## Token-Saving Architecture

### 1 — Consolidate 4 Advisor Calls → 1 Structured Call

**Old:** 4 separate GPT-4o calls (Momentum + Sentiment + Risk + Portfolio)
each with their own system prompt + full market context.

**New:** 1 Haiku call using `client.messages.parse()` where the system prompt
contains all 4 advisor personas and the output schema returns all 4 opinions
simultaneously.

```python
class AdvisorOpinion(BaseModel):
    recommendation: Literal["BUY", "SELL", "PASS"]
    confidence: int          # 0-100
    reasoning: str           # 1-2 sentences

class AdvisorPanel(BaseModel):
    momentum: AdvisorOpinion
    sentiment: AdvisorOpinion
    risk: AdvisorOpinion
    portfolio: AdvisorOpinion
```

Result: **2 API calls per stock** instead of 5. Same opinions, same data.

### 2 — Prompt Caching on System Prompts

Both the panel system prompt and the head advisor system prompt are large and
never change between stocks in the same cycle. Mark them with
`cache_control: {type: "ephemeral"}`. The system prompt is the same text
repeated for every stock in the same run → cache read after the first stock.

```python
system=[{
    "type": "text",
    "text": PANEL_SYSTEM_PROMPT,
    "cache_control": {"type": "ephemeral"}
}]
```

Do NOT put the current timestamp or stock symbol in the system prompt.
Put all volatile data (price, RSI, positions) in the user message only.

### 3 — Structured Outputs (no fragile JSON parsing)

Use `client.messages.parse()` with Pydantic models for every Claude call.
No more stripping markdown code fences, no more `json.loads()` try/except.
`result.parsed_output` is a typed object with validation built in.

Define output schemas:
- `AdvisorPanel` — for the specialist panel call
- `TradeDecision` — for the head advisor call

### 4 — Effort Parameter

```python
output_config={"effort": "low"}   # Haiku advisor panel — simple classification
output_config={"effort": "medium"} # Sonnet head advisor — balanced reasoning
```

### 5 — Batches API for Async Tasks

Pre-market Form 4 analysis and end-of-day summaries are not time-sensitive.
Submit them as batch requests (50% cost reduction). Poll for results before
the market opens / before logging.

### 6 — Thinking Disabled

No extended thinking is needed for intraday trading decisions.
Explicitly set `thinking={"type": "disabled"}` on all calls to prevent
unexpected token spend.

---

## File Structure

```
alpaca-trader-claude/
├── .env.local                    # Same as original (Alpaca keys + ANTHROPIC_API_KEY)
├── requirements.txt
├── config.py                     # Copy from original, replace OPENAI_* with ANTHROPIC_*
├── main.py                       # Orchestrator (identical logic to original)
├── market_data.py                # Copy unchanged from original
├── trade_executor.py             # Copy unchanged from original
├── performance_tracker.py        # Copy unchanged from original
├── performance_brief.py          # Copy unchanged from original
├── form4_fetcher.py              # Copy unchanged from original
├── daily_summary.py              # Rewrite LLM call → Anthropic Batches
├── advisors/
│   ├── __init__.py
│   ├── base.py                   # Rewrite: Anthropic SDK, prompt caching, .parse()
│   ├── panel.py                  # NEW: consolidated 4-in-1 advisor call (Haiku)
│   ├── head_advisor.py           # Rewrite: Anthropic SDK, Sonnet, .parse()
│   └── form4_analyst.py          # Rewrite: Anthropic Batches (Haiku)
└── summaries/                    # Same output format as original
```

---

## Key Implementation Details

### `config.py` changes

```python
# Replace this:
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o"
OPENAI_TEMPERATURE = 0.3

# With this:
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PANEL_MODEL = "claude-haiku-4-5"       # Specialist advisor panel
HEAD_MODEL = "claude-sonnet-4-6"       # Head advisor final decision
ASYNC_MODEL = "claude-haiku-4-5"       # Batches: Form 4 analysis
SUMMARY_MODEL = "claude-sonnet-4-6"    # Batches: Daily summary
```

### `advisors/base.py` — Anthropic client singleton

```python
import anthropic
from config import ANTHROPIC_API_KEY

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
```

No temperature parameter (Claude does not use it the same way; use `effort` instead).

### `advisors/panel.py` — Consolidated 4-advisor call

System prompt contains all 4 advisor personas separated by headers. The
prompt must be **stable** (no timestamps, no stock names) so it caches across
all stocks in the same cycle.

```python
from pydantic import BaseModel
from typing import Literal
from config import PANEL_MODEL
from advisors.base import client

PANEL_SYSTEM_PROMPT = """You are an AI trading analysis panel. You will analyze
a stock opportunity from four distinct perspectives simultaneously.

## Momentum Analyst
[... existing MomentumAnalyst system prompt ...]

## Sentiment Analyst
[... existing SentimentAnalyst system prompt ...]

## Risk Manager
[... existing RiskManager system prompt ...]

## Portfolio Strategist
[... existing PortfolioStrategist system prompt ...]

For each perspective, produce a structured recommendation.
"""

class AdvisorOpinion(BaseModel):
    recommendation: Literal["BUY", "SELL", "PASS"]
    confidence: int
    reasoning: str

class AdvisorPanel(BaseModel):
    momentum: AdvisorOpinion
    sentiment: AdvisorOpinion
    risk: AdvisorOpinion
    portfolio: AdvisorOpinion

def run_panel(stock_data: dict, portfolio_context: dict) -> list[dict]:
    """Run all 4 advisors in a single cached Haiku call."""
    response = client.messages.parse(
        model=PANEL_MODEL,
        max_tokens=512,
        thinking={"type": "disabled"},
        output_config={"effort": "low"},
        system=[{
            "type": "text",
            "text": PANEL_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": _build_user_message(stock_data, portfolio_context)}],
        output_format=AdvisorPanel,
    )
    panel: AdvisorPanel = response.parsed_output

    # Convert to same format as original advisor list
    return [
        {**panel.momentum.model_dump(),  "advisor": "📈 Momentum Analyst"},
        {**panel.sentiment.model_dump(), "advisor": "📰 Sentiment Analyst"},
        {**panel.risk.model_dump(),      "advisor": "🛡️ Risk Manager"},
        {**panel.portfolio.model_dump(), "advisor": "🏗️ Portfolio Strategist"},
    ]
```

The `run_panel()` return value is a drop-in replacement for the `opinions` list
that `HeadAdvisor.decide()` already accepts — no changes needed to `main.py`.

### `advisors/head_advisor.py` — Sonnet with structured output

```python
from pydantic import BaseModel
from typing import Literal
from config import HEAD_MODEL
from advisors.base import client

class TradeDecision(BaseModel):
    decision: Literal["BUY", "SELL", "PASS"]
    confidence: int
    shares: int
    stop_loss: float
    take_profit: float
    reasoning: str

HEAD_SYSTEM_PROMPT = """[... existing HeadAdvisor SYSTEM_PROMPT unchanged ...]"""

class HeadAdvisor:
    def decide(self, stock_data, advisor_opinions, portfolio_context,
               form4_context=None, performance_brief=None) -> dict:

        response = client.messages.parse(
            model=HEAD_MODEL,
            max_tokens=256,
            thinking={"type": "disabled"},
            output_config={"effort": "medium"},
            system=[{
                "type": "text",
                "text": HEAD_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": self._build_decision_prompt(...)}],
            output_format=TradeDecision,
        )

        result = response.parsed_output.model_dump()
        result["symbol"] = stock_data["symbol"]
        return result
```

### `advisors/form4_analyst.py` — Batches API

Form 4 analysis runs pre-market and is inherently async. Submit as a batch,
poll until complete (with a timeout), and fall back to an empty briefing if it
takes too long.

```python
import time
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

def generate_briefing_async(buys: list, now) -> dict:
    """Submit Form 4 analysis as a batch request (50% cheaper)."""
    batch = client.messages.batches.create(requests=[
        Request(
            custom_id="form4-briefing",
            params=MessageCreateParamsNonStreaming(
                model=ASYNC_MODEL,
                max_tokens=1024,
                system=FORM4_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_form4_prompt(buys, now)}],
            )
        )
    ])

    # Poll (pre-market window is ~30 min, give it 10 min max)
    deadline = time.time() + 600
    while time.time() < deadline:
        status = client.messages.batches.retrieve(batch.id)
        if status.processing_status == "ended":
            break
        time.sleep(30)

    # Parse results
    for result in client.messages.batches.results(batch.id):
        if result.result.type == "succeeded":
            return _parse_briefing(result.result.message)

    return _empty_briefing("Batch timed out or failed")
```

### `daily_summary.py` — Batches API

Same pattern as Form 4. Daily summary runs at market close when there is no
latency requirement. Submit as batch at 4:00 PM, results arrive within 1 hour.

---

## What to Copy Unchanged

These files have **no LLM calls** and are identical between both versions.
Copy them verbatim:

- `market_data.py`
- `trade_executor.py`
- `performance_tracker.py`
- `performance_brief.py`
- `form4_fetcher.py`
- `config.py` (except the API key section above)
- All advisor system prompt text (move to the new panel/head files)

---

## `.env.local` additions

```
ANTHROPIC_API_KEY=sk-ant-...
# Keep existing Alpaca keys unchanged
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
```

---

## `requirements.txt`

```
anthropic>=0.92.0
pydantic>=2.0.0
alpaca-py>=0.8.0
requests>=2.31.0
pytz>=2023.3
python-dotenv>=1.0.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
pytest>=7.0.0
```

---

## Comparison Metrics to Log

Add these to the trading loop log so you can compare both versions later:

```python
# After each cycle, log:
logger.info(f"TOKENS | input={usage.input_tokens} "
            f"cached={usage.cache_read_input_tokens} "
            f"output={usage.output_tokens}")
```

Track per-cycle:
- Total input tokens
- Cache-read tokens (target: > 60% of input after the first stock)
- Total output tokens
- Number of API calls (target: 2 per stock vs 5 in original)
- Wall-clock time per cycle

---

## Gotchas / Notes

1. **`client.messages.parse()` vs `client.messages.create()`** — Use `.parse()`
   for structured outputs. It validates automatically and raises if the model
   returns invalid JSON. No need for `json.loads()` or markdown stripping.

2. **Cache invalidation** — The panel system prompt must stay byte-identical
   across all stocks in a cycle. Do NOT interpolate the stock symbol or any
   timestamps into the system prompt. All volatile data goes in the user
   message only.

3. **Batch polling in pre-market** — The Form 4 batch is submitted when the
   bot wakes up in pre-market (~8:30–9:00 AM ET). Give it a 10-minute timeout
   and fall back gracefully. Do not block market open on it.

4. **No temperature parameter** — The Claude API does not use `temperature`
   the same way. Use the `effort` parameter instead. `effort: "low"` for the
   panel call, `effort: "medium"` for the head advisor.

5. **Advisor name compatibility** — The `opinions` list passed to
   `HeadAdvisor.decide()` must still contain `{"advisor": "...", "recommendation":
   ..., "confidence": ..., "reasoning": ...}` dicts. The panel call returns
   exactly this format, so `main.py` and `HeadAdvisor` require zero changes.

6. **`stop_reason: "refusal"`** — Handle this in `HeadAdvisor.decide()`:
   fall back to `PASS` with `confidence=0`.
