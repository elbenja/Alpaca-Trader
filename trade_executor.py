"""
Trade Executor — Places orders, monitors positions, logs trades.
Handles bracket orders (entry + stop loss + take profit).
"""

import json
import logging
from datetime import datetime
import requests
from config import (
    ALPACA_HEADERS,
    ALPACA_BASE_URL,
    TRADES_FILE,
    RISK_PER_TRADE,
    STOP_LOSS_PCT,
    TAKE_PROFIT_PCT,
)

logger = logging.getLogger(__name__)


class TradeExecutor:
    """Manages order execution on Alpaca paper account."""

    def __init__(self):
        self.base_url = ALPACA_BASE_URL
        self.headers = ALPACA_HEADERS
        self.trades_log = self._load_trades_log()

    def execute_trade(
        self,
        symbol: str,
        qty: int,
        side: str,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
        reasoning: str = "",
    ) -> dict:
        """
        Place a bracket order (entry + SL + TP) on Alpaca.

        Args:
            symbol: Stock ticker
            qty: Quantity to trade
            side: "buy" or "sell"
            entry_price: Current price (for reference)
            stop_loss_price: SL price level
            take_profit_price: TP price level
            reasoning: Trade rationale for logging

        Returns:
            Dict with order status, order IDs, or error
        """
        if side not in ("buy", "sell"):
            logger.error(f"Invalid side: {side}")
            return {"status": "error", "reason": "Invalid side"}

        try:
            # Place main order with OTO (One-Triggers-Other) bracket
            main_order = {
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "type": "market",
                "time_in_force": "day",
                "order_class": "bracket",
                "take_profit": {"limit_price": take_profit_price},
                "stop_loss": {"stop_price": stop_loss_price},
            }

            response = requests.post(
                f"{self.base_url}/v2/orders",
                headers=self.headers,
                json=main_order,
            )

            if response.status_code not in (200, 201):
                error_msg = response.text
                logger.error(
                    f"Failed to place bracket order for {symbol}: {error_msg}"
                )
                return {
                    "status": "error",
                    "symbol": symbol,
                    "reason": error_msg,
                }

            order_data = response.json()
            order_id = order_data.get("id")

            trade_record = {
                "timestamp": datetime.now().isoformat(),
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "entry_price": entry_price,
                "stop_loss": stop_loss_price,
                "take_profit": take_profit_price,
                "order_id": order_id,
                "status": "submitted",
                "reasoning": reasoning,
            }

            self.trades_log.append(trade_record)
            self._save_trades_log()

            logger.info(
                f"✅ Order placed: {side.upper()} {qty} {symbol} @ ${entry_price:.2f} "
                f"(SL: ${stop_loss_price:.2f}, TP: ${take_profit_price:.2f})"
            )

            return {
                "status": "success",
                "symbol": symbol,
                "order_id": order_id,
                "qty": qty,
                "side": side,
            }

        except Exception as e:
            logger.error(f"Exception placing order for {symbol}: {e}")
            return {"status": "error", "symbol": symbol, "reason": str(e)}

    def close_position(self, symbol: str) -> dict:
        """
        Close an existing position (sell if long, buy to cover if short).

        Args:
            symbol: Stock ticker

        Returns:
            Dict with close status or error
        """
        try:
            response = requests.delete(
                f"{self.base_url}/v2/positions/{symbol}",
                headers=self.headers,
                params={"cancel_orders": True},
            )

            if response.status_code not in (200, 204):
                error_msg = response.text
                logger.error(f"Failed to close {symbol}: {error_msg}")
                return {"status": "error", "symbol": symbol, "reason": error_msg}

            logger.info(f"✅ Position closed: {symbol}")
            return {"status": "success", "symbol": symbol}

        except Exception as e:
            logger.error(f"Exception closing position {symbol}: {e}")
            return {"status": "error", "symbol": symbol, "reason": str(e)}

    def get_open_orders(self) -> list:
        """Fetch all open orders from Alpaca."""
        try:
            response = requests.get(
                f"{self.base_url}/v2/orders",
                headers=self.headers,
                params={"status": "open"},
            )

            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Failed to fetch open orders: {response.text}")
                return []

        except Exception as e:
            logger.error(f"Exception fetching open orders: {e}")
            return []

    def _load_trades_log(self) -> list:
        """Load trade history from JSON file."""
        try:
            with open(TRADES_FILE, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return []
        except Exception as e:
            logger.warning(f"Failed to load trades log: {e}")
            return []

    def _save_trades_log(self):
        """Save trade history to JSON file."""
        try:
            with open(TRADES_FILE, "w") as f:
                json.dump(self.trades_log, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save trades log: {e}")
