import unittest
from unittest.mock import patch

import scheduler
from mstu_trading.integrations import scheduler as package_scheduler


class SchedulerTest(unittest.TestCase):
    def test_root_wrapper_and_package_module_share_identity(self):
        self.assertIs(scheduler, package_scheduler)

    def test_run_mode_webhook_uses_worker_without_group_webhook(self):
        with patch("scheduler.webhook_worker.run_webhook_cycle", return_value={"ok": True, "webhook": {"last_push_status": "success"}}) as mock_worker, patch(
            "scheduler.send_to_webhook"
        ) as mock_group_webhook:
            result = scheduler.run_mode("webhook")

        self.assertTrue(mock_worker.called)
        self.assertFalse(mock_group_webhook.called)
        self.assertEqual(result["webhook"]["last_push_status"], "success")


if __name__ == "__main__":
    unittest.main()
