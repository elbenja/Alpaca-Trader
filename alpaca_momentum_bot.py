#!/usr/bin/env python3
"""
Alpaca Intraday Momentum Trading Bot
Trades S&P 500 top movers with momentum detection (hourly/15-min)
Uses RSI + price action for entry signals
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
import requests

# Setup logging to file
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(OUTPUT_DIR, exist_ok=True)

log_file = os.path.join(OUTPUT_DIR, f"bot_log_{datetime.now().strftime('%Y%m%d')}.txt")
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Alpaca API config
API_KEY = os.getenv("ALPACA_API_KEY")
SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
BASE_URL = "https://paper-api.alpaca.markets"  # Paper trading
HEADERS = {
    "APCA-API-KEY-ID": API_KEY,
    "APCA-API-SECRET-KEY": SECRET_KEY,
}

# Trading config
RISK_PER_TRADE = 0.075  # 7.5% of account (middle of aggressive range)
STOP_LOSS_PCT = 0.02  # 2% stop loss
TAKE_PROFIT_PCT = 0.05  # 5% take profit target
MIN_VOLUME = 1_000_000  # Only trade high volume stocks
RSI_THRESHOLD = 60  # Momentum signal (above 60 = strong uptrend)


def get_account():
    """Get account information"""
    resp = requests.get(f"{BASE_URL}/v2/account", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def get_sp500_symbols():
    """Get S&P 500 symbols (using a static list for now)"""
    # In production, you'd fetch this dynamically
    sp500 = [
        "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "BRK.B",
        "JNJ", "WMT", "JPM", "V", "PG", "UNH", "MA", "DIS", "AMD", "INTC", "CSCO", "IBM", "QCOM", "AVGO",
    ]
    return sp500


def get_latest_bars(symbols: list, limit: int = 50, timeframe: str = "15m"):
    """Get latest bars for symbols (15-minute data for intraday)"""
    bars_data = {}
    for symbol in symbols:
        try:
            resp = requests.get(
                f"{BASE_URL}/v2/stocks/{symbol}/bars",
                headers=HEADERS,
                params={"limit": limit, "timeframe": timeframe},
            )
            resp.raise_for_status()
            bars_data[symbol] = resp.json().get("bars", [])
        except Exception as e:
            logger.warning(f"Error fetching {symbol}: {e}")
    return bars_data


def calculate_rsi(bars: list, period: int = 14) -> Optional[float]:
    """Calculate RSI from bar data"""
    if len(bars) < period + 1:
        return None

    closes = [bar["c"] for bar in bars]
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]

    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]

    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100 if avg_gain > 0 else 0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def identify_momentum_stocks(bars_data: dict) -> list:
    """Find stocks with strong momentum signals"""
    momentum_stocks = []

    for symbol, bars in bars_data.items():
        if len(bars) < 20:
            continue

        # Check volume
        avg_volume = sum(bar["v"] for bar in bars[-5:]) / 5
        if avg_volume < MIN_VOLUME:
            continue

        # Calculate metrics
        rsi = calculate_rsi(bars)
        if rsi is None:
            continue

        # Price momentum (compare current to 5 bars ago)
        current_price = bars[-1]["c"]
        price_5_bars_ago = bars[-5]["c"] if len(bars) >= 5 else bars[0]["c"]
        price_momentum = (current_price - price_5_bars_ago) / price_5_bars_ago

        # Signal: RSI > 60 (strong momentum) + recent uptrend
        if rsi > RSI_THRESHOLD and price_momentum > 0.01:
            momentum_stocks.append({
                "symbol": symbol,
                "price": current_price,
                "rsi": rsi,
                "momentum": price_momentum * 100,
                "volume": avg_volume,
            })

    # Return top 5 by momentum
    return sorted(momentum_stocks, key=lambda x: x["momentum"], reverse=True)[:5]


def get_positions():
    """Get current open positions"""
    resp = requests.get(f"{BASE_URL}/v2/positions", headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def place_order(symbol: str, qty: int, side: str, order_type: str = "market"):
    """Place an order"""
    data = {
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "type": order_type,
        "time_in_force": "day",
    }
    resp = requests.post(f"{BASE_URL}/v2/orders", headers=HEADERS, json=data)
    resp.raise_for_status()
    return resp.json()


def save_signals(signals: list):
    """Save momentum signals to JSON"""
    signals_file = os.path.join(OUTPUT_DIR, f"signals_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(signals_file, 'w') as f:
        json.dump(signals, f, indent=2)
    logger.info(f"Signals saved to {signals_file}")


def save_trade(trade_info: dict):
    """Append trade to trades log"""
    trades_file = os.path.join(OUTPUT_DIR, "trades.json")
    trades = []

    if os.path.exists(trades_file):
        with open(trades_file, 'r') as f:
            trades = json.load(f)

    trades.append(trade_info)

    with open(trades_file, 'w') as f:
        json.dump(trades, f, indent=2)
    logger.info(f"Trade logged: {trade_info['symbol']}")


def run_bot():
    """Main bot loop"""
    logger.info("🤖 Alpaca Momentum Trading Bot Starting...")
    logger.info(f"Risk per trade: {RISK_PER_TRADE*100}% | Stop loss: {STOP_LOSS_PCT*100}% | TP: {TAKE_PROFIT_PCT*100}%")
    logger.info(f"Output directory: {OUTPUT_DIR}")

    account = get_account()
    buying_power = float(account["buying_power"])
    logger.info(f"Account buying power: ${buying_power:,.2f}")

    # Get S&P 500 stocks
    symbols = get_sp500_symbols()
    logger.info(f"Scanning {len(symbols)} stocks for momentum...")

    # Get bars and identify momentum
    bars_data = get_latest_bars(symbols)
    momentum_stocks = identify_momentum_stocks(bars_data)

    if not momentum_stocks:
        logger.warning("❌ No momentum signals found")
        return

    logger.info(f"✅ Found {len(momentum_stocks)} momentum stocks:")
    for stock in momentum_stocks:
        logger.info(f"  {stock['symbol']}: Price=${stock['price']:.2f}, RSI={stock['rsi']:.1f}, Momentum={stock['momentum']:.2f}%")

    # Save signals to file
    save_signals(momentum_stocks)

    # Check current positions
    positions = get_positions()
    open_symbols = {p["symbol"] for p in positions}
    logger.info(f"Current open positions: {open_symbols if open_symbols else 'None'}")

    # Trade logic
    for stock in momentum_stocks:
        symbol = stock["symbol"]
        price = stock["price"]

        # Skip if already have position
        if symbol in open_symbols:
            logger.info(f"⏭️  {symbol}: Already in position, skipping")
            continue

        # Calculate position size based on risk
        risk_amount = buying_power * RISK_PER_TRADE
        stop_loss_price = price * (1 - STOP_LOSS_PCT)
        risk_per_share = price - stop_loss_price
        qty = int(risk_amount / risk_per_share)

        if qty <= 0:
            logger.warning(f"❌ {symbol}: Position too small ({qty} shares)")
            continue

        # Place entry order
        logger.info(f"📈 Entering {symbol}: {qty} shares @ ${price:.2f}")
        try:
            order = place_order(symbol, qty, "buy")
            logger.info(f"   ✅ Order placed: {order.get('id')}")

            # Log trade info
            take_profit_price = price * (1 + TAKE_PROFIT_PCT)
            logger.info(f"   SL: ${stop_loss_price:.2f} | TP: ${take_profit_price:.2f}")

            # Save trade to JSON
            trade_record = {
                "timestamp": datetime.now().isoformat(),
                "symbol": symbol,
                "qty": qty,
                "entry_price": price,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "order_id": order.get('id'),
                "rsi": stock["rsi"],
                "momentum_pct": stock["momentum"],
            }
            save_trade(trade_record)

        except Exception as e:
            logger.error(f"   ❌ Order failed: {e}")


if __name__ == "__main__":
    run_bot()
