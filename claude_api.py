#!/usr/bin/env python3
"""Claude API token reading and rate-limit polling."""

import getpass
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

CREDENTIALS_PATH = Path.home() / ".claude" / ".credentials.json"
KEYCHAIN_SERVICE = "Claude Code-credentials"

API_URL = "https://api.anthropic.com/v1/messages"
API_HEADERS_TEMPLATE = {
    "anthropic-version": "2023-06-01",
    "anthropic-beta": "oauth-2025-04-20",
    "Content-Type": "application/json",
    "User-Agent": "claude-code/2.1.5",
}
API_BODY = {
    "model": "claude-haiku-4-5-20251001",
    "max_tokens": 1,
    "messages": [{"role": "user", "content": "hi"}],
}


def _extract_access_token(blob: str) -> str | None:
    blob = blob.strip()
    if not blob:
        return None
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        if isinstance(data.get("accessToken"), str):
            return data["accessToken"]
        for v in data.values():
            if isinstance(v, dict) and isinstance(v.get("accessToken"), str):
                return v["accessToken"]
    m = re.search(r'"accessToken"\s*:\s*"([^"]+)"', blob)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_\-.~+/=]{20,}", blob):
        return blob
    return None


def _read_token_keychain() -> str | None:
    try:
        out = subprocess.run(
            ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", getpass.getuser(), "-w"],
            check=True, capture_output=True, text=True, timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return _extract_access_token(out.stdout)


def _read_token_file() -> str | None:
    try:
        raw = CREDENTIALS_PATH.read_text()
    except OSError:
        return None
    return _extract_access_token(raw)


def read_token() -> str | None:
    if sys.platform == "darwin":
        return _read_token_keychain()
    return _read_token_file()


async def poll_api(token: str) -> dict | None:
    headers = {**API_HEADERS_TEMPLATE, "Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=20.0) as http:
            resp = await http.post(API_URL, headers=headers, json=API_BODY)
    except httpx.HTTPError as e:
        print(f"[API] call failed: {e}", file=sys.stderr)
        return None
    if resp.status_code >= 400:
        print(f"[API] HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        return None

    def hdr(name: str, default: str = "0") -> str:
        return resp.headers.get(name, default)

    now = time.time()

    def reset_minutes(reset_ts: str) -> int:
        try:
            r = float(reset_ts)
        except ValueError:
            return 0
        mins = (r - now) / 60.0
        return int(round(mins)) if mins > 0 else 0

    def pct(util: str) -> int:
        try:
            return int(round(float(util) * 100))
        except ValueError:
            return 0

    def tokens(raw: str) -> int:
        try:
            return int(raw)
        except ValueError:
            return 0

    return {
        "5h_utilization_pct": pct(hdr("anthropic-ratelimit-unified-5h-utilization")),
        "5h_reset_minutes": reset_minutes(hdr("anthropic-ratelimit-unified-5h-reset")),
        "5h_status": hdr("anthropic-ratelimit-unified-5h-status", "unknown"),
        "7d_utilization_pct": pct(hdr("anthropic-ratelimit-unified-7d-utilization")),
        "7d_reset_minutes": reset_minutes(hdr("anthropic-ratelimit-unified-7d-reset")),
        "7d_status": hdr("anthropic-ratelimit-unified-7d-status", "unknown"),
        "tokens_remaining_5h": tokens(hdr("anthropic-ratelimit-unified-5h-remaining")),
        "tokens_limit_5h": tokens(hdr("anthropic-ratelimit-unified-5h-limit")),
        "tokens_remaining_7d": tokens(hdr("anthropic-ratelimit-unified-7d-remaining")),
        "tokens_limit_7d": tokens(hdr("anthropic-ratelimit-unified-7d-limit")),
    }
