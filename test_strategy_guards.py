import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import app_runtime
import config
from strategy import TradingStrategy


class StrategyGuardsTest(unittest.TestCase):
    def setUp(self):
        os.makedirs(os.path.dirname(config.POSITION_STATE_FILE), exist_ok=True)

    def tearDown(self):
        if os.path.exists(config.POSITION_STATE_FILE):
            os.remove(config.POSITION_STATE_FILE)
        if os.path.exists(app_runtime.SQLITE_STATE_FILE):
            os.remove(app_runtime.SQLITE_STATE_FILE)

    def write_position(self, payload):
        with open(config.POSITION_STATE_FILE, "w") as f:
            json.dump(payload, f)

    def test_daily_reset_keeps_position(self):
        self.write_position({
            "holding_shares": 120,
            "buy_price": 7.5,
            "target_price": 7.7,
            "stop_price": 7.3,
            "position_source": "regular",
            "daily_ops_count": 3,
            "daily_pnl": -45.5,
            "available_cash": 888.0,
            "last_reset_date": "2026-04-21",
        })

        fake_now = datetime(2026, 4, 22, 14, 5, tzinfo=timezone.utc)  # 北京 22:05
        with patch("strategy.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            strategy = TradingStrategy()
            strategy.analyze({
                "price": 7.4,
                "prev_close": 7.6,
                "high": 7.6,
                "low": 7.35,
                "volume": 1000000,
                "session": "regular",
            })

        self.assertEqual(strategy.daily_ops_count, 0)
        self.assertEqual(strategy.daily_pnl, 0.0)
        self.assertEqual(strategy.holding_shares, 120)
        self.assertEqual(strategy.last_reset_date, "2026-04-22")

    def test_regular_buy_signal_is_blocked_near_open(self):
        self.write_position({
            "holding_shares": 0,
            "buy_price": 0,
            "target_price": 0,
            "stop_price": 0,
            "position_source": "",
            "daily_ops_count": 0,
            "daily_pnl": 0.0,
            "available_cash": 1400.0,
            "last_reset_date": "2026-04-22",
        })

        fake_now = datetime(2026, 4, 22, 13, 45, tzinfo=timezone.utc)  # 北京 21:45
        with patch("strategy.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            strategy = TradingStrategy()
            result = strategy.analyze({
                "price": 7.35,
                "prev_close": 7.6,
                "high": 7.8,
                "low": 7.3,
                "volume": 10_000_000,
                "session": "regular",
            })

        self.assertEqual(result["action"], "TIME_WINDOW_BLOCKED")
        self.assertEqual(result["signal_type"], "NO_TRADE_WINDOW")
        self.assertIn("新开仓", result["blocked_reason"])

    def test_regular_buy_signal_allowed_inside_window(self):
        self.write_position({
            "holding_shares": 0,
            "buy_price": 0,
            "target_price": 0,
            "stop_price": 0,
            "position_source": "",
            "daily_ops_count": 0,
            "daily_pnl": 0.0,
            "available_cash": 1400.0,
            "last_reset_date": "2026-04-22",
        })

        fake_now = datetime(2026, 4, 22, 14, 15, tzinfo=timezone.utc)  # 北京 22:15
        with patch("strategy.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            strategy = TradingStrategy()
            result = strategy.analyze({
                "price": 7.35,
                "prev_close": 7.6,
                "high": 7.8,
                "low": 7.3,
                "volume": 10_000_000,
                "session": "regular",
            })

        self.assertEqual(result["action"], "BUY")
        self.assertEqual(result["position_source"], "regular")

    def test_regular_buy_signal_can_still_trigger_when_intraday_signals_are_strong(self):
        self.write_position({
            "holding_shares": 0,
            "buy_price": 0,
            "target_price": 0,
            "stop_price": 0,
            "position_source": "",
            "daily_ops_count": 0,
            "daily_pnl": 0.0,
            "available_cash": 1400.0,
            "last_reset_date": "2026-04-22",
        })

        fake_now = datetime(2026, 4, 22, 14, 15, tzinfo=timezone.utc)  # 北京 22:15
        with patch("strategy.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            strategy = TradingStrategy()
            result = strategy.analyze({
                "price": 7.35,
                "prev_close": 7.6,
                "high": 7.8,
                "low": 7.3,
                "volume": 10_000_000,
                "session": "regular",
                "mstr": {
                    "mstr_price": 380.0,
                    "mstr_prev_close": 373.0,
                    "mstr_high": 392.0,
                    "mstr_low": 378.0,
                    "mstr_volume": 60_000_000,
                    "mstr_change_pct": 1.8,
                    "mstr_ema_bullish": False,
                    "mstr_macd_bullish": False,
                }
            })

        self.assertEqual(result["action"], "BUY")
        self.assertFalse(result["mstr_trend_ok"])
        self.assertIn("不直接阻断分时做T", result["reason"])

    def test_regular_buy_signal_allowed_when_mstr_trend_confirmed(self):
        self.write_position({
            "holding_shares": 0,
            "buy_price": 0,
            "target_price": 0,
            "stop_price": 0,
            "position_source": "",
            "daily_ops_count": 0,
            "daily_pnl": 0.0,
            "available_cash": 1400.0,
            "last_reset_date": "2026-04-22",
        })

        fake_now = datetime(2026, 4, 22, 14, 15, tzinfo=timezone.utc)  # 北京 22:15
        with patch("strategy.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            strategy = TradingStrategy()
            result = strategy.analyze({
                "price": 7.35,
                "prev_close": 7.6,
                "high": 7.8,
                "low": 7.3,
                "volume": 10_000_000,
                "session": "regular",
                "mstr": {
                    "mstr_price": 380.0,
                    "mstr_prev_close": 373.0,
                    "mstr_high": 392.0,
                    "mstr_low": 378.0,
                    "mstr_volume": 60_000_000,
                    "mstr_change_pct": 1.8,
                    "mstr_ema_bullish": True,
                    "mstr_macd_bullish": True,
                }
            })

        self.assertEqual(result["action"], "BUY")
        self.assertTrue(result["mstr_trend_ok"])


if __name__ == "__main__":
    unittest.main()
