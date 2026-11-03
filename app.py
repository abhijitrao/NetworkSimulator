"""Local-only Flask dashboard and API for POS Network Simulator."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import sys
import threading
import webbrowser

from flask import Flask, Response, jsonify, render_template, request

from simulator.network_interfaces import get_network_interfaces

from simulator.config_store import ProfileStore
from simulator.models import FaultSettings, ProxyProfile
from simulator.proxy.manager import ProxyManager

# PyInstaller extracts bundled read-only resources to _MEIPASS. Keep user data
# beside the executable so profiles survive restarts and one-file temp cleanup.
FROZEN = bool(getattr(sys, "frozen", False))
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
CONFIG_PATH = DATA_DIR / "profiles.json"
EXAMPLE_PATH = RESOURCE_DIR / "config" / "profiles.example.json"
LOG = logging.getLogger("posnet.dashboard")


def create_app(config_path: str | Path = CONFIG_PATH, manager: ProxyManager | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder=str(RESOURCE_DIR / "templates"),
        static_folder=str(RESOURCE_DIR / "static"),
    )
    store = ProfileStore(config_path)
    event_lock = threading.RLock()
    event_log: list[dict] = []
    raw_hex_logging = False  # Always OFF on startup; diagnostic capture is opt-in.

    def record_event(event: dict) -> None:
        with event_lock:
            event_log.append(event)
            del event_log[:-1000]

    proxy_manager = manager or ProxyManager(on_event=record_event)
    proxy_manager.on_event = record_event
    state_lock = threading.RLock()

    if not Path(config_path).exists() and EXAMPLE_PATH.exists():
        examples = [ProxyProfile.from_dict(item) for item in json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))]
        for profile in examples:
            profile.enabled = False
        store.save(examples)

    def profiles() -> list[ProxyProfile]:
        return store.load()

    def find_profile(profile_id: str, items: list[ProxyProfile] | None = None) -> ProxyProfile:
        for item in items if items is not None else profiles():
            if item.id == profile_id:
                return item
        raise LookupError("Profile not found")

    @app.before_request
    def restrict_management_to_localhost():
        if request.remote_addr not in {"127.0.0.1", "::1"}:
            return jsonify(error="Management API is local-only"), 403
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("Origin")
            if origin and not origin.startswith(("http://127.0.0.1:", "http://localhost:")):
                return jsonify(error="Cross-origin management requests are not allowed"), 403
        return None

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/network/interfaces")
    def api_network_interfaces():
        return jsonify(interfaces=get_network_interfaces())

    @app.get("/api/state")
    def api_state():
        items = profiles()
        status_by_id = {item["profile_id"]: item for item in proxy_manager.status()}
        return jsonify(profiles=[{
            **profile.to_dict(),
            "runtime": status_by_id.get(profile.id, {"running": False, "active_connections": 0, "connections": []}),
        } for profile in items])

    @app.post("/api/profiles")
    def create_profile():
        profile = ProxyProfile.from_dict(request.get_json(force=True))
        with state_lock:
            items = profiles()
            if any(item.id == profile.id for item in items):
                return jsonify(error="Profile ID already exists"), 409
            items.append(profile)
            store.save(items)
        return jsonify(profile=profile.to_dict()), 201

    @app.put("/api/profiles/<profile_id>")
    def update_profile(profile_id: str):
        payload = request.get_json(force=True)
        replacement = ProxyProfile.from_dict({**payload, "id": profile_id})
        with state_lock:
            items = profiles()
            current = find_profile(profile_id, items)
            if any(row["profile_id"] == profile_id and row["running"] for row in proxy_manager.status()):
                return jsonify(error="Stop this proxy before editing its endpoint or listener settings"), 409
            items[items.index(current)] = replacement
            store.save(items)
        return jsonify(profile=replacement.to_dict())

    @app.delete("/api/profiles/<profile_id>")
    def delete_profile(profile_id: str):
        with state_lock:
            items = profiles()
            current = find_profile(profile_id, items)
            if any(row["profile_id"] == profile_id and row["running"] for row in proxy_manager.status()):
                return jsonify(error="Stop this proxy before deleting it"), 409
            items.remove(current)
            store.save(items)
        return jsonify(ok=True)

    @app.post("/api/profiles/<profile_id>/start")
    def start_profile(profile_id: str):
        profile = find_profile(profile_id)
        if not profile.enabled:
            return jsonify(error="Profile is disabled. Enable it before starting."), 409
        try:
            proxy_manager.start(profile)
        except (OSError, ValueError) as exc:
            LOG.warning("Start failed for %s: %s", profile.name, exc)
            return jsonify(error=str(exc)), 400
        return jsonify(ok=True)

    @app.post("/api/profiles/<profile_id>/stop")
    def stop_profile(profile_id: str):
        proxy_manager.stop(profile_id)
        return jsonify(ok=True)

    @app.post("/api/profiles/<profile_id>/fault")
    def set_fault(profile_id: str):
        settings = FaultSettings.from_dict(request.get_json(force=True))
        settings.validate()
        try:
            proxy_manager.set_fault(profile_id, settings)
        except ValueError as exc:
            return jsonify(error=str(exc)), 409
        with state_lock:
            items = profiles()
            profile = find_profile(profile_id, items)
            profile.fault_profile = settings
            store.save(items)
        return jsonify(ok=True, fault_profile=vars(settings))

    @app.post("/api/profiles/<profile_id>/processing-codes")
    def set_processing_codes(profile_id: str):
        payload = request.get_json(force=True)
        raw_codes = payload.get("processing_codes", [])
        if not isinstance(raw_codes, list):
            return jsonify(error="processing_codes must be an array"), 400
        codes = list(dict.fromkeys(str(code).strip() for code in raw_codes if str(code).strip()))
        if any(len(code) != 6 or not code.isdigit() for code in codes):
            return jsonify(error="Each Processing Code must contain exactly 6 digits"), 400
        apply_to = payload.get("apply_to")
        if apply_to is not None and apply_to not in {"request", "response", "both"}:
            return jsonify(error="apply_to must be request, response or both"), 400
        with state_lock:
            items = profiles()
            profile = find_profile(profile_id, items)
            if profile.transport_label != "tcp" and codes:
                return jsonify(error="Processing Code rules are supported only for Plain TCP profiles"), 400
            profile.processing_codes = codes
            if apply_to is not None:
                profile.fault_profile.apply_to = apply_to
                profile.fault_profile.validate()
            store.save(items)
        if apply_to is not None:
            try:
                proxy_manager.set_fault(profile_id, profile.fault_profile)
            except ValueError:
                pass
        try:
            proxy_manager.set_processing_codes(profile_id, codes)
        except ValueError:
            # A stopped profile will use the saved values when it starts.
            pass
        return jsonify(ok=True, processing_codes=codes, apply_to=apply_to)

    @app.get("/api/diagnostics/raw-hex")
    def get_raw_hex_setting():
        return jsonify(enabled=raw_hex_logging)

    @app.post("/api/diagnostics/raw-hex")
    def set_raw_hex_setting():
        nonlocal raw_hex_logging
        payload = request.get_json(force=True) or {}
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            return jsonify(error="enabled must be a boolean"), 400
        raw_hex_logging = enabled
        proxy_manager.set_raw_hex_logging(enabled)
        if not enabled:
            with event_lock:
                event_log[:] = [item for item in event_log if item.get("type") not in {"RAW_REQUEST", "RAW_RESPONSE"}]
        return jsonify(ok=True, enabled=raw_hex_logging)

    @app.get("/api/events")
    def api_events():
        since = float(request.args.get("since", "0"))
        with event_lock:
            events = [item for item in event_log if item["timestamp"] > since]
        return jsonify(events=events, raw_hex_logging=raw_hex_logging)

    @app.post("/api/events/clear")
    def clear_events():
        with event_lock:
            event_log.clear()
        return jsonify(ok=True)

    @app.get("/api/events/export")
    def export_events():
        with event_lock:
            events = sorted(event_log, key=lambda item: item.get("timestamp", 0))

        from datetime import datetime
        from textwrap import wrap

        # Fixed-width columns keep the TXT file aligned in monospaced editors.
        widths = (23, 14, 18, 8, 16)
        headers = ("TIMESTAMP", "EVENT", "PROFILE", "MTI", "PROCESSING CODE")
        detail_width = 120
        separator = "-" * (sum(widths) + len(widths) * 2 + detail_width)

        def format_row(values: tuple[str, ...]) -> str:
            return "  ".join(value[:width].ljust(width) for value, width in zip(values, widths))

        lines = [
            "POS Network Simulator - Traffic Event Log",
            f"Total events: {len(events)}",
            "Order: Oldest first, newest last",
            separator,
            format_row(headers) + "  DETAILS",
            separator,
        ]

        for item in events:
            timestamp = datetime.fromtimestamp(item.get("timestamp", 0)).astimezone().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            values = (
                timestamp,
                str(item.get("type", "")),
                str(item.get("profile", "")),
                str(item.get("mti", "") or "-"),
                str(item.get("processing_code", "") or "-"),
            )
            detail = str(item.get("detail", "")).replace("\\r", " ").replace("\\n", " ").replace("\\t", " ")
            lines.append(format_row(values) + "  " + detail)

        body = "\\n".join(lines) + "\\n"
        return Response(
            body,
            mimetype="text/plain; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="pos-traffic-logs.txt"'},
        )

    @app.post("/api/profiles/<profile_id>/abort")
    def abort_profile(profile_id: str):
        try:
            count = proxy_manager.abort_connections(profile_id)
        except ValueError as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(ok=True, sockets_closed=count)

    @app.post("/api/profiles/start-all")
    def start_all():
        results = []
        for profile in profiles():
            if not profile.enabled:
                continue
            try:
                proxy_manager.start(profile)
                results.append({"id": profile.id, "ok": True})
            except (OSError, ValueError) as exc:
                results.append({"id": profile.id, "ok": False, "error": str(exc)})
        return jsonify(results=results)

    @app.post("/api/profiles/stop-all")
    def stop_all():
        proxy_manager.stop_all()
        return jsonify(ok=True)

    @app.get("/api/profiles/export")
    def export_profiles():
        response = jsonify([profile.to_dict() for profile in profiles()])
        response.headers["Content-Disposition"] = 'attachment; filename="pos-network-profiles.json"'
        return response

    @app.post("/api/profiles/import")
    def import_profiles():
        payload = request.get_json(force=True)
        if not isinstance(payload, list):
            return jsonify(error="Import must be a JSON array of profiles"), 400
        incoming = [ProxyProfile.from_dict(item) for item in payload]
        replace = request.args.get("mode") == "replace"
        with state_lock:
            if proxy_manager.status():
                return jsonify(error="Stop all running proxies before importing profiles"), 409
            current = profiles()
            merged = ProfileStore.import_profiles(current, incoming, replace=replace)
            store.save(merged)
        return jsonify(ok=True, imported=len(incoming), total=len(merged), mode="replace" if replace else "merge")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok", management="localhost-only")

    @app.errorhandler(ValueError)
    def invalid_request(exc):
        return jsonify(error=str(exc)), 400

    @app.errorhandler(LookupError)
    def missing_resource(exc):
        return jsonify(error=str(exc)), 404

    app.extensions["profile_store"] = store
    app.extensions["proxy_manager"] = proxy_manager
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    port = int(os.environ.get("POS_SIMULATOR_PORT", "5050"))
    dashboard_url = f"http://127.0.0.1:{port}"
    app = create_app()
    LOG.info("Dashboard available at %s", dashboard_url)
    if not os.environ.get("POS_SIMULATOR_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(dashboard_url)).start()
    app.run(host="127.0.0.1", port=port, threaded=True, debug=False, use_reloader=False)
