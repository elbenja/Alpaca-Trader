"""
Wealth Advisor Bot — Configuration
All trading parameters, API config, and stock universe in one place.
"""

import os
from datetime import time
from dotenv import load_dotenv

# Load environment variables from .env.local
load_dotenv(".env.local")

# =============================================================================
# API Configuration
# =============================================================================

# Alpaca (Paper Trading)
ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = "https://paper-api.alpaca.markets"
ALPACA_DATA_URL = "https://data.alpaca.markets"
ALPACA_HEADERS = {
    "APCA-API-KEY-ID": ALPACA_API_KEY,
    "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
}

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o"
OPENAI_TEMPERATURE = 0.3  # Low for consistent, analytical responses

# =============================================================================
# Trading Parameters
# =============================================================================

# Risk management (Aggressive profile)
RISK_PER_TRADE = 0.075       # 7.5% of buying power per trade
STOP_LOSS_PCT = 0.02         # 2% stop loss
TAKE_PROFIT_PCT = 0.05       # 5% take profit target
MAX_POSITIONS = 10           # Maximum simultaneous positions
MAX_PORTFOLIO_PCT = 0.40     # Max 40% of portfolio in a single stock

# Volume filter
MIN_VOLUME = 1_000_000       # Only trade stocks with 1M+ avg volume

# Momentum thresholds (used for pre-filtering before sending to advisors)
RSI_PERIOD = 14
RSI_THRESHOLD = 55           # Pre-filter: RSI > 55 to send to advisors
MOMENTUM_LOOKBACK = 5        # Compare price to N bars ago
MOMENTUM_MIN_PCT = 0.005     # Minimum 0.5% price increase to consider

# =============================================================================
# Stock Universe (31 tickers)
# =============================================================================

STOCK_UNIVERSE = [
    # Tech Giants
    "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA",
    # Financials
    "BRK.B", "JPM", "V", "MA",
    # Healthcare / Consumer
    "JNJ", "WMT", "PG", "UNH", "DIS",
    # Semiconductors
    "AMD", "INTC", "QCOM", "AVGO",
    # Enterprise Tech
    "CSCO", "IBM",
    # User-added tickers
    "MU", "WDC", "FIX",
    # AI picks-and-shovels
    "SNDK", "ORCL", "CDNS", "FICO", "LITE", "STX",
]

# Sector mapping (for Portfolio Strategist diversification analysis)
SECTOR_MAP = {
    "AAPL": "Technology", "MSFT": "Technology", "GOOGL": "Technology",
    "AMZN": "Consumer Discretionary", "NVDA": "Semiconductors",
    "META": "Technology", "TSLA": "Consumer Discretionary",
    "BRK.B": "Financials", "JPM": "Financials", "V": "Financials",
    "MA": "Financials", "JNJ": "Healthcare", "WMT": "Consumer Staples",
    "PG": "Consumer Staples", "UNH": "Healthcare", "DIS": "Communication Services",
    "PYPL": "Financials", "ADBE": "Technology", "NFLX": "Communication Services",
    "CRM": "Technology", "AMD": "Semiconductors", "INTC": "Semiconductors",
    "QCOM": "Semiconductors", "AVGO": "Semiconductors",
    "CSCO": "Technology", "IBM": "Technology",
    "MU": "Semiconductors", "WDC": "Technology", "FIX": "Industrials",
    "SNDK": "Semiconductors", "ORCL": "Technology",
    "CDNS": "Technology", "FICO": "Technology",
    "LITE": "Technology", "STX": "Technology",
}

# =============================================================================
# Scheduling
# =============================================================================

MARKET_OPEN = time(9, 30)    # 9:30 AM ET
MARKET_CLOSE = time(16, 0)   # 4:00 PM ET
RUN_INTERVAL_MINUTES = 50    # Run every 50 minutes
TIMEZONE = "US/Eastern"

# =============================================================================
# Output / Logging
# =============================================================================

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
SUMMARIES_DIR = os.path.join(OUTPUT_DIR, "summaries")
TRADES_FILE = os.path.join(OUTPUT_DIR, "trades.json")
PERFORMANCE_LOG_FILE = os.path.join(OUTPUT_DIR, "performance_log.json")
PERFORMANCE_BRIEF_CACHE_FILE = os.path.join(OUTPUT_DIR, "performance_brief_cache.json")
