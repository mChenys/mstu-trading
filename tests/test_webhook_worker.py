import json
import os
import unittest
from unittest.mock import patch

import config
import dashboard_service
import webhook_worker
from mstu_trading.integrations import webhook_worker as package_webhook_worker


class WebhookWorkerTest(unittest.TestCase):
    def test_root_wrapper_and_package_module_share_identity(self):
        self.assertIs(webhook_worker, package_webhook_worker)

    def setUp(self):
        self.webhook_state_file = os.path.join(
            os.path.dirname(config.POSITION_STATE_FILE), "webhook_config_test_worker.json"
        )
        self.original_webhook_state_file = dashboard_service.WEBHOOK_CONFIG_FILE
        dashboard_service.WEBHOOK_CONFIG_FILE = self.webhook_state_file
        webhook_worker.dashboard_service.WEBHOOK_CONFIG_FILE = self.webhook_state_file
        if os.path.exists(self.webhook_state_file):
            os.remove(self.webhook_state_file)

    def tearDown(self):
        dashboard_service.WEBHOOK_CONFIG_FILE = self.original_webhook_state_file
        webhook_worker.dashboard_service.WEBHOOK_CONFIG_FILE = self.original_webhook_state_file
        if os.path.exists(self.webhook_state_file):
            os.remove(self.webhook_state_file)

    def test_worker_pushes_trade_signal(self):
        with open(self.webhook_state_file, "w") as f:
            json.dump(
                {
                    "url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                    "mode": "trade_only",
                    "enabled": True,
                    "last_signature": "",
                },
                f,
            )

        with patch("webhook_worker.get_mstu_quote") as mock_quote, patch(
            "webhook_worker.TradingStrategy"
        ) as mock_strategy_cls, patch("dashboard_service.requests.post") as mock_post:
            mock_quote.return_value = {
                "symbol": "MSTU",
                "price": 7.35,
                "prev_close": 7.20,
                "high": 7.40,
                "low": 7.21,
                "volume": 1000000,
                "session": "regular",
                "change_pct": 2.08,
                "mstr": {
                    "mstr_price": 380.0,
                    "mstr_change_pct": 1.8,
                },
            }
            mock_strategy = mock_strategy_cls.return_value
            mock_strategy.analyze.return_value = {
                "action": "BUY",
                "reason": "VWAP上方延续启动",
                "signals": ["VWAP上方延续启动"],
            }
            mock_post.return_value.raise_for_status.return_value = None

            result = webhook_worker.run_webhook_cycle()

        self.assertTrue(mock_post.called)
        self.assertEqual(result["webhook"]["last_push_status"], "success")

    def test_worker_deduplicates_signal(self):
        with open(self.webhook_state_file, "w") as f:
            json.dump(
                {
                    "url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                    "mode": "all",
                    "enabled": True,
                    "last_signature": "WATCH|PREMARKET|盘前参考MSTR+7.1%，无明确信号|7.93",
                },
                f,
            )

        with patch("webhook_worker.get_mstu_quote") as mock_quote, patch(
            "webhook_worker.TradingStrategy"
        ) as mock_strategy_cls, patch("dashboard_service.requests.post") as mock_post:
            mock_quote.return_value = {
                "symbol": "MSTU",
                "price": 7.93,
                "prev_close": 8.32,
                "high": 8.66,
                "low": 7.94,
                "volume": 60517000,
                "session": "premarket",
                "change_pct": -4.32,
                "mstr": {
                    "mstr_price": 175.57,
                    "mstr_change_pct": -2.17,
                },
            }
            mock_strategy = mock_strategy_cls.return_value
            mock_strategy.analyze.return_value = {
                "action": "PREMARKET",
                "reason": "盘前参考MSTR+7.1%，无明确信号",
                "signals": ["⚠️ MSTR高开+7.1%，涨幅过大不追"],
            }

            result = webhook_worker.run_webhook_cycle()

        self.assertFalse(mock_post.called)
        self.assertEqual(result["webhook"]["last_push_status"], "deduped")


if __name__ == "__main__":
    unittest.main()
