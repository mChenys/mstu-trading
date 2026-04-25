"""统一飞书消息网关。

目标：
1. 统一 webhook / chat API 两种发送方式。
2. 让业务层只表达“我要发什么”，不关心底层通道。
3. 保留兼容接口，方便现有模块平滑迁移。
"""

from __future__ import annotations

import json
from typing import Any

import requests

import config
from sqlite_storage import find_successful_outbound_by_dedupe_key, record_outbound_message


def _build_text_payload(text: str) -> dict[str, Any]:
    return {
        "msg_type": "text",
        "content": {"text": text},
    }


def send_webhook_text(webhook_url: str, text: str, timeout: int = 10) -> requests.Response:
    return requests.post(
        webhook_url,
        json=_build_text_payload(text),
        timeout=timeout,
    )


def _get_tenant_access_token(timeout: int = 10) -> str | None:
    app_id = getattr(config, "FEISHU_APP_ID", "")
    app_secret = getattr(config, "FEISHU_APP_SECRET", "")
    if not app_id or not app_secret:
        return None

    response = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(payload.get("msg") or "failed to get tenant access token")
    return payload.get("tenant_access_token")


def send_chat_text(chat_id: str, text: str, timeout: int = 10) -> requests.Response:
    token = _get_tenant_access_token(timeout=timeout)
    if not token:
        raise RuntimeError("missing FEISHU_APP_ID or FEISHU_APP_SECRET")

    return requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        params={"receive_id_type": "chat_id"},
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        },
        timeout=timeout,
    )


def send_text_message(
    text: str,
    *,
    webhook_url: str | None = None,
    chat_id: str | None = None,
    prefer_chat_api: bool = True,
    timeout: int = 10,
    record_outbound: bool = False,
    outbound_event_type: str = "outbound_text",
    trade_id: str | None = None,
    agent_source: str = "",
    dedupe_key: str | None = None,
) -> tuple[bool, str]:
    """发送文本消息并返回 (是否成功, 结果说明)。"""
    if record_outbound and dedupe_key:
        existing = find_successful_outbound_by_dedupe_key(
            dedupe_key,
            event_type=outbound_event_type,
        )
        if existing:
            return True, "idempotent"

    if prefer_chat_api and chat_id:
        try:
            response = send_chat_text(chat_id, text, timeout=timeout)
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") == 0:
                if record_outbound:
                    record_outbound_message(
                        event_type=outbound_event_type,
                        message_text=text,
                        success=True,
                        detail="chat_api",
                        trade_id=trade_id,
                        agent_source=agent_source,
                        dedupe_key=dedupe_key,
                        channel="feishu",
                        transport="chat_api",
                    )
                return True, "chat_api"
            if record_outbound:
                record_outbound_message(
                    event_type=outbound_event_type,
                    message_text=text,
                    success=False,
                    detail=payload.get("msg", "chat_api_failed"),
                    trade_id=trade_id,
                    agent_source=agent_source,
                    dedupe_key=dedupe_key,
                    channel="feishu",
                    transport="chat_api",
                )
            return False, payload.get("msg", "chat_api_failed")
        except Exception as exc:
            if not webhook_url:
                if record_outbound:
                    record_outbound_message(
                        event_type=outbound_event_type,
                        message_text=text,
                        success=False,
                        detail=str(exc),
                        trade_id=trade_id,
                        agent_source=agent_source,
                        dedupe_key=dedupe_key,
                        channel="feishu",
                        transport="chat_api",
                    )
                return False, str(exc)

    if webhook_url:
        try:
            response = send_webhook_text(webhook_url, text, timeout=timeout)
            response.raise_for_status()
            if record_outbound:
                record_outbound_message(
                    event_type=outbound_event_type,
                    message_text=text,
                    success=True,
                    detail="webhook",
                    trade_id=trade_id,
                    agent_source=agent_source,
                    dedupe_key=dedupe_key,
                    channel="feishu",
                    transport="webhook",
                )
            return True, "webhook"
        except Exception as exc:
            if record_outbound:
                record_outbound_message(
                    event_type=outbound_event_type,
                    message_text=text,
                    success=False,
                    detail=str(exc),
                    trade_id=trade_id,
                    agent_source=agent_source,
                    dedupe_key=dedupe_key,
                    channel="feishu",
                    transport="webhook",
                )
            return False, str(exc)

    if record_outbound:
        record_outbound_message(
            event_type=outbound_event_type,
            message_text=text,
            success=False,
            detail="missing_feishu_channel",
            trade_id=trade_id,
            agent_source=agent_source,
            dedupe_key=dedupe_key,
            channel="feishu",
            transport="none",
        )
    return False, "missing_feishu_channel"


def send_default_text_message(text: str, timeout: int = 10) -> bool:
    ok, _ = send_text_message(
        text,
        webhook_url=getattr(config, "FEISHU_WEBHOOK", ""),
        chat_id=getattr(config, "FEISHU_GROUP_ID", ""),
        prefer_chat_api=True,
        timeout=timeout,
    )
    return ok
