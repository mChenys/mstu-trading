#!/usr/bin/env python3
import json
import os
import unittest

import app_runtime
from trade_confirmation import (
    POSITION_FILE,
    TRADE_LOG_FILE,
    confirm_trade,
    find_pending_trade,
    generate_trade_id,
    log_pending_trade,
    parse_confirmation,
)


class ConfirmationFlowTest(unittest.TestCase):
    def setUp(self):
        self.paths = [
            TRADE_LOG_FILE,
            POSITION_FILE,
            app_runtime.SQLITE_STATE_FILE,
        ]
        os.makedirs(os.path.dirname(TRADE_LOG_FILE), exist_ok=True)
        for path in self.paths:
            if os.path.exists(path):
                os.remove(path)

        init_pos = {
            "symbol": "MSTU",
            "cost_price": 14.554,
            "shares": 3000,
            "available_cash": 1400,
            "holding_shares": 0,
            "buy_price": 0,
            "target_price": 0,
            "stop_price": 0,
            "position_source": "",
            "updated_at": "2026-04-21T21:00:00+08:00",
        }
        with open(POSITION_FILE, "w") as f:
            json.dump(init_pos, f, indent=2)

    def tearDown(self):
        for path in self.paths:
            if os.path.exists(path):
                os.remove(path)

    def test_full_confirmation_flow_preserves_history(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        trade_id = generate_trade_id(signal)
        trade = log_pending_trade(signal, trade_id)

        confirm = parse_confirmation("确认")
        self.assertTrue(confirm["confirmed"])
        matched = find_pending_trade(confirm["trade_id"])
        self.assertEqual(matched["trade_id"], trade["trade_id"])

        position = confirm_trade(matched)
        self.assertEqual(position["holding_shares"], 89)
        self.assertEqual(position["buy_price"], 7.84)
        self.assertAlmostEqual(position["available_cash"], 700.77, places=2)
        self.assertAlmostEqual(position["holding_cost_basis"], 699.23, places=2)
        self.assertAlmostEqual(position["daily_fees"], 1.47, places=2)

        next_signal = {
            "action": "SELL",
            "price": 8.02,
            "shares": 89,
            "reason": "达到目标价",
        }
        next_trade_id = generate_trade_id(next_signal)
        log_pending_trade(next_signal, next_trade_id)

        with open(TRADE_LOG_FILE, "r") as f:
            trade_log = json.load(f)

        self.assertEqual(len(trade_log["trades"]), 2)
        self.assertEqual(
            [item["status"] for item in trade_log["trades"]],
            ["confirmed_by_user", "pending_user_confirmation"],
        )


if __name__ == "__main__":
    unittest.main()
