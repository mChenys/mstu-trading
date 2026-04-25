import unittest
from unittest.mock import patch

import pandas as pd

import fetcher


class FetcherQuoteTest(unittest.TestCase):
    def test_premarket_quote_uses_last_completed_daily_close_as_prev_close(self):
        info = {
            "preMarketPrice": 7.9605,
            "preMarketChangePercent": -4.21,
            "regularMarketPrice": 7.95,
            "regularMarketPreviousClose": 7.02,
            "previousClose": 7.02,
        }
        daily_hist = pd.DataFrame(
            {
                "Open": [8.45, 8.31],
                "High": [8.52, 8.66],
                "Low": [8.16, 7.94],
                "Close": [8.32, 8.32],
                "Volume": [10_000_000, 60_517_000],
            },
            index=pd.to_datetime(["2026-04-21", "2026-04-22"]),
        )

        class FakeTicker:
            def __init__(self, info_payload, hist_payload):
                self.info = info_payload
                self._hist = hist_payload

            def history(self, period="5d"):
                return self._hist

        with patch.object(fetcher, "get_session_type", return_value="premarket"), patch.object(
            fetcher.yf, "Ticker", return_value=FakeTicker(info, daily_hist)
        ):
            quote = fetcher.get_yahoo_quote("MSTU")

        self.assertEqual(quote["prev_close"], 8.32)
        self.assertAlmostEqual(quote["change_pct"], -4.32, places=2)
        self.assertAlmostEqual(quote["premarket_change_pct"], -4.21, places=2)


if __name__ == "__main__":
    unittest.main()
