import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

import app_runtime
import config
import dashboard_service
import sqlite_storage
import trade_confirmation
import trade_service
import web_app
from mstu_trading.web import app as package_web_app
from mstu_trading.web import dashboard_service as package_dashboard_service

from dashboard_service import build_dashboard_snapshot
from web_app import create_app


class DashboardServiceTest(unittest.TestCase):
    def test_root_wrappers_and_package_modules_share_identity(self):
        self.assertIs(dashboard_service, package_dashboard_service)
        self.assertIs(web_app, package_web_app)

    def setUp(self):
        self.temp_state_dir = tempfile.mkdtemp(prefix="mstu-dashboard-test-")
        self.original_position_state_file = config.POSITION_STATE_FILE
        self.original_sqlite_state_file = sqlite_storage.SQLITE_STATE_FILE
        self.original_trade_log_file = trade_confirmation.TRADE_LOG_FILE
        self.original_position_file = trade_confirmation.POSITION_FILE
        self.original_webhook_state_file = dashboard_service.WEBHOOK_CONFIG_FILE
        self.original_heartbeat_file = dashboard_service.WEBHOOK_DAEMON_HEARTBEAT_FILE
        config.POSITION_STATE_FILE = os.path.join(self.temp_state_dir, "position.json")
        sqlite_storage.SQLITE_STATE_FILE = os.path.join(self.temp_state_dir, "state.db")
        trade_confirmation.TRADE_LOG_FILE = os.path.join(self.temp_state_dir, "trade_log.json")
        trade_confirmation.POSITION_FILE = config.POSITION_STATE_FILE
        self.position_dir = os.path.dirname(config.POSITION_STATE_FILE)
        os.makedirs(self.position_dir, exist_ok=True)
        self.webhook_state_file = os.path.join(self.temp_state_dir, "webhook_config.json")
        dashboard_service.WEBHOOK_CONFIG_FILE = self.webhook_state_file
        self.heartbeat_file = os.path.join(self.temp_state_dir, "webhook_daemon_heartbeat_test.json")
        dashboard_service.WEBHOOK_DAEMON_HEARTBEAT_FILE = self.heartbeat_file

    def tearDown(self):
        config.POSITION_STATE_FILE = self.original_position_state_file
        sqlite_storage.SQLITE_STATE_FILE = self.original_sqlite_state_file
        trade_confirmation.TRADE_LOG_FILE = self.original_trade_log_file
        trade_confirmation.POSITION_FILE = self.original_position_file
        dashboard_service.WEBHOOK_CONFIG_FILE = self.original_webhook_state_file
        dashboard_service.WEBHOOK_DAEMON_HEARTBEAT_FILE = self.original_heartbeat_file
        shutil.rmtree(self.temp_state_dir, ignore_errors=True)

    def write_position(self, payload):
        with open(config.POSITION_STATE_FILE, "w") as f:
            json.dump(payload, f)

    def test_build_dashboard_snapshot_success(self):
        self.write_position(
            {
                "holding_shares": 89,
                "buy_price": 7.84,
                "target_price": 7.93,
                "stop_price": 7.78,
                "position_source": "premarket-momentum",
                "daily_ops_count": 1,
                "daily_pnl": 16.02,
                "available_cash": 702.24,
            }
        )
        with patch("dashboard_service.get_mstu_quote") as mock_quote, patch(
            "dashboard_service.TradingStrategy"
        ) as mock_strategy_cls:
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
                    "mstr_ema_bullish": True,
                    "mstr_macd_bullish": True,
                },
            }
            mock_strategy = mock_strategy_cls.return_value
            mock_strategy.analyze.return_value = {
                "action": "BUY",
                "reason": "VWAP上方延续启动",
                "signals": ["VWAP上方延续启动"],
                "mstr_trend_ok": True,
            }

            snapshot = build_dashboard_snapshot()

        self.assertEqual(snapshot["status"], "ok")
        self.assertEqual(snapshot["quote"]["symbol"], "MSTU")
        self.assertEqual(snapshot["signal"]["action"], "BUY")
        self.assertEqual(snapshot["ui"]["market_phase"], "REGULAR")
        self.assertEqual(snapshot["ui"]["decision_status"], "BUY")
        self.assertIn("年", snapshot["ui"]["date_label"])
        self.assertIn("周", snapshot["ui"]["date_label"])
        self.assertIn("trace", snapshot)
        self.assertGreaterEqual(len(snapshot["trace"]), 3)
        self.assertEqual(snapshot["trace"][-1]["status"], "success")
        self.assertEqual(snapshot["position"]["holding_shares"], 89)
        self.assertIn("key_levels", snapshot["quote"])
        self.assertEqual(snapshot["quote"]["key_levels"]["nearest_support_label"], "第一支撑")
        self.assertEqual(snapshot["quote"]["key_levels"]["nearest_resistance_label"], "第二压力")
        self.assertIn("中枢位", dashboard_service._format_feishu_text(snapshot["ui"], snapshot["signal"], snapshot["quote"]))
        self.assertIn("recommended", snapshot["backtest"])
        self.assertIn("model_breakdown", snapshot["backtest"])
        self.assertEqual(snapshot["system"]["signal_symbol"], "MSTR")
        self.assertEqual(snapshot["system"]["execution_symbol"], "MSTU")
        self.assertIn("ops", snapshot)
        self.assertIn("stats", snapshot["ops"])
        self.assertIn("webhook", snapshot)
        self.assertIn("daemon", snapshot)

    def test_load_ops_overview_reports_pending_trades_and_outbound(self):
        signal = {
            "action": "BUY",
            "price": 7.84,
            "shares": 89,
            "target_price": 7.93,
            "stop_price": 7.78,
            "position_source": "premarket-momentum",
            "reason": "盘前高开+2.8%",
        }
        trade_service.create_trade_proposal(signal, message_id="ops-proposal-001")
        from sqlite_storage import record_outbound_message

        record_outbound_message(
            event_type="execution_notice_sent",
            message_text="hello ops",
            success=True,
            detail="idempotent",
            dedupe_key="ops-outbound-001",
            channel="feishu",
            transport="webhook",
        )

        overview = dashboard_service.load_ops_overview()

        self.assertGreaterEqual(overview["stats"]["pending_trade_count"], 1)
        self.assertGreaterEqual(overview["stats"]["action_required_trade_count"], 1)
        self.assertGreaterEqual(overview["stats"]["recent_outbound_count"], 1)
        self.assertGreaterEqual(overview["stats"]["recent_dedupe_hits"], 1)
        self.assertIn("recovery", overview)

    def test_build_dashboard_snapshot_handles_quote_error(self):
        with patch("dashboard_service.get_mstu_quote", return_value={"error": "network down"}):
            snapshot = build_dashboard_snapshot()

        self.assertEqual(snapshot["status"], "degraded")
        self.assertEqual(snapshot["quote"]["status"], "error")
        self.assertEqual(snapshot["signal"]["action"], "ERROR")
        self.assertEqual(snapshot["position"]["holding_shares"], 0)
        self.assertEqual(snapshot["trace"][-1]["status"], "error")

    def test_build_dashboard_snapshot_reports_daemon_offline_when_no_heartbeat(self):
        with patch("dashboard_service.get_mstu_quote", return_value={"error": "network down"}):
            snapshot = build_dashboard_snapshot()

        self.assertEqual(snapshot["daemon"]["status"], "offline")

    def test_build_dashboard_snapshot_uses_default_position_when_missing(self):
        with patch("dashboard_service.get_mstu_quote", return_value={"error": "quote unavailable"}):
            snapshot = build_dashboard_snapshot()

        self.assertEqual(snapshot["position"]["holding_shares"], 0)
        self.assertEqual(snapshot["position"]["position_source"], "")
        self.assertIn("available_cash", snapshot["position"])

    def test_build_dashboard_snapshot_does_not_push_plain_text_for_feishu_webhook(self):
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

        with patch("dashboard_service.get_mstu_quote") as mock_quote, patch(
            "dashboard_service.TradingStrategy"
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
                    "mstr_ema_bullish": True,
                    "mstr_macd_bullish": True,
                },
            }
            mock_strategy = mock_strategy_cls.return_value
            mock_strategy.analyze.return_value = {
                "action": "BUY",
                "reason": "VWAP上方延续启动",
                "signals": ["VWAP上方延续启动"],
                "mstr_trend_ok": True,
            }
            mock_post.return_value.status_code = 200
            mock_post.return_value.text = "ok"

            snapshot = build_dashboard_snapshot()

        self.assertFalse(mock_post.called)
        self.assertEqual(snapshot["webhook"]["url"], "https://open.feishu.cn/open-apis/bot/v2/hook/test")
        self.assertEqual(snapshot["webhook"]["enabled"], True)

    def test_build_dashboard_snapshot_preserves_last_push_state(self):
        with open(self.webhook_state_file, "w") as f:
            json.dump(
                {
                    "url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                    "mode": "all",
                    "enabled": True,
                    "last_signature": "WATCH|PREMARKET|盘前参考MSTR+7.1%，无明确信号|7.93",
                    "last_push_status": "success",
                    "last_push_message": "推送成功",
                },
                f,
            )

        with patch("dashboard_service.get_mstu_quote") as mock_quote, patch(
            "dashboard_service.TradingStrategy"
        ) as mock_strategy_cls, patch("dashboard_service.requests.post") as mock_post:
            mock_quote.return_value = {
                "symbol": "MSTU",
                "price": 7.93,
                "prev_close": 7.02,
                "high": 8.66,
                "low": 7.94,
                "volume": 60517000,
                "session": "premarket",
                "change_pct": 12.96,
                "mstr": {
                    "mstr_price": 175.57,
                    "mstr_change_pct": 7.07,
                    "mstr_ema_bullish": True,
                    "mstr_macd_bullish": False,
                },
            }
            mock_strategy = mock_strategy_cls.return_value
            mock_strategy.analyze.return_value = {
                "action": "PREMARKET",
                "reason": "盘前参考MSTR+7.1%，无明确信号",
                "signals": ["⚠️ MSTR高开+7.1%，涨幅过大不追"],
                "mstr_trend_ok": False,
            }

            snapshot = build_dashboard_snapshot()

        self.assertFalse(mock_post.called)
        self.assertEqual(snapshot["webhook"]["last_push_status"], "success")
        self.assertEqual(snapshot["webhook"]["last_push_message"], "推送成功")


class DashboardWebAppTest(unittest.TestCase):
    def setUp(self):
        self.temp_state_dir = tempfile.mkdtemp(prefix="mstu-dashboard-web-test-")
        self.original_position_state_file = config.POSITION_STATE_FILE
        self.original_sqlite_state_file = sqlite_storage.SQLITE_STATE_FILE
        self.original_trade_log_file = trade_confirmation.TRADE_LOG_FILE
        self.original_position_file = trade_confirmation.POSITION_FILE
        self.original_webhook_state_file = dashboard_service.WEBHOOK_CONFIG_FILE
        config.POSITION_STATE_FILE = os.path.join(self.temp_state_dir, "position.json")
        sqlite_storage.SQLITE_STATE_FILE = os.path.join(self.temp_state_dir, "state.db")
        trade_confirmation.TRADE_LOG_FILE = os.path.join(self.temp_state_dir, "trade_log.json")
        trade_confirmation.POSITION_FILE = config.POSITION_STATE_FILE
        self.webhook_state_file = os.path.join(self.temp_state_dir, "webhook_config_test_web.json")
        dashboard_service.WEBHOOK_CONFIG_FILE = self.webhook_state_file
        self.app = create_app().test_client()

    def tearDown(self):
        config.POSITION_STATE_FILE = self.original_position_state_file
        sqlite_storage.SQLITE_STATE_FILE = self.original_sqlite_state_file
        trade_confirmation.TRADE_LOG_FILE = self.original_trade_log_file
        trade_confirmation.POSITION_FILE = self.original_position_file
        dashboard_service.WEBHOOK_CONFIG_FILE = self.original_webhook_state_file
        shutil.rmtree(self.temp_state_dir, ignore_errors=True)

    def test_health_endpoint(self):
        response = self.app.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_dashboard_endpoint(self):
        with patch("web_app.build_dashboard_snapshot", return_value={"status": "ok", "quote": {}, "signal": {}, "position": {}, "backtest": {}, "system": {}}):
            response = self.app.get("/api/dashboard")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["status"], "ok")

    def test_ops_endpoint(self):
        with patch("web_app.load_ops_overview", return_value={"stats": {"pending_trade_count": 0}, "pending_trades": [], "recent_events": [], "recent_outbound": []}):
            response = self.app.get("/api/ops")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["stats"]["pending_trade_count"], 0)

    def test_ops_recover_endpoint(self):
        with patch("web_app.run_recovery_scan", return_value={"checked": 3, "expired_count": 1, "expired_trade_ids": ["MSTU-1"], "pending_after_scan": 0}):
            response = self.app.post("/api/ops/recover")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["expired_count"], 1)

    def test_trade_detail_endpoint(self):
        with patch(
            "web_app.get_trade_context",
            return_value={"proposal": {"trade_id": "MSTU-123"}, "position": {}, "events": [], "outbound_messages": []},
        ):
            response = self.app.get("/api/trades/MSTU-123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["proposal"]["trade_id"], "MSTU-123")

    def test_trade_expire_endpoint(self):
        with patch(
            "web_app.expire_trade",
            return_value={"handled": True, "trade_id": "MSTU-123", "proposal": {"status": "expired"}},
        ):
            response = self.app.post("/api/trades/MSTU-123/expire")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["proposal"]["status"], "expired")

    def test_trade_claim_endpoint(self):
        with patch(
            "web_app.claim_trade",
            return_value={"handled": True, "trade_id": "MSTU-123", "claimed_by": "hermes", "proposal": {"claimed_by": "hermes"}},
        ):
            response = self.app.post("/api/trades/MSTU-123/claim", json={"agent_source": "hermes"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["claimed_by"], "hermes")

    def test_trade_release_endpoint(self):
        with patch(
            "web_app.release_trade",
            return_value={"handled": True, "trade_id": "MSTU-123", "proposal": {"claimed_by": ""}},
        ):
            response = self.app.post("/api/trades/MSTU-123/release", json={"agent_source": "hermes"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["proposal"]["claimed_by"], "")

    def test_dashboard_page_contains_sections(self):
        response = self.app.get("/")

        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        self.assertIn("Live Signal", body)
        self.assertIn("languageSwitcher", body)
        self.assertIn("Backtest Overview", body)
        self.assertIn("MSTR -&gt; Signal", body)
        self.assertIn("MSTR Signal Feed", body)
        self.assertIn("MSTU Execution Feed", body)
        self.assertIn("Market Phase", body)
        self.assertIn("Decision Status", body)
        self.assertIn("T Model Breakdown", body)
        self.assertIn("Trading Date", body)
        self.assertIn("Refresh Flow", body)
        self.assertIn("Activity Log", body)
        self.assertIn("Agent Ops", body)
        self.assertIn("技术信号与做T基调", body)
        self.assertIn("Action Required Trades", body)
        self.assertIn("Webhook Push", body)
        self.assertIn("关键价位", body)
        self.assertIn("发送测试消息", body)
        self.assertIn("Last Push Time", body)
        self.assertIn("Last Pushed Signal", body)
        self.assertIn("insight-grid", body)
        self.assertIn("webhook-secondary-row", body)
        self.assertNotIn("panel-label\">Daemon Status", body)
        self.assertNotIn("daemon-inline", body)

    def test_static_assets_available(self):
        css = self.app.get("/static/dashboard.css", buffered=True)
        js = self.app.get("/static/dashboard.js", buffered=True)

        self.assertEqual(css.status_code, 200)
        self.assertEqual(js.status_code, 200)
        self.assertGreater(len(css.get_data()), 0)
        self.assertGreater(len(js.get_data()), 0)
        js_body = js.get_data(as_text=True)
        self.assertIn("/api/webhook-config", js_body)
        self.assertIn("loadWebhookConfig()", js_body)
        self.assertIn("Daemon Status", js_body)
        self.assertIn("Last heartbeat", js_body)
        self.assertIn("Last cycle", js_body)
        self.assertIn("dedupeSignalDetails", js_body)
        self.assertIn("/api/ops/recover", js_body)
        self.assertIn("/api/trades/", js_body)
        self.assertIn("translateMarketPhase", js_body)
        self.assertIn("translateDecisionStatus", js_body)
        self.assertIn("buildTradingDateLabel", js_body)
        self.assertIn("keyLevelsSummary", js_body)
        self.assertIn("中枢位", js_body)

    def test_webhook_config_roundtrip(self):
        response = self.app.post(
            "/api/webhook-config",
            json={
                "url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                "mode": "trade_only",
                "enabled": True,
            },
        )

        self.assertEqual(response.status_code, 200)
        saved = response.get_json()
        self.assertEqual(saved["url"], "https://open.feishu.cn/open-apis/bot/v2/hook/test")
        self.assertEqual(saved["mode"], "trade_only")

        get_response = self.app.get("/api/webhook-config")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(
            get_response.get_json()["url"],
            "https://open.feishu.cn/open-apis/bot/v2/hook/test",
        )

    def test_webhook_test_endpoint(self):
        self.app.post(
            "/api/webhook-config",
            json={
                "url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                "mode": "trade_only",
                "enabled": True,
            },
        )

        with patch("web_app.send_test_webhook_message", return_value={"ok": True, "message": "测试消息已发送"}) as mock_send:
            response = self.app.post("/api/webhook-test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["ok"], True)
        self.assertTrue(mock_send.called)

    def test_send_test_webhook_message_records_readable_signal_summary(self):
        self.app.post(
            "/api/webhook-config",
            json={
                "url": "https://open.feishu.cn/open-apis/bot/v2/hook/test",
                "mode": "trade_only",
                "enabled": True,
            },
        )

        with patch("dashboard_service.requests.post") as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.raise_for_status.return_value = None
            result = dashboard_service.send_test_webhook_message()

        self.assertTrue(result["ok"])
        self.assertIn("Dashboard webhook connectivity check", result["webhook"]["last_signal_summary"])


if __name__ == "__main__":
    unittest.main()
