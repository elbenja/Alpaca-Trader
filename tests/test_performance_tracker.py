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


class TestSyncClosedTrades(unittest.TestCase):
    def test_returns_zero_when_log_is_empty(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([], f)
            tmp = f.name
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp):
                from performance_tracker import sync_closed_trades
                result = sync_closed_trades()
            self.assertEqual(result, 0)
        finally:
            os.unlink(tmp)

    def test_does_not_close_entry_when_position_still_open(self):
        entry = {
            "order_id": "ord-1", "symbol": "NVDA", "side": "buy",
            "qty": 5, "entry_price": 450.0, "entry_date": "2026-05-01",
            "advisor_votes": {}, "status": "open",
            "exit_price": None, "exit_date": None, "pnl_pct": None, "outcome": None,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([entry], f)
            tmp = f.name
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp), \
                 patch("performance_tracker.get_positions", return_value=[{"symbol": "NVDA"}]):
                from performance_tracker import sync_closed_trades, load_performance_log
                result = sync_closed_trades()
                log = load_performance_log()
            self.assertEqual(result, 0)
            self.assertEqual(log[0]["status"], "open")
        finally:
            os.unlink(tmp)

    def test_closes_entry_and_computes_win(self):
        entry = {
            "order_id": "ord-2", "symbol": "MSFT", "side": "buy",
            "qty": 10, "entry_price": 380.0, "entry_date": "2026-04-13",
            "advisor_votes": {}, "status": "open",
            "exit_price": None, "exit_date": None, "pnl_pct": None, "outcome": None,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([entry], f)
            tmp = f.name
        from unittest.mock import MagicMock
        fill_resp = MagicMock()
        fill_resp.raise_for_status = MagicMock()
        fill_resp.json.return_value = [
            {
                "symbol": "MSFT", "side": "sell",
                "price": "399.0",
                "transaction_time": "2026-04-15T14:00:00Z",
            }
        ]
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp), \
                 patch("performance_tracker.get_positions", return_value=[]), \
                 patch("performance_tracker.requests.get", return_value=fill_resp):
                from performance_tracker import sync_closed_trades, load_performance_log
                result = sync_closed_trades()
                log = load_performance_log()
            self.assertEqual(result, 1)
            closed = log[0]
            self.assertEqual(closed["status"], "closed")
            self.assertAlmostEqual(closed["exit_price"], 399.0)
            self.assertEqual(closed["exit_date"], "2026-04-15")
            self.assertAlmostEqual(closed["pnl_pct"], 5.0, places=1)
            self.assertEqual(closed["outcome"], "win")
        finally:
            os.unlink(tmp)

    def test_closes_entry_and_computes_loss(self):
        entry = {
            "order_id": "ord-3", "symbol": "AMD", "side": "buy",
            "qty": 8, "entry_price": 200.0, "entry_date": "2026-04-20",
            "advisor_votes": {}, "status": "open",
            "exit_price": None, "exit_date": None, "pnl_pct": None, "outcome": None,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([entry], f)
            tmp = f.name
        from unittest.mock import MagicMock
        fill_resp = MagicMock()
        fill_resp.raise_for_status = MagicMock()
        fill_resp.json.return_value = [
            {
                "symbol": "AMD", "side": "sell",
                "price": "196.0",
                "transaction_time": "2026-04-21T10:00:00Z",
            }
        ]
        try:
            with patch("performance_tracker.PERFORMANCE_LOG_FILE", tmp), \
                 patch("performance_tracker.get_positions", return_value=[]), \
                 patch("performance_tracker.requests.get", return_value=fill_resp):
                from performance_tracker import sync_closed_trades, load_performance_log
                result = sync_closed_trades()
                log = load_performance_log()
            self.assertEqual(result, 1)
            self.assertEqual(log[0]["outcome"], "loss")
            self.assertAlmostEqual(log[0]["pnl_pct"], -2.0, places=1)
        finally:
            os.unlink(tmp)


if __name__ == "__main__":
    unittest.main()
