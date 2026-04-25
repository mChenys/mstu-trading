import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import app_runtime
import sqlite_storage
import trade_confirmation
import trade_message_handler
from trade_confirmation import attach_trade_message_context, generate_trade_id, log_pending_trade
from trade_message_handler import handle_trade_message


class TradeMessageHandlerTest(unittest.TestCase):
    def setUp(self):
        self.temp_state_dir = tempfile.mkdtemp(prefix="mstu-message-handler-test-")
        self.original_sqlite_state_file = sqlite_storage.SQLITE_STATE_FILE
        self.original_trade_log_file = trade_confirmation.TRADE_LOG_FILE
        self.original_position_file = trade_confirmation.POSITION_FILE
        self.original_handler_position_file = trade_message_handler.POSITION_FILE
        sqlite_storage.SQLITE_STATE_FILE = os.path.join(self.temp_state_dir, "state.db")
        trade_confirmation.TRADE_LOG_FILE = os.path.join(self.temp_state_dir, "trade_log.json")
        trade_confirmation.POSITION_FILE = os.path.join(self.temp_state_dir, "position.json")
        trade_message_handler.POSITION_FILE = trade_confirmation.POSITION_FILE
        self.base_dir = os.path.dirname(trade_confirmation.TRADE_LOG_FILE)
        os.makedirs(self.base_dir, exist_ok=True)

        with open(trade_confirmation.POSITION_FILE, "w") as f:
            json.dump({
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
            }, f)

    def tearDown(self):
        sqlite_storage.SQLITE_STATE_FILE = self.original_sqlite_state_file
        trade_confirmation.TRADE_LOG_FILE = self.original_trade_log_file
        trade_confirmation.POSITION_FILE = self.original_position_file
        trade_message_handler.POSITION_FILE = self.original_handler_position_file
        shutil.rmtree(self.temp_state_dir, ignore_errors=True)

    def test_confirm_uses_trade_id_from_reply_text(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%"
        }
        trade_id = generate_trade_id(signal)
        log_pending_trade(signal, trade_id)

        reply_text = f"🟢 **MSTU 买入建议**\n📋 交易ID: `{trade_id}`"
        with patch("trade_message_handler.send_trade_execution_notice", return_value=True) as mock_notify:
            result = handle_trade_message("确认", reply_to_text=reply_text)

        self.assertTrue(result["handled"])
        self.assertEqual(result["position"]["holding_shares"], 89)
        self.assertEqual(result["position"]["position_source"], "premarket-momentum")
        self.assertTrue(result["notification_sent"])
        mock_notify.assert_called_once()

        with open(trade_confirmation.TRADE_LOG_FILE, "r") as f:
            log = json.load(f)
        self.assertEqual(log["trades"][0]["status"], "confirmed_by_user")
        self.assertEqual(log["trades"][0]["message_context"]["last_user_reply_text"], "确认")

    def test_confirm_without_pending_trade_returns_clear_message(self):
        result = handle_trade_message("确认")

        self.assertTrue(result["handled"])
        self.assertEqual(result["action"], "confirm")
        self.assertIn("未找到待确认交易", result["result"])

    def test_sell_confirmation_updates_cash_pnl_and_clears_position(self):
        with open(trade_confirmation.POSITION_FILE, "w") as f:
            json.dump({
                "symbol": "MSTU",
                "shares": 3000,
                "holding_shares": 89,
                "available_cash": 700.77,
                "buy_price": 7.84,
                "holding_cost_basis": 699.23,
                "target_price": 7.93,
                "stop_price": 7.78,
                "position_source": "premarket-momentum",
                "daily_ops_count": 1,
                "daily_pnl": 0.0,
                "daily_fees": 1.47,
            }, f)

        signal = {
            "action": "SELL",
            "price": 8.02,
            "shares": 89,
            "reason": "达到目标价",
        }
        trade_id = generate_trade_id(signal)
        log_pending_trade(signal, trade_id)

        reply_text = f"🎯 卖出提醒\n🔢 卖出ID: {trade_id}"
        with patch("trade_message_handler.send_trade_execution_notice", return_value=True) as mock_notify:
            result = handle_trade_message("确认", reply_to_text=reply_text)

        self.assertTrue(result["handled"])
        self.assertEqual(result["position"]["holding_shares"], 0)
        self.assertAlmostEqual(result["position"]["available_cash"], 1413.05, places=2)
        self.assertAlmostEqual(result["position"]["daily_pnl"], 13.05, places=2)
        self.assertAlmostEqual(result["position"]["daily_fees"], 2.97, places=2)
        self.assertEqual(result["position"]["position_source"], "")
        self.assertTrue(result["notification_sent"])
        mock_notify.assert_called_once()

        with open(trade_confirmation.TRADE_LOG_FILE, "r") as f:
            log = json.load(f)
        self.assertEqual(log["trades"][-1]["proposal_type"], "trade_execution_request")
        self.assertEqual(log["trades"][-1]["status"], "confirmed_by_user")

    def test_reject_pending_trade_sends_execution_notice(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%"
        }
        trade_id = generate_trade_id(signal)
        log_pending_trade(signal, trade_id)

        with patch("trade_message_handler.send_trade_execution_notice", return_value=True) as mock_notify:
            result = handle_trade_message(f"取消 {trade_id}")

        self.assertTrue(result["handled"])
        self.assertEqual(result["action"], "trade_rejected")
        self.assertTrue(result["notification_sent"])
        mock_notify.assert_called_once()

    def test_confirm_uses_reply_to_id_context(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%"
        }
        trade_id = generate_trade_id(signal)
        log_pending_trade(signal, trade_id)
        attach_trade_message_context(
            trade_id,
            message_id="msg-proposal-001",
            thread_id="thread-001",
            message_text="proposal text",
        )

        with patch("trade_message_handler.send_trade_execution_notice", return_value=True):
            result = handle_trade_message(
                "确认",
                reply_to_id="msg-proposal-001",
                user_message_id="msg-user-001",
            )

        self.assertTrue(result["handled"])
        self.assertEqual(result["position"]["holding_shares"], 89)
        self.assertAlmostEqual(result["position"]["available_cash"], 700.77, places=2)
        self.assertAlmostEqual(result["position"]["holding_cost_basis"], 699.23, places=2)
        with open(trade_confirmation.TRADE_LOG_FILE, "r") as f:
            log = json.load(f)
        self.assertEqual(log["trades"][0]["message_context"]["proposal_message_id"], "msg-proposal-001")
        self.assertEqual(log["trades"][0]["message_context"]["last_user_reply_id"], "msg-user-001")

    def test_manual_sell_confirmation_creates_standard_trade_record(self):
        with open(trade_confirmation.POSITION_FILE, "w") as f:
            json.dump({
                "symbol": "MSTU",
                "shares": 3000,
                "holding_shares": 95,
                "available_cash": 706.3,
                "buy_price": 7.84,
                "target_price": 7.93,
                "stop_price": 7.78,
                "position_source": "regular",
                "daily_ops_count": 0,
                "daily_pnl": 0.0,
            }, f)

        with patch("trade_message_handler.send_trade_execution_notice", return_value=True):
            result = handle_trade_message("昨晚已经止损了这 95 股，7.08 卖出了")

        self.assertTrue(result["handled"])
        self.assertEqual(result["action"], "sell_confirm")
        with open(trade_confirmation.TRADE_LOG_FILE, "r") as f:
            log = json.load(f)
        manual_trade = log["trades"][-1]
        self.assertEqual(manual_trade["proposal_type"], "manual_execution_report")
        self.assertEqual(manual_trade["status"], "confirmed_by_user")
        self.assertEqual(manual_trade["action"], "SELL")
        self.assertEqual(manual_trade["message_context"]["interaction_type"], "manual_execution_report")

    def test_manual_buy_confirmation_creates_standard_trade_record(self):
        with patch("trade_message_handler.send_trade_execution_notice", return_value=True):
            result = handle_trade_message("已买入 7.84 89股")

        self.assertTrue(result["handled"])
        self.assertEqual(result["action"], "buy_confirm")
        self.assertAlmostEqual(result["position"]["available_cash"], 700.77, places=2)
        self.assertAlmostEqual(result["position"]["daily_fees"], 1.47, places=2)
        with open(trade_confirmation.TRADE_LOG_FILE, "r") as f:
            log = json.load(f)
        manual_trade = log["trades"][-1]
        self.assertEqual(manual_trade["proposal_type"], "manual_execution_report")
        self.assertEqual(manual_trade["status"], "confirmed_by_user")
        self.assertEqual(manual_trade["action"], "BUY")
        self.assertAlmostEqual(manual_trade["fees"], 1.47, places=2)

    def test_duplicate_user_reply_is_idempotent_for_pending_trade(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%"
        }
        trade_id = generate_trade_id(signal)
        log_pending_trade(signal, trade_id)
        attach_trade_message_context(trade_id, message_id="proposal-dup-001")

        with patch("trade_message_handler.send_trade_execution_notice", return_value=True):
            first = handle_trade_message(
                "确认",
                reply_to_id="proposal-dup-001",
                user_message_id="user-dup-001",
            )
            second = handle_trade_message(
                "确认",
                reply_to_id="proposal-dup-001",
                user_message_id="user-dup-001",
            )

        self.assertTrue(first["handled"])
        self.assertTrue(second["handled"])
        self.assertTrue(second["idempotent"])
        self.assertTrue(second["duplicate_message"])
        self.assertEqual(first["position"]["holding_shares"], 89)
        self.assertEqual(second["position"]["holding_shares"], 89)

    def test_duplicate_manual_buy_reply_is_idempotent(self):
        with patch("trade_message_handler.send_trade_execution_notice", return_value=True):
            first = handle_trade_message("已买入 7.84 89股", user_message_id="manual-dup-001")
            second = handle_trade_message("已买入 7.84 89股", user_message_id="manual-dup-001")

        self.assertTrue(first["handled"])
        self.assertTrue(second["handled"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(first["trade_id"], second["trade_id"])

    def test_defer_reply_marks_trade_deferred(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%"
        }
        trade_id = generate_trade_id(signal)
        log_pending_trade(signal, trade_id)
        attach_trade_message_context(trade_id, message_id="proposal-defer-001")

        result = handle_trade_message("先等等", reply_to_id="proposal-defer-001", user_message_id="user-defer-001")

        self.assertTrue(result["handled"])
        self.assertEqual(result["action"], "trade_deferred")
        with open(trade_confirmation.TRADE_LOG_FILE, "r") as f:
            log = json.load(f)
        self.assertEqual(log["trades"][0]["status"], "deferred_by_user")

    def test_modify_reply_marks_trade_modified(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%"
        }
        trade_id = generate_trade_id(signal)
        log_pending_trade(signal, trade_id)
        attach_trade_message_context(trade_id, message_id="proposal-modify-001")

        result = handle_trade_message("改成 100股", reply_to_id="proposal-modify-001", user_message_id="user-modify-001")

        self.assertTrue(result["handled"])
        self.assertEqual(result["action"], "trade_modified")
        with open(trade_confirmation.TRADE_LOG_FILE, "r") as f:
            log = json.load(f)
        self.assertEqual(log["trades"][0]["status"], "modified_by_user")

    def test_clarify_reply_marks_trade_needs_clarification(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%"
        }
        trade_id = generate_trade_id(signal)
        log_pending_trade(signal, trade_id)
        attach_trade_message_context(trade_id, message_id="proposal-clarify-001")

        result = handle_trade_message("什么意思？", reply_to_id="proposal-clarify-001", user_message_id="user-clarify-001")

        self.assertTrue(result["handled"])
        self.assertEqual(result["action"], "trade_needs_clarification")
        with open(trade_confirmation.TRADE_LOG_FILE, "r") as f:
            log = json.load(f)
        self.assertEqual(log["trades"][0]["status"], "needs_clarification")


if __name__ == "__main__":
    unittest.main()
