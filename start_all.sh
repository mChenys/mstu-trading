#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

nohup .venv/bin/python web_app.py > web_app.log 2>&1 &
nohup .venv/bin/python webhook_daemon.py > webhook_daemon.log 2>&1 &

echo "Started web_app.py and webhook_daemon.py"
echo "Logs:"
echo "  $ROOT_DIR/web_app.log"
echo "  $ROOT_DIR/webhook_daemon.log"
