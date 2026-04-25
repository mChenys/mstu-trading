"""MSTU 交易确认机制。

这里负责维护结构化 Trade Proposal，供 OpenClaw Agent 与飞书协作：
1. 创建待确认 proposal。
2. 记录 proposal 的消息上下文。
3. 在用户确认/拒绝后推进状态，并同步持仓。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone

from app_runtime import POSITION_STATE_FILE, TRADE_LOG_FILE, ensure_state_dir
from fee_model import BUY, SELL, estimate_fees, estimate_round_trip
from sqlite_storage import (
    append_message_event,
    get_position_snapshot,
    get_trade_record,
    list_trade_records,
    load_json_document,
    save_json_document,
    upsert_position_snapshot,
    upsert_trade_record,
)


POSITION_FILE = POSITION_STATE_FILE
TRADE_LOG_VERSION = 2

STATUS_PENDING_CONFIRMATION = "pending_user_confirmation"
STATUS_CONFIRMED = "confirmed_by_user"
STATUS_REJECTED = "rejected_by_user"
STATUS_EXPIRED = "expired"
STATUS_DEFERRED = "deferred_by_user"
STATUS_MODIFIED = "modified_by_user"
STATUS_NEEDS_CLARIFICATION = "needs_clarification"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _default_trade_log() -> dict:
    return {"trades": [], "version": TRADE_LOG_VERSION}


def _load_trade_log() -> dict:
    trades = list_trade_records(limit=500)
    if trades:
        trades.sort(key=lambda item: item.get("created_at", ""))
        return {"trades": trades, "version": TRADE_LOG_VERSION}

    data = load_json_document("trade_log", _default_trade_log(), json_path=TRADE_LOG_FILE)
    data.setdefault("trades", [])
    data["version"] = max(int(data.get("version", 1)), TRADE_LOG_VERSION)
    return data


def _save_trade_log(log: dict) -> None:
    save_json_document("trade_log", log, json_path=TRADE_LOG_FILE)
    for trade in log.get("trades", []):
        upsert_trade_record(trade)


def _normalize_trade_status(trade: dict) -> str:
    status = str(trade.get("status", "")).strip()
    legacy = {
        "pending": STATUS_PENDING_CONFIRMATION,
        "confirmed": STATUS_CONFIRMED,
        "rejected": STATUS_REJECTED,
    }
    return legacy.get(status, status or STATUS_PENDING_CONFIRMATION)


def _proposal_context(
    trade_id: str,
    message_text: str = "",
    *,
    channel: str = "feishu",
    agent_source: str = "",
    message_id: str | None = None,
    thread_id: str | None = None,
) -> dict:
    return {
        "channel": channel,
        "agent_source": agent_source,
        "interaction_type": "trade_execution_request",
        "proposal_message_id": message_id or "",
        "proposal_thread_id": thread_id or "",
        "proposal_text": message_text or "",
        "last_user_reply_id": "",
        "last_user_reply_text": "",
        "trade_id": trade_id,
        "expected_user_actions": ["confirm", "reject"],
    }


def _mark_expired_pending_trades(log: dict) -> None:
    now = _utc_now()
    for existing in log["trades"]:
        status = _normalize_trade_status(existing)
        expires_at = existing.get("expires_at")
        if status != STATUS_PENDING_CONFIRMATION:
            existing["status"] = status
            continue
        if not expires_at:
            existing["status"] = STATUS_PENDING_CONFIRMATION
            continue
        expire_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        existing["status"] = STATUS_EXPIRED if expire_dt <= now else STATUS_PENDING_CONFIRMATION


def _expire_trade(trade: dict, *, event_type: str, detail: str, agent_source: str = "") -> dict:
    trade["status"] = STATUS_EXPIRED
    trade["expired_at"] = _utc_now_iso()
    append_message_event(
        trade_id=trade.get("trade_id"),
        event_type=event_type,
        agent_source=agent_source or trade.get("agent_source", ""),
        channel=(trade.get("message_context") or {}).get("channel", ""),
        message_id=(trade.get("message_context") or {}).get("proposal_message_id", ""),
        thread_id=(trade.get("message_context") or {}).get("proposal_thread_id", ""),
        payload={
            "status": trade.get("status"),
            "detail": detail,
            "reason": trade.get("reason", ""),
        },
    )
    return trade


def generate_trade_id(signal: dict) -> str:
    """生成交易 ID。"""
    now = _utc_now()
    timestamp = now.strftime("%Y%m%d%H%M")
    price = signal.get("price", 0)
    shares = signal.get("shares", 0)
    hash_input = f"{now.isoformat()}-{price}-{shares}"
    hash_val = hashlib.md5(hash_input.encode()).hexdigest()[:6]
    return f"MSTU-{timestamp}-{hash_val}"


def log_pending_trade(signal: dict, trade_id: str, *, agent_source: str = "") -> dict:
    """记录待确认 proposal。"""
    ensure_state_dir()
    created_at = _utc_now_iso()
    trade_entry = {
        "trade_id": trade_id,
        "action": signal.get("action", "BUY"),
        "price": signal.get("price", 0),
        "shares": signal.get("shares", 0),
        "target_price": signal.get("target_price", 0),
        "stop_price": signal.get("stop_price", 0),
        "position_source": signal.get("position_source", ""),
        "reason": signal.get("reason", ""),
        "status": STATUS_PENDING_CONFIRMATION,
        "agent_source": agent_source,
        "claimed_by": "",
        "claimed_at": "",
        "claim_expires_at": "",
        "created_at": created_at,
        "expires_at": (_utc_now() + timedelta(minutes=30)).isoformat(),
        "confirmed_at": None,
        "proposal_type": "trade_execution_request",
        "schema_version": TRADE_LOG_VERSION,
        "signal_snapshot": {
            "action": signal.get("action", "BUY"),
            "reason": signal.get("reason", ""),
            "signals": signal.get("signals", []),
        },
        "message_context": _proposal_context(trade_id, agent_source=agent_source),
    }

    log = _load_trade_log()
    _mark_expired_pending_trades(log)
    log["trades"].append(trade_entry)
    log["trades"] = log["trades"][-200:]
    _save_trade_log(log)
    append_message_event(
        trade_id=trade_id,
        event_type="proposal_created",
        agent_source=agent_source,
        channel=trade_entry["message_context"].get("channel", ""),
        payload={
            "action": trade_entry["action"],
            "status": trade_entry["status"],
            "reason": trade_entry["reason"],
            "shares": trade_entry["shares"],
            "price": trade_entry["price"],
        },
    )
    return trade_entry


def attach_trade_message_context(
    trade_id: str,
    *,
    message_id: str | None = None,
    thread_id: str | None = None,
    message_text: str | None = None,
    channel: str = "feishu",
    agent_source: str | None = None,
) -> dict | None:
    """在 proposal 发出后回填消息上下文，供后续 reply 匹配使用。"""
    log = _load_trade_log()
    for trade in log["trades"]:
        if trade.get("trade_id") != trade_id:
            continue
        context = trade.get("message_context") or _proposal_context(
            trade_id,
            agent_source=trade.get("agent_source", ""),
        )
        if message_id is not None:
            context["proposal_message_id"] = message_id
        if thread_id is not None:
            context["proposal_thread_id"] = thread_id
        if message_text is not None:
            context["proposal_text"] = message_text
        context["channel"] = channel
        if agent_source is not None:
            context["agent_source"] = agent_source
            trade["agent_source"] = agent_source
        trade["message_context"] = context
        _save_trade_log(log)
        append_message_event(
            trade_id=trade_id,
            event_type="proposal_context_attached",
            agent_source=trade.get("agent_source", ""),
            channel=channel,
            message_id=context.get("proposal_message_id", ""),
            thread_id=context.get("proposal_thread_id", ""),
            payload={
                "proposal_message_id": context.get("proposal_message_id", ""),
                "proposal_thread_id": context.get("proposal_thread_id", ""),
                "has_proposal_text": bool(context.get("proposal_text")),
            },
        )
        return trade
    return None


def record_user_reply_context(
    trade: dict,
    *,
    reply_message_id: str | None = None,
    reply_text: str | None = None,
    agent_source: str = "",
) -> dict:
    context = trade.get("message_context") or _proposal_context(
        trade.get("trade_id", ""),
        agent_source=trade.get("agent_source", ""),
    )
    if reply_message_id is not None:
        context["last_user_reply_id"] = reply_message_id
    if reply_text is not None:
        context["last_user_reply_text"] = reply_text
    trade["message_context"] = context
    append_message_event(
        trade_id=trade.get("trade_id"),
        event_type="user_reply_recorded",
        agent_source=agent_source or trade.get("agent_source", ""),
        channel=context.get("channel", ""),
        message_id=reply_message_id or "",
        thread_id=context.get("proposal_thread_id", ""),
        payload={
            "reply_text": reply_text or "",
            "proposal_message_id": context.get("proposal_message_id", ""),
        },
    )
    return trade


def parse_confirmation(message: str, reply_to_id: str = None) -> dict:
    """解析用户确认消息。"""
    message_lower = message.lower().strip()
    buy_keywords = ["已买入", "买入", "确认买入"]
    sell_keywords = ["已卖出", "卖出", "确认卖出"]
    confirm_keywords = ["确认", "执行", "完成", "done", "ok", "✓", "✅"]
    reject_keywords = ["不买", "不卖", "取消", "放弃", "拒绝", "no", "skip"]
    defer_keywords = ["先等等", "等等", "稍后", "晚点", "先不急", "先观察", "hold on"]
    clarification_keywords = ["什么意思", "怎么做", "没看懂", "解释一下", "为什么", "?", "？"]
    modify_keywords = ["改成", "改为", "少买", "多买", "加到", "减到", "部分", "改价", "调整"]

    if any(kw in message_lower for kw in reject_keywords):
        return {"confirmed": False, "action": "reject", "trade_id": None, "reply_to_id": reply_to_id}

    if any(kw in message_lower for kw in defer_keywords):
        return {"confirmed": False, "action": "defer", "trade_id": None, "reply_to_id": reply_to_id}

    trade_id_match = re.search(r"MSTU-\d{12}-[a-f0-9]{6}", message)
    trade_id = trade_id_match.group() if trade_id_match else None

    if any(kw in message_lower for kw in sell_keywords):
        return {"confirmed": True, "action": "sell_confirm", "trade_id": trade_id, "reply_to_id": reply_to_id}

    if any(kw in message_lower for kw in buy_keywords):
        return {"confirmed": True, "action": "buy_confirm", "trade_id": trade_id, "reply_to_id": reply_to_id}

    if any(kw in message_lower for kw in modify_keywords):
        return {"confirmed": False, "action": "modify", "trade_id": trade_id, "reply_to_id": reply_to_id}

    if any(kw in message_lower for kw in clarification_keywords):
        return {"confirmed": False, "action": "clarify", "trade_id": trade_id, "reply_to_id": reply_to_id}

    if any(kw in message_lower for kw in confirm_keywords):
        return {"confirmed": True, "action": "confirm", "trade_id": trade_id, "reply_to_id": reply_to_id}

    return {"confirmed": False, "action": None, "trade_id": None, "reply_to_id": reply_to_id}


def find_pending_trade(trade_id: str = None, reply_to_id: str = None) -> dict | None:
    """通过 trade_id 或 proposal message id 查找待确认 proposal。"""
    log = _load_trade_log()
    _mark_expired_pending_trades(log)
    pending_trades = [
        t for t in log["trades"]
        if _normalize_trade_status(t) == STATUS_PENDING_CONFIRMATION
    ]

    if trade_id:
        for trade in pending_trades:
            if trade.get("trade_id") == trade_id:
                return trade

    if reply_to_id:
        for trade in pending_trades:
            context = trade.get("message_context") or {}
            if context.get("proposal_message_id") == reply_to_id:
                return trade

    if pending_trades:
        pending_trades.sort(key=lambda item: item.get("created_at", ""), reverse=True)
        return pending_trades[0]
    return None


def _load_position() -> dict:
    snapshot = get_position_snapshot("current")
    if snapshot:
        return snapshot
    return load_json_document("position_state", {}, json_path=POSITION_FILE)


def _save_position(position: dict) -> None:
    upsert_position_snapshot("current", position)
    save_json_document("position_state", position, json_path=POSITION_FILE)


def _persist_trade_update(trade: dict) -> None:
    log = _load_trade_log()
    for existing in log["trades"]:
        if existing.get("trade_id") == trade.get("trade_id"):
            existing.update(trade)
            break
    else:
        log["trades"].append(trade)
        log["trades"] = log["trades"][-200:]
    _save_trade_log(log)


def expire_trade_proposal(
    trade_id: str,
    *,
    detail: str = "manual_expire",
    agent_source: str = "",
) -> dict | None:
    """手动将待确认 proposal 标记为已过期。"""
    trade = get_trade_proposal(trade_id)
    if not trade:
        return None
    normalized_status = _normalize_trade_status(trade)
    if normalized_status != STATUS_PENDING_CONFIRMATION:
        trade["status"] = normalized_status
        return trade
    expired_trade = _expire_trade(
        trade,
        event_type="trade_expired",
        detail=detail,
        agent_source=agent_source,
    )
    _persist_trade_update(expired_trade)
    return expired_trade


def reconcile_pending_trade_states(*, agent_source: str = "") -> dict:
    """批量扫描并落库 pending proposal 的过期状态。"""
    log = _load_trade_log()
    expired_trade_ids: list[str] = []
    changed = False
    now = _utc_now()

    for trade in log["trades"]:
        if _normalize_trade_status(trade) != STATUS_PENDING_CONFIRMATION:
            trade["status"] = _normalize_trade_status(trade)
            continue
        expires_at = trade.get("expires_at")
        if not expires_at:
            continue
        expire_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        if expire_dt > now:
            continue
        expired_trade_ids.append(trade.get("trade_id", ""))
        _expire_trade(
            trade,
            event_type="trade_expired_auto",
            detail="recovery_scan",
            agent_source=agent_source,
        )
        changed = True

    if changed:
        _save_trade_log(log)

    return {
        "checked": len(log.get("trades", [])),
        "expired_count": len(expired_trade_ids),
        "expired_trade_ids": [trade_id for trade_id in expired_trade_ids if trade_id],
    }


def list_trade_proposals(*, status: str | None = None, limit: int = 50) -> list[dict]:
    """列出 proposal，默认按创建时间倒序返回最近记录。"""
    trades = list_trade_records(status=status, limit=limit)
    if not trades:
        log = _load_trade_log()
        _mark_expired_pending_trades(log)
        trades = list(log["trades"])
    if status:
        trades = [trade for trade in trades if _normalize_trade_status(trade) == status]
    trades.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return trades[:limit]


def get_trade_proposal(trade_id: str) -> dict | None:
    """按 trade_id 查询单条 proposal。"""
    trade = get_trade_record(trade_id)
    if trade:
        return trade
    log = _load_trade_log()
    _mark_expired_pending_trades(log)
    for item in log["trades"]:
        if item.get("trade_id") == trade_id:
            return item
    return None


def get_position_state() -> dict:
    """提供给 Agent 的当前持仓快照。"""
    position = _load_position()
    if position:
        return position
    return {
        "symbol": "MSTU",
        "shares": 0,
        "holding_shares": 0,
        "available_cash": 0.0,
        "daily_ops_count": 0,
        "daily_pnl": 0.0,
        "daily_fees": 0.0,
        "cumulative_fees": 0.0,
        "holding_cost_basis": 0.0,
    }


def record_manual_execution(
    *,
    action: str,
    price: float,
    shares: int,
    reason: str,
    position_source: str = "",
    pnl: float | None = None,
    total_fees: float | None = None,
    stop_price: float = 0.0,
    target_price: float = 0.0,
    reply_message_id: str | None = None,
    reply_text: str | None = None,
    channel: str = "feishu",
    agent_source: str = "",
) -> dict:
    """为人工直接回报的成交生成标准化 trade record。"""
    signal = {
        "action": action,
        "price": price,
        "shares": shares,
    }
    trade_id = generate_trade_id(signal)
    trade = {
        "trade_id": trade_id,
        "action": action,
        "price": price,
        "shares": shares,
        "target_price": target_price,
        "stop_price": stop_price,
        "position_source": position_source,
        "reason": reason,
        "status": STATUS_CONFIRMED,
        "agent_source": agent_source,
        "created_at": _utc_now_iso(),
        "confirmed_at": _utc_now_iso(),
        "proposal_type": "manual_execution_report",
        "schema_version": TRADE_LOG_VERSION,
        "signal_snapshot": {
            "action": action,
            "reason": reason,
            "signals": [],
        },
        "message_context": {
            "channel": channel,
            "agent_source": agent_source,
            "interaction_type": "manual_execution_report",
            "proposal_message_id": "",
            "proposal_thread_id": "",
            "proposal_text": "",
            "last_user_reply_id": reply_message_id or "",
            "last_user_reply_text": reply_text or "",
            "trade_id": trade_id,
            "expected_user_actions": [],
        },
    }
    if pnl is not None:
        trade["pnl"] = round(pnl, 2)
    if total_fees is not None:
        trade["fees"] = round(total_fees, 2)
    _persist_trade_update(trade)
    append_message_event(
        trade_id=trade_id,
        event_type="manual_execution_recorded",
        agent_source=agent_source,
        channel=channel,
        message_id=reply_message_id or "",
        payload={
            "action": action,
            "reason": reason,
            "shares": shares,
            "price": price,
            "pnl": trade.get("pnl"),
            "fees": trade.get("fees"),
        },
    )
    return trade


def confirm_trade(trade: dict, *, agent_source: str = "") -> dict:
    """确认交易执行并更新持仓。"""
    ensure_state_dir()
    trade["status"] = STATUS_CONFIRMED
    trade["confirmed_at"] = _utc_now_iso()

    position = _load_position()
    action = trade.get("action", "BUY")
    price = trade.get("price", 0)
    shares = trade.get("shares", 0)
    position.setdefault("daily_fees", 0.0)
    position.setdefault("cumulative_fees", 0.0)
    current_shares = position.get("holding_shares", 0)
    current_buy_price = position.get("buy_price", 0.0)
    current_cost_basis = position.get("holding_cost_basis", current_buy_price * current_shares)

    if action == BUY:
        current_cash = position.get("available_cash", 1400)
        buy_fees = estimate_fees(BUY, price=price, shares=shares)
        total_cash_cost = buy_fees.gross_amount + buy_fees.total_fees
        total_cost_basis = current_cost_basis + total_cash_cost
        if current_shares > 0:
            total_cost = current_buy_price * current_shares + price * shares
            new_shares = current_shares + shares
            new_avg_price = total_cost / new_shares
        else:
            new_shares = shares
            new_avg_price = price

        position["holding_shares"] = new_shares
        position["buy_price"] = round(new_avg_price, 4)
        position["target_price"] = trade.get("target_price", 0)
        position["stop_price"] = trade.get("stop_price", 0)
        position["position_source"] = trade.get("position_source", "")
        position["available_cash"] = round(current_cash - total_cash_cost, 2)
        position["holding_cost_basis"] = round(total_cost_basis, 2)
        position["daily_ops_count"] = position.get("daily_ops_count", 0) + 1
        position["daily_fees"] = round(position.get("daily_fees", 0.0) + buy_fees.total_fees, 2)
        position["cumulative_fees"] = round(position.get("cumulative_fees", 0.0) + buy_fees.total_fees, 2)
        trade["fees"] = buy_fees.total_fees
        trade["fee_breakdown"] = buy_fees.to_dict()

    elif action == SELL:
        current_cash = position.get("available_cash", 1400)
        sell_shares = min(shares, current_shares)
        avg_cost_basis = (current_cost_basis / current_shares) if current_shares > 0 else 0.0
        allocated_cost_basis = avg_cost_basis * sell_shares
        sell_fees = estimate_fees(SELL, price=price, shares=sell_shares)
        profit = sell_fees.net_amount - allocated_cost_basis

        position["holding_shares"] = current_shares - sell_shares
        position["available_cash"] = round(current_cash + sell_fees.net_amount, 2)
        position["daily_ops_count"] = position.get("daily_ops_count", 0) + 1
        position["daily_pnl"] = round(position.get("daily_pnl", 0) + profit, 2)
        position["daily_fees"] = round(position.get("daily_fees", 0.0) + sell_fees.total_fees, 2)
        position["cumulative_fees"] = round(position.get("cumulative_fees", 0.0) + sell_fees.total_fees, 2)
        remaining_cost_basis = max(current_cost_basis - allocated_cost_basis, 0.0)
        position["holding_cost_basis"] = round(remaining_cost_basis, 2)
        trade["fees"] = sell_fees.total_fees
        trade["pnl"] = round(profit, 2)
        trade["fee_breakdown"] = sell_fees.to_dict()

        if position["holding_shares"] <= 0:
            position["holding_shares"] = 0
            position["buy_price"] = 0
            position["target_price"] = 0
            position["stop_price"] = 0
            position["position_source"] = ""
            position["holding_cost_basis"] = 0.0

    position["updated_at"] = _utc_now_iso()
    _save_position(position)
    _persist_trade_update(trade)
    append_message_event(
        trade_id=trade.get("trade_id"),
        event_type="trade_confirmed",
        agent_source=agent_source or trade.get("agent_source", ""),
        channel=(trade.get("message_context") or {}).get("channel", ""),
        message_id=(trade.get("message_context") or {}).get("last_user_reply_id", ""),
        thread_id=(trade.get("message_context") or {}).get("proposal_thread_id", ""),
        payload={
            "action": action,
            "status": trade.get("status"),
            "holding_shares": position.get("holding_shares", 0),
            "available_cash": position.get("available_cash", 0.0),
        },
    )
    return position


def reject_trade(trade: dict, *, agent_source: str = "") -> dict:
    """标记 proposal 被用户拒绝。"""
    ensure_state_dir()
    trade["status"] = STATUS_REJECTED
    trade["rejected_at"] = _utc_now_iso()
    _persist_trade_update(trade)
    append_message_event(
        trade_id=trade.get("trade_id"),
        event_type="trade_rejected",
        agent_source=agent_source or trade.get("agent_source", ""),
        channel=(trade.get("message_context") or {}).get("channel", ""),
        message_id=(trade.get("message_context") or {}).get("last_user_reply_id", ""),
        thread_id=(trade.get("message_context") or {}).get("proposal_thread_id", ""),
        payload={
            "status": trade.get("status"),
            "reason": trade.get("reason", ""),
        },
    )
    return trade


def mark_trade_needs_follow_up(
    trade: dict,
    *,
    status: str,
    reply_text: str,
    event_type: str,
    agent_source: str = "",
) -> dict:
    """把待确认 proposal 标记成需要进一步人工协作。"""
    ensure_state_dir()
    trade["status"] = status
    trade["updated_at"] = _utc_now_iso()
    _persist_trade_update(trade)
    append_message_event(
        trade_id=trade.get("trade_id"),
        event_type=event_type,
        agent_source=agent_source or trade.get("agent_source", ""),
        channel=(trade.get("message_context") or {}).get("channel", ""),
        message_id=(trade.get("message_context") or {}).get("last_user_reply_id", ""),
        thread_id=(trade.get("message_context") or {}).get("proposal_thread_id", ""),
        payload={
            "status": status,
            "reply_text": reply_text,
        },
    )
    return trade


def claim_trade_proposal(
    trade_id: str,
    *,
    agent_source: str,
    ttl_minutes: int = 10,
    force: bool = False,
) -> dict | None:
    trade = get_trade_proposal(trade_id)
    if not trade:
        return None
    now = _utc_now()
    claim_expires_at = trade.get("claim_expires_at") or ""
    claim_expired = True
    if claim_expires_at:
        try:
            claim_expired = datetime.fromisoformat(claim_expires_at.replace("Z", "+00:00")) <= now
        except ValueError:
            claim_expired = True
    current_claimant = trade.get("claimed_by", "")
    if current_claimant and current_claimant != agent_source and not claim_expired and not force:
        return trade

    trade["claimed_by"] = agent_source
    trade["claimed_at"] = now.isoformat()
    trade["claim_expires_at"] = (now + timedelta(minutes=ttl_minutes)).isoformat()
    _persist_trade_update(trade)
    append_message_event(
        trade_id=trade.get("trade_id"),
        event_type="trade_claimed",
        agent_source=agent_source,
        channel=(trade.get("message_context") or {}).get("channel", ""),
        message_id=(trade.get("message_context") or {}).get("proposal_message_id", ""),
        thread_id=(trade.get("message_context") or {}).get("proposal_thread_id", ""),
        payload={
            "claimed_by": trade["claimed_by"],
            "claimed_at": trade["claimed_at"],
            "claim_expires_at": trade["claim_expires_at"],
            "force": force,
        },
    )
    return trade


def release_trade_claim(trade_id: str, *, agent_source: str) -> dict | None:
    trade = get_trade_proposal(trade_id)
    if not trade:
        return None
    if trade.get("claimed_by") and trade.get("claimed_by") != agent_source:
        return trade
    trade["claimed_by"] = ""
    trade["claimed_at"] = ""
    trade["claim_expires_at"] = ""
    _persist_trade_update(trade)
    append_message_event(
        trade_id=trade.get("trade_id"),
        event_type="trade_claim_released",
        agent_source=agent_source,
        channel=(trade.get("message_context") or {}).get("channel", ""),
        message_id=(trade.get("message_context") or {}).get("proposal_message_id", ""),
        thread_id=(trade.get("message_context") or {}).get("proposal_thread_id", ""),
        payload={"released_by": agent_source},
    )
    return trade


def format_buy_signal_with_id(signal: dict, trade_id: str) -> str:
    """格式化带交互上下文的买入建议。"""
    price = signal.get("price", 0)
    shares = signal.get("shares", 0)
    target = signal.get("target_price", 0)
    stop = signal.get("stop_price", 0)
    reason = signal.get("reason", "")
    source = signal.get("position_source", "")

    source_label = {
        "premarket-dip": "盘前低吸",
        "premarket-momentum": "盘前追涨",
        "overnight-dip": "夜盘低吸",
        "overnight-momentum": "夜盘追涨",
        "regular": "盘中做T",
    }.get(source, source)

    round_trip_profit = estimate_round_trip(price, target, shares)
    round_trip_loss = estimate_round_trip(price, stop, shares)
    buy_fee = round_trip_profit["buy"]["total_fees"]
    sell_fee_at_target = round_trip_profit["sell"]["total_fees"]
    sell_fee_at_stop = round_trip_loss["sell"]["total_fees"]
    estimated_profit = round_trip_profit["net_pnl"]
    estimated_loss = round_trip_loss["net_pnl"]

    return f"""🟢 **MSTU 买入建议（{source_label}）**

📋 交易ID: `{trade_id}`
🧭 交互类型: `trade_execution_request`
⏳ 当前状态: `pending_user_confirmation`
💰 价格: ${price:.2f}
📈 建议买入: {shares}股
🎯 目标价: ${target:.2f}
⛔ 止损价: ${stop:.2f}
💸 预估手续费: 买入${buy_fee:.2f} | 卖出${sell_fee_at_target:.2f}/${sell_fee_at_stop:.2f}
💵 预估净盈利: ${estimated_profit:+.2f} | 预估净亏损: ${estimated_loss:+.2f}

📍 信号: {reason}

---
💡 **确认执行请回复**: `已买入 {trade_id}` 或直接回复本消息说"确认"
💡 **取消本次建议请回复**: `取消 {trade_id}`
⏰ 本信号30分钟内有效"""


def get_confirmation_response(trade: dict, position: dict) -> str:
    """生成确认后的响应消息。"""
    action = trade.get("action", "BUY")

    if action == BUY:
        return f"""✅ **交易已确认执行**

📋 交易ID: {trade["trade_id"]}
💰 买入价: ${trade["price"]:.2f}
📈 买入股数: {trade["shares"]}股
💸 手续费: ${trade.get("fees", 0):.2f}

📊 **当前持仓状态**:
- 持股: {position.get("holding_shares", 0)}股
- 成本价: ${position.get("buy_price", 0):.4f}
- 目标价: ${position.get("target_price", 0):.2f}
- 止损价: ${position.get("stop_price", 0):.2f}
- 可用现金: ${position.get("available_cash", 0):.2f}
- 持仓成本(含费): ${position.get("holding_cost_basis", 0):.2f}

💡 盘中监控会基于此持仓状态运行"""

    if action == SELL:
        return f"""✅ **卖出已确认执行**

📋 交易ID: {trade["trade_id"]}
💰 卖出价: ${trade["price"]:.2f}
📈 卖出股数: {trade["shares"]}股
💸 手续费: ${trade.get("fees", 0):.2f}
📊 净盈亏: ${trade.get("pnl", 0):+.2f}

📊 **当前持仓状态**:
- 持股: {position.get("holding_shares", 0)}股
- 可用现金: ${position.get("available_cash", 0):.2f}"""

    return f"✅ 已确认交易 {trade.get('trade_id', '--')}"


if __name__ == "__main__":
    test_signal = {
        "action": "BUY",
        "price": 7.84,
        "shares": 89,
        "target_price": 7.93,
        "stop_price": 7.78,
        "position_source": "premarket-momentum",
        "reason": "盘前高开+2.8%",
    }

    trade_id = generate_trade_id(test_signal)
    trade = log_pending_trade(test_signal, trade_id)
    print(json.dumps(trade, ensure_ascii=False, indent=2))
