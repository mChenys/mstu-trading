#!/bin/zsh
set -euo pipefail

pkill -f "web_app.py" || true
pkill -f "webhook_daemon.py" || true

echo "Stopped web_app.py and webhook_daemon.py"
