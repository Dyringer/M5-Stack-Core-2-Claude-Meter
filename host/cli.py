#!/usr/bin/env python3
"""Claude Meter — command-line interface.

Polls Claude API rate-limit headers, collects PC stats, and pushes them to
the M5Stack device.  Behaviour is identical to the old main.py.

Usage:
    python cli.py --ip ADDR [--layout FILE] [--palette NAME]
    python cli.py --ip ADDR --set-wifi-ssid SSID --set-wifi-pass PW
"""

import argparse
import asyncio
import pathlib
import signal
import sys

from core import device as _device_module
from core.engine import Engine


def main() -> None:
    parser = argparse.ArgumentParser(description="Claude Meter host")
    parser.add_argument("--ip",     metavar="ADDR", required=True, help="Device IP")
    parser.add_argument("--layout", metavar="FILE", type=pathlib.Path,
                        help="Layout JSON (default: config/layout.json)")
    parser.add_argument("--palette", metavar="NAME",
                        help="Theme name from _themes in layout.json (default: sahara)")
    parser.add_argument("--set-wifi-ssid", metavar="SSID",
                        help="Push new Wi-Fi SSID to device and exit (requires --set-wifi-pass)")
    parser.add_argument("--set-wifi-pass", metavar="PASSWORD",
                        help="Push new Wi-Fi password to device and exit (requires --set-wifi-ssid)")
    args = parser.parse_args()

    if bool(args.set_wifi_ssid) ^ bool(args.set_wifi_pass):
        parser.error("--set-wifi-ssid and --set-wifi-pass must be used together")

    if args.set_wifi_ssid and args.set_wifi_pass:
        try:
            dev = _device_module.Device(ip=args.ip)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            sys.exit(1)
        ok = dev.push_wifi(args.set_wifi_ssid, args.set_wifi_pass)
        if ok:
            print(f"Wi-Fi saved on device (ssid={args.set_wifi_ssid}). Device is rebooting.")
            sys.exit(0)
        print("ERROR: Wi-Fi push failed.", file=sys.stderr)
        sys.exit(1)

    try:
        eng = Engine(
            ip=args.ip,
            layout=args.layout,
            palette_name=args.palette,
            on_log=print,
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    async def _run() -> None:
        loop = asyncio.get_running_loop()

        def _on_signal(*_):
            print("\nShutting down...", file=sys.stderr)
            eng.stop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _on_signal)
            except NotImplementedError:
                signal.signal(sig, _on_signal)   # Windows fallback

        await eng.run()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
