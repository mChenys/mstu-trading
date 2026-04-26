"""SQLite 兼容存储层。

设计目标：
1. 用 sqlite 提供更稳的持久化。
2. 保留 JSON 镜像，兼容现有脚本、测试和人工排查。
3. 遇到已有 JSON 数据时自动迁移进 sqlite。
"""

from __future__ import annotations

from contextlib import closing, contextmanager
import json
import os
import sqlite3
from typing import Any

from mstu_trading.app_runtime import SQLITE_STATE_FILE, ensure_state_dir


def _execute(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] | list[Any] = ()) -> None:
    with closing(conn.execute(query, params)):
        return


def _fetchone(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] | list[Any] = ()) -> sqlite3.Row | None:
    with closing(conn.execute(query, params)) as cursor:
        return cursor.fetchone()


def _fetchall(conn: sqlite3.Connection, query: str, params: tuple[Any, ...] | list[Any] = ()) -> list[sqlite3.Row]:
    with closing(conn.execute(query, params)) as cursor:
        return cursor.fetchall()


def _initialize_schema(conn: sqlite3.Connection) -> None:
    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS kv_store (
            key TEXT PRIMARY KEY,
            value_json TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS trade_records (
            trade_id TEXT PRIMARY KEY,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            proposal_type TEXT NOT NULL,
            agent_source TEXT,
            claimed_by TEXT,
            claimed_at TEXT,
            claim_expires_at TEXT,
            created_at TEXT,
            confirmed_at TEXT,
            rejected_at TEXT,
            expires_at TEXT,
            price REAL,
            shares INTEGER,
            target_price REAL,
            stop_price REAL,
            pnl REAL,
            position_source TEXT,
            reason TEXT,
            channel TEXT,
            proposal_message_id TEXT,
            proposal_thread_id TEXT,
            last_user_reply_id TEXT,
            schema_version INTEGER,
            payload_json TEXT NOT NULL
        )
        """,
    )
    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS position_snapshots (
            snapshot_key TEXT PRIMARY KEY,
            updated_at TEXT,
            holding_shares INTEGER,
            buy_price REAL,
            target_price REAL,
            stop_price REAL,
            position_source TEXT,
            daily_ops_count INTEGER,
            daily_pnl REAL,
            available_cash REAL,
            payload_json TEXT NOT NULL
        )
        """,
    )
    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS message_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT,
            event_type TEXT NOT NULL,
            agent_source TEXT,
            channel TEXT,
            message_id TEXT,
            thread_id TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            payload_json TEXT NOT NULL
        )
        """,
    )
    _execute(
        conn,
        """
        CREATE TABLE IF NOT EXISTS outbound_messages (
            outbound_id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id TEXT,
            event_type TEXT NOT NULL,
            agent_source TEXT,
            dedupe_key TEXT,
            channel TEXT,
            transport TEXT,
            success INTEGER NOT NULL,
            detail TEXT,
            message_text TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """,
    )
    _ensure_column(conn, "trade_records", "agent_source", "TEXT")
    _ensure_column(conn, "trade_records", "claimed_by", "TEXT")
    _ensure_column(conn, "trade_records", "claimed_at", "TEXT")
    _ensure_column(conn, "trade_records", "claim_expires_at", "TEXT")
    _ensure_column(conn, "message_events", "agent_source", "TEXT")
    _ensure_column(conn, "outbound_messages", "agent_source", "TEXT")


def _ensure_column(conn: sqlite3.Connection, table_name: str, column_name: str, column_def: str) -> None:
    columns = {
        row[1]
        for row in _fetchall(conn, f"PRAGMA table_info({table_name})")
    }
    if column_name not in columns:
        _execute(conn, f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")


def _connect() -> sqlite3.Connection:
    ensure_state_dir()
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(2):
        conn: sqlite3.Connection | None = None
        try:
            conn = sqlite3.connect(SQLITE_STATE_FILE)
            conn.row_factory = sqlite3.Row
            _execute(conn, "PRAGMA busy_timeout = 5000")
            _execute(conn, "PRAGMA journal_mode = DELETE")
            _initialize_schema(conn)
            return conn
        except sqlite3.OperationalError as exc:
            if conn is not None:
                conn.close()
            last_error = exc
            message = str(exc).lower()
            should_retry = attempt == 0 and ("readonly" in message or "disk i/o" in message)
            if not should_retry:
                raise
            if os.path.exists(SQLITE_STATE_FILE):
                try:
                    os.remove(SQLITE_STATE_FILE)
                except OSError:
                    raise
    assert last_error is not None
    raise last_error


@contextmanager
def _managed_connection() -> sqlite3.Connection:
    conn = _connect()
    try:
        yield conn
    finally:
        conn.close()


def load_json_document(key: str, fallback: dict[str, Any], json_path: str | None = None) -> dict[str, Any]:
    """优先从 sqlite 读，sqlite 为空时回退 JSON 并自动迁移。"""
    with _managed_connection() as conn:
        row = _fetchone(conn, "SELECT value_json FROM kv_store WHERE key = ?", (key,))
        if row:
            try:
                data = json.loads(row["value_json"])
                if isinstance(data, dict):
                    return data
            except json.JSONDecodeError:
                pass

    if json_path and os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
            if isinstance(data, dict):
                save_json_document(key, data, json_path=json_path)
                return data
        except Exception:
            pass
    return dict(fallback)


def save_json_document(key: str, payload: dict[str, Any], json_path: str | None = None) -> None:
    serialized = json.dumps(payload, ensure_ascii=False)
    with _managed_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO kv_store (key, value_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, serialized),
        )
        conn.commit()

    if json_path:
        ensure_state_dir()
        with open(json_path, "w") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)


def upsert_trade_record(trade: dict[str, Any]) -> None:
    context = trade.get("message_context") or {}
    with _managed_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO trade_records (
                trade_id, action, status, proposal_type, agent_source, claimed_by,
                claimed_at, claim_expires_at, created_at, confirmed_at,
                rejected_at, expires_at, price, shares, target_price, stop_price,
                pnl, position_source, reason, channel, proposal_message_id,
                proposal_thread_id, last_user_reply_id, schema_version, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(trade_id) DO UPDATE SET
                action = excluded.action,
                status = excluded.status,
                proposal_type = excluded.proposal_type,
                agent_source = excluded.agent_source,
                claimed_by = excluded.claimed_by,
                claimed_at = excluded.claimed_at,
                claim_expires_at = excluded.claim_expires_at,
                created_at = excluded.created_at,
                confirmed_at = excluded.confirmed_at,
                rejected_at = excluded.rejected_at,
                expires_at = excluded.expires_at,
                price = excluded.price,
                shares = excluded.shares,
                target_price = excluded.target_price,
                stop_price = excluded.stop_price,
                pnl = excluded.pnl,
                position_source = excluded.position_source,
                reason = excluded.reason,
                channel = excluded.channel,
                proposal_message_id = excluded.proposal_message_id,
                proposal_thread_id = excluded.proposal_thread_id,
                last_user_reply_id = excluded.last_user_reply_id,
                schema_version = excluded.schema_version,
                payload_json = excluded.payload_json
            """,
            (
                trade.get("trade_id"),
                trade.get("action", ""),
                trade.get("status", ""),
                trade.get("proposal_type", ""),
                trade.get("agent_source", ""),
                trade.get("claimed_by", ""),
                trade.get("claimed_at", ""),
                trade.get("claim_expires_at", ""),
                trade.get("created_at", ""),
                trade.get("confirmed_at", ""),
                trade.get("rejected_at", ""),
                trade.get("expires_at", ""),
                trade.get("price"),
                trade.get("shares"),
                trade.get("target_price"),
                trade.get("stop_price"),
                trade.get("pnl"),
                trade.get("position_source", ""),
                trade.get("reason", ""),
                context.get("channel", ""),
                context.get("proposal_message_id", ""),
                context.get("proposal_thread_id", ""),
                context.get("last_user_reply_id", ""),
                trade.get("schema_version"),
                json.dumps(trade, ensure_ascii=False),
            ),
        )
        conn.commit()


def get_trade_record(trade_id: str) -> dict[str, Any] | None:
    with _managed_connection() as conn:
        row = _fetchone(
            conn,
            "SELECT payload_json FROM trade_records WHERE trade_id = ?",
            (trade_id,),
        )
    if not row:
        return None
    return json.loads(row["payload_json"])


def list_trade_records(*, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    query = "SELECT payload_json FROM trade_records"
    params: list[Any] = []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    query += " ORDER BY datetime(created_at) DESC LIMIT ?"
    params.append(limit)
    with _managed_connection() as conn:
        rows = _fetchall(conn, query, params)
    return [json.loads(row["payload_json"]) for row in rows]


def upsert_position_snapshot(snapshot_key: str, payload: dict[str, Any]) -> None:
    with _managed_connection() as conn:
        _execute(
            conn,
            """
            INSERT INTO position_snapshots (
                snapshot_key, updated_at, holding_shares, buy_price, target_price,
                stop_price, position_source, daily_ops_count, daily_pnl,
                available_cash, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_key) DO UPDATE SET
                updated_at = excluded.updated_at,
                holding_shares = excluded.holding_shares,
                buy_price = excluded.buy_price,
                target_price = excluded.target_price,
                stop_price = excluded.stop_price,
                position_source = excluded.position_source,
                daily_ops_count = excluded.daily_ops_count,
                daily_pnl = excluded.daily_pnl,
                available_cash = excluded.available_cash,
                payload_json = excluded.payload_json
            """,
            (
                snapshot_key,
                payload.get("updated_at", ""),
                payload.get("holding_shares"),
                payload.get("buy_price"),
                payload.get("target_price"),
                payload.get("stop_price"),
                payload.get("position_source", ""),
                payload.get("daily_ops_count"),
                payload.get("daily_pnl"),
                payload.get("available_cash"),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        conn.commit()


def get_position_snapshot(snapshot_key: str) -> dict[str, Any] | None:
    with _managed_connection() as conn:
        row = _fetchone(
            conn,
            "SELECT payload_json FROM position_snapshots WHERE snapshot_key = ?",
            (snapshot_key,),
        )
    if not row:
        return None
    return json.loads(row["payload_json"])


def append_message_event(
    *,
    trade_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    agent_source: str = "",
    channel: str = "",
    message_id: str = "",
    thread_id: str = "",
) -> int:
    with _managed_connection() as conn:
        with closing(
            conn.execute(
                """
                INSERT INTO message_events (
                    trade_id, event_type, agent_source, channel, message_id, thread_id, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    event_type,
                    agent_source,
                    channel,
                    message_id,
                    thread_id,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
        ) as cursor:
            conn.commit()
            return int(cursor.lastrowid)


def list_message_events(*, trade_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    query = """
        SELECT event_id, trade_id, event_type, agent_source, channel, message_id, thread_id, created_at, payload_json
        FROM message_events
    """
    params: list[Any] = []
    if trade_id:
        query += " WHERE trade_id = ?"
        params.append(trade_id)
    query += " ORDER BY event_id DESC LIMIT ?"
    params.append(limit)

    with _managed_connection() as conn:
        rows = _fetchall(conn, query, params)

    return [
        {
            "event_id": row["event_id"],
            "trade_id": row["trade_id"],
            "event_type": row["event_type"],
            "agent_source": row["agent_source"],
            "channel": row["channel"],
            "message_id": row["message_id"],
            "thread_id": row["thread_id"],
            "created_at": row["created_at"],
            "payload": json.loads(row["payload_json"]),
        }
        for row in rows
    ]


def find_latest_message_event_by_message_id(message_id: str, *, event_type: str | None = None) -> dict[str, Any] | None:
    query = """
        SELECT event_id, trade_id, event_type, agent_source, channel, message_id, thread_id, created_at, payload_json
        FROM message_events
        WHERE message_id = ?
    """
    params: list[Any] = [message_id]
    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)
    query += " ORDER BY event_id DESC LIMIT 1"

    with _managed_connection() as conn:
        row = _fetchone(conn, query, params)
    if not row:
        return None
    return {
        "event_id": row["event_id"],
        "trade_id": row["trade_id"],
        "event_type": row["event_type"],
        "agent_source": row["agent_source"],
        "channel": row["channel"],
        "message_id": row["message_id"],
        "thread_id": row["thread_id"],
        "created_at": row["created_at"],
        "payload": json.loads(row["payload_json"]),
    }


def record_outbound_message(
    *,
    event_type: str,
    message_text: str,
    success: bool,
    detail: str,
    trade_id: str | None = None,
    agent_source: str = "",
    dedupe_key: str | None = None,
    channel: str = "",
    transport: str = "",
) -> int:
    with _managed_connection() as conn:
        with closing(
            conn.execute(
                """
                INSERT INTO outbound_messages (
                    trade_id, event_type, agent_source, dedupe_key, channel, transport,
                    success, detail, message_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    event_type,
                    agent_source,
                    dedupe_key,
                    channel,
                    transport,
                    1 if success else 0,
                    detail,
                    message_text,
                ),
            )
        ) as cursor:
            conn.commit()
            return int(cursor.lastrowid)


def find_successful_outbound_by_dedupe_key(dedupe_key: str, *, event_type: str | None = None) -> dict[str, Any] | None:
    query = """
        SELECT outbound_id, trade_id, event_type, agent_source, dedupe_key, channel, transport,
               success, detail, message_text, created_at
        FROM outbound_messages
        WHERE dedupe_key = ? AND success = 1
    """
    params: list[Any] = [dedupe_key]
    if event_type:
        query += " AND event_type = ?"
        params.append(event_type)
    query += " ORDER BY outbound_id DESC LIMIT 1"
    with _managed_connection() as conn:
        row = _fetchone(conn, query, params)
    if not row:
        return None
    return {
        "outbound_id": row["outbound_id"],
        "trade_id": row["trade_id"],
        "event_type": row["event_type"],
        "agent_source": row["agent_source"],
        "dedupe_key": row["dedupe_key"],
        "channel": row["channel"],
        "transport": row["transport"],
        "success": bool(row["success"]),
        "detail": row["detail"],
        "message_text": row["message_text"],
        "created_at": row["created_at"],
    }


def list_outbound_messages(
    *,
    trade_id: str | None = None,
    event_type: str | None = None,
    limit: int = 100,
    success_only: bool = False,
) -> list[dict[str, Any]]:
    query = """
        SELECT outbound_id, trade_id, event_type, agent_source, dedupe_key, channel, transport,
               success, detail, message_text, created_at
        FROM outbound_messages
    """
    params: list[Any] = []
    clauses: list[str] = []
    if trade_id:
        clauses.append("trade_id = ?")
        params.append(trade_id)
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if success_only:
        clauses.append("success = 1")
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY outbound_id DESC LIMIT ?"
    params.append(limit)
    with _managed_connection() as conn:
        rows = _fetchall(conn, query, params)
    return [
        {
            "outbound_id": row["outbound_id"],
            "trade_id": row["trade_id"],
            "event_type": row["event_type"],
            "agent_source": row["agent_source"],
            "dedupe_key": row["dedupe_key"],
            "channel": row["channel"],
            "transport": row["transport"],
            "success": bool(row["success"]),
            "detail": row["detail"],
            "message_text": row["message_text"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]
