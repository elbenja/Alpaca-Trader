import json
import os
import tempfile
import unittest
from unittest.mock import patch


class TestLoadPerformanceLog(unittest.TestCase):
    def test_returns_empty_list_when_file_missing(self):
        with patch("performance_tracker.PERFORMANCE_LOG_FILE", "/nonexistent/path.json"):
            from performance_tracker import load_performance_log
            result = load_performance_log()
        self.assertEqual(result, [])

    def test_returns_empty_list_on_corrupt_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("not valid json{{{")
            tmp = f.name
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp):
                from performance_tracker import load_performance_log
                result = load_performance_log()
            self.assertEqual(result, [])
        finally:
            os.unlink(tmp)


class TestSaveLoadRoundtrip(unittest.TestCase):
    def test_save_and_load_returns_same_data(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            tmp = f.name
        try:
            sample = [{"order_id": "abc", "symbol": "NVDA", "status": "open"}]
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp):
                from performance_tracker import save_performance_log, load_performance_log
                save_performance_log(sample)
                result = load_performance_log()
            self.assertEqual(result, sample)
        finally:
            os.unlink(tmp)


class TestAppendPerformanceEntry(unittest.TestCase):
    def test_appends_phase1_entry_with_correct_fields(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([], f)
            tmp = f.name
        try:
            opinions = [
                {"advisor": "📈 Momentum Analyst", "recommendation": "BUY", "confidence": 80},
                {"advisor": "🛡️ Risk Manager", "recommendation": "PASS", "confidence": 60},
            ]
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp):
                from performance_tracker import append_performance_entry, load_performance_log
                append_performance_entry(
                    order_id="ord-123",
                    symbol="NVDA",
                    side="buy",
                    qty=5,
                    entry_price=450.00,
                    entry_date="2026-05-12",
                    advisor_votes=opinions,
                )
                log = load_performance_log()
            self.assertEqual(len(log), 1)
            entry = log[0]
            self.assertEqual(entry["order_id"], "ord-123")
            self.assertEqual(entry["symbol"], "NVDA")
            self.assertEqual(entry["status"], "open")
            self.assertIsNone(entry["exit_price"])
            self.assertIsNone(entry["outcome"])
            self.assertIn("📈 Momentum Analyst", entry["advisor_votes"])
            self.assertEqual(
                entry["advisor_votes"]["📈 Momentum Analyst"]["recommendation"], "BUY"
            )
            self.assertEqual(
                entry["advisor_votes"]["🛡️ Risk Manager"]["recommendation"], "PASS"
            )
        finally:
            os.unlink(tmp)

    def test_appends_to_existing_entries(self):
        existing = [{"order_id": "old-1", "symbol": "MSFT", "status": "closed"}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(existing, f)
            tmp = f.name
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp):
                from performance_tracker import append_performance_entry, load_performance_log
                append_performance_entry(
                    order_id="ord-2",
                    symbol="AAPL",
                    side="buy",
                    qty=3,
                    entry_price=200.0,
                    entry_date="2026-05-12",
                    advisor_votes=[],
                )
                log = load_performance_log()
            self.assertEqual(len(log), 2)
            self.assertEqual(log[0]["order_id"], "old-1")
            self.assertEqual(log[1]["order_id"], "ord-2")
        finally:
            os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
