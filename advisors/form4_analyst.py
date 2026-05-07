"""
🕵️ Form 4 Analyst — Generates the morning insider-buying briefing for the Head Advisor.
Consumes deterministically filtered buys from form4_fetcher.py and uses GPT-4o only
for narrative synthesis (cluster notes, recommended action, exec summary).
"""

import json
import logging
import os
from datetime import datetime

from openai import OpenAI

from config import OPENAI_API_KEY, OPENAI_MODEL, OPENAI_TEMPERATURE, SUMMARIES_DIR

logger = logging.getLogger(__name__)

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """You are the Form 4 Analyst for a professional trading desk.
Your sole job is to deliver a concise, high-signal briefing to the Head Advisor
about meaningful insider buying activity based on Form 4 filings.

STRICT RULES:
- The buys you are given have ALREADY been filtered to: open-market purchases (code P),
  value >= $200k, S&P 500 companies only. You do NOT need to re-filter them.
- Do NOT fabricate historical context (e.g. "first buy in 18 months") — you don't have it.
- Call out clusters (same ticker, multiple insiders) and cross-sector themes.
- Tone: neutral, factual, professional. No filler.

You MUST respond with valid JSON only (no markdown fences), matching this schema:
{
    "briefing_markdown": "<full briefing text in the exact structure requested>",
    "per_ticker_notes": {"<TICKER>": "<1-sentence note for head advisor>", ...},
    "recommended_action": "<1-2 sentence overall recommendation>"
}
"""

BRIEFING_TEMPLATE_INSTRUCTION = """
The briefing_markdown field MUST follow this exact structure:

HEAD ADVISOR BRIEFING – FORM 4 INSIDER BUYS
Date: {date}
Number of qualifying buys today: {n}

EXECUTIVE SUMMARY
(one sentence high-level takeaway + total dollar value of all qualifying buys combined)

DETAILED TRANSACTIONS
(for each qualifying buy, in order:)
• Ticker: [Symbol]
• Company: [Full name]
• Insider: [Name] – [Title]
• Transaction Date: [Date]
• Shares Purchased: [Number]
• Price per Share: $[Price]
• Total Value: $[Exact dollar amount]
• Ownership After Transaction: [post-trade shares]
• Notes: [any cluster/size observations from the data provided only]

CLUSTER / THEME NOTES
(clusters of same ticker, cross-sector themes)

RECOMMENDED ACTION FOR HEAD ADVISOR
(1–2 sentences)

END OF BRIEFING
"""


class Form4Analyst:
    """Generates the Head Advisor briefing from pre-filtered Form 4 buys."""

    def __init__(self):
        self.name = "🕵️ Form 4 Analyst"

    def generate_briefing(self, qualifying_buys: list, date: datetime) -> dict:
        """
        Build a morning insider briefing. Saves the markdown to summaries/form4-YYYY-MM-DD.md.

        Args:
            qualifying_buys: list of rows from form4_fetcher.get_qualifying_form4_buys()
            date: datetime to stamp the briefing with

        Returns:
            {
                "briefing_markdown": str,
                "per_ticker_notes": {ticker: note},
                "recommended_action": str,
                "qualifying_tickers": [unique tickers],
                "summary_path": str or None,
            }
        """
        date_str = date.strftime("%Y-%m-%d")
        unique_tickers = sorted({b["ticker"] for b in qualifying_buys})

        if not qualifying_buys:
            briefing = (
                f"HEAD ADVISOR BRIEFING – FORM 4 INSIDER BUYS\n"
                f"Date: {date_str}\n\n"
                f"No Form 4 open-market purchases ≥ $200k in S&P 500 companies filed overnight.\n\n"
                f"END OF BRIEFING\n"
            )
            path = self._save_briefing(briefing, date_str)
            logger.info(f"{self.name}: no qualifying buys today")
            return {
                "briefing_markdown": briefing,
                "per_ticker_notes": {},
                "recommended_action": "No actionable Form 4 signal today.",
                "qualifying_tickers": [],
                "summary_path": path,
            }

        user_message = self._build_user_message(qualifying_buys, date_str)
        try:
            response = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=OPENAI_TEMPERATURE,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT + BRIEFING_TEMPLATE_INSTRUCTION.format(
                        date=date_str, n=len(qualifying_buys)
                    )},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=2000,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content.strip()
            result = json.loads(content)
            briefing = result.get("briefing_markdown", "")
            per_ticker = result.get("per_ticker_notes", {}) or {}
            action = result.get("recommended_action", "")
        except Exception as e:
            logger.error(f"{self.name}: briefing generation failed — {e}")
            briefing = self._fallback_briefing(qualifying_buys, date_str)
            per_ticker = {t: f"Qualifying Form 4 buy: see briefing for {t}" for t in unique_tickers}
            action = "LLM synthesis unavailable — review raw briefing manually."

        path = self._save_briefing(briefing, date_str)

        logger.info(
            f"{self.name}: generated briefing with {len(qualifying_buys)} buys across "
            f"{len(unique_tickers)} tickers → {path}"
        )
        return {
            "briefing_markdown": briefing,
            "per_ticker_notes": per_ticker,
            "recommended_action": action,
            "qualifying_tickers": unique_tickers,
            "summary_path": path,
        }

    def _build_user_message(self, buys: list, date_str: str) -> str:
        total = sum(b["value"] for b in buys)
        lines = [
            f"DATE: {date_str}",
            f"NUMBER OF QUALIFYING BUYS: {len(buys)}",
            f"TOTAL DOLLAR VALUE: ${total:,.0f}",
            "",
            "RAW QUALIFYING BUYS (pre-filtered to P code, >=$200k, S&P 500 only):",
        ]
        for b in buys:
            lines.append(
                f"- {b['ticker']} | {b['company']} | {b['insider']} ({b['title']}) | "
                f"trade_date={b['trade_date']} | shares={b['shares']:,} @ ${b['price']:.2f} | "
                f"value=${b['value']:,.0f} | owned_after={b['owned_after']:,} | "
                f"filed={b['filing_datetime']}"
            )
        lines.append("")
        lines.append("Produce the briefing JSON now. Do not invent historical context.")
        return "\n".join(lines)

    def _fallback_briefing(self, buys: list, date_str: str) -> str:
        total = sum(b["value"] for b in buys)
        lines = [
            "HEAD ADVISOR BRIEFING – FORM 4 INSIDER BUYS",
            f"Date: {date_str}",
            f"Number of qualifying buys today: {len(buys)}",
            "",
            "EXECUTIVE SUMMARY",
            f"LLM synthesis unavailable. Raw total across all qualifying buys: ${total:,.0f}.",
            "",
            "DETAILED TRANSACTIONS",
        ]
        for b in buys:
            lines.extend([
                f"• Ticker: {b['ticker']}",
                f"• Company: {b['company']}",
                f"• Insider: {b['insider']} – {b['title']}",
                f"• Transaction Date: {b['trade_date']}",
                f"• Shares Purchased: {b['shares']:,}",
                f"• Price per Share: ${b['price']:.2f}",
                f"• Total Value: ${b['value']:,.0f}",
                f"• Ownership After Transaction: {b['owned_after']:,} shares",
                f"• Notes: (raw data, no LLM synthesis)",
                "",
            ])
        lines.extend(["END OF BRIEFING", ""])
        return "\n".join(lines)

    def _save_briefing(self, briefing: str, date_str: str) -> str:
        try:
            os.makedirs(SUMMARIES_DIR, exist_ok=True)
            path = os.path.join(SUMMARIES_DIR, f"form4-{date_str}.md")
            with open(path, "w") as f:
                f.write(briefing)
            return path
        except Exception as e:
            logger.error(f"{self.name}: failed to save briefing — {e}")
            return ""
