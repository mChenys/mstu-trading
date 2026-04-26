"""运行时配置与状态路径。

给 OpenClaw Agent 使用时，希望把“代码目录”和“状态目录”分离：
1. 代码可以放在任意工作区。
2. 状态文件默认落在 ~/.openclaw/workspace/mstu-trading。
3. 也允许通过环境变量覆写，方便多环境/测试隔离。
"""

from __future__ import annotations

import os


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_STATE_DIR = os.path.join(
    os.path.expanduser("~"),
    ".openclaw",
    "workspace",
    "mstu-trading",
)
STATE_DIR = os.getenv("MSTU_TRADING_STATE_DIR", DEFAULT_STATE_DIR)


def env_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def state_path(filename: str) -> str:
    return os.path.join(STATE_DIR, filename)


POSITION_STATE_FILE = state_path("position.json")
TRADE_LOG_FILE = state_path("trade_log.json")
SQLITE_STATE_FILE = state_path("state.db")
WEBHOOK_CONFIG_FILE = state_path("webhook_config.json")
WEBHOOK_DAEMON_HEARTBEAT_FILE = state_path("webhook_daemon_heartbeat.json")
ALPHA_VANTAGE_CACHE_FILE = state_path("av_cache.json")


def ensure_state_dir() -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
