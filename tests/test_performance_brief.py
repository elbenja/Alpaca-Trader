import json
import os
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

SAMPLE_CLOSED = [
    {
        "order_id": f"ord-{i}",
        "symbol": sym,
        "side": "buy",
        "qty": 10,
        "entry_price": 100.0,
        "entry_date": "2026-04-13",
        "exit_date": f"2026-04-{13 + i}",
        "exit_price": price,
        "pnl_pct": round((price - 100.0) / 100.0 * 100, 2),
        "outcome": "win" if price > 100 else "loss",
        "status": "closed",
        "advisor_votes": {
            "📈 Momentum Analyst":     {"recommendation": "BUY",  "confidence": 80},
            "📰 Sentiment Analyst":    {"recommendation": "PASS", "confidence": 40},
            "🛡️ Risk Manager":         {"recommendation": "BUY",  "confidence": 75},
            "🏗️ Portfolio Strategist": {"recommendation": "BUY",  "confidence": 70},
        },
    }
    for i, (sym, price) in enumerate([
        ("NVDA", 105.0), ("MSFT", 103.0), ("AAPL", 98.0),
        ("AMZN", 106.0), ("AMD",  97.0),
    ])
]


class TestBuildPerformanceBrief(unittest.TestCase):
    def setUp(self):
        self.cache_file = tempfile.mktemp(suffix=".json")

    def tearDown(self):
        if os.path.exists(self.cache_file):
            os.unlink(self.cache_file)

    def test_insufficient_history_when_fewer_than_5_trades(self):
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED[:3]):
            from performance_brief import build_performance_brief
            result = build_performance_brief(date(2026, 5, 12))
        self.assertIn("Insufficient history", result)
        self.assertNotIn("Recent Trades", result)

    def test_recent_section_present_on_non_monday(self):
        tuesday = date(2026, 5, 12)
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED):
            from performance_brief import build_performance_brief
            result = build_performance_brief(tuesday)
        self.assertIn("Performance Brief (2026-05-12)", result)
        self.assertIn("Recent Trades", result)
        self.assertIn("Track record:", result)
        self.assertIn("3W / 2L", result)

    def test_patterns_section_absent_on_non_monday(self):
        tuesday = date(2026, 5, 12)
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED):
            from performance_brief import build_performance_brief
            result = build_performance_brief(tuesday)
        self.assertNotIn("30-Day Patterns", result)

    def test_patterns_section_present_on_monday(self):
        monday = date(2026, 5, 11)
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED):
            from performance_brief import build_performance_brief
            result = build_performance_brief(monday)
        self.assertIn("30-Day Patterns", result)
        self.assertIn("Sentiment Analyst out", result)

    def test_caching_avoids_second_log_load(self):
        tuesday = date(2026, 5, 12)
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED) as mock_load:
            from performance_brief import build_performance_brief
            first = build_performance_brief(tuesday)
            second = build_performance_brief(tuesday)
        self.assertEqual(first, second)
        self.assertEqual(mock_load.call_count, 1)

    def test_brief_shows_win_loss_symbols(self):
        tuesday = date(2026, 5, 12)
        with patch("performance_brief.PERFORMANCE_BRIEF_CACHE_FILE", self.cache_file), \
             patch("performance_brief.load_performance_log", return_value=SAMPLE_CLOSED):
            from performance_brief import build_performance_brief
            result = build_performance_brief(tuesday)
        self.assertIn("NVDA", result)
        self.assertIn("+5.0%", result)
        self.assertIn("AAPL", result)
        self.assertIn("-2.0%", result)


if __name__ == "__main__":
    unittest.main()
