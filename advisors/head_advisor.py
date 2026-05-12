"""
⚖️ Head Advisor — The final decision maker.
Reviews all specialist opinions and makes the definitive BUY/SELL/PASS call.
"""

import json
import logging
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TEMPERATURE

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are the Head Wealth Advisor — the final decision maker on an aggressive trading team.
You receive analysis from 4 specialist advisors and make the DEFINITIVE trade decision.

Your specialists:
1. 📈 Momentum Analyst — Technical trend analysis
2. 📰 Sentiment Analyst — Market mood and macro context
3. 🛡️ Risk Manager — Portfolio risk assessment
4. 🏗️ Portfolio Strategist — Diversification and allocation

DECISION FRAMEWORK:
1. CONSENSUS: If 3+ advisors say BUY with confidence > 70%, it's a strong BUY.
2. VETO POWER: If the Risk Manager says PASS with confidence > 80%, seriously consider PASS regardless of others.
3. TIE-BREAKING: When split, weigh Momentum Analyst highest (they read the actual price data).
4. POSITION SIZING: Based on risk parameters, determine the exact number of shares to buy.

You are AGGRESSIVE but DISCIPLINED:
- You pull the trigger when the team agrees
- You override cautious advisors when momentum is undeniable
- But you respect serious risk warnings

RESPOND WITH THIS EXACT JSON FORMAT:
{
    "decision": "BUY" | "SELL" | "PASS",
    "confidence": <integer 0-100>,
    "shares": <integer, number of shares to trade, 0 if PASS>,
    "stop_loss": <float, stop loss price>,
    "take_profit": <float, take profit price>,
    "reasoning": "<2-3 sentence summary of why, referencing advisor opinions>"
}
"""


class HeadAdvisor:
    """Final decision maker — synthesizes all advisor opinions."""

    def __init__(self):
        self.name = "⚖️ Head Advisor"

    def decide(
        self,
        stock_data: dict,
        advisor_opinions: list,
        portfolio_context: dict,
        form4_context: dict = None,
        performance_brief: str = None,
    ) -> dict:
        """
        Make final trade decision based on all advisor opinions.

        Args:
            stock_data: Dict with symbol, price, rsi, momentum, volume
            advisor_opinions: List of dicts from each advisor's analyze()
            portfolio_context: Dict with account info, positions
            form4_context: Optional dict with keys:
              - ticker_note (str): 1-sentence insider-buy note for this ticker, if any
              - overall_action (str): Form 4 Analyst's overall recommendation for the day
              - is_force_added (bool): True if this ticker was added to the cycle
                solely because of a qualifying Form 4 buy (bypassed momentum filter)
            performance_brief: Optional markdown string summarising recent trade performance

        Returns:
            Dict with decision, confidence, shares, stop_loss, take_profit, reasoning
        """
        user_message = self._build_decision_prompt(
            stock_data, advisor_opinions, portfolio_context, form4_context, performance_brief
        )

        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=OPENAI_TEMPERATURE,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=400,
            )

            content = response.choices[0].message.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

            result = json.loads(content)
            result["symbol"] = stock_data["symbol"]

            logger.info(
                f"  ⚖️ HEAD ADVISOR DECISION: {result['decision']} {stock_data['symbol']} "
                f"(confidence: {result['confidence']}%, shares: {result.get('shares', 0)})"
            )
            logger.info(f"     Reasoning: {result['reasoning']}")

            return result

        except Exception as e:
            logger.error(f"  ⚖️ Head Advisor decision failed: {e}")
            return {
                "symbol": stock_data["symbol"],
                "decision": "PASS",
                "confidence": 0,
                "shares": 0,
                "stop_loss": 0,
                "take_profit": 0,
                "reasoning": f"Decision failed: {e}",
            }

    def _build_decision_prompt(
        self,
        stock_data: dict,
        advisor_opinions: list,
        portfolio_context: dict,
        form4_context: dict = None,
        performance_brief: str = None,
    ) -> str:
        """Build the prompt with all advisor opinions for final decision."""

        opinions_text = ""
        for opinion in advisor_opinions:
            opinions_text += (
                f"\n{opinion['advisor']}:\n"
                f"  Recommendation: {opinion['recommendation']}\n"
                f"  Confidence: {opinion['confidence']}%\n"
                f"  Reasoning: {opinion['reasoning']}\n"
            )

        performance_block = ""
        if performance_brief:
            performance_block = f"\n--- Recent Performance Brief ---\n{performance_brief}\n"

        form4_block = ""
        if form4_context and (form4_context.get("ticker_note") or form4_context.get("is_force_added")):
            note = form4_context.get("ticker_note", "")
            action = form4_context.get("overall_action", "")
            forced = form4_context.get("is_force_added", False)
            lines = ["\n--- Form 4 Insider Signal (pre-market briefing) ---"]
            if note:
                lines.append(f"This ticker's insider note: {note}")
            if action:
                lines.append(f"Overall daily action: {action}")
            if forced:
                lines.append(
                    "NOTE: This ticker was added to today's first-cycle candidates "
                    "BECAUSE of a qualifying Form 4 insider buy — it did NOT pass the "
                    "momentum pre-filter. Treat the insider buy as the primary thesis; "
                    "momentum/RSI above may be weak or neutral."
                )
            form4_block = "\n".join(lines) + "\n"

        # Calculate suggested position sizing with multiple constraints
        buying_power = portfolio_context.get("buying_power", 0)
        equity = portfolio_context.get("equity", 0)
        price = stock_data["price"]
        stop_loss_price = price * (1 - 0.02)  # 2% stop loss
        take_profit_price = price * (1 + 0.05)  # 5% take profit

        # Constraint 1: Maximum shares based on available buying power
        max_shares_by_power = int(buying_power / price) if price > 0 else 0

        # Constraint 2: Maximum shares based on portfolio concentration (40% of equity)
        max_position_value = equity * 0.40
        max_shares_by_concentration = int(max_position_value / price) if price > 0 else 0

        # Constraint 3: Maximum shares based on risk (7.5% of buying power)
        risk_amount = buying_power * 0.075  # 7.5% risk per trade
        risk_per_share = price - stop_loss_price
        max_shares_by_risk = int(risk_amount / risk_per_share) if risk_per_share > 0 else 0

        # Take the minimum of all three constraints
        suggested_shares = min(max_shares_by_power, max_shares_by_concentration, max_shares_by_risk)
        suggested_shares = max(suggested_shares, 0)  # Ensure non-negative

        # Calculate position value for concentration reporting
        position_value = suggested_shares * price if suggested_shares > 0 else 0
        portfolio_concentration = (position_value / equity * 100) if equity > 0 else 0

        return f"""
TRADE DECISION REQUIRED: {stock_data['symbol']}
{performance_block}
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

--- Your Decision ---
Review all advisor opinions and the position sizing constraints.
Make the final BUY, SELL, or PASS decision.
If BUY: use the suggested shares above (or lower if you want to be more conservative).
IMPORTANT: Do NOT exceed the suggested shares — respect the buying power and concentration limits.
"""
