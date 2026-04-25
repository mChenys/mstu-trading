"""MSTU 交易确认消息处理器

当 Jarvis 在群聊收到用户的交易确认消息时，自动执行：
1. 解析确认内容
2. 匹配待确认交易
3. 更新 position.json
4. 回复确认结果

这个模块被设计为可以被 OpenClaw agent 直接调用。
"""

import json
import re
from datetime import datetime, timezone, timedelta

from app_runtime import POSITION_STATE_FILE, TRADE_LOG_FILE
from fee_model import BUY, SELL, estimate_fees, max_affordable_shares
from trade_confirmation import (
    find_pending_trade,
    parse_confirmation,
    confirm_trade,
    reject_trade,
    get_position_state,
    get_confirmation_response,
    mark_trade_needs_follow_up,
    record_user_reply_context,
    record_manual_execution,
    STATUS_DEFERRED,
    STATUS_MODIFIED,
    STATUS_NEEDS_CLARIFICATION,
)
from execution_notifier import send_trade_execution_notice
from sqlite_storage import (
    append_message_event,
    find_latest_message_event_by_message_id,
    save_json_document,
    upsert_position_snapshot,
)

POSITION_FILE = POSITION_STATE_FILE


def _extract_trade_id(*texts: str) -> str:
    """从消息正文或被回复原文中提取交易ID。"""
    pattern = r'MSTU-\d{12}-[a-f0-9]{6}'
    for text in texts:
        if not text:
            continue
        match = re.search(pattern, text)
        if match:
            return match.group(0)
    return None


def _duplicate_reply_result(user_message_id: str) -> dict | None:
    if not user_message_id:
        return None
    existing = find_latest_message_event_by_message_id(
        user_message_id,
        event_type="user_reply_processed",
    )
    if not existing:
        return None
    payload = dict(existing.get("payload") or {})
    payload["handled"] = True
    payload["idempotent"] = True
    payload["duplicate_message"] = True
    return payload


def _finalize_user_reply(result: dict, *, user_message_id: str = None, reply_to_id: str = None) -> dict:
    if user_message_id and result.get("handled"):
        append_message_event(
            trade_id=result.get("trade_id"),
            event_type="user_reply_processed",
            agent_source=result.get("agent_source", ""),
            message_id=user_message_id,
            thread_id=reply_to_id or "",
            payload={
                "action": result.get("action", ""),
                "trade_id": result.get("trade_id"),
                "result": result.get("result", ""),
                "position": result.get("position"),
                "notification_sent": bool(result.get("notification_sent", False)),
            },
        )
    return result

def handle_trade_message(
    message: str,
    reply_to_text: str = None,
    *,
    reply_to_id: str = None,
    user_message_id: str = None,
    agent_source: str = "",
) -> dict:
    """
    处理群聊中的交易确认消息
    
    Args:
        message: 用户发送的消息文本
        reply_to_text: 用户回复的原文（如果有）
    
    Returns:
        dict: {
            "handled": bool,      # 是否被识别为交易消息
            "action": str,        # buy_confirm / sell_confirm / stop_loss_confirm
            "result": str,        # 处理结果描述
            "position": dict      # 更新后的持仓状态
        }
    """
    msg = message.strip()
    duplicate = _duplicate_reply_result(user_message_id)
    if duplicate is not None:
        return duplicate

    # 优先走交易ID确认链路，兼容“确认”/“已买入 TRADE_ID”这类推荐回复格式
    reply_text = (reply_to_text or "").strip()
    trade_id = _extract_trade_id(msg, reply_text)
    confirmation = parse_confirmation(msg, reply_to_id=reply_to_id)
    if trade_id and not confirmation.get("trade_id"):
        confirmation["trade_id"] = trade_id

    if confirmation.get("action") == "reject":
        pending_trade = find_pending_trade(confirmation.get("trade_id"), reply_to_id=reply_to_id)
        if pending_trade:
            record_user_reply_context(
                pending_trade,
                reply_message_id=user_message_id,
                reply_text=msg,
                agent_source=agent_source,
            )
            rejected = reject_trade(pending_trade, agent_source=agent_source)
            notification_sent = send_trade_execution_notice(
                "trade_rejected",
                f"❎ 已取消交易 {rejected['trade_id']}",
                load_position(),
                agent_source=agent_source,
            )
            return _finalize_user_reply({
                "handled": True,
                "action": "trade_rejected",
                "result": f"❎ 已取消交易 {rejected['trade_id']}",
                "position": load_position(),
                "trade_id": rejected["trade_id"],
                "notification_sent": notification_sent,
                "agent_source": agent_source,
            }, user_message_id=user_message_id, reply_to_id=reply_to_id)
        return _finalize_user_reply({
            "handled": True,
            "action": "trade_rejected",
            "result": "⚠️ 未找到可取消的待确认交易",
            "position": load_position(),
            "agent_source": agent_source,
        }, user_message_id=user_message_id, reply_to_id=reply_to_id)

    if confirmation.get("action") in {"defer", "modify", "clarify"}:
        pending_trade = find_pending_trade(confirmation.get("trade_id"), reply_to_id=reply_to_id)
        if not pending_trade:
            return _finalize_user_reply({
                "handled": True,
                "action": confirmation.get("action"),
                "result": "⚠️ 未找到待处理的交易上下文，请带上 trade_id 或直接回复原消息",
                "position": load_position(),
                "agent_source": agent_source,
            }, user_message_id=user_message_id, reply_to_id=reply_to_id)

        record_user_reply_context(
            pending_trade,
            reply_message_id=user_message_id,
            reply_text=msg,
            agent_source=agent_source,
        )
        status_map = {
            "defer": (STATUS_DEFERRED, "trade_deferred", "⏸️ 已标记为稍后处理，当前 proposal 暂不执行"),
            "modify": (STATUS_MODIFIED, "trade_modified", "🛠️ 已记录你的修改要求，请按新条件重新确认"),
            "clarify": (STATUS_NEEDS_CLARIFICATION, "trade_needs_clarification", "💬 已标记为待澄清，建议补充说明后再执行"),
        }
        status, action, result_text = status_map[confirmation["action"]]
        updated = mark_trade_needs_follow_up(
            pending_trade,
            status=status,
            reply_text=msg,
            event_type=action,
            agent_source=agent_source,
        )
        return _finalize_user_reply({
            "handled": True,
            "action": action,
            "result": result_text,
            "position": load_position(),
            "trade_id": updated.get("trade_id"),
            "notification_sent": False,
            "agent_source": agent_source,
        }, user_message_id=user_message_id, reply_to_id=reply_to_id)

    if confirmation.get("confirmed"):
        pending_trade = find_pending_trade(confirmation.get("trade_id"), reply_to_id=reply_to_id)
        if pending_trade:
            record_user_reply_context(
                pending_trade,
                reply_message_id=user_message_id,
                reply_text=msg,
                agent_source=agent_source,
            )
            position = confirm_trade(pending_trade, agent_source=agent_source)
            result_text = get_confirmation_response(pending_trade, position)
            notification_sent = send_trade_execution_notice(
                confirmation.get("action") or "confirm",
                result_text,
                position,
                agent_source=agent_source,
            )
            return _finalize_user_reply({
                "handled": True,
                "action": confirmation.get("action") or "confirm",
                "result": result_text,
                "position": position,
                "trade_id": pending_trade.get("trade_id"),
                "notification_sent": notification_sent,
                "agent_source": agent_source,
            }, user_message_id=user_message_id, reply_to_id=reply_to_id)
        # 显式“已买入/已卖出”但没有 pending proposal 时，回退到手工成交路径。
        if confirmation.get("action") == "confirm":
            return _finalize_user_reply({
                "handled": True,
                "action": confirmation.get("action") or "confirm",
                "result": "⚠️ 未找到待确认交易，请检查是否已过期或已确认",
                "position": load_position(),
                "agent_source": agent_source,
            }, user_message_id=user_message_id, reply_to_id=reply_to_id)
    
    # ===== 卖出/止损确认 =====
    sell_patterns = [
        r"已卖出", r"已止损", r"止损卖出", r"卖出了", r"止损了",
        r"sell", r"stopped?\s*out",
        r"已卖", r"清仓"
    ]
    sell_matched = any(re.search(p, msg, re.IGNORECASE) for p in sell_patterns)
    
    # ===== 买入确认 =====
    buy_patterns = [
        r"已买入", r"买入成功", r"确认买入", r"买了", r"买入了",
        r"buy", r"bought",
        r"已买"
    ]
    buy_matched = any(re.search(p, msg, re.IGNORECASE) for p in buy_patterns)
    
    # ===== 价格提取 =====
    # 优先提取明确的 $数字 格式，再找纯数字
    price_match = re.search(r'\$\s*(\d+\.?\d*)', msg)
    if not price_match:
        # 找 "价格 X.XX" 或 "X.XX 卖出/买入" 模式
        price_match = re.search(r'(?:价格|价)\s*[:\s]*(\d+\.?\d*)', msg)
    if not price_match:
        price_match = re.search(r'(\d+\.\d+)\s+\d+\s*股', msg)
    if not price_match:
        # 找句子末尾的价格
        price_match = re.search(r'(\d+\.\d+)\s*(?:卖|买|$|，|。|$)', msg)
    extracted_price = float(price_match.group(1)) if price_match else None
    
    # ===== 股数提取 =====
    shares_match = re.search(r'(\d+)\s*股', msg)
    extracted_shares = int(shares_match.group(1)) if shares_match else None
    
    # ===== 止损价提取 =====
    stop_match = re.search(r'止损\s*\$?(\d+\.?\d*)', msg)
    extracted_stop = float(stop_match.group(1)) if stop_match else None
    
    # 不是交易消息，跳过
    if not sell_matched and not buy_matched:
        return {"handled": False}
    
    # 加载当前持仓
    position = load_position()
    
    if sell_matched:
        return _finalize_user_reply(
            handle_sell_confirmation(
                position,
                extracted_price,
                extracted_shares,
                msg,
                agent_source=agent_source,
            ),
            user_message_id=user_message_id,
            reply_to_id=reply_to_id,
        )
    
    if buy_matched:
        return _finalize_user_reply(
            handle_buy_confirmation(
                position,
                extracted_price,
                extracted_shares,
                extracted_stop,
                msg,
                agent_source=agent_source,
            ),
            user_message_id=user_message_id,
            reply_to_id=reply_to_id,
        )


def handle_sell_confirmation(
    position: dict,
    price: float = None,
    shares: int = None,
    msg: str = "",
    *,
    agent_source: str = "",
) -> dict:
    """处理卖出/止损确认"""
    
    # 从持仓获取数据
    holding = position.get("holding_shares", 0)
    buy_price = position.get("buy_price", 0)
    position.setdefault("daily_fees", 0.0)
    position.setdefault("cumulative_fees", 0.0)
    current_cost_basis = position.get("holding_cost_basis", buy_price * holding)
    
    if holding <= 0:
        return {
            "handled": True,
            "action": "sell_confirm",
            "result": "⚠️ 当前无持仓，无需卖出",
            "position": position,
            "agent_source": agent_source,
        }
    
    # 使用提取的价格，或回退到止损价
    sell_price = price or position.get("stop_price", 0)
    sell_shares = shares or holding  # 默认全部卖出
    sell_shares = min(sell_shares, holding)
    
    # 计算盈亏
    avg_cost_basis = (current_cost_basis / holding) if holding > 0 else 0.0
    allocated_cost_basis = avg_cost_basis * sell_shares
    fee_breakdown = estimate_fees(SELL, price=sell_price, shares=sell_shares)
    pnl = fee_breakdown.net_amount - allocated_cost_basis
    cash_change = fee_breakdown.net_amount
    remaining_cost_basis = max(current_cost_basis - allocated_cost_basis, 0.0)
    
    # 更新持仓
    position["holding_shares"] = max(0, holding - sell_shares)
    position["available_cash"] = round(position.get("available_cash", 0) + cash_change, 2)
    position["daily_ops_count"] = position.get("daily_ops_count", 0) + 1
    position["daily_pnl"] = round(position.get("daily_pnl", 0) + pnl, 2)
    position["daily_fees"] = round(position.get("daily_fees", 0.0) + fee_breakdown.total_fees, 2)
    position["cumulative_fees"] = round(position.get("cumulative_fees", 0.0) + fee_breakdown.total_fees, 2)
    position["holding_cost_basis"] = round(remaining_cost_basis, 2)
    
    # 清仓后重置
    if position["holding_shares"] <= 0:
        position["holding_shares"] = 0
        position["buy_price"] = 0
        position["target_price"] = 0
        position["stop_price"] = 0
        position["position_source"] = ""
        position["holding_cost_basis"] = 0.0
    
    position["last_trade"] = {
        "action": "SELL",
        "price": sell_price,
        "shares": sell_shares,
        "pnl": round(pnl, 2),
        "fees": fee_breakdown.total_fees,
        "reason": "止损卖出" if "止损" in msg else "卖出",
        "date": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    }
    position["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    save_position(position)
    manual_trade = record_manual_execution(
        action=SELL,
        price=sell_price,
        shares=sell_shares,
        pnl=pnl,
        total_fees=fee_breakdown.total_fees,
        reason="止损卖出" if "止损" in msg else "卖出",
        position_source=position.get("position_source", ""),
        stop_price=position.get("stop_price", 0),
        target_price=position.get("target_price", 0),
        reply_text=msg,
        agent_source=agent_source,
    )
    result_msg = f"""✅ **卖出已确认**

💰 卖出价: ${sell_price:.2f} × {sell_shares}股
💸 手续费: ${fee_breakdown.total_fees:.2f}
📊 净盈亏: ${pnl:+.2f}
💵 可用现金: ${position['available_cash']:.2f}
📦 剩余持仓: {position['holding_shares']}股"""
    
    if position["holding_shares"] == 0:
        result_msg += "\n🔓 做T空仓，等待下一个买入信号"

    notification_sent = send_trade_execution_notice(
        "sell_confirm",
        result_msg,
        position,
        agent_source=agent_source,
    )
    
    return {
        "handled": True,
        "action": "sell_confirm",
        "result": result_msg,
        "position": position,
        "notification_sent": notification_sent,
        "trade_id": manual_trade["trade_id"],
        "agent_source": agent_source,
    }


def handle_buy_confirmation(
    position: dict,
    price: float = None,
    shares: int = None,
    stop_price: float = None,
    msg: str = "",
    *,
    agent_source: str = "",
) -> dict:
    """处理买入确认"""
    
    # 使用提取的价格，或回退到推送中的建议价
    buy_price = price or position.get("buy_price", 0)
    position.setdefault("daily_fees", 0.0)
    position.setdefault("cumulative_fees", 0.0)
    
    # 计算可买股数（如果未指定）
    if shares:
        buy_shares = shares
    else:
        available = position.get("available_cash", 0)
        buy_shares = max_affordable_shares(available, buy_price) if buy_price > 0 else 0
    
    fee_breakdown = estimate_fees(BUY, price=buy_price, shares=buy_shares)
    cost = fee_breakdown.gross_amount + fee_breakdown.total_fees

    # 更新持仓
    current_shares = position.get("holding_shares", 0)
    current_buy_price = position.get("buy_price", 0)
    current_cost_basis = position.get("holding_cost_basis", current_buy_price * current_shares)
    
    if current_shares > 0 and current_buy_price > 0:
        # 已有持仓，计算新均价
        total_cost = current_buy_price * current_shares + buy_price * buy_shares
        new_shares = current_shares + buy_shares
        new_avg = total_cost / new_shares
    else:
        new_shares = buy_shares
        new_avg = buy_price
    
    position["holding_shares"] = new_shares
    position["buy_price"] = round(new_avg, 4)
    position["available_cash"] = round(position.get("available_cash", 0) - cost, 2)
    position["holding_cost_basis"] = round(current_cost_basis + cost, 2)
    position["daily_ops_count"] = position.get("daily_ops_count", 0) + 1
    position["daily_fees"] = round(position.get("daily_fees", 0.0) + fee_breakdown.total_fees, 2)
    position["cumulative_fees"] = round(position.get("cumulative_fees", 0.0) + fee_breakdown.total_fees, 2)
    
    if stop_price:
        position["stop_price"] = stop_price
    
    position["last_trade"] = {
        "action": "BUY",
        "price": buy_price,
        "shares": buy_shares,
        "fees": fee_breakdown.total_fees,
        "reason": "用户确认买入",
        "date": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    }
    position["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    save_position(position)
    manual_trade = record_manual_execution(
        action=BUY,
        price=buy_price,
        shares=buy_shares,
        pnl=0.0,
        total_fees=fee_breakdown.total_fees,
        reason="用户确认买入",
        position_source=position.get("position_source", ""),
        stop_price=position.get("stop_price", 0),
        target_price=position.get("target_price", 0),
        reply_text=msg,
        agent_source=agent_source,
    )
    
    result_msg = f"""✅ **买入已确认**

💰 买入价: ${buy_price:.2f} × {buy_shares}股
💸 手续费: ${fee_breakdown.total_fees:.2f}
📊 当前持仓: {new_shares}股 @ ${new_avg:.4f}
📦 持仓成本(含费): ${position['holding_cost_basis']:.2f}
💵 可用现金: ${position['available_cash']:.2f}
🎯 目标价: ${position.get('target_price', 0):.2f}
⛔ 止损价: ${position.get('stop_price', 0):.2f}

💡 盘中监控已基于此持仓运行"""
    notification_sent = send_trade_execution_notice(
        "buy_confirm",
        result_msg,
        position,
        agent_source=agent_source,
    )
    
    return {
        "handled": True,
        "action": "buy_confirm",
        "result": result_msg,
        "position": position,
        "notification_sent": notification_sent,
        "trade_id": manual_trade["trade_id"],
        "agent_source": agent_source,
    }


def load_position() -> dict:
    """加载持仓状态"""
    position = get_position_state()
    if position:
        return position
    return {
        "symbol": "MSTU",
        "shares": 0,
        "holding_shares": 0,
        "available_cash": 706.3,
        "daily_ops_count": 0,
        "daily_pnl": 0.0,
        "daily_fees": 0.0,
        "cumulative_fees": 0.0,
        "holding_cost_basis": 0.0,
    }


def save_position(position: dict):
    """保存持仓状态"""
    upsert_position_snapshot("current", position)
    save_json_document("position_state", position, json_path=POSITION_FILE)

def get_current_status() -> str:
    """获取当前持仓状态文本（供 Jarvis 快速查询）"""
    position = load_position()
    holding = position.get("holding_shares", 0)
    
    if holding > 0:
        return f"""📦 MSTU 当前持仓: {holding}股 @ ${position.get('buy_price', 0):.2f}
🎯 目标: ${position.get('target_price', 0):.2f} | ⛔ 止损: ${position.get('stop_price', 0):.2f}
💵 可用: ${position.get('available_cash', 0):.2f}"""
    else:
        return f"📦 MSTU 空仓 | 💵 可用: ${position.get('available_cash', 0):.2f}"


if __name__ == "__main__":
    # 测试
    print("=== 测试卖出确认 ===")
    result = handle_trade_message("昨晚已经止损了这 95 股，7.08 卖出了")
    print(f"handled: {result['handled']}")
    print(f"action: {result['action']}")
    print(f"result:\n{result['result']}")
    print(f"\nposition: {json.dumps(result['position'], indent=2)}")
