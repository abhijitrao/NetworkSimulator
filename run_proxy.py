"""Start all enabled proxy profiles from a JSON configuration file."""
from __future__ import annotations

import argparse
import logging
import signal
import threading
from pathlib import Path

from simulator.config_store import ProfileStore
from simulator.proxy.manager import ProxyManager


def main() -> int:
    parser = argparse.ArgumentParser(description="POS Network Simulator - TCP proxy runner")
    parser.add_argument("--config", default="config/profiles.example.json", help="Path to the profile JSON file")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config_path = Path(args.config).resolve()
    profiles = ProfileStore(config_path).load()
    if not profiles:
        logging.error("No profiles found in %s", config_path)
        return 2

    manager = ProxyManager()
    started = 0
    for profile in profiles:
        if not profile.enabled:
            continue
        try:
            manager.start(profile)
            started += 1
        except (OSError, ValueError) as exc:
            logging.error("Could not start profile '%s': %s", profile.name, exc)

    if not started:
        logging.warning("No enabled profiles were started. Edit the JSON file and set enabled=true.")
        return 0

    stopped = threading.Event()
    def request_stop(signum, frame):
        logging.info("Shutdown requested")
        stopped.set()

    signal.signal(signal.SIGINT, request_stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, request_stop)
    logging.info("%d proxy profile(s) running. Press Ctrl+C to stop.", started)
    try:
        stopped.wait()
    finally:
        manager.stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
