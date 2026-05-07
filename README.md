# Wealth Advisor Trading Bot 🤖

A multi-agent LLM-powered trading system where 5 GPT-4o advisors collaborate on every trade decision.

## Architecture

```
Main Loop (Hourly)
├── Market Data Collector
├── 📈 Momentum Analyst (RSI, trend analysis)
├── 📰 Sentiment Analyst (market mood, macro)
├── 🛡️ Risk Manager (portfolio risk)
├── 🏗️ Portfolio Strategist (diversification)
└── ⚖️ Head Advisor (final decision)
    └── Trade Executor (bracket orders)

At Market Close:
└── Daily Summary (GPT-4o powered report)
```

## Setup

### 1. Install Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 2. Set Environment Variables

Create a `.env.local` file with your API credentials:

```env
ALPACA_API_KEY=your_alpaca_api_key
ALPACA_SECRET_KEY=your_alpaca_secret_key
OPENAI_API_KEY=your_openai_api_key
```

### 3. Run the Bot

```bash
python3 main.py
```

The bot will:
- Run hourly during market hours (9:30 AM – 4:00 PM ET)
- Analyze momentum candidates
- Get opinions from all 5 advisors
- Execute trades approved by the Head Advisor
- Generate daily summary at market close

## Project Structure

```
Alpaca-Trader/
├── config.py                   # Trading parameters, stock universe, API config
├── main.py                     # Orchestrator (hourly scheduler + loop)
├── market_data.py              # Alpaca data fetching & technical analysis
├── trade_executor.py           # Order placement & position management
├── daily_summary.py            # End-of-day GPT-4o summary
├── advisors/
│   ├── base.py                 # Base advisor class (shared GPT-4o logic)
│   ├── momentum_analyst.py     # Technical analysis specialist
│   ├── sentiment_analyst.py    # Market sentiment specialist
│   ├── risk_manager.py         # Portfolio risk specialist
│   ├── portfolio_strategist.py # Diversification specialist
│   └── head_advisor.py         # Final decision maker
├── alpaca_momentum_bot.py      # Original bot (reference)
└── requirements.txt            # Python dependencies
```

## Configuration

Edit `config.py` to customize:

- **Trading Parameters**: Risk per trade (7.5%), stop loss (2%), take profit (5%)
- **Stock Universe**: 29 tickers (AAPL, MSFT, GOOGL, etc.)
- **Max Positions**: 10 concurrent positions
- **Market Hours**: 9:30 AM – 4:00 PM ET
- **Run Interval**: Hourly

## How It Works (Each Cycle)

1. **Collect Data** — Fetch 15-min bars, positions, account info from Alpaca
2. **Identify Candidates** — Pre-filter for RSI > 55 + positive momentum
3. **Specialist Analysis** — 4 advisors independently analyze each stock
4. **Head Advisor Decision** — Weighs consensus + veto power of Risk Manager
5. **Execute Trades** — Bracket orders with stop loss & take profit
6. **Log Trades** — Saved to `trades.json` for analysis

## At Market Close

Generates a professional end-of-day summary:
- Trades executed and rationale
- Advisor consensus patterns
- Portfolio snapshot
- Risk management actions
- Brief market outlook

Saved to `summaries/YYYY-MM-DD.md`

## Logging

- Real-time logs to console
- Daily logs to `trading_bot.log`
- Trades recorded in `trades.json`
- Summaries in `summaries/` directory

## Cost Estimate

- ~20 GPT-4o calls per hourly run (4 analysts × ~5 candidates)
- ~5 Head Advisor calls per run
- ~1 summary call at market close
- **~$0.15–$0.25 per day** (7 hourly runs)

## Safety Notes

- **Paper Trading**: Uses Alpaca's paper trading account (no real money)
- **Risk Management**: Configurable position sizing, max exposure, stop losses
- **Logging**: All decisions logged for review and debugging
- **Graceful Shutdown**: Press Ctrl+C to stop safely

## Development

To test individual components:

```python
# Test advisors
from advisors.momentum_analyst import MomentumAnalyst
analyst = MomentumAnalyst()
opinion = analyst.analyze(stock_data, portfolio_context)

# Test trade execution
from trade_executor import TradeExecutor
executor = TradeExecutor()
result = executor.execute_trade("AAPL", 50, "buy", 150.00, 147.00, 157.50)

# Test daily summary
from daily_summary import run_daily_summary
run_daily_summary(portfolio_snapshot)
```

## License

Proprietary — Use for personal trading only.
