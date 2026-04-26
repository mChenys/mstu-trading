import os
import tempfile
import unittest

import pandas as pd

from market_data_store import (
    archive_snapshot_path,
    latest_data_path,
    merge_archived_snapshots,
    record_snapshot_from_csv,
)


class MarketDataStoreTest(unittest.TestCase):
    def test_paths_follow_latest_archive_layout(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            latest = latest_data_path("BTC-USD", "15m", data_root=tmpdir)
            archive = archive_snapshot_path("BTC-USD", "15m", "2026-04-25", data_root=tmpdir)

        self.assertTrue(latest.endswith("data/latest/btc-usd/15m.csv"))
        self.assertTrue(archive.endswith("data/archive/btc-usd/15m/2026-04-25.csv"))

    def test_record_snapshot_updates_archive_and_latest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_csv = os.path.join(tmpdir, "source.csv")
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
            df.to_csv(source_csv)

            result = record_snapshot_from_csv(
                symbol="MSTU",
                interval="15m",
                source_csv=source_csv,
                snapshot_date="2026-04-25",
                data_root=tmpdir,
            )

            self.assertTrue(os.path.exists(result["archive"]))
            self.assertTrue(os.path.exists(result["latest"]))

    def test_record_snapshot_keeps_existing_archive_snapshot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source_csv = os.path.join(tmpdir, "source.csv")
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
            df.to_csv(source_csv)

            first = record_snapshot_from_csv(
                symbol="MSTU",
                interval="15m",
                source_csv=source_csv,
                snapshot_date="2026-04-25",
                data_root=tmpdir,
            )
            second = record_snapshot_from_csv(
                symbol="MSTU",
                interval="15m",
                source_csv=source_csv,
                snapshot_date="2026-04-25",
                data_root=tmpdir,
            )

            self.assertNotEqual(first["archive"], second["archive"])
            self.assertTrue(os.path.exists(first["archive"]))
            self.assertTrue(os.path.exists(second["archive"]))

    def test_merge_archived_snapshots_deduplicates_and_sorts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_dir = os.path.join(tmpdir, "data", "archive", "mstu", "15m")
            os.makedirs(archive_dir, exist_ok=True)

            first = pd.DataFrame(
                {
                    "Open": [1.0, 2.0],
                    "High": [1.1, 2.1],
                    "Low": [0.9, 1.9],
                    "Close": [1.05, 2.05],
                    "Volume": [100, 200],
                },
                index=pd.to_datetime(["2026-04-20 09:30:00", "2026-04-20 10:00:00"]),
            )
            second = pd.DataFrame(
                {
                    "Open": [2.0, 3.0],
                    "High": [2.1, 3.1],
                    "Low": [1.9, 2.9],
                    "Close": [2.05, 3.05],
                    "Volume": [200, 300],
                },
                index=pd.to_datetime(["2026-04-20 10:00:00", "2026-04-20 10:30:00"]),
            )
            first.to_csv(os.path.join(archive_dir, "2026-04-20.csv"))
            second.to_csv(os.path.join(archive_dir, "2026-04-21.csv"))

            merged_path = merge_archived_snapshots("MSTU", "15m", data_root=tmpdir)
            merged = pd.read_csv(merged_path, index_col=0)

            self.assertEqual(len(merged), 3)
            self.assertEqual(list(merged.index), [
                "2026-04-20 09:30:00",
                "2026-04-20 10:00:00",
                "2026-04-20 10:30:00",
            ])


if __name__ == "__main__":
    unittest.main()
