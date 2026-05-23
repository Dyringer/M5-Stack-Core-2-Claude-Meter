#!/usr/bin/env python3
"""Poll Claude API rate-limit headers, collect PC stats, and push to M5Stack."""

import asyncio
import os
import signal
import socket
import json
import sys
import time

import psutil

from claude_api import read_token, poll_api
from layout import load_layout


# ── Constants ─────────────────────────────────────────────────────────────────

DEVICE_PORT          = int(os.environ.get("M5_PORT", "5555"))
DEVICE_TIMEOUT       = 5     # seconds per TCP connect/recv
CLAUDE_POLL_INTERVAL = 30    # seconds between Claude API calls
DEVICE_PUSH_INTERVAL = 5     # seconds between device pushes

_SKIP_FSTYPES = {"", "squashfs", "tmpfs", "devtmpfs"}

_device_ip:   str  = ""    # resolved once at startup
_layout_sent: bool = False  # reset on TCP failure so next push re-sends layout


# ── Device networking ─────────────────────────────────────────────────────────

def resolve_device() -> str:
    """Try mDNS first ('claudemeter.local'), fall back to M5_HOST env var."""
    try:
        ip = socket.getaddrinfo("claudemeter.local", DEVICE_PORT)[0][4][0]
        print(f"[device] Resolved claudemeter.local → {ip}")
        return ip
    except OSError:
        pass
    fallback = os.environ.get("M5_HOST", "192.168.50.157")
    print(f"[device] mDNS not found, using M5_HOST={fallback}")
    return fallback


def _send_frame(frame: dict) -> bool:
    """Open a connection, send one newline-terminated JSON frame, read OK.
    The device accepts exactly one frame per connection."""
    try:
        with socket.create_connection((_device_ip, DEVICE_PORT), timeout=DEVICE_TIMEOUT) as sock:
            sock.sendall((json.dumps(frame) + "\n").encode())
            sock.recv(64)
        return True
    except OSError as error:
        print(f"[device] Send failed: {error}", file=sys.stderr)
        return False


def push_to_device(values: dict) -> None:
    """Send layout (once per session) then a value-update frame, each on its own connection."""
    global _layout_sent
    if not _layout_sent:
        if not _send_frame(load_layout()):
            return
        _layout_sent = True
        print("[device] Layout sent")
    if not _send_frame({"cmd": "update", "values": values}):
        _layout_sent = False


# ── PC stats ──────────────────────────────────────────────────────────────────

def _total_disk_pct() -> float:
    """Aggregate used/total across all physical partitions, deduplicated by device."""
    total = used = 0
    seen: set = set()
    for part in psutil.disk_partitions(all=False):
        if part.fstype in _SKIP_FSTYPES:
            continue
        if sys.platform == "win32" and "cdrom" in part.opts:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
        except (PermissionError, OSError):
            continue
        key = (usage.total, part.device)
        if key in seen:
            continue
        seen.add(key)
        total += usage.total
        used  += usage.used
    return round(used / total * 100, 1) if total else 0.0


def pc_stats() -> dict:
    bat = psutil.sensors_battery()
    return {
        "cpu":  round(psutil.cpu_percent(interval=None), 1),
        "ram":  round(psutil.virtual_memory().percent, 1),
        "disk": _total_disk_pct(),
        "bat":  round(bat.percent) if bat else None,
    }


# ── Value assembly ────────────────────────────────────────────────────────────

def _fmt_reset(minutes: int) -> str:
    if minutes <= 0: return "now"
    if minutes < 60: return "{}m".format(minutes)
    hours, mins = divmod(minutes, 60)
    return "{}h{:02d}m".format(hours, mins)


def build_values(api_payload: dict) -> dict:
    """Flatten API + PC stats into {widget_id: value} matching layout.json IDs."""
    pc  = pc_stats()
    p5h = api_payload.get("5h_utilization_pct", 0)
    p7d = api_payload.get("7d_utilization_pct", 0)
    bat = pc["bat"]
    return {
        "5h_val":   "{}%".format(p5h),
        "5h_rst":   "rst {}".format(_fmt_reset(api_payload.get("5h_reset_minutes", 0))),
        "5h_bar":   p5h,
        "7d_val":   "{}%".format(p7d),
        "7d_rst":   "rst {}".format(_fmt_reset(api_payload.get("7d_reset_minutes", 0))),
        "7d_bar":   p7d,
        "cpu":      "{}%".format(pc["cpu"]),
        "cpu_bar":  pc["cpu"],
        "ram":      "{}%".format(pc["ram"]),
        "ram_bar":  pc["ram"],
        "disk":     "{}%".format(pc["disk"]),
        "disk_bar": pc["disk"],
        "bat":      "{}%".format(bat) if bat is not None else "--",
        "bat_bar":  bat if bat is not None else 0,
    }


# ── Logging ───────────────────────────────────────────────────────────────────

def log_api(payload: dict) -> None:
    for window in ("5h", "7d"):
        print(
            f"[claude] {window}  {payload[f'{window}_utilization_pct']:3d}%"
            f"  reset {payload[f'{window}_reset_minutes']}m"
            f"  status={payload[f'{window}_status']}"
        )


# ── Main loop ─────────────────────────────────────────────────────────────────

async def main() -> None:
    global _device_ip
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

    _device_ip = resolve_device()
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
            push_to_device(build_values(api_payload))
            last_device_push = now

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
