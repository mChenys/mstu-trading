import json
import os
import tempfile
import unittest
from unittest.mock import patch

import backtest
import optimize_backtest
from mstu_trading.backtest import optimize as package_optimize


class BacktestExperimentTest(unittest.TestCase):
    def test_optimize_root_wrapper_and_package_module_share_identity(self):
        self.assertIs(optimize_backtest, package_optimize)

    def test_quadrant_experiment_returns_all_variants(self):
        fake_metrics = {
            "final_value": 1500.0,
            "return_pct": 7.14,
            "max_drawdown": 5.0,
            "sharpe_ratio": None,
            "total_closed": 10,
            "won": 6,
            "lost": 4,
            "win_rate": 60.0,
        }

        calls = []

        def fake_collect(strategy_class, csv_path=None, cash=1400, commission=0.001, strategy_params=None):
            calls.append(strategy_params)
            return dict(fake_metrics)

        with patch("backtest.collect_backtest_metrics", side_effect=fake_collect):
            result = backtest.run_quadrant_experiment({"mstu": "a.csv", "mstr": "b.csv", "btc": "c.csv"})

        self.assertEqual(set(result["variants"].keys()), {"baseline", "macd_only", "btc_only", "macd_plus_btc"})
        self.assertEqual(len(calls), 4)
        self.assertEqual(result["variants"]["baseline"]["win_rate"], 60.0)
        self.assertEqual(result["variants"]["btc_only"]["params"]["enable_btc_tone"], True)
        self.assertEqual(result["variants"]["macd_only"]["params"]["enable_macd_enhanced"], True)

    def test_save_experiment_result_writes_json_file(self):
        payload = {"experiment": "quadrant", "variants": {"baseline": {"win_rate": 60.0}}}

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = backtest.save_experiment_result(payload, output_dir=tmpdir, filename="test.json")

            self.assertTrue(os.path.exists(output_path))
            with open(output_path, "r") as f:
                saved = json.load(f)

        self.assertEqual(saved["experiment"], "quadrant")
        self.assertEqual(saved["variants"]["baseline"]["win_rate"], 60.0)


if __name__ == "__main__":
    unittest.main()
