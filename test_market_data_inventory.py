import os
import tempfile
import unittest

import pandas as pd

from market_data_store import market_data_inventory


class MarketDataInventoryTest(unittest.TestCase):
    def test_inventory_summarizes_symbols_and_intervals(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            for relpath in [
                "data/latest/mstu/15m.csv",
                "data/archive/mstu/15m/2026-04-25.csv",
                "data/archive/mstu/15m/2026-05-02.csv",
                "data/merged/mstu/15m.csv",
            ]:
                path = os.path.join(tmpdir, relpath)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                df = pd.DataFrame(
                    {
                        "Open": [1.0, 2.0],
                        "High": [1.1, 2.1],
                        "Low": [0.9, 1.9],
                        "Close": [1.05, 2.05],
                        "Volume": [100, 200],
                    },
                    index=pd.to_datetime(["2026-04-24 09:30:00", "2026-04-24 10:00:00"]),
                )
                df.to_csv(path)

            summary = market_data_inventory(data_root=tmpdir)

        self.assertEqual(summary["status"], "ok")
        self.assertIn("mstu", summary["symbols"])
        self.assertEqual(summary["symbols"]["mstu"]["15m"]["archive_snapshots"], 2)
        self.assertEqual(summary["symbols"]["mstu"]["15m"]["latest_rows"], 2)


if __name__ == "__main__":
    unittest.main()
