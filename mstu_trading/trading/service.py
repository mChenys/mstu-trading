"""OpenClaw Agent 友好的交易服务入口。

目标：
1. Agent 只调用清晰动作，不直接碰 trade_log.json / position.json。
2. 保持与现有模块兼容，逐步收口到这一层。
"""

from __future__ import annotations

from typing import Any

from mstu_trading.trading.confirmation import (
    STATUS_DEFERRED,
    STATUS_MODIFIED,
    STATUS_NEEDS_CLARIFICATION,
    STATUS_PENDING_CONFIRMATION,
    attach_trade_message_context,
    claim_trade_proposal,
    expire_trade_proposal,
    format_buy_signal_with_id,
    generate_trade_id,
    get_position_state,
    get_trade_proposal,
    list_trade_proposals,
    log_pending_trade,
    release_trade_claim,
    reconcile_pending_trade_states,
)
from mstu_trading.storage.sqlite_storage import list_message_events, list_outbound_messages
from mstu_trading.trading.message_handler import handle_trade_message


def create_trade_proposal(
    signal: dict[str, Any],
    *,
    message_id: str | None = None,
    thread_id: str | None = None,
    channel: str = "feishu",
    agent_source: str = "unknown",
) -> dict[str, Any]:
    """创建一条待确认 proposal，并返回 Agent 可直接使用的结构。"""
    trade_id = generate_trade_id(signal)
    proposal = log_pending_trade(signal, trade_id, agent_source=agent_source)
    message_text = format_buy_signal_with_id(signal, trade_id)
    proposal = attach_trade_message_context(
        trade_id,
        message_id=message_id,
        thread_id=thread_id,
        message_text=message_text,
        channel=channel,
        agent_source=agent_source,
    ) or proposal
    return {
        "trade_id": trade_id,
        "proposal": proposal,
        "message_text": message_text,
        "status": proposal.get("status", STATUS_PENDING_CONFIRMATION),
        "agent_source": proposal.get("agent_source", agent_source),
    }


def list_pending_trades(limit: int = 20) -> list[dict[str, Any]]:
    return list_trade_proposals(status=STATUS_PENDING_CONFIRMATION, limit=limit)


def list_action_required_trades(limit: int = 20) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for status in [STATUS_PENDING_CONFIRMATION, STATUS_DEFERRED, STATUS_MODIFIED, STATUS_NEEDS_CLARIFICATION]:
        results.extend(list_trade_proposals(status=status, limit=limit))
    results.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return results[:limit]


def get_trade_context(trade_id: str) -> dict[str, Any] | None:
    proposal = get_trade_proposal(trade_id)
    if not proposal:
        return None
    return {
        "proposal": proposal,
        "position": get_position_state(),
        "events": list_message_events(trade_id=trade_id, limit=50),
        "outbound_messages": list_outbound_messages(trade_id=trade_id, limit=50),
        "claim": {
            "claimed_by": proposal.get("claimed_by", ""),
            "claimed_at": proposal.get("claimed_at", ""),
            "claim_expires_at": proposal.get("claim_expires_at", ""),
        },
    }


def list_trade_events(trade_id: str, limit: int = 50) -> list[dict[str, Any]]:
    return list_message_events(trade_id=trade_id, limit=limit)


def expire_trade(
    trade_id: str,
    *,
    detail: str = "manual_expire",
    agent_source: str = "unknown",
) -> dict[str, Any]:
    trade = expire_trade_proposal(trade_id, detail=detail, agent_source=agent_source)
    return {
        "handled": trade is not None,
        "trade_id": trade_id,
        "proposal": trade,
    }


def run_recovery_scan(*, agent_source: str = "system") -> dict[str, Any]:
    summary = reconcile_pending_trade_states(agent_source=agent_source)
    summary["pending_after_scan"] = len(list_pending_trades())
    return summary


def claim_trade(
    trade_id: str,
    *,
    agent_source: str,
    ttl_minutes: int = 10,
    force: bool = False,
) -> dict[str, Any]:
    proposal = claim_trade_proposal(
        trade_id,
        agent_source=agent_source,
        ttl_minutes=ttl_minutes,
        force=force,
    )
    return {
        "handled": proposal is not None,
        "trade_id": trade_id,
        "proposal": proposal,
        "claimed_by": (proposal or {}).get("claimed_by", ""),
    }


def release_trade(
    trade_id: str,
    *,
    agent_source: str,
) -> dict[str, Any]:
    proposal = release_trade_claim(trade_id, agent_source=agent_source)
    return {
        "handled": proposal is not None,
        "trade_id": trade_id,
        "proposal": proposal,
    }


def apply_user_reply(
    message: str,
    *,
    reply_to_text: str | None = None,
    reply_to_id: str | None = None,
    user_message_id: str | None = None,
    agent_source: str = "unknown",
) -> dict[str, Any]:
    """统一处理用户回复，供 Agent 直接调用。"""
    result = handle_trade_message(
        message,
        reply_to_text=reply_to_text,
        reply_to_id=reply_to_id,
        user_message_id=user_message_id,
        agent_source=agent_source,
    )
    action = result.get("action", "")
    trade_id = None
    result_text = str(result.get("result", ""))
    # 从结果文本中复用已有 trade_id 文案，不强依赖上层再解析
    for token in result_text.replace("`", " ").split():
        if token.startswith("MSTU-"):
            trade_id = token
            break
    if not trade_id and reply_to_text:
        for token in reply_to_text.replace("`", " ").split():
            if token.startswith("MSTU-"):
                trade_id = token
                break

    return {
        "handled": bool(result.get("handled")),
        "action": action,
        "trade_id": trade_id,
        "result": result.get("result", ""),
        "position": result.get("position") or get_position_state(),
        "notification_sent": bool(result.get("notification_sent", False)),
        "idempotent": bool(result.get("idempotent", False)),
        "duplicate_message": bool(result.get("duplicate_message", False)),
        "agent_source": agent_source,
    }
