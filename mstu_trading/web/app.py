import os
from pathlib import Path

from flask import Flask, jsonify, render_template
from flask import request

from mstu_trading.web.dashboard_service import (
    build_dashboard_snapshot,
    load_ops_overview,
    load_webhook_config,
    save_webhook_config,
    send_test_webhook_message,
)
from mstu_trading.trading.service import claim_trade, expire_trade, get_trade_context, release_trade, run_recovery_scan


REPO_ROOT = Path(__file__).resolve().parents[2]


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(REPO_ROOT / "templates"),
        static_folder=str(REPO_ROOT / "static"),
        static_url_path="/static",
    )

    @app.after_request
    def add_no_cache_headers(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/api/dashboard")
    def dashboard_api():
        return jsonify(build_dashboard_snapshot())

    @app.get("/api/ops")
    def ops_api():
        return jsonify(load_ops_overview())

    @app.post("/api/ops/recover")
    def ops_recover_api():
        return jsonify(run_recovery_scan(agent_source="dashboard"))

    @app.get("/api/trades/<trade_id>")
    def trade_detail_api(trade_id: str):
        payload = get_trade_context(trade_id)
        if payload is None:
            return jsonify({"error": "trade_not_found", "trade_id": trade_id}), 404
        return jsonify(payload)

    @app.post("/api/trades/<trade_id>/expire")
    def trade_expire_api(trade_id: str):
        payload = expire_trade(trade_id, agent_source="dashboard")
        if not payload["handled"]:
            return jsonify({"error": "trade_not_found", "trade_id": trade_id}), 404
        return jsonify(payload)

    @app.post("/api/trades/<trade_id>/claim")
    def trade_claim_api(trade_id: str):
        payload = request.get_json(silent=True) or {}
        agent_source = str(payload.get("agent_source", "dashboard")).strip() or "dashboard"
        ttl_minutes = int(payload.get("ttl_minutes", 10))
        force = bool(payload.get("force", False))
        result = claim_trade(
            trade_id,
            agent_source=agent_source,
            ttl_minutes=ttl_minutes,
            force=force,
        )
        if not result["handled"]:
            return jsonify({"error": "trade_not_found", "trade_id": trade_id}), 404
        return jsonify(result)

    @app.post("/api/trades/<trade_id>/release")
    def trade_release_api(trade_id: str):
        payload = request.get_json(silent=True) or {}
        agent_source = str(payload.get("agent_source", "dashboard")).strip() or "dashboard"
        result = release_trade(trade_id, agent_source=agent_source)
        if not result["handled"]:
            return jsonify({"error": "trade_not_found", "trade_id": trade_id}), 404
        return jsonify(result)

    @app.get("/api/webhook-config")
    def webhook_config_get():
        return jsonify(load_webhook_config())

    @app.post("/api/webhook-config")
    def webhook_config_post():
        payload = request.get_json(silent=True) or {}
        return jsonify(save_webhook_config(payload))

    @app.post("/api/webhook-test")
    def webhook_test_post():
        return jsonify(send_test_webhook_message())

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("WEB_APP_PORT", "5000"))
    app.run(host="127.0.0.1", port=port, debug=False)
