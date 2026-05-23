#!/usr/bin/env python3
"""USB deployment tool for the M5Stack device firmware.

Usage:
  python tools/deploy.py              # auto-detect port, upload and reset
  python tools/deploy.py --port COM3  # specify port explicitly
  python tools/deploy.py --list       # list connected serial devices
  python tools/deploy.py --repl       # open interactive REPL
  python tools/deploy.py --no-reset   # upload without soft-resetting
"""

import argparse
import subprocess
import sys


DEVICE_FILE = "device/main.py"
REMOTE_PATH = ":main.py"


def run(cmd: list[str]) -> int:
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode


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

    upload_cmd = cmd + ["cp", DEVICE_FILE, REMOTE_PATH]
    rc = run(upload_cmd)
    if rc != 0:
        print(f"\nUpload failed (exit {rc}). Is the device connected and mpremote installed?", file=sys.stderr)
        sys.exit(rc)

    if reset:
        reset_cmd = cmd + ["reset"]
        run(reset_cmd)

    print("\nDone.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy firmware to M5Stack over USB.")
    parser.add_argument("--port", "-p", help="Serial port (e.g. COM3 or /dev/ttyUSB0). Auto-detected if omitted.")
    parser.add_argument("--list", "-l", action="store_true", help="List connected serial devices and exit.")
    parser.add_argument("--repl", "-r", action="store_true", help="Open an interactive REPL on the device.")
    parser.add_argument("--no-reset", dest="reset", action="store_false", default=True, help="Skip soft-reset after upload.")
    args = parser.parse_args()

    if args.list:
        list_ports()
    elif args.repl:
        open_repl(args.port)
    else:
        deploy(args.port, args.reset)


if __name__ == "__main__":
    main()
