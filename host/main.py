#!/usr/bin/env python3
"""Poll Claude API rate-limit headers, collect PC stats, and push to M5Stack."""

import argparse
import asyncio
import pathlib
import signal
import subprocess
import sys
import time

import psutil

import data_source.data_sources as data_sources
import device
from data_source.claude_api import read_token, poll_api


# ── Constants ─────────────────────────────────────────────────────────────────

CLAUDE_POLL_INTERVAL = 30   # seconds between Claude API calls
DEVICE_PUSH_INTERVAL = 5    # seconds between device pushes


# ── Logging ───────────────────────────────────────────────────────────────────

def log_api(payload: dict) -> None:
    for window in ("5h", "7d"):
        print(
            f"[claude] {window}  {payload[f'{window}_utilization_pct']:3d}%"
            f"  reset {payload[f'{window}_reset_minutes']}m"
            f"  status={payload[f'{window}_status']}"
        )


# ── Main loop ─────────────────────────────────────────────────────────────────

async def main(ip: str | None = None, layout: pathlib.Path | None = None, palette_name: str | None = None) -> None:
    stop = asyncio.Event()

    def _on_signal(*_):
        print("\nShutting down...", file=sys.stderr)
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            signal.signal(sig, _on_signal)   # Windows fallback

    token = read_token()
    if not token:
        print("ERROR: no Claude token found", file=sys.stderr)
        sys.exit(1)

    dev = device.Device(ip=ip, layout=layout, palette=palette_name)
    psutil.cpu_percent(interval=None)   # prime — first call always returns 0.0

    api_payload:      dict | None = None
    last_api_fetch:   float = 0.0
    last_device_push: float = 0.0

    print("Running — Ctrl+C to stop")

    while not stop.is_set():
        now = time.time()

        if now - last_api_fetch >= CLAUDE_POLL_INTERVAL:
            result = await poll_api(token)
            if result is not None:
                api_payload    = result
                last_api_fetch = now
                log_api(api_payload)
            else:
                print("[claude] Poll failed, retrying next cycle", file=sys.stderr)

        if api_payload is not None and now - last_device_push >= DEVICE_PUSH_INTERVAL:
            dev.push(data_sources.collect(api_payload))
            last_device_push = now

        try:
            await asyncio.wait_for(stop.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass

    print("Stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Claude Meter host")
    parser.add_argument("--ip",     metavar="ADDR", help="Device IP (skips mDNS discovery)")
    parser.add_argument("--layout",  metavar="FILE", type=pathlib.Path, help="Layout JSON (default: host/config/layout.json)")
    parser.add_argument("--palette", metavar="NAME",                   help="Theme name from _themes in layout.json (default: sahara)")
    args = parser.parse_args()

    try:
        asyncio.run(main(args.ip, args.layout, args.palette))
    except KeyboardInterrupt:
        print("\nStopped.")
