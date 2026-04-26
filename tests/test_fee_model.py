import unittest
from unittest.mock import patch

from fee_model import BUY, SELL, estimate_fees, estimate_round_trip, max_affordable_shares


class FeeModelTest(unittest.TestCase):
    def test_buy_fee_schedule_matches_broker_rules(self):
        fees = estimate_fees(BUY, price=7.84, shares=89)

        self.assertAlmostEqual(fees.gross_amount, 697.76, places=2)
        self.assertAlmostEqual(fees.total_fees, 1.47, places=2)
        self.assertAlmostEqual(fees.net_amount, -699.23, places=2)

    def test_sell_fee_schedule_and_round_trip_pnl(self):
        fees = estimate_fees(SELL, price=8.02, shares=89)
        round_trip = estimate_round_trip(7.84, 8.02, 89)

        self.assertAlmostEqual(fees.total_fees, 1.50, places=2)
        self.assertAlmostEqual(fees.net_amount, 712.28, places=2)
        self.assertAlmostEqual(round_trip["net_pnl"], 13.05, places=2)

    def test_max_affordable_shares_accounts_for_fees(self):
        self.assertEqual(max_affordable_shares(700.0, 7.84), 89)
        self.assertEqual(max_affordable_shares(699.23, 7.84), 89)

    def test_stamp_duty_can_be_enabled_via_config(self):
        with patch("config.STAMP_DUTY_ENABLED", True), patch("config.STAMP_DUTY_USD_TO_RM_FX", 4.7):
            fees = estimate_fees(BUY, price=10.0, shares=100)

        self.assertAlmostEqual(fees.stamp_duty, 1.06, places=2)
        self.assertAlmostEqual(fees.total_fees, 2.65, places=2)


if __name__ == "__main__":
    unittest.main()
