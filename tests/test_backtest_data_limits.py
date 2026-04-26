import unittest

from backtest import build_intraday_limit_hint


class BacktestDataLimitTest(unittest.TestCase):
    def test_build_intraday_limit_hint_for_long_minute_window(self):
        hint = build_intraday_limit_hint(interval="15m", period="120d")
        self.assertIn("Yahoo", hint)
        self.assertIn("60", hint)
        self.assertIn("15m", hint)


if __name__ == "__main__":
    unittest.main()
