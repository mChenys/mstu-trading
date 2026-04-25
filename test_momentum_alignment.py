import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd

import app_runtime
import config
import fetcher
from strategy import TradingStrategy


class MomentumAlignmentTest(unittest.TestCase):
    def setUp(self):
        os.makedirs(os.path.dirname(config.POSITION_STATE_FILE), exist_ok=True)
        fetcher._trend_cache.clear()

    def tearDown(self):
        if os.path.exists(config.POSITION_STATE_FILE):
            os.remove(config.POSITION_STATE_FILE)
        if os.path.exists(app_runtime.SQLITE_STATE_FILE):
            os.remove(app_runtime.SQLITE_STATE_FILE)
        fetcher._trend_cache.clear()

    def write_position(self, payload):
        with open(config.POSITION_STATE_FILE, "w") as f:
            json.dump(payload, f)

    def test_trend_snapshot_marks_continuation_above_vwap_as_momentum_ready(self):
        index = pd.date_range("2026-04-22 09:30", periods=25, freq="15min", tz="America/New_York")
        opens = [100.0] + [100.3 + i * 0.35 for i in range(24)]
        closes = [100.2] + [100.5 + i * 0.35 for i in range(24)]
        closes[-2] = 108.8
        closes[-1] = 109.2
        highs = [c + 0.25 for c in closes]
        lows = [o - 0.25 for o in opens]
        volumes = [1000] * 24 + [1600]
        hist = pd.DataFrame(
            {
                "Open": opens,
                "High": highs,
                "Low": lows,
                "Close": closes,
                "Volume": volumes,
            },
            index=index,
        )

        class FakeTicker:
            def history(self, period=None, interval=None):
                return hist

        with patch.object(fetcher.yf, "Ticker", return_value=FakeTicker()):
            snapshot = fetcher.get_yahoo_trend_snapshot("MSTR", period="5d", interval="15m", ttl_seconds=0)

        self.assertNotIn("error", snapshot)
        self.assertFalse(snapshot["vwap_cross_up"])
        self.assertTrue(snapshot["vwap_hold_above"])
        self.assertTrue(snapshot["vwap_momentum_ready"])

    def test_regular_analysis_uses_continuation_language_for_momentum_ready(self):
        self.write_position(
            {
                "holding_shares": 0,
                "buy_price": 0,
                "target_price": 0,
                "stop_price": 0,
                "position_source": "",
                "daily_ops_count": 0,
                "daily_pnl": 0.0,
                "available_cash": 1400.0,
                "last_reset_date": "2026-04-22",
            }
        )

        fake_now = datetime(2026, 4, 22, 14, 15, tzinfo=timezone.utc)
        with patch("strategy.datetime") as mock_dt:
            mock_dt.now.return_value = fake_now
            strategy = TradingStrategy()
            result = strategy.analyze(
                {
                    "price": 7.35,
                    "prev_close": 7.2,
                    "high": 7.4,
                    "low": 7.25,
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
                        "mstr_vwap_momentum_ready": True,
                        "mstr_vwap_cross_up": False,
                        "mstr_vwap_hold_above": True,
                        "mstr_volume_expanding": True,
                        "mstr_volume_ratio": 1.6,
                        "mstr_gap_too_big": False,
                        "mstr_bull_structure_weak": True,
                        "mstr_bull_structure_strong": False,
                    },
                }
            )

        self.assertEqual(result["action"], "BUY")
        self.assertIn("VWAP上方延续启动", result["reason"])
        self.assertNotIn("VWAP上穿 + 量比", result["reason"])


if __name__ == "__main__":
    unittest.main()
