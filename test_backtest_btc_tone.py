import unittest

from backtest import evaluate_daily_tone_snapshot


class DailyToneSnapshotTest(unittest.TestCase):
    def test_bullish_strong_tone_relaxes_forward_side(self):
        result = evaluate_daily_tone_snapshot(
            mstr_change_pct=2.1,
            mstr_ema_bullish=True,
            mstr_macd_bullish=True,
            mstr_bull_structure_weak=True,
            btc_change_pct=2.3,
            btc_ema_bullish=True,
            btc_price_above_fast=True,
        )

        self.assertEqual(result["tone"], "bullish_strong")
        self.assertEqual(result["forward_bias"], 0.5)
        self.assertEqual(result["reverse_bias"], -0.25)

    def test_bearish_strong_tone_relaxes_reverse_side(self):
        result = evaluate_daily_tone_snapshot(
            mstr_change_pct=-2.2,
            mstr_ema_bullish=False,
            mstr_macd_bullish=False,
            mstr_bull_structure_weak=False,
            btc_change_pct=-2.4,
            btc_ema_bullish=False,
            btc_price_above_fast=False,
        )

        self.assertEqual(result["tone"], "bearish_strong")
        self.assertEqual(result["forward_bias"], -0.25)
        self.assertEqual(result["reverse_bias"], 0.5)


if __name__ == "__main__":
    unittest.main()
