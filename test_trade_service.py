import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import app_runtime
import sqlite_storage
import trade_confirmation
import trade_service


class TradeServiceTest(unittest.TestCase):
    def setUp(self):
        self.temp_state_dir = tempfile.mkdtemp(prefix="mstu-trade-service-test-")
        self.original_sqlite_state_file = sqlite_storage.SQLITE_STATE_FILE
        self.original_trade_log_file = trade_confirmation.TRADE_LOG_FILE
        self.original_position_file = trade_confirmation.POSITION_FILE
        sqlite_storage.SQLITE_STATE_FILE = os.path.join(self.temp_state_dir, "state.db")
        trade_confirmation.TRADE_LOG_FILE = os.path.join(self.temp_state_dir, "trade_log.json")
        trade_confirmation.POSITION_FILE = os.path.join(self.temp_state_dir, "position.json")
        self.base_dir = os.path.dirname(trade_confirmation.TRADE_LOG_FILE)
        os.makedirs(self.base_dir, exist_ok=True)
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

    def tearDown(self):
        sqlite_storage.SQLITE_STATE_FILE = self.original_sqlite_state_file
        trade_confirmation.TRADE_LOG_FILE = self.original_trade_log_file
        trade_confirmation.POSITION_FILE = self.original_position_file
        shutil.rmtree(self.temp_state_dir, ignore_errors=True)

    def test_create_trade_proposal_returns_message_and_context(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        result = trade_service.create_trade_proposal(
            signal,
            message_id="proposal-001",
            thread_id="thread-001",
        )

        self.assertIn("message_text", result)
        self.assertIn("trade_id", result)
        self.assertEqual(result["proposal"]["message_context"]["proposal_message_id"], "proposal-001")
        self.assertEqual(result["proposal"]["agent_source"], "unknown")
        self.assertEqual(len(trade_service.list_pending_trades()), 1)

    def test_create_trade_proposal_records_agent_source(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        result = trade_service.create_trade_proposal(
            signal,
            message_id="proposal-hermes-001",
            agent_source="hermes",
        )

        self.assertEqual(result["proposal"]["agent_source"], "hermes")
        context = trade_service.get_trade_context(result["trade_id"])
        self.assertEqual(context["proposal"]["agent_source"], "hermes")
        self.assertEqual(context["events"][-1]["agent_source"], "hermes")

    def test_apply_user_reply_confirms_trade(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        proposal = trade_service.create_trade_proposal(signal, message_id="proposal-001")

        with patch("trade_message_handler.send_trade_execution_notice", return_value=True):
            result = trade_service.apply_user_reply(
                "确认",
                reply_to_id="proposal-001",
                user_message_id="user-001",
            )

        self.assertTrue(result["handled"])
        self.assertEqual(result["position"]["holding_shares"], 89)
        context = trade_service.get_trade_context(proposal["trade_id"])
        self.assertEqual(context["proposal"]["status"], "confirmed_by_user")
        self.assertEqual(context["proposal"]["message_context"]["last_user_reply_id"], "user-001")

    def test_apply_user_reply_is_idempotent_for_same_message_id(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        trade_service.create_trade_proposal(signal, message_id="proposal-dup-002")

        with patch("trade_message_handler.send_trade_execution_notice", return_value=True):
            first = trade_service.apply_user_reply(
                "确认",
                reply_to_id="proposal-dup-002",
                user_message_id="user-dup-002",
            )
            second = trade_service.apply_user_reply(
                "确认",
                reply_to_id="proposal-dup-002",
                user_message_id="user-dup-002",
            )

        self.assertTrue(first["handled"])
        self.assertTrue(second["handled"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["position"]["holding_shares"], 89)
        self.assertEqual(second["position"]["holding_shares"], 89)

    def test_get_trade_context_includes_outbound_messages(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        proposal = trade_service.create_trade_proposal(signal, message_id="proposal-outbound-001")

        from sqlite_storage import record_outbound_message

        record_outbound_message(
            trade_id=proposal["trade_id"],
            event_type="execution_notice_sent",
            message_text="hello trade",
            success=True,
            detail="webhook",
            dedupe_key="trade-outbound-001",
            channel="feishu",
            transport="webhook",
        )

        context = trade_service.get_trade_context(proposal["trade_id"])

        self.assertEqual(len(context["outbound_messages"]), 1)
        self.assertEqual(context["outbound_messages"][0]["trade_id"], proposal["trade_id"])

    def test_expire_trade_marks_pending_proposal_expired(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        proposal = trade_service.create_trade_proposal(signal, message_id="proposal-expire-001")

        result = trade_service.expire_trade(proposal["trade_id"])

        self.assertTrue(result["handled"])
        self.assertEqual(result["proposal"]["status"], "expired")

    def test_run_recovery_scan_auto_expires_stale_pending_trade(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        proposal = trade_service.create_trade_proposal(signal, message_id="proposal-recovery-001")
        future_now = datetime.now(timezone.utc) + timedelta(minutes=31)

        with patch("trade_confirmation._utc_now", return_value=future_now), patch(
            "trade_confirmation._utc_now_iso",
            return_value=future_now.isoformat(),
        ):
            summary = trade_service.run_recovery_scan()

        self.assertEqual(summary["expired_count"], 1)
        self.assertIn(proposal["trade_id"], summary["expired_trade_ids"])
        context = trade_service.get_trade_context(proposal["trade_id"])
        self.assertEqual(context["proposal"]["status"], "expired")

    def test_list_action_required_trades_includes_modified_and_deferred(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        deferred = trade_service.create_trade_proposal(signal, message_id="proposal-ar-001")
        modified = trade_service.create_trade_proposal(signal, message_id="proposal-ar-002")

        trade_service.apply_user_reply(
            "先等等",
            reply_to_id="proposal-ar-001",
            user_message_id="user-ar-001",
        )
        trade_service.apply_user_reply(
            "改成 100股",
            reply_to_id="proposal-ar-002",
            user_message_id="user-ar-002",
        )

        trades = trade_service.list_action_required_trades()
        statuses = {item["trade_id"]: item["status"] for item in trades}

        self.assertEqual(statuses[deferred["trade_id"]], "deferred_by_user")
        self.assertEqual(statuses[modified["trade_id"]], "modified_by_user")

    def test_claim_trade_prevents_other_agent_from_taking_active_claim(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        proposal = trade_service.create_trade_proposal(signal, message_id="proposal-claim-001", agent_source="openclaw")

        first = trade_service.claim_trade(proposal["trade_id"], agent_source="openclaw")
        second = trade_service.claim_trade(proposal["trade_id"], agent_source="hermes")

        self.assertTrue(first["handled"])
        self.assertEqual(first["claimed_by"], "openclaw")
        self.assertEqual(second["claimed_by"], "openclaw")
        context = trade_service.get_trade_context(proposal["trade_id"])
        self.assertEqual(context["claim"]["claimed_by"], "openclaw")

    def test_release_trade_claim_allows_other_agent_to_claim(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        proposal = trade_service.create_trade_proposal(signal, message_id="proposal-claim-002", agent_source="openclaw")

        trade_service.claim_trade(proposal["trade_id"], agent_source="openclaw")
        trade_service.release_trade(proposal["trade_id"], agent_source="openclaw")
        claimed = trade_service.claim_trade(proposal["trade_id"], agent_source="hermes")

        self.assertEqual(claimed["claimed_by"], "hermes")


if __name__ == "__main__":
    unittest.main()
