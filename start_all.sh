#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

WEB_APP_PORT="${WEB_APP_PORT:-5000}"

if lsof -nP -iTCP:"$WEB_APP_PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $WEB_APP_PORT is still occupied. Run ./stop_all.sh first or free the port manually."
  exit 1
fi

nohup env WEB_APP_PORT="$WEB_APP_PORT" .venv/bin/python web_app.py > web_app.log 2>&1 &
nohup .venv/bin/python webhook_daemon.py > webhook_daemon.log 2>&1 &

echo "Started web_app.py and webhook_daemon.py"
echo "Dashboard URL:"
echo "  http://127.0.0.1:${WEB_APP_PORT}"
echo "Logs:"
echo "  $ROOT_DIR/web_app.log"
echo "  $ROOT_DIR/webhook_daemon.log"
