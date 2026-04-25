"""交易执行回执通知。"""

from feishu_gateway import send_default_text_message


def send_text_webhook(message: str) -> bool:
    """通过 webhook 发送纯文本消息。"""
    return send_default_text_message(message)


def format_trade_execution_notice(action: str, result: str, position: dict) -> str:
    """统一格式化交易执行成功后的群回执。"""
    holding = position.get("holding_shares", 0)
    available_cash = position.get("available_cash", 0.0)
    daily_pnl = position.get("daily_pnl", 0.0)
    source = position.get("position_source", "")
    source_label = {
        "premarket-dip": "盘前低吸",
        "premarket-momentum": "盘前追涨",
        "overnight-dip": "夜盘低吸",
        "overnight-momentum": "夜盘追涨",
        "regular": "盘中做T",
        "": "空仓/无新增仓位",
    }.get(source, source or "空仓/无新增仓位")

    return (
        f"📬 交易执行回执\n\n"
        f"📌 类型: {action}\n"
        f"{result}\n\n"
        f"📦 当前做T持仓: {holding}股\n"
        f"🏷️ 仓位来源: {source_label}\n"
        f"💵 可用现金: ${available_cash:.2f}\n"
        f"📊 今日PnL: ${daily_pnl:+.2f}"
    )


def send_trade_execution_notice(
    action: str,
    result: str,
    position: dict,
    *,
    agent_source: str = "",
) -> bool:
    """发送交易执行成功回执。"""
    message = format_trade_execution_notice(action, result, position)
    from feishu_gateway import send_text_message

    ok, _ = send_text_message(
        message,
        webhook_url=__import__("config").FEISHU_WEBHOOK,
        chat_id=__import__("config").FEISHU_GROUP_ID,
        prefer_chat_api=True,
        timeout=10,
        record_outbound=True,
        outbound_event_type="execution_notice_sent",
        agent_source=agent_source,
        dedupe_key=f"execution_notice:{hash(message)}",
    )
    return ok
