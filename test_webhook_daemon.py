import unittest
from unittest.mock import patch

import webhook_daemon
import dashboard_service


class WebhookDaemonTest(unittest.TestCase):
    def setUp(self):
        self.original_heartbeat_file = webhook_daemon.HEARTBEAT_FILE
        self.test_heartbeat_file = "/tmp/mstu_webhook_daemon_heartbeat_test.json"
        webhook_daemon.HEARTBEAT_FILE = self.test_heartbeat_file
        dashboard_service.WEBHOOK_DAEMON_HEARTBEAT_FILE = self.test_heartbeat_file
        if __import__("os").path.exists(self.test_heartbeat_file):
            __import__("os").remove(self.test_heartbeat_file)

    def tearDown(self):
        webhook_daemon.HEARTBEAT_FILE = self.original_heartbeat_file
        dashboard_service.WEBHOOK_DAEMON_HEARTBEAT_FILE = self.original_heartbeat_file
        if __import__("os").path.exists(self.test_heartbeat_file):
            __import__("os").remove(self.test_heartbeat_file)

    def test_run_loop_once_executes_worker_once(self):
        with patch("webhook_daemon.run_webhook_cycle", return_value={"ok": True}) as mock_cycle:
            result = webhook_daemon.run_loop(interval_seconds=60, once=True)

        self.assertTrue(mock_cycle.called)
        self.assertEqual(mock_cycle.call_count, 1)
        self.assertEqual(result["ok"], True)

    def test_run_loop_uses_default_interval(self):
        self.assertEqual(webhook_daemon.DEFAULT_INTERVAL_SECONDS, 60)

    def test_run_loop_once_writes_heartbeat_file(self):
        with patch("webhook_daemon.run_webhook_cycle", return_value={"ok": True, "webhook": {"last_push_status": "success"}}):
            webhook_daemon.run_loop(interval_seconds=60, once=True)

        self.assertTrue(__import__("os").path.exists(self.test_heartbeat_file))
        with open(self.test_heartbeat_file, "r") as f:
            heartbeat = __import__("json").load(f)
        self.assertEqual(heartbeat["interval_seconds"], 60)
        self.assertEqual(heartbeat["last_cycle_status"], "ok")


if __name__ == "__main__":
    unittest.main()
