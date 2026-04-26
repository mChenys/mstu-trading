"""MSTU 定时调度 - 三时段监控 + 飞书推送

时段设计（北京时间）：
- 夜盘: 08:00-16:00 (周日-周四) -> 低频监控
- 盘前: 16:00-21:30 -> 低吸/追涨做T
- 盘中: 21:30-00:00 -> 做T核心
- 睡觉: 00:00-08:00 -> 不推送
"""

from datetime import datetime, timezone, timedelta
import json

import mstu_trading.config as config
from mstu_trading.strategy.fee_model import max_affordable_shares
from mstu_trading.integrations.feishu_gateway import send_text_message
from mstu_trading.market_data.fetcher import get_mstu_quote, format_price_info, get_session_type
import mstu_trading.integrations.webhook_worker as webhook_worker
from strategy import TradingStrategy, format_trade_signal

# 导入交易确认机制
try:
    from mstu_trading.trading.confirmation import (
        generate_trade_id,
        log_pending_trade,
        format_buy_signal_with_id,
        parse_confirmation,
        find_pending_trade,
        confirm_trade,
        get_confirmation_response,
    )

    CONFIRMATION_ENABLED = True
except ImportError:
    CONFIRMATION_ENABLED = False


def _format_date(date_str: str) -> str:
    """日期加周几，如 2026-04-17(周五)"""
    if not date_str:
        return "未知"
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        return f"{date_str}({weekdays[dt.weekday()]})"
    except Exception:
        return date_str


def _prev_trading_day(date_str: str) -> str:
    """推算前一交易日日期"""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        prev = dt - timedelta(days=1)
        while prev.weekday() >= 5:
            prev -= timedelta(days=1)
        return prev.strftime("%Y-%m-%d")
    except Exception:
        return ""


def send_to_webhook(msg: str):
    """发送消息到飞书群，优先 chat API，失败后回退 webhook。"""
    ok, detail = send_text_message(
        msg,
        webhook_url=config.FEISHU_WEBHOOK,
        chat_id=config.FEISHU_GROUP_ID,
        prefer_chat_api=True,
        timeout=10,
        record_outbound=True,
        outbound_event_type="scheduler_text_sent",
        agent_source="scheduler",
        dedupe_key=f"scheduler_text:{hash(msg)}",
    )
    if not ok:
        print(f"飞书消息发送失败: {detail}")
    return ok


def _position_status(strategy: TradingStrategy) -> str:
    """格式化当前持仓状态"""
    if strategy.holding_shares > 0:
        return f"""📦 **当前做T持仓**: {strategy.holding_shares}股 @ ${strategy.buy_price:.2f}
🎯 目标: ${strategy.target_price:.2f} | ⛔ 止损: ${strategy.stop_price:.2f}
📊 今日已操作: {strategy.daily_ops_count}/{config.MAX_LOTS_PER_DAY}次"""
    else:
        return f"📦 做T空仓 | 今日已操作: {strategy.daily_ops_count}/{config.MAX_LOTS_PER_DAY}次"


def _cash_display(strategy: TradingStrategy) -> float:
    """统一展示当前策略状态中的可用现金。"""
    return round(strategy.available_cash, 2)


def scan():
    """通用扫描"""
    session = get_session_type()

    if session in ["sleep", "closed"]:
        return None

    quote = get_mstu_quote()
    if "error" in quote:
        return f"❌ MSTU 扫描失败: {quote['error']}"

    strategy = TradingStrategy()
    signal = strategy.analyze(quote)

    # 买入信号：使用交易确认机制
    if signal.get("action") == "BUY" and CONFIRMATION_ENABLED:
        trade_id = generate_trade_id(signal)
        log_pending_trade(signal, trade_id, agent_source="scheduler")
        msg = format_buy_signal_with_id(signal, trade_id)
        try:
            from mstu_trading.trading.confirmation import attach_trade_message_context

            attach_trade_message_context(trade_id, message_text=msg, agent_source="scheduler")
        except Exception:
            pass
    else:
        # 格式化推送
        msg = format_trade_signal(signal, strategy)

    # 盘中完整版
    if session == "regular":
        price = quote.get("price", 0)
        prev_close = quote.get("prev_close", 0)
        cost_distance = (price - config.COST_PRICE) / config.COST_PRICE * 100
        position_pnl = (price - config.COST_PRICE) * config.POSITION
        change_vs_prev = (price - prev_close) / prev_close * 100 if prev_close else 0

        header = f"""📊 **MSTU 盘中扫描**（基于MSTR正股分析）

💰 价格: ${price:.2f} (vs昨收{change_vs_prev:+.1f}%)
📈 底仓: {config.POSITION}股 | 成本${config.COST_PRICE} | 浮亏{cost_distance:+.1f}% (${position_pnl:+,.0f})
💵 可用: ${_cash_display(strategy):.2f}
{_position_status(strategy)}"""

        # 加入 MSTR 底层指标
        if "mstr" in quote:
            m = quote["mstr"]
            header += f"\n📊 MSTR底层: ${m.get('mstr_price', 0):.2f} ({m.get('mstr_change_pct', 0):+.1f}%) -> MSTU预期{m.get('mstu_expected_change', 0):+.1f}%"

        if msg:
            # msg 已有完整格式，header 只补充持仓/成本信息
            # 如果 msg 已含指标详情，直接拼接
            return header + "\n\n" + msg
        return header + "\n\n📋 正常波动，继续监控"

    return msg


def morning_report():
    """盘前报告"""
    quote = get_mstu_quote()

    if "error" in quote:
        return f"❌ MSTU 盘前检查失败: {quote['error']}"

    is_realtime = quote.get("is_realtime", False)
    price = quote.get("price", 0)
    prev_close = quote.get("prev_close", 0)
    trading_day = quote.get("latest_trading_day", "")
    prev_day = _prev_trading_day(trading_day)
    cost_distance = (price - config.COST_PRICE) / config.COST_PRICE * 100
    position_pnl = (price - config.COST_PRICE) * config.POSITION
    buy_power = max_affordable_shares(config.AVAILABLE_CASH, price) if price > 0 else 0
    gap_pct = (price - prev_close) / prev_close * 100 if prev_close else 0

    trading_day_label = _format_date(trading_day)
    prev_day_label = _format_date(prev_day)

    strategy = TradingStrategy()
    pos_info = _position_status(strategy)
    available_cash = _cash_display(strategy)
    buy_power = max_affordable_shares(available_cash, price) if price > 0 else 0

    # 区分实时价和历史价
    if is_realtime:
        price_line = f"📊 **盘前实时**: ${price:.2f} (vs昨收${prev_close:.2f}, {gap_pct:+.1f}%)"
        prev_line = f"💰 周五收盘: ${prev_close:.2f} ({trading_day_label})"
    else:
        price_line = f"📅 最新收盘: ${price:.2f} ({trading_day_label})"
        prev_line = f"💰 前日收盘: ${prev_close:.2f} ({prev_day_label})"

    return f"""🌅 **MSTU 盘前报告** ({datetime.now(timezone(timedelta(hours=8))).strftime('%m-%d %H:%M')} 北京)

{price_line}
{prev_line}
📈 底仓盈亏: {cost_distance:+.1f}% (${position_pnl:+,.0f})
💵 可用: ${available_cash:.2f} (约{buy_power}股)

{pos_info}

⏰ 今日监控时段:
  • 盘前 16:00-21:30 做T模式
  • 盘中 21:30-00:00 做T模式
  • 00:00后自动停止

💡 全时段做T监控已开启"""


def overnight_report():
    """夜盘报告"""
    quote = get_mstu_quote()

    if "error" in quote:
        return f"❌ MSTU 夜盘检查失败: {quote['error']}"

    price = quote.get("price", 0)
    prev_close = quote.get("prev_close", 0)
    trading_day = quote.get("latest_trading_day", "")
    prev_day = _prev_trading_day(trading_day)
    change = (price - prev_close) / prev_close * 100 if prev_close else 0
    cost_distance = (price - config.COST_PRICE) / config.COST_PRICE * 100
    position_pnl = (price - config.COST_PRICE) * config.POSITION

    strategy = TradingStrategy()
    pos_info = _position_status(strategy)
    available_cash = _cash_display(strategy)

    return f"""🌙 **MSTU 夜盘速报** ({datetime.now(timezone(timedelta(hours=8))).strftime('%m-%d %H:%M')} 北京)

💰 最新收盘: ${price:.2f} ({_format_date(trading_day)})
📊 前日收盘: ${prev_close:.2f} ({_format_date(prev_day)})
📈 底仓: {cost_distance:+.1f}% (${position_pnl:+,.0f})
💵 可用: ${available_cash:.2f}

{pos_info}

⏰ 下一个关注点: 16:00 盘前"""


def evening_summary():
    """盘中结束总结"""
    quote = get_mstu_quote()

    if "error" in quote:
        return f"❌ MSTU 收盘检查失败: {quote['error']}"

    price = quote.get("price", 0)
    change_pct = quote.get("change_pct", 0)
    high = quote.get("high", 0)
    low = quote.get("low", 0)
    trading_day = quote.get("latest_trading_day", "")
    cost_distance = (price - config.COST_PRICE) / config.COST_PRICE * 100
    position_pnl = (price - config.COST_PRICE) * config.POSITION

    strategy = TradingStrategy()
    pos_info = _position_status(strategy)
    available_cash = _cash_display(strategy)

    # 如果还有持仓，提醒
    if strategy.holding_shares > 0:
        hold_warning = f"\n⚠️ 还有做T持仓 {strategy.holding_shares}股 @ ${strategy.buy_price:.2f}，请注意处理！"
    else:
        hold_warning = ""

    return f"""🌙 **MSTU 盘中结束** ({datetime.now(timezone(timedelta(hours=8))).strftime('%m-%d %H:%M')} 北京)

📅 收盘: ${price:.2f} ({_format_date(trading_day)})
📊 日内: ${low:.2f} - ${high:.2f} ({change_pct:+.2f}%)
📈 底仓: {cost_distance:+.1f}% (${position_pnl:+,.0f})
💵 可用: ${available_cash:.2f}

{pos_info}{hold_warning}

😴 休息时间到，00:00-08:00 不再推送
🌙 夜盘 08:00 开始监控"""


def run_mode(mode: str):
    if mode == "morning":
        return morning_report()
    if mode == "overnight":
        return overnight_report()
    if mode == "evening":
        return evening_summary()
    if mode == "webhook":
        return webhook_worker.run_webhook_cycle()
    return scan()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["scan", "morning", "overnight", "evening", "webhook"], default="scan")
    args = parser.parse_args()

    result = run_mode(args.mode)

    if args.mode == "webhook":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result and result != "SILENT":
        print(result)
        send_to_webhook(result)
    elif result == "SILENT":
        print("SILENT")

