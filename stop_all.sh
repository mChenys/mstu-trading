#!/bin/zsh
set -euo pipefail

WEB_APP_PORT="${WEB_APP_PORT:-5000}"

free_port() {
  local port="$1"
  local pids
  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [[ -z "$pids" ]]; then
    return
  fi

  echo "Stopping processes listening on port $port: $pids"
  kill $pids 2>/dev/null || true
  sleep 1

  pids=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)
  if [[ -n "$pids" ]]; then
    echo "Force killing remaining port $port listeners: $pids"
    kill -9 $pids 2>/dev/null || true
  fi
}

pkill -f "web_app.py" || true
pkill -f "webhook_daemon.py" || true
free_port "$WEB_APP_PORT"

echo "Stopped web_app.py and webhook_daemon.py, and attempted to free port $WEB_APP_PORT"
