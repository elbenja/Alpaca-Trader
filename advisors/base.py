"""
Base Advisor — Shared GPT-4o integration for all wealth advisors.
Each advisor inherits from this and defines their own system prompt.
"""

import json
import logging
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TEMPERATURE

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)

RESPONSE_FORMAT_INSTRUCTION = """
You MUST respond with valid JSON only. No markdown, no extra text.
Use this exact format:
{
    "recommendation": "BUY" | "SELL" | "PASS",
    "confidence": <integer 0-100>,
    "reasoning": "<2-3 sentence explanation>"
}
"""


class BaseAdvisor:
    """Base class for all wealth advisors. Provides GPT-4o analysis."""

    def __init__(self, name: str, role: str, system_prompt: str):
        self.name = name
        self.role = role
        self.system_prompt = system_prompt

    def analyze(self, stock_data: dict, portfolio_context: dict) -> dict:
        """
        Ask GPT-4o to analyze a stock opportunity.

        Args:
            stock_data: Dict with symbol, price, rsi, momentum, volume, bars
            portfolio_context: Dict with account info, current positions, exposure

        Returns:
            Dict with recommendation, confidence, reasoning
        """
        user_message = self._build_user_message(stock_data, portfolio_context)

        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=OPENAI_TEMPERATURE,
                messages=[
                    {"role": "system", "content": self.system_prompt + RESPONSE_FORMAT_INSTRUCTION},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=300,
            )

            content = response.choices[0].message.content.strip()

            # Parse JSON response
            # Handle potential markdown code block wrapping
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(content)

            # Validate required fields
            assert result.get("recommendation") in ("BUY", "SELL", "PASS")
            assert 0 <= result.get("confidence", -1) <= 100
            assert isinstance(result.get("reasoning"), str)

            result["advisor"] = self.name
            logger.info(
                f"  {self.name}: {result['recommendation']} "
                f"(confidence: {result['confidence']}%) — {result['reasoning'][:80]}..."
            )
            return result

        except json.JSONDecodeError as e:
            logger.error(f"  {self.name}: Failed to parse GPT response — {e}")
            logger.error(f"  Raw response: {content[:200]}")
            return self._fallback_response("JSON parse error")
        except Exception as e:
            logger.error(f"  {self.name}: Analysis failed — {e}")
            return self._fallback_response(str(e))

    def _build_user_message(self, stock_data: dict, portfolio_context: dict) -> str:
        """Build the user message with market data context."""

        # Format recent price action
        bars_summary = ""
        bars = stock_data.get("bars", [])
        if bars and len(bars) >= 5:
            recent = bars[-5:]
            bars_summary = "Recent 5 bars (oldest→newest): " + ", ".join(
                f"${b['c']:.2f}" for b in recent
            )

        # Format current positions
        positions_str = "None"
        positions = portfolio_context.get("positions", [])
        if positions:
            positions_str = ", ".join(
                f"{p['symbol']} ({p.get('qty', '?')} shares @ ${float(p.get('avg_entry_price', 0)):.2f})"
                for p in positions
            )

        msg = f"""
STOCK ANALYSIS REQUEST: {stock_data['symbol']}

--- Market Data ---
Current Price: ${stock_data['price']:.2f}
RSI (14): {stock_data['rsi']:.1f}
Momentum (5-bar): {stock_data['momentum']:.2f}%
Avg Volume (5-bar): {stock_data['volume']:,.0f}
{bars_summary}

--- Portfolio Context ---
Account Equity: ${portfolio_context.get('equity', 0):,.2f}
Buying Power: ${portfolio_context.get('buying_power', 0):,.2f}
Current Positions ({len(positions)}/{portfolio_context.get('max_positions', 10)}): {positions_str}
Portfolio Exposure: {portfolio_context.get('exposure_summary', 'N/A')}

--- Your Task ---
Analyze this stock from your perspective as {self.role}.
Should we BUY, SELL, or PASS on {stock_data['symbol']} right now?
"""
        return msg

    def _fallback_response(self, error_msg: str) -> dict:
        """Return a safe PASS response when analysis fails."""
        return {
            "advisor": self.name,
            "recommendation": "PASS",
            "confidence": 0,
            "reasoning": f"Analysis unavailable: {error_msg}",
        }
