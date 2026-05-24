"""Async polling engine — shared by cli.py and tui.py."""

import asyncio
import pathlib
import time
from collections.abc import Callable

import psutil

import data_source.data_sources as data_sources
from core import device as _device_module
from data_source.claude_api import poll_api, read_token

# ── Defaults ──────────────────────────────────────────────────────────────────

CLAUDE_POLL_INTERVAL = 30.0   # seconds between Claude API calls
DEVICE_PUSH_INTERVAL = 5.0    # seconds between device pushes


class Engine:
    """Polls Claude API and pushes live stats to the device.

    Callers supply an ``on_log`` callback that receives one-line messages;
    ``on_data`` is an optional hook called after each successful API poll
    with the raw payload dict.

    Both callbacks are invoked from within the asyncio event loop — they
    must not block.
    """

    def __init__(
        self,
        ip:                   str          | None = None,
        layout:               pathlib.Path | None = None,
        palette_name:         str          | None = None,
        on_log:               Callable[[str], None] | None = None,
        on_data:              Callable[[dict], None] | None = None,
        api_poll_interval:    float = CLAUDE_POLL_INTERVAL,
        device_push_interval: float = DEVICE_PUSH_INTERVAL,
    ) -> None:
        token = read_token()
        if not token:
            raise RuntimeError("no Claude token found")

        self._token              = token
        self._ip                 = ip
        self._layout             = layout
        self._palette_name       = palette_name
        self._on_log             = on_log or (lambda _: None)
        self._on_data            = on_data
        self._api_interval       = api_poll_interval
        self._push_interval      = device_push_interval
        self._stop_event:        asyncio.Event | None = None
        self._running            = False

        # Prime psutil so the first cpu_percent() call returns a real value
        psutil.cpu_percent(interval=None)

    # ── Public API ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Run the polling loop until ``stop()`` is called."""
        self._stop_event = asyncio.Event()
        self._running    = True

        dev = _device_module.Device(
            ip=self._ip,
            layout=self._layout,
            palette=self._palette_name,
        )

        api_payload:      dict | None = None
        last_api_fetch:   float = 0.0
        last_device_push: float = 0.0

        self._on_log("Running — Ctrl+C to stop")

        while not self._stop_event.is_set():
            now = time.time()

            # ── Claude API poll ───────────────────────────────────────────────
            if now - last_api_fetch >= self._api_interval:
                result = await poll_api(self._token)
                if result is not None:
                    api_payload    = result
                    last_api_fetch = now
                    self._log_api(api_payload)
                    if self._on_data:
                        self._on_data(api_payload)
                else:
                    self._on_log("[claude] Poll failed, retrying next cycle")

            # ── Device push ───────────────────────────────────────────────────
            if api_payload is not None and now - last_device_push >= self._push_interval:
                await asyncio.to_thread(dev.push, data_sources.collect(api_payload))
                last_device_push = now

            # ── Wait up to 1 s or until stop() ───────────────────────────────
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=1.0)
            except asyncio.TimeoutError:
                pass

        self._running = False
        self._on_log("Stopped.")

    def stop(self) -> None:
        """Signal the loop to exit cleanly. Safe to call from any coroutine."""
        if self._stop_event is not None:
            self._stop_event.set()

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _log_api(self, payload: dict) -> None:
        for window in ("5h", "7d"):
            self._on_log(
                f"[claude] {window}  {payload[f'{window}_utilization_pct']:3d}%"
                f"  reset {payload[f'{window}_reset_minutes']}m"
                f"  status={payload[f'{window}_status']}"
            )
