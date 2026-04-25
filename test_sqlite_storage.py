import json
import os
import sqlite3
import unittest
from unittest import mock

import app_runtime
import feishu_gateway
import trade_confirmation
import trade_service


class SqliteStorageTest(unittest.TestCase):
    def setUp(self):
        self.paths = [
            trade_confirmation.TRADE_LOG_FILE,
            trade_confirmation.POSITION_FILE,
            app_runtime.SQLITE_STATE_FILE,
        ]
        os.makedirs(os.path.dirname(trade_confirmation.TRADE_LOG_FILE), exist_ok=True)
        for path in self.paths:
            if os.path.exists(path):
                os.remove(path)

    def tearDown(self):
        for path in self.paths:
            if os.path.exists(path):
                os.remove(path)

    def test_log_pending_trade_persists_to_sqlite_and_json(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        trade_id = trade_confirmation.generate_trade_id(signal)
        trade_confirmation.log_pending_trade(signal, trade_id)

        self.assertTrue(os.path.exists(app_runtime.SQLITE_STATE_FILE))
        self.assertTrue(os.path.exists(trade_confirmation.TRADE_LOG_FILE))

        conn = sqlite3.connect(app_runtime.SQLITE_STATE_FILE)
        try:
            row = conn.execute("SELECT value_json FROM kv_store WHERE key = 'trade_log'").fetchone()
            trade_row = conn.execute("SELECT proposal_type FROM trade_records WHERE trade_id = ?", (trade_id,)).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(trade_row[0], "trade_execution_request")

        with open(trade_confirmation.TRADE_LOG_FILE, "r") as f:
            payload = json.load(f)
        self.assertEqual(payload["trades"][0]["trade_id"], trade_id)

    def test_confirm_trade_bootstraps_position_from_json_into_sqlite(self):
        with open(trade_confirmation.POSITION_FILE, "w") as f:
            json.dump(
                {
                    "symbol": "MSTU",
                    "shares": 3000,
                    "holding_shares": 0,
                    "available_cash": 1400,
                    "buy_price": 0,
                    "target_price": 0,
                    "stop_price": 0,
                    "position_source": "",
                    "daily_ops_count": 0,
                    "daily_pnl": 0.0,
                },
                f,
            )

        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        trade_id = trade_confirmation.generate_trade_id(signal)
        trade = trade_confirmation.log_pending_trade(signal, trade_id)
        position = trade_confirmation.confirm_trade(trade)

        self.assertEqual(position["holding_shares"], 89)
        self.assertAlmostEqual(position["available_cash"], 700.77, places=2)
        self.assertAlmostEqual(position["holding_cost_basis"], 699.23, places=2)
        conn = sqlite3.connect(app_runtime.SQLITE_STATE_FILE)
        try:
            row = conn.execute("SELECT value_json FROM kv_store WHERE key = 'position_state'").fetchone()
            snapshot_row = conn.execute("SELECT holding_shares FROM position_snapshots WHERE snapshot_key = 'current'").fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(snapshot_row[0], 89)

    def test_trade_events_are_recorded_for_proposal_lifecycle(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        proposal = trade_service.create_trade_proposal(
            signal,
            message_id="proposal-001",
            thread_id="thread-001",
        )
        trade_id = proposal["trade_id"]

        with open(trade_confirmation.POSITION_FILE, "w") as f:
            json.dump(
                {
                    "symbol": "MSTU",
                    "shares": 3000,
                    "holding_shares": 0,
                    "available_cash": 1400,
                    "buy_price": 0,
                    "target_price": 0,
                    "stop_price": 0,
                    "position_source": "",
                    "daily_ops_count": 0,
                    "daily_pnl": 0.0,
                },
                f,
            )

        result = trade_service.apply_user_reply(
            "确认",
            reply_to_id="proposal-001",
            user_message_id="user-001",
        )
        self.assertTrue(result["handled"])
        context = trade_service.get_trade_context(trade_id)
        event_types = [event["event_type"] for event in context["events"]]
        self.assertIn("proposal_created", event_types)
        self.assertIn("proposal_context_attached", event_types)
        self.assertIn("user_reply_recorded", event_types)
        self.assertIn("trade_confirmed", event_types)

    def test_agent_source_and_claim_are_persisted(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        proposal = trade_service.create_trade_proposal(
            signal,
            message_id="proposal-agent-001",
            agent_source="hermes",
        )
        trade_service.claim_trade(proposal["trade_id"], agent_source="hermes")

        conn = sqlite3.connect(app_runtime.SQLITE_STATE_FILE)
        try:
            trade_row = conn.execute(
                "SELECT agent_source, claimed_by FROM trade_records WHERE trade_id = ?",
                (proposal["trade_id"],),
            ).fetchone()
            event_row = conn.execute(
                "SELECT agent_source FROM message_events WHERE trade_id = ? ORDER BY event_id DESC LIMIT 1",
                (proposal["trade_id"],),
            ).fetchone()
        finally:
            conn.close()

        self.assertEqual(trade_row[0], "hermes")
        self.assertEqual(trade_row[1], "hermes")
        self.assertEqual(event_row[0], "hermes")

    def test_outbound_messages_are_recorded_and_deduped(self):
        with mock.patch("feishu_gateway.send_webhook_text") as mock_send:
            mock_send.return_value.raise_for_status.return_value = None
            ok1, detail1 = feishu_gateway.send_text_message(
                "hello outbound",
                webhook_url="https://example.com/hook",
                prefer_chat_api=False,
                record_outbound=True,
                outbound_event_type="test_outbound",
                dedupe_key="outbound-001",
            )
            ok2, detail2 = feishu_gateway.send_text_message(
                "hello outbound",
                webhook_url="https://example.com/hook",
                prefer_chat_api=False,
                record_outbound=True,
                outbound_event_type="test_outbound",
                dedupe_key="outbound-001",
            )

        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertEqual(detail1, "webhook")
        self.assertEqual(detail2, "idempotent")
        self.assertEqual(mock_send.call_count, 1)


if __name__ == "__main__":
    unittest.main()
