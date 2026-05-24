#!/usr/bin/env python3
"""Claude Meter — Textual TUI.

Lets you select a theme, set the device IP, test the connection,
push a layout, and run / stop the polling engine — all from a terminal UI.

Usage:
    python tui.py
"""

import asyncio
import json
import pathlib
import time

from textual import on
from textual.app import App, ComposeResult
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    RichLog,
)
from textual.containers import Horizontal, Vertical

from core import device as _device_module
from core.engine import Engine

# ── Config paths ──────────────────────────────────────────────────────────────

_LAYOUT_PATH    = pathlib.Path(__file__).parent / "config" / "layout.json"
_STATE_PATH     = pathlib.Path(__file__).parent / "config" / "tui_state.json"


# ── Persistence helpers ───────────────────────────────────────────────────────

def load_tui_state() -> dict:
    """Return saved state or empty dict if missing / corrupt."""
    try:
        return json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_tui_state(state: dict) -> None:
    _STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ── Theme helpers ─────────────────────────────────────────────────────────────

def _read_theme_names(layout_path: pathlib.Path | None = None) -> list[str]:
    """Return ordered theme names from layout.json _themes."""
    path = layout_path or _LAYOUT_PATH
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return list(raw.get("_themes", {}).keys())
    except (OSError, json.JSONDecodeError):
        return []


# ── App ───────────────────────────────────────────────────────────────────────

class ClaudeMeterApp(App):
    """Textual TUI for Claude Meter device control."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main-row {
        height: 1fr;
    }

    #theme-list {
        width: 18;
        border: solid $primary;
        border-title-color: $text-muted;
    }

    #right-panel {
        width: 1fr;
        padding: 0 1;
    }

    #conn-row {
        height: 3;
        margin-bottom: 1;
    }

    #ip-input {
        width: 1fr;
    }

    #btn-test {
        width: 8;
        margin-left: 1;
    }

    #wifi-row {
        height: 3;
        margin-bottom: 1;
    }

    #wifi-ssid {
        width: 1fr;
    }

    #wifi-pass {
        width: 1fr;
        margin-left: 1;
    }

    #btn-wifi {
        width: 14;
        margin-left: 1;
    }

    #engine-row {
        height: 3;
        margin-bottom: 1;
    }

    #btn-run {
        width: 10;
        margin-right: 1;
    }

    #btn-stop {
        width: 10;
    }

    #log {
        height: 1fr;
        border: solid $primary;
        border-title-color: $text-muted;
    }
    """

    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self._engine:       Engine | None            = None
        self._engine_task:  asyncio.Task | None      = None
        self._state:        dict                     = load_tui_state()
        self._themes:       list[str]                = _read_theme_names()

    # ── Compose ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        with Horizontal(id="main-row"):
            # Left: theme list
            lv = ListView(
                *[ListItem(Label(name), name=name) for name in self._themes],
                id="theme-list",
            )
            lv.border_title = "Themes"
            yield lv

            # Right: connection controls + log
            with Vertical(id="right-panel"):
                with Horizontal(id="conn-row"):
                    yield Input(
                        placeholder="Device IP",
                        id="ip-input",
                    )
                    yield Button("Test", id="btn-test", variant="default")

                with Horizontal(id="wifi-row"):
                    yield Input(placeholder="Wi-Fi SSID", id="wifi-ssid")
                    yield Input(placeholder="Wi-Fi password",
                                id="wifi-pass", password=True)
                    yield Button("Save Wi-Fi", id="btn-wifi", variant="default")

                with Horizontal(id="engine-row"):
                    yield Button("▶ Run",  id="btn-run",  variant="success")
                    yield Button("■ Stop", id="btn-stop", variant="error")

                rl = RichLog(id="log", highlight=True, markup=True)
                rl.border_title = "Log"
                yield rl

        yield Footer()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        # Restore last IP
        saved_ip = self._state.get("ip", "")
        self.query_one("#ip-input", Input).value = saved_ip

        # Highlight last-used palette
        saved_palette = self._state.get("palette", self._themes[0] if self._themes else "")
        lv = self.query_one("#theme-list", ListView)
        for i, name in enumerate(self._themes):
            if name == saved_palette:
                lv.index = i
                break

        self._log(f"[bold]Claude Meter TUI[/bold] ready  "
                  f"palette=[cyan]{saved_palette or '—'}[/cyan]  "
                  f"ip=[cyan]{saved_ip or '—'}[/cyan]")

    async def on_unmount(self) -> None:
        if self._engine:
            self._engine.stop()
        if self._engine_task and not self._engine_task.done():
            await self._engine_task

    # ── Theme selection ───────────────────────────────────────────────────────

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        name = event.item.name
        if not name:
            return
        self._state["palette"] = name
        save_tui_state(self._state)
        ip = self._state.get("ip") or None
        if not ip:
            self._log(f"Theme [cyan]{name}[/cyan] saved (no IP set)")
            return
        self._log(f"Theme [cyan]{name}[/cyan] — pushing …")
        await asyncio.to_thread(self._do_push, ip, name)

    # ── IP input ──────────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "ip-input":
            self._state["ip"] = event.value
            save_tui_state(self._state)

    # ── Buttons ───────────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-test")
    async def handle_test(self) -> None:
        ip      = self._state.get("ip") or None
        palette = self._state.get("palette", "sahara")
        if not ip:
            self._log("[red]Set a device IP first[/red]")
            return
        self._log(f"[yellow]Testing connection[/yellow] → {ip} …")
        await asyncio.to_thread(self._do_test, ip, palette)

    def _do_test(self, ip: str, palette: str) -> None:
        try:
            dev = _device_module.Device(ip=ip, palette=palette)
            import socket as _socket
            with _socket.create_connection(
                (dev._ip, _device_module.DEVICE_PORT),
                timeout=_device_module.DEVICE_TIMEOUT,
            ):
                pass
            self.call_from_thread(
                self._log,
                f"[green]Connection OK[/green] ({dev._ip})"
            )
        except Exception as exc:
            self.call_from_thread(
                self._log,
                f"[red]Connection FAILED:[/red] {exc}"
            )

    def _do_push(self, ip: str, palette: str) -> None:
        try:
            # Fresh Device instance → _layout_sent=False → _ensure_layout fires immediately
            dev = _device_module.Device(ip=ip, palette=palette)
            ok = dev._ensure_layout()
            if ok:
                self.call_from_thread(
                    self._log,
                    f"[green]Layout pushed[/green] palette=[cyan]{palette}[/cyan]"
                )
            else:
                self.call_from_thread(self._log, "[red]Push failed — check connection[/red]")
        except Exception as exc:
            self.call_from_thread(self._log, f"[red]Push error:[/red] {exc}")

    # ── Wi-Fi config ──────────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-wifi")
    async def handle_wifi(self) -> None:
        ip   = self._state.get("ip") or None
        ssid = self.query_one("#wifi-ssid", Input).value.strip()
        pw   = self.query_one("#wifi-pass", Input).value

        if not ip:
            self._log("[red]Set a device IP first[/red]")
            return
        if not ssid or not pw:
            self._log("[red]Wi-Fi SSID and password required[/red]")
            return

        self._log(f"[yellow]Sending Wi-Fi config[/yellow] → {ip} (device will reboot) …")
        await asyncio.to_thread(self._do_wifi, ip, ssid, pw)

    def _do_wifi(self, ip: str, ssid: str, password: str) -> None:
        try:
            dev = _device_module.Device(ip=ip)
            ok = dev.push_wifi(ssid, password)
            if ok:
                self.call_from_thread(self._clear_wifi_inputs)
                self.call_from_thread(
                    self._log,
                    f"[green]Wi-Fi saved[/green] ssid=[cyan]{ssid}[/cyan] — device rebooting"
                )
            else:
                self.call_from_thread(self._log, "[red]Wi-Fi push failed — check connection[/red]")
        except Exception as exc:
            self.call_from_thread(self._log, f"[red]Wi-Fi push error:[/red] {exc}")

    def _clear_wifi_inputs(self) -> None:
        self.query_one("#wifi-ssid", Input).value = ""
        self.query_one("#wifi-pass", Input).value = ""

    @on(Button.Pressed, "#btn-run")
    async def handle_run(self) -> None:
        if self._engine_task and not self._engine_task.done():
            self._log("[yellow]Engine already running[/yellow]")
            return

        ip      = self._state.get("ip") or None
        palette = self._state.get("palette", "sahara")

        if not ip:
            self._log("[red]Set a device IP first[/red]")
            return

        try:
            self._engine = Engine(
                ip=ip,
                palette_name=palette,
                on_log=self._log,
            )
        except RuntimeError as exc:
            self._log(f"[red]Engine error:[/red] {exc}")
            return

        self._engine_task = asyncio.create_task(self._engine.run())
        self._log(f"[green]Engine started[/green] palette=[cyan]{palette}[/cyan]")

    @on(Button.Pressed, "#btn-stop")
    async def handle_stop(self) -> None:
        if self._engine and self._engine.is_running:
            self._engine.stop()
            self._log("[yellow]Stop requested …[/yellow]")
        else:
            self._log("Engine is not running")

    # ── Log helper ────────────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        """Append a timestamped line to the log widget (main-thread only)."""
        ts = time.strftime("%H:%M:%S")
        self.query_one("#log", RichLog).write(f"[dim]{ts}[/dim]  {msg}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ClaudeMeterApp().run()
