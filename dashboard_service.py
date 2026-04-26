import json
import os
from typing import Any
from datetime import datetime, timezone, timedelta
import requests

from app_runtime import WEBHOOK_CONFIG_FILE, WEBHOOK_DAEMON_HEARTBEAT_FILE, ensure_state_dir
import config
from feishu_gateway import send_webhook_text
from fetcher import get_mstu_quote
from indicators_enhanced import analyze_price_vs_levels, calculate_pivot_points
from sqlite_storage import list_message_events, list_outbound_messages, list_trade_records
from strategy import TradingStrategy
from trade_service import list_action_required_trades, run_recovery_scan


ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
OPTIMIZATION_RESULTS_FILE = os.path.join(ROOT_DIR, "optimization_results.json")


def _trace_event(
    trace: list[dict[str, Any]],
    step: str,
    status: str,
    detail: str,
    detail_code: str = "",
    detail_params: dict[str, Any] | None = None,
) -> None:
    trace.append(
        {
            "step": step,
            "status": status,
            "detail": detail,
            "detail_code": detail_code,
            "detail_params": detail_params or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


def _default_position() -> dict[str, Any]:
    return {
        "holding_shares": 0,
        "buy_price": 0.0,
        "target_price": 0.0,
        "stop_price": 0.0,
        "position_source": "",
        "daily_ops_count": 0,
        "daily_pnl": 0.0,
        "available_cash": config.AVAILABLE_CASH,
    }


def _default_webhook_config() -> dict[str, Any]:
    return {
        "url": "",
        "mode": "trade_only",
        "enabled": False,
        "last_signature": "",
        "last_push_status": "idle",
        "last_push_message": "",
        "last_push_message_code": "",
        "last_push_message_params": {},
        "last_push_at": "",
        "last_signal_summary": "",
    }


def load_webhook_config() -> dict[str, Any]:
    if not os.path.exists(WEBHOOK_CONFIG_FILE):
        return _default_webhook_config()
    try:
        with open(WEBHOOK_CONFIG_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return _default_webhook_config()
    config_data = _default_webhook_config()
    config_data.update({k: data.get(k, v) for k, v in config_data.items()})
    return config_data


def save_webhook_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_webhook_config()
    if "url" in payload:
        incoming_url = str(payload.get("url", "")).strip()
        if incoming_url or not current.get("url"):
            current["url"] = incoming_url
    if "mode" in payload:
        incoming_mode = str(payload.get("mode", "")).strip()
        if incoming_mode:
            current["mode"] = incoming_mode
    if "enabled" in payload:
        current["enabled"] = bool(payload.get("enabled"))
    for key in ["last_signature", "last_push_status", "last_push_message", "last_push_message_code", "last_push_message_params", "last_push_at", "last_signal_summary"]:
        if key in payload:
            current[key] = payload[key]

    current["url"] = str(current.get("url", "")).strip()
    current["mode"] = str(current.get("mode", "trade_only")).strip() or "trade_only"
    current["enabled"] = bool(current.get("enabled", False))
    ensure_state_dir()
    tmp_file = f"{WEBHOOK_CONFIG_FILE}.tmp"
    with open(tmp_file, "w") as f:
        json.dump(current, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, WEBHOOK_CONFIG_FILE)
    return current


def load_position_state() -> dict[str, Any]:
    if not os.path.exists(config.POSITION_STATE_FILE):
        return _default_position()
    try:
        with open(config.POSITION_STATE_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return _default_position()

    position = _default_position()
    position.update({k: data.get(k, v) for k, v in position.items()})
    return position


def load_backtest_summary() -> dict[str, Any]:
    recommended = {
        "gap_down_pct": -0.04,
        "gap_up_pct": 0.012,
        "max_chase_pct": 0.04,
        "dip_profit_pct": 0.02,
        "dip_stop_pct": 0.018,
        "mom_profit_pct": 0.018,
        "mom_stop_pct": 0.01,
        "trade_amount": 250,
        "mom_trade_amount": 750,
    }
    summary: dict[str, Any] = {
        "recommended": recommended,
        "status": "unavailable",
        "best_result": None,
        "model_breakdown": [
            {"label": "Base Position", "value": config.POSITION, "description": "长期底仓，只做背景仓位"},
            {"label": "Forward T", "value": "Low buy / high sell", "description": "低买高卖的正向做T"},
            {"label": "Reverse T", "value": "Trim then buy back", "description": "高抛已有底仓，再低位买回"},
            {"label": "Cross-session T", "value": "Enabled", "description": "允许T仓跨交易日持有"},
        ],
    }
    if not os.path.exists(OPTIMIZATION_RESULTS_FILE):
        return summary

    try:
        with open(OPTIMIZATION_RESULTS_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return summary

    if isinstance(data, list) and data:
        best = data[0]
        summary.update(
            {
                "status": "ok",
                "best_result": {
                    "return_pct": best.get("return_pct"),
                    "final_value": best.get("final_value"),
                    "max_drawdown": best.get("max_drawdown"),
                    "win_rate": best.get("win_rate"),
                    "total_closed": best.get("total_closed"),
                    "signal_hits": best.get("signal_hits", {}),
                    "params": {
                        key: best.get(key)
                        for key in recommended
                        if key in best
                    },
                },
            }
        )
    return summary


def load_webhook_daemon_status() -> dict[str, Any]:
    status = {
        "status": "offline",
        "last_heartbeat_at": "",
        "last_cycle_status": "",
        "last_cycle_message": "",
        "interval_seconds": 60,
    }
    if not os.path.exists(WEBHOOK_DAEMON_HEARTBEAT_FILE):
        return status
    try:
        with open(WEBHOOK_DAEMON_HEARTBEAT_FILE, "r") as f:
            data = json.load(f)
    except Exception:
        return status

    status.update({k: data.get(k, v) for k, v in status.items()})
    heartbeat_at = data.get("last_heartbeat_at")
    try:
        heartbeat_dt = datetime.fromisoformat(heartbeat_at)
        now = datetime.now(timezone.utc)
        interval_seconds = int(status.get("interval_seconds", 60))
        status["status"] = "running" if (now - heartbeat_dt).total_seconds() <= interval_seconds * 2 else "stale"
    except Exception:
        status["status"] = "offline"
    return status


def _normalize_market_phase(session: Any) -> str:
    mapping = {
        "premarket": "PREMARKET",
        "regular": "REGULAR",
        "overnight": "OVERNIGHT",
        "closed": "CLOSED",
        "sleep": "OFFLINE",
    }
    return mapping.get(str(session or "").lower(), "UNKNOWN")


def _date_label_shanghai() -> str:
    week_map = {
        0: "周一",
        1: "周二",
        2: "周三",
        3: "周四",
        4: "周五",
        5: "周六",
        6: "周日",
    }
    now = datetime.now(timezone.utc) + timedelta(hours=8)
    return f"{now.year}年{now.month}月{now.day}日({week_map[now.weekday()]})"


def _build_push_signature(ui: dict[str, Any], signal: dict[str, Any], quote: dict[str, Any]) -> str:
    return "|".join(
        [
            str(ui.get("decision_status", "")),
            str(ui.get("market_phase", "")),
            str(signal.get("reason", "")),
            str(quote.get("price", "")),
        ]
    )


def _build_signal_summary(ui: dict[str, Any], signal: dict[str, Any]) -> str:
    status = str(ui.get("decision_status", "--")).upper()
    reason = str(signal.get("reason", "--")).strip()
    return f"{status} | {reason}" if reason else status


def _should_push_signal(webhook: dict[str, Any], ui: dict[str, Any], signal: dict[str, Any]) -> bool:
    if not webhook.get("enabled") or not webhook.get("url"):
        return False
    status = str(ui.get("decision_status", "")).upper()
    action = str(signal.get("action", "")).upper()
    if webhook.get("mode") == "trade_only":
        return status in {"BUY", "SELL"} or action in {"BUY", "SELL"}
    return True


def _format_feishu_text(ui: dict[str, Any], signal: dict[str, Any], quote: dict[str, Any]) -> str:
    mstr = quote.get("mstr", {})
    mstr_price = mstr.get("price", mstr.get("mstr_price", "--"))
    mstr_change_pct = mstr.get("change_pct", mstr.get("mstr_change_pct", "--"))
    signals = signal.get("signals") or []
    tips = "\n".join(f"- {item}" for item in signals) if signals else "- 无额外提示"
    key_levels = quote.get("key_levels") or {}
    levels_lines = [
        f"- 中枢位: ${key_levels.get('pivot', '--')}",
        f"- 第一支撑: ${key_levels.get('s1', '--')}",
        f"- 第二支撑: ${key_levels.get('s2', '--')}",
        f"- 第一压力: ${key_levels.get('r1', '--')}",
        f"- 第二压力: ${key_levels.get('r2', '--')}",
        f"- 当前区间: {key_levels.get('zone_label', '--')}",
    ]
    return (
        "【MSTU 做T信号】\n"
        f"日期：{ui.get('date_label', '--')}\n"
        f"阶段：{ui.get('market_phase', '--')}\n"
        f"决策：{ui.get('decision_status', '--')}\n\n"
        f"MSTR 信号源：${mstr_price} ({mstr_change_pct}%)\n"
        f"MSTU 执行价：${quote.get('price', '--')}\n\n"
        f"关键价位：\n" + "\n".join(levels_lines) + "\n\n"
        f"原因：{signal.get('reason', '--')}\n"
        f"提示：\n{tips}"
    )


def _zone_label(zone: str) -> str:
    mapping = {
        "strong_bullish": "强势区间",
        "bullish": "偏强区间",
        "bearish": "偏弱区间",
        "strong_bearish": "弱势区间",
        "neutral": "中性区间",
    }
    return mapping.get(str(zone or "").lower(), "中性区间")


def _nearest_level_label(level_type: str, level_name: str) -> str:
    labels = {
        "support": {"S1": "第一支撑", "S2": "第二支撑", "S3": "第三支撑"},
        "resistance": {"R1": "第一压力", "R2": "第二压力", "R3": "第三压力"},
    }
    return labels.get(level_type, {}).get(level_name, level_name or "--")


def _build_key_levels(quote: dict[str, Any]) -> dict[str, Any]:
    reference = quote.get("mstr") or {}
    prev_high = reference.get("mstr_high", quote.get("high", 0))
    prev_low = reference.get("mstr_low", quote.get("low", 0))
    prev_close = reference.get("mstr_prev_close", quote.get("prev_close", 0))
    current_price = reference.get("mstr_price", quote.get("price", 0))
    if not prev_high or not prev_low or not prev_close or not current_price:
        return {}

    levels = calculate_pivot_points(float(prev_high), float(prev_low), float(prev_close))
    analysis = analyze_price_vs_levels(float(current_price), levels)
    hits = analysis.get("signals") or []
    execution_price = float(quote.get("price", 0) or 0.0)
    conversion_ratio = (execution_price / float(current_price)) if current_price and execution_price else 0.0
    nearest_support_label = ""
    nearest_support = analysis.get("nearest_support")
    if nearest_support:
        if nearest_support == levels.get("s1"):
            nearest_support_label = "第一支撑"
        elif nearest_support == levels.get("s2"):
            nearest_support_label = "第二支撑"
        elif nearest_support == levels.get("s3"):
            nearest_support_label = "第三支撑"
    nearest_resistance_label = ""
    nearest_resistance = analysis.get("nearest_resistance")
    if nearest_resistance:
        if nearest_resistance == levels.get("r1"):
            nearest_resistance_label = "第一压力"
        elif nearest_resistance == levels.get("r2"):
            nearest_resistance_label = "第二压力"
        elif nearest_resistance == levels.get("r3"):
            nearest_resistance_label = "第三压力"

    return {
        **levels,
        "signal_symbol": "MSTR" if reference else config.SYMBOL,
        "execution_symbol": config.SYMBOL,
        "conversion_ratio": round(conversion_ratio, 6) if conversion_ratio else 0.0,
        "mstu_equivalent": {
            key: round(value * conversion_ratio, 2)
            for key, value in levels.items()
        } if conversion_ratio else {},
        "zone": analysis.get("zone", "neutral"),
        "zone_label": _zone_label(analysis.get("zone", "neutral")),
        "nearest_support": nearest_support,
        "nearest_support_key": "S1" if nearest_support_label == "第一支撑" else "S2" if nearest_support_label == "第二支撑" else "S3" if nearest_support_label == "第三支撑" else "",
        "nearest_support_label": nearest_support_label or "--",
        "nearest_resistance": nearest_resistance,
        "nearest_resistance_key": "R1" if nearest_resistance_label == "第一压力" else "R2" if nearest_resistance_label == "第二压力" else "R3" if nearest_resistance_label == "第三压力" else "",
        "nearest_resistance_label": nearest_resistance_label or "--",
        "active_signals": [
            {
                "type": item.get("type", ""),
                "level": item.get("level", ""),
                "label": _nearest_level_label(item.get("type", ""), item.get("level", "")),
                "value": item.get("value"),
                "distance_pct": item.get("distance_pct"),
            }
            for item in hits
        ],
    }


def maybe_push_webhook(
    webhook: dict[str, Any],
    ui: dict[str, Any],
    signal: dict[str, Any],
    quote: dict[str, Any],
    trace: list[dict[str, Any]],
) -> dict[str, Any]:
    updated = dict(webhook)
    if not _should_push_signal(updated, ui, signal):
        updated["last_push_status"] = "skipped"
        updated["last_push_message"] = "当前模式下不触发推送"
        updated["last_push_message_code"] = "WEBHOOK_SKIPPED_BY_MODE"
        updated["last_push_message_params"] = {}
        return updated

    signature = _build_push_signature(ui, signal, quote)
    if signature == updated.get("last_signature"):
        updated["last_push_status"] = "deduped"
        updated["last_push_message"] = "同一信号已推送，已去重"
        updated["last_push_message_code"] = "WEBHOOK_DEDUPED"
        updated["last_push_message_params"] = {}
        _trace_event(trace, "webhook", "success", "Webhook 去重，未重复推送", "WEBHOOK_DEDUPED", {})
        save_webhook_config(updated)
        return updated

    payload = {
        "msg_type": "text",
        "content": {"text": _format_feishu_text(ui, signal, quote)},
    }
    try:
        _trace_event(trace, "webhook", "running", "推送飞书 Webhook", "WEBHOOK_PUSHING", {})
        response = send_webhook_text(updated["url"], _format_feishu_text(ui, signal, quote), timeout=8)
        response.raise_for_status()
        updated["last_signature"] = signature
        updated["last_push_status"] = "success"
        updated["last_push_message"] = "推送成功"
        updated["last_push_message_code"] = "WEBHOOK_PUSH_SUCCESS"
        updated["last_push_message_params"] = {}
        updated["last_push_at"] = datetime.now(timezone.utc).isoformat()
        updated["last_signal_summary"] = _build_signal_summary(ui, signal)
        _trace_event(trace, "webhook", "success", "Webhook 推送成功", "WEBHOOK_PUSH_SUCCESS", {})
    except Exception as exc:
        updated["last_push_status"] = "error"
        updated["last_push_message"] = str(exc)
        updated["last_push_message_code"] = "WEBHOOK_PUSH_ERROR"
        updated["last_push_message_params"] = {"error": str(exc)}
        updated["last_push_at"] = datetime.now(timezone.utc).isoformat()
        _trace_event(trace, "webhook", "error", f"Webhook 推送失败: {exc}", "WEBHOOK_PUSH_ERROR", {"error": str(exc)})
    save_webhook_config(updated)
    return updated


def send_test_webhook_message() -> dict[str, Any]:
    webhook = load_webhook_config()
    if not webhook.get("url"):
        webhook["last_push_status"] = "error"
        webhook["last_push_message"] = "未配置 Webhook URL"
        webhook["last_push_message_code"] = "WEBHOOK_URL_MISSING"
        webhook["last_push_message_params"] = {}
        save_webhook_config(webhook)
        return {"ok": False, "message": "未配置 Webhook URL", "webhook": webhook}

    text = (
        "【MSTU 做T测试消息】\n"
        f"日期：{_date_label_shanghai()}\n"
        "这是从 Dashboard 发出的测试推送，用于确认飞书机器人链路是否可用。"
    )
    try:
        response = send_webhook_text(webhook["url"], text, timeout=8)
        response.raise_for_status()
        webhook["last_push_status"] = "success"
        webhook["last_push_message"] = "测试消息已发送"
        webhook["last_push_message_code"] = "WEBHOOK_TEST_SUCCESS"
        webhook["last_push_message_params"] = {}
        webhook["last_push_at"] = datetime.now(timezone.utc).isoformat()
        webhook["last_signal_summary"] = "TEST_MESSAGE | Dashboard webhook connectivity check"
        save_webhook_config(webhook)
        return {"ok": True, "message": "测试消息已发送", "webhook": webhook}
    except Exception as exc:
        webhook["last_push_status"] = "error"
        webhook["last_push_message"] = str(exc)
        webhook["last_push_message_code"] = "WEBHOOK_TEST_ERROR"
        webhook["last_push_message_params"] = {"error": str(exc)}
        webhook["last_push_at"] = datetime.now(timezone.utc).isoformat()
        save_webhook_config(webhook)
        return {"ok": False, "message": str(exc), "webhook": webhook}


def _normalize_decision_status(signal: dict[str, Any]) -> str:
    action = str(signal.get("action", "")).upper()
    if action in {"BUY", "SELL", "HOLD", "ERROR"}:
        return action
    if action == "TIME_WINDOW_BLOCKED":
        return "BLOCKED"
    if action in {"PREMARKET", "OVERNIGHT"}:
        reason = str(signal.get("reason", ""))
        if "无明确信号" in reason or "观察" in reason or "不足" in reason:
            return "WATCH"
        return "SETUP"
    if action == "OFF":
        return "OFFLINE"
    return "WATCH"


def load_ops_overview(limit: int = 8) -> dict[str, Any]:
    try:
        recovery = run_recovery_scan(agent_source="dashboard_service")
        pending_trades = list_trade_records(status="pending_user_confirmation", limit=limit)
        action_required_trades = list_action_required_trades(limit=limit)
        recent_events = list_message_events(limit=limit)
        recent_outbound = list_outbound_messages(limit=limit)
    except Exception:
        recovery = {
            "checked": 0,
            "expired_count": 0,
            "expired_trade_ids": [],
            "pending_after_scan": 0,
        }
        pending_trades = []
        action_required_trades = []
        recent_events = []
        recent_outbound = []
    dedupe_hits = [
        item for item in recent_outbound
        if str(item.get("detail", "")).lower() == "idempotent"
    ]
    failed_outbound = [item for item in recent_outbound if not item.get("success")]
    return {
        "pending_trades": pending_trades,
        "action_required_trades": action_required_trades,
        "recent_events": recent_events,
        "recent_outbound": recent_outbound,
        "recovery": recovery,
        "stats": {
            "pending_trade_count": len(pending_trades),
            "action_required_trade_count": len(action_required_trades),
            "recent_event_count": len(recent_events),
            "recent_outbound_count": len(recent_outbound),
            "recent_dedupe_hits": len(dedupe_hits),
            "recent_outbound_failures": len(failed_outbound),
            "recent_auto_expired": int(recovery.get("expired_count", 0)),
        },
    }


def build_dashboard_snapshot() -> dict[str, Any]:
    trace: list[dict[str, Any]] = []
    _trace_event(trace, "webhook", "running", "读取 Webhook 配置", "WEBHOOK_CONFIG_LOADING", {})
    webhook = load_webhook_config()
    _trace_event(trace, "webhook", "success", "Webhook 配置已加载", "WEBHOOK_CONFIG_LOADED", {})
    _trace_event(trace, "position", "running", "读取持仓状态", "POSITION_LOADING", {})
    position = load_position_state()
    _trace_event(trace, "position", "success", "持仓状态已加载", "POSITION_LOADED", {})
    _trace_event(trace, "backtest", "running", "读取回测摘要", "BACKTEST_LOADING", {})
    backtest = load_backtest_summary()
    _trace_event(trace, "backtest", "success", "回测摘要已加载", "BACKTEST_LOADED", {})
    _trace_event(trace, "ops", "running", "读取 Agent 运维视图", "OPS_LOADING", {})
    ops = load_ops_overview()
    _trace_event(trace, "ops", "success", "Agent 运维视图已加载", "OPS_LOADED", {})
    _trace_event(trace, "daemon", "running", "读取 webhook daemon 心跳", "DAEMON_LOADING", {})
    daemon = load_webhook_daemon_status()
    _trace_event(trace, "daemon", "success", f"daemon 状态: {daemon.get('status', 'offline')}", "DAEMON_STATUS", {"status": daemon.get("status", "offline")})
    _trace_event(trace, "quote", "running", "获取 MSTU/MSTR 行情", "QUOTE_LOADING", {})
    quote = get_mstu_quote()

    if "error" in quote:
        _trace_event(trace, "quote", "error", f"行情获取失败: {quote['error']}", "QUOTE_ERROR", {"error": quote["error"]})
        return {
            "status": "degraded",
            "quote": {"status": "error", "error": quote["error"]},
            "signal": {"action": "ERROR", "reason": quote["error"], "signals": []},
            "position": position,
            "backtest": backtest,
            "daemon": daemon,
            "ui": {
                "market_phase": "UNKNOWN",
                "decision_status": "ERROR",
                "date_label": _date_label_shanghai(),
            },
            "system": {
                "signal_symbol": "MSTR",
                "execution_symbol": config.SYMBOL,
            },
            "ops": ops,
            "webhook": webhook,
            "trace": trace,
        }

    _trace_event(trace, "quote", "success", "行情获取完成", "QUOTE_LOADED", {})
    _trace_event(trace, "signal", "running", "执行策略分析", "SIGNAL_ANALYZING", {})
    strategy = TradingStrategy()
    signal = strategy.analyze(quote)
    _trace_event(trace, "signal", "success", f"策略动作: {signal.get('action', 'UNKNOWN')}", "SIGNAL_ACTION", {"action": signal.get("action", "UNKNOWN")})
    mstr = quote.get("mstr", {})
    key_levels = _build_key_levels(quote)
    ui = {
        "market_phase": _normalize_market_phase(quote.get("session")),
        "decision_status": _normalize_decision_status(signal),
        "date_label": _date_label_shanghai(),
    }
    _trace_event(trace, "snapshot", "success", "本次刷新完成", "SNAPSHOT_DONE", {})

    return {
        "status": "ok",
        "quote": {
            "status": "ok",
            "symbol": quote.get("symbol", config.SYMBOL),
            "price": quote.get("price"),
            "prev_close": quote.get("prev_close"),
            "change_pct": quote.get("change_pct"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "volume": quote.get("volume"),
            "session": quote.get("session"),
            "key_levels": key_levels,
            "mstr": {
                "price": mstr.get("mstr_price"),
                "change_pct": mstr.get("mstr_change_pct"),
                "ema_bullish": mstr.get("mstr_ema_bullish"),
                "macd_bullish": mstr.get("mstr_macd_bullish"),
            },
        },
        "signal": signal,
        "position": position,
        "backtest": backtest,
        "daemon": daemon,
        "ui": ui,
        "system": {
            "signal_symbol": "MSTR",
            "execution_symbol": config.SYMBOL,
        },
        "ops": ops,
        "webhook": webhook,
        "trace": trace,
    }
