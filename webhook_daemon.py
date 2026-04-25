import argparse
import json
import time
import os
from datetime import datetime, timezone

from webhook_worker import run_webhook_cycle


DEFAULT_INTERVAL_SECONDS = 60
HEARTBEAT_FILE = os.path.join(
    os.path.dirname(__file__),
    "..",
    ".openclaw-placeholder",
)


def _default_heartbeat_path():
    import dashboard_service
    return dashboard_service.WEBHOOK_DAEMON_HEARTBEAT_FILE


if HEARTBEAT_FILE.endswith(".openclaw-placeholder"):
    HEARTBEAT_FILE = _default_heartbeat_path()


def write_heartbeat(result, interval_seconds: int):
    payload = {
        "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "last_cycle_status": "ok" if result.get("ok") else "error",
        "last_cycle_message": result.get("signal", {}).get("reason") or result.get("quote", {}).get("error", ""),
        "interval_seconds": interval_seconds,
    }
    os.makedirs(os.path.dirname(HEARTBEAT_FILE), exist_ok=True)
    with open(HEARTBEAT_FILE, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def run_loop(interval_seconds: int = DEFAULT_INTERVAL_SECONDS, once: bool = False):
    result = run_webhook_cycle()
    write_heartbeat(result, interval_seconds)
    if once:
        return result

    while True:
        time.sleep(interval_seconds)
        result = run_webhook_cycle()
        write_heartbeat(result, interval_seconds)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL_SECONDS, help="轮询间隔（秒）")
    parser.add_argument("--once", action="store_true", help="只执行一次")
    args = parser.parse_args()

    result = run_loop(interval_seconds=args.interval, once=args.once)
    if args.once:
        print(json.dumps(result, ensure_ascii=False, indent=2))
