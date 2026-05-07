import sys
import tempfile
import types
import unittest
from datetime import date
from pathlib import Path

openai_stub = types.ModuleType("openai")


class _OpenAIStub:
    def __init__(self, *args, **kwargs):
        pass


openai_stub.OpenAI = _OpenAIStub
sys.modules.setdefault("openai", openai_stub)

dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *args, **kwargs: None
sys.modules.setdefault("dotenv", dotenv_stub)

import daily_summary


class DailySummaryFooterTests(unittest.TestCase):
    def test_build_performance_footer_uses_previous_summary_equity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            summaries_dir = Path(tmpdir)
            previous_summary = summaries_dir / "2026-04-13.md"
            previous_summary.write_text(
                "# Daily Summary - 2026-04-13\n\n"
                "With an account equity of $10,177.23 and buying power of $8,809.13.\n"
            )

            footer = daily_summary.build_performance_footer(
                current_equity=10730.17,
                summary_date=date(2026, 4, 14),
                summaries_dir=str(summaries_dir),
            )

            self.assertIn("Daily gain: +5.43%", footer)
            self.assertIn("Gain since April 13, 2026: +7.30%", footer)

    def test_build_performance_footer_uses_starting_equity_on_first_day(self):
        footer = daily_summary.build_performance_footer(
            current_equity=10177.23,
            summary_date=date(2026, 4, 13),
            summaries_dir="/tmp/unused",
        )

        self.assertIn("Daily gain: +1.77%", footer)
        self.assertIn("Gain since April 13, 2026: +1.77%", footer)


if __name__ == "__main__":
    unittest.main()
