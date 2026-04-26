import os
import tempfile
import unittest

import pandas as pd

from market_data_store import health_check_market_data


class MarketDataHealthTest(unittest.TestCase):
    def test_health_check_reports_missing_layers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = health_check_market_data(
                pairs=[("MSTU", "15m")],
                data_root=tmpdir,
            )

        self.assertEqual(result["status"], "error")
        self.assertTrue(any(item["status"] == "missing" for item in result["checks"]))

    def test_health_check_reports_ok_for_complete_layout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for relpath in [
                "data/latest/mstu/15m.csv",
                "data/archive/mstu/15m/2026-04-25.csv",
                "data/merged/mstu/15m.csv",
            ]:
                path = os.path.join(tmpdir, relpath)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                df = pd.DataFrame(
                    {
                        "Open": [1.0],
                        "High": [1.1],
                        "Low": [0.9],
                        "Close": [1.05],
                        "Volume": [100],
                    },
                    index=pd.to_datetime(["2026-04-24 09:30:00"]),
                )
                df.to_csv(path)

            result = health_check_market_data(
                pairs=[("MSTU", "15m")],
                data_root=tmpdir,
            )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(all(item["status"] == "ok" for item in result["checks"]))


if __name__ == "__main__":
    unittest.main()
