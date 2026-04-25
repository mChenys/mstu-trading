import argparse
import json
from typing import Any

import dashboard_service
from fetcher import get_mstu_quote
from strategy import TradingStrategy


def run_webhook_cycle() -> dict[str, Any]:
    trace: list[dict[str, Any]] = []
    dashboard_service._trace_event(trace, "webhook", "running", "读取 Webhook 配置")
    webhook = dashboard_service.load_webhook_config()
    dashboard_service._trace_event(trace, "webhook", "success", "Webhook 配置已加载")

    quote = get_mstu_quote()
    if "error" in quote:
        dashboard_service._trace_event(trace, "quote", "error", f"行情获取失败: {quote['error']}")
        return {"ok": False, "quote": quote, "trace": trace, "webhook": webhook}

    strategy = TradingStrategy()
    signal = strategy.analyze(quote)
    quote["key_levels"] = dashboard_service._build_key_levels(quote)
    ui = {
        "market_phase": dashboard_service._normalize_market_phase(quote.get("session")),
        "decision_status": dashboard_service._normalize_decision_status(signal),
        "date_label": dashboard_service._date_label_shanghai(),
    }
    webhook = dashboard_service.maybe_push_webhook(webhook, ui, signal, quote, trace)
    return {
        "ok": True,
        "quote": quote,
        "signal": signal,
        "ui": ui,
        "webhook": webhook,
        "trace": trace,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true", help="输出 JSON 结果")
    args = parser.parse_args()
    result = run_webhook_cycle()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(result)
