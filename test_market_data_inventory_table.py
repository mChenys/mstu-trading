import unittest

from market_data_store import format_inventory_table


class MarketDataInventoryTableTest(unittest.TestCase):
    def test_format_inventory_table_returns_human_readable_lines(self):
        inventory = {
            "status": "ok",
            "symbols": {
                "mstu": {
                    "15m": {
                        "archive_snapshots": 2,
                        "latest_rows": 100,
                        "merged_rows": 150,
                        "latest_start": "2026-04-01 09:30:00",
                        "latest_end": "2026-04-25 19:45:00",
                        "merged_start": "2026-03-01 09:30:00",
                        "merged_end": "2026-04-25 19:45:00",
                    }
                }
            },
        }

        text = format_inventory_table(inventory)

        self.assertIn("symbol", text.lower())
        self.assertIn("mstu", text)
        self.assertIn("15m", text)
        self.assertIn("150", text)


if __name__ == "__main__":
    unittest.main()
