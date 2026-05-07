"""
Market Data — Alpaca data fetching and technical analysis.
Handles all communication with Alpaca's market data API.
"""

import logging
from typing import Optional
import requests
from config import (
    ALPACA_BASE_URL, ALPACA_DATA_URL, ALPACA_HEADERS,
    RSI_PERIOD, RSI_THRESHOLD, MOMENTUM_LOOKBACK, MOMENTUM_MIN_PCT,
    MIN_VOLUME, MAX_POSITIONS, SECTOR_MAP,
)

logger = logging.getLogger(__name__)


def get_account() -> dict:
    """Get Alpaca account information."""
    resp = requests.get(f"{ALPACA_BASE_URL}/v2/account", headers=ALPACA_HEADERS)
    resp.raise_for_status()
    return resp.json()


def get_positions() -> list:
    """Get current open positions."""
    resp = requests.get(f"{ALPACA_BASE_URL}/v2/positions", headers=ALPACA_HEADERS)
    resp.raise_for_status()
    return resp.json()


def get_bars(symbols: list, limit: int = 50, timeframe: str = "15Min") -> dict:
    """
    Get latest bars for multiple symbols using Alpaca Data API v2.
    Returns dict of {symbol: [bars]}.
    """
    bars_data = {}

    for symbol in symbols:
        try:
            resp = requests.get(
                f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/bars",
                headers=ALPACA_HEADERS,
                params={"limit": limit, "timeframe": timeframe},
            )
            resp.raise_for_status()
            bars_data[symbol] = resp.json().get("bars", [])
        except Exception as e:
            logger.warning(f"Error fetching bars for {symbol}: {e}")

    return bars_data


def calculate_rsi(bars: list, period: int = RSI_PERIOD) -> Optional[float]:
    """Calculate RSI from bar data."""
    if len(bars) < period + 1:
        return None

    closes = [bar["c"] for bar in bars]
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100 if avg_gain > 0 else 0

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def get_momentum_candidates(bars_data: dict) -> list:
    """
    Pre-filter stocks for momentum signals before sending to advisors.
    Returns list of stock dicts with: symbol, price, rsi, momentum, volume, bars
    """
    candidates = []

    for symbol, bars in bars_data.items():
        if len(bars) < 20:
            continue

        # Volume filter
        avg_volume = sum(bar["v"] for bar in bars[-5:]) / 5
        if avg_volume < MIN_VOLUME:
            continue

        # RSI
        rsi = calculate_rsi(bars)
        if rsi is None:
            continue

        # Price momentum
        current_price = bars[-1]["c"]
        lookback_price = bars[-MOMENTUM_LOOKBACK]["c"] if len(bars) >= MOMENTUM_LOOKBACK else bars[0]["c"]
        price_momentum = (current_price - lookback_price) / lookback_price

        # Pre-filter: RSI above threshold + positive momentum
        if rsi > RSI_THRESHOLD and price_momentum > MOMENTUM_MIN_PCT:
            candidates.append({
                "symbol": symbol,
                "price": current_price,
                "rsi": rsi,
                "momentum": price_momentum * 100,
                "volume": avg_volume,
                "bars": bars,  # Include raw bars for advisors
                "sector": SECTOR_MAP.get(symbol, "Unknown"),
            })

    # Sort by momentum strength, return top candidates
    return sorted(candidates, key=lambda x: x["momentum"], reverse=True)[:8]


def build_force_added_candidates(tickers: list, timeframe: str = "15Min") -> list:
    """
    Build candidate dicts for tickers that bypass the momentum pre-filter
    (e.g., force-added via a qualifying Form 4 insider buy).

    Tickers with no bar data are dropped. RSI/momentum/volume are computed
    best-effort so the downstream advisor prompt format stays consistent.
    """
    if not tickers:
        return []

    bars_data = get_bars(tickers, limit=50, timeframe=timeframe)
    forced = []
    for symbol, bars in bars_data.items():
        if not bars:
            logger.warning(f"Force-add: no bars for {symbol}, skipping")
            continue

        avg_volume = (
            sum(bar["v"] for bar in bars[-5:]) / 5 if len(bars) >= 5 else bars[-1].get("v", 0)
        )
        rsi = calculate_rsi(bars) if len(bars) >= RSI_PERIOD + 1 else 50.0
        current_price = bars[-1]["c"]
        if len(bars) >= MOMENTUM_LOOKBACK:
            lookback_price = bars[-MOMENTUM_LOOKBACK]["c"]
        else:
            lookback_price = bars[0]["c"]
        price_momentum = (
            (current_price - lookback_price) / lookback_price if lookback_price else 0
        )

        forced.append({
            "symbol": symbol,
            "price": current_price,
            "rsi": rsi if rsi is not None else 50.0,
            "momentum": price_momentum * 100,
            "volume": avg_volume,
            "bars": bars,
            "sector": SECTOR_MAP.get(symbol, "Unknown"),
            "force_added_reason": "form4_insider_buy",
        })

    return forced


def build_portfolio_context(account: dict, positions: list) -> dict:
    """
    Build a portfolio context dict for advisor analysis.
    Includes account info, positions, sector exposure, etc.
    """
    equity = float(account.get("equity", 0))
    buying_power = float(account.get("buying_power", 0))

    # Calculate sector exposure
    sector_exposure = {}
    for pos in positions:
        symbol = pos["symbol"]
        sector = SECTOR_MAP.get(symbol, "Unknown")
        market_value = abs(float(pos.get("market_value", 0)))
        sector_exposure[sector] = sector_exposure.get(sector, 0) + market_value

    # Build exposure summary string
    exposure_parts = []
    for sector, value in sorted(sector_exposure.items(), key=lambda x: -x[1]):
        pct = (value / equity * 100) if equity > 0 else 0
        exposure_parts.append(f"{sector}: {pct:.1f}%")
    exposure_summary = ", ".join(exposure_parts) if exposure_parts else "No current exposure"

    return {
        "equity": equity,
        "buying_power": buying_power,
        "positions": positions,
        "max_positions": MAX_POSITIONS,
        "sector_exposure": sector_exposure,
        "exposure_summary": exposure_summary,
    }
