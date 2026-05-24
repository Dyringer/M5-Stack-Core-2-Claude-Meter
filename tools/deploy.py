#!/usr/bin/env python3
"""USB deployment tool for the M5Stack device firmware.

Usage:
  python tools/deploy.py                              # auto-detect port, upload and reset
  python tools/deploy.py --port COM3                  # specify port explicitly
  python tools/deploy.py --list                       # list connected serial devices
  python tools/deploy.py --repl                       # open interactive REPL
  python tools/deploy.py --no-reset                   # upload without soft-resetting

  # Write / update Wi-Fi credentials in /flash/config.json on the device:
  python tools/deploy.py --config-set wifi_ssid=MyNetwork --config-set wifi_pass=secret123

  # Any key supported (merges with existing config):
  python tools/deploy.py --config-set tcp_port=5556
"""

import argparse
import json
import subprocess
import sys
import tempfile
import os

DEVICE_FILE   = "device/main.py"
REMOTE_PATH   = ":main.py"
REMOTE_CONFIG = ":/flash/config.json"


def run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


def run_capture(cmd: list[str]) -> tuple[int, str]:
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def list_ports() -> None:
    rc = run(["mpremote", "connect", "list"])
    sys.exit(rc)


def open_repl(port: str | None) -> None:
    cmd = ["mpremote"]
    if port:
        cmd += ["connect", port]
    cmd.append("repl")
    sys.exit(run(cmd))


def deploy(port: str | None, reset: bool) -> None:
    cmd = ["mpremote"]
    if port:
        cmd += ["connect", port]

    rc = run(cmd + ["cp", DEVICE_FILE, REMOTE_PATH])
    if rc != 0:
        print(f"\nUpload failed (exit {rc}). Is the device connected and mpremote installed?",
              file=sys.stderr)
        sys.exit(rc)

    if reset:
        run(cmd + ["reset"])

    print("\nDone.")


def config_set(port: str | None, pairs: list[str], reset: bool) -> None:
    """
    Merge KEY=VALUE pairs into /flash/config.json on the device.

    Steps:
      1. Try to read existing /flash/config.json from device.
      2. Parse it (or start from {}).
      3. Apply new key/value pairs (auto-cast ints).
      4. Write merged JSON to a temp file and upload it.
    """
    base_cmd = ["mpremote"]
    if port:
        base_cmd += ["connect", port]

    # ── Read existing config from device ──────────────────────────────────
    existing: dict = {}
    rc, out = run_capture(base_cmd + ["cat", REMOTE_CONFIG])
    if rc == 0 and out.strip():
        try:
            existing = json.loads(out.strip())
            print(f"[config] Existing config: {existing}")
        except json.JSONDecodeError:
            print("[config] Warning: existing config.json is invalid JSON — starting fresh.")

    # ── Apply new values ──────────────────────────────────────────────────
    for pair in pairs:
        if "=" not in pair:
            print(f"[config] Skipping invalid pair (no '='): {pair!r}", file=sys.stderr)
            continue
        key, _, raw_val = pair.partition("=")
        key = key.strip()
        # Auto-cast integers
        try:
            val = int(raw_val)
        except ValueError:
            val = raw_val
        existing[key] = val
        print(f"[config]   {key} = {val!r}")

    # ── Write merged config to temp file and upload ───────────────────────
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
        json.dump(existing, tmp, indent=2)
        tmp_path = tmp.name

    try:
        rc = run(base_cmd + ["cp", tmp_path, REMOTE_CONFIG])
        if rc != 0:
            print(f"\nConfig upload failed (exit {rc}).", file=sys.stderr)
            sys.exit(rc)
    finally:
        os.unlink(tmp_path)

    print(f"\n[config] Written to {REMOTE_CONFIG}: {existing}")

    if reset:
        run(base_cmd + ["reset"])

    print("\nDone.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy firmware to M5Stack over USB.")
    parser.add_argument("--port",       "-p",  help="Serial port (e.g. COM3 or /dev/ttyUSB0).")
    parser.add_argument("--list",       "-l",  action="store_true",  help="List connected serial devices and exit.")
    parser.add_argument("--repl",       "-r",  action="store_true",  help="Open an interactive REPL on the device.")
    parser.add_argument("--no-reset",   dest="reset", action="store_false", default=True,
                        help="Skip soft-reset after upload.")
    parser.add_argument("--config-set", dest="config_pairs", metavar="KEY=VALUE",
                        action="append", default=[],
                        help="Set a config value in /flash/config.json (repeatable). "
                             "Example: --config-set wifi_ssid=MyNet --config-set wifi_pass=s3cr3t")
    args = parser.parse_args()

    if args.list:
        list_ports()
    elif args.repl:
        open_repl(args.port)
    elif args.config_pairs:
        config_set(args.port, args.config_pairs, args.reset)
    else:
        deploy(args.port, args.reset)


if __name__ == "__main__":
    main()
