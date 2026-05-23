#!/usr/bin/env python3
"""Poll Claude API rate-limit headers, print stats, and push to M5Stack."""

import asyncio
import os
import signal
import socket
import json
import sys
import time

import psutil

from claude_api import read_token, poll_api

M5STACK_HOST = os.environ.get("M5_HOST", "192.168.50.157")
M5STACK_PORT = int(os.environ.get("M5_PORT", "5555"))
M5STACK_TIMEOUT = 5
M5STACK_RETRY_INTERVAL = 5    # seconds between device push attempts

CLAUDE_POLL_INTERVAL = 30     # seconds between API calls

PROTOCOL_VERSION = 1

# Cross-platform root disk path
_DISK_PATH = "/" if sys.platform != "win32" else "C:\\"


def send_to_m5stack(payload: dict) -> bool:
    try:
        with socket.create_connection((M5STACK_HOST, M5STACK_PORT), timeout=M5STACK_TIMEOUT) as sock:
            sock.sendall((json.dumps(payload) + "\n").encode())
            sock.recv(64)
        print(f"[M5] Sent to {M5STACK_HOST}:{M5STACK_PORT}")
        return True
    except OSError as e:
        print(f"[M5] Unreachable: {e}", file=sys.stderr)
        return False


def print_payload(payload: dict) -> None:
    print(f"5h  utilization : {payload['5h_utilization_pct']}%  (resets in {payload['5h_reset_minutes']} min)  status={payload['5h_status']}")
    print(f"5h  remaining   : {payload['tokens_remaining_5h']} / {payload['tokens_limit_5h']}")
    print(f"7d  utilization : {payload['7d_utilization_pct']}%  (resets in {payload['7d_reset_minutes']} min)  status={payload['7d_status']}")
    print(f"7d  remaining   : {payload['tokens_remaining_7d']} / {payload['tokens_limit_7d']}")


def pc_stats() -> dict:
    return {
        "pc_time": time.strftime("%H:%M:%S"),
        "pc_cpu": round(psutil.cpu_percent(interval=None), 1),
        "pc_ram": round(psutil.virtual_memory().percent, 1),
        "pc_disk": round(psutil.disk_usage(_DISK_PATH).percent, 1),
    }


async def main() -> None:
    stop = asyncio.Event()

    def _on_signal(*_):
        print("\nShutting down...", file=sys.stderr)
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _on_signal)
        except NotImplementedError:
            # Windows falls back to the default KeyboardInterrupt path
            signal.signal(sig, _on_signal)

    token = read_token()
    if not token:
        print("ERROR: no token found", file=sys.stderr)
        sys.exit(1)

    # Prime cpu_percent so the first real sample is meaningful
    psutil.cpu_percent(interval=None)

    payload: dict | None = None
    last_api_fetch: float = 0.0   # force immediate fetch on first iteration
    last_device_push: float = 0.0

    print("Running — Ctrl+C to stop")

    while not stop.is_set():
        now = time.time()

        # Refresh Claude usage every CLAUDE_POLL_INTERVAL seconds
        if now - last_api_fetch >= CLAUDE_POLL_INTERVAL:
            new_payload = await poll_api(token)
            if new_payload is not None:
                payload = new_payload
                last_api_fetch = time.time()
                print_payload(payload)
            else:
                print("[API] Retrying next cycle...", file=sys.stderr)

        # Push to device every M5STACK_RETRY_INTERVAL seconds (with latest payload)
        if payload is not None and time.time() - last_device_push >= M5STACK_RETRY_INTERVAL:
            push = {
                "v": PROTOCOL_VERSION,
                **payload,
                **pc_stats(),
            }
            send_to_m5stack(push)
            last_device_push = time.time()

        try:
            await asyncio.wait_for(stop.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            pass

    print("Stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nStopped.")
