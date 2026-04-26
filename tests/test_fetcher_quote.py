import unittest
from unittest.mock import patch
import runpy
from pathlib import Path

import pandas as pd

import fetcher
import feishu_gateway
from mstu_trading.market_data import fetcher as package_fetcher
from mstu_trading.integrations import feishu_gateway as package_feishu_gateway


class FetcherQuoteTest(unittest.TestCase):
    def test_root_wrapper_and_package_module_share_identity(self):
        self.assertIs(fetcher, package_fetcher)

    def test_feishu_root_wrapper_and_package_module_share_identity(self):
        self.assertIs(feishu_gateway, package_feishu_gateway)

    def test_feishu_root_patch_applies_to_package_calls(self):
        with patch("feishu_gateway.send_webhook_text") as mock_send:
            mock_send.return_value.raise_for_status.return_value = None
            ok, detail = package_feishu_gateway.send_text_message(
                "wrapper patch",
                webhook_url="https://example.com/hook",
                prefer_chat_api=False,
            )

        self.assertTrue(ok)
        self.assertEqual(detail, "webhook")
        self.assertEqual(mock_send.call_count, 1)

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

    def test_root_fetcher_script_executes_package_main(self):
        fetcher_path = Path(__file__).resolve().parent.parent / "fetcher.py"
        with patch("mstu_trading.market_data.fetcher.get_session_type", return_value="regular"), patch(
            "mstu_trading.market_data.fetcher.get_mstu_quote", return_value={"error": "test"}
        ), patch("mstu_trading.market_data.fetcher.format_price_info", return_value="formatted"), patch(
            "builtins.print"
        ) as mock_print:
            runpy.run_path(str(fetcher_path), run_name="__main__")

        mock_print.assert_any_call("当前时段: regular")
        mock_print.assert_any_call("formatted")


if __name__ == "__main__":
    unittest.main()
