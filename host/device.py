"""Protocol layer — device discovery and TCP frame transport."""

import json
import pathlib
import socket
import sys

DEVICE_PORT    = 5555
DEVICE_TIMEOUT = 5   # seconds per TCP connect/recv

_DEFAULT_LAYOUT  = pathlib.Path(__file__).parent / "config" / "layout.json"
_DEFAULT_PALETTE = "sahara"


def _load_layout(path: pathlib.Path, palette_name: str) -> tuple[dict, dict]:
    """Load layout JSON, inject named palette, strip host-only fields.

    Returns:
        frame:   clean {"cmd": "layout", ...} ready to send to device
        mapping: {widget_id: source_key} kept in memory for value updates
    """
    raw    = json.loads(path.read_text(encoding="utf-8"))
    themes = raw.get("_themes", {})

    if palette_name not in themes:
        available = ", ".join(themes.keys())
        raise ValueError(f"Unknown palette '{palette_name}'. Available: {available}")

    palette = {name: int(value, 16) for name, value in themes[palette_name].items()}

    mapping      = {}
    clean_groups = []
    for group in raw["groups"]:
        clean_widgets = []
        for widget in group.get("widgets", []):
            source = widget.get("source")
            if source:
                mapping[widget["id"]] = source
            clean_widgets.append({k: v for k, v in widget.items() if k != "source"})
        clean_groups.append({**group, "widgets": clean_widgets})

    return {"cmd": "layout", "palette": palette, "groups": clean_groups}, mapping


class Device:
    def __init__(self,
                 ip:      str          | None = None,
                 layout:  pathlib.Path | None = None,
                 palette: str          | None = None) -> None:
        self._ip           = ip if ip else self._resolve()
        self._layout_file  = layout  or _DEFAULT_LAYOUT
        self._palette_name = palette or _DEFAULT_PALETTE
        self._layout_sent  = False
        self._mapping:     dict = {}

    @staticmethod
    def _resolve() -> str:
        try:
            ip = socket.getaddrinfo("claudemeter.local", DEVICE_PORT)[0][4][0]
            print(f"[device] Resolved claudemeter.local → {ip}")
            return ip
        except OSError as exc:
            raise RuntimeError(
                "Could not resolve claudemeter.local — "
                "is the device on the network? Pass --ip <address> to connect directly."
            ) from exc

    def _send_frame(self, frame: dict) -> bool:
        """Open a connection, send one newline-terminated JSON frame, read OK."""
        try:
            with socket.create_connection((self._ip, DEVICE_PORT), timeout=DEVICE_TIMEOUT) as sock:
                sock.sendall((json.dumps(frame) + "\n").encode())
                sock.recv(64)
            return True
        except OSError as error:
            print(f"[device] Send failed: {error}", file=sys.stderr)
            return False

    def push(self, data_pool: dict) -> None:
        """Send layout (once per session) then a value-update frame."""
        if not self._ensure_layout():
            return
        self._send_values(data_pool)

    def _ensure_layout(self) -> bool:
        if self._layout_sent:
            return True
        frame, self._mapping = _load_layout(self._layout_file, self._palette_name)
        if not self._send_frame(frame):
            return False
        self._layout_sent = True
        print(f"[device] Layout sent  palette={self._palette_name}")
        return True

    def _send_values(self, data_pool: dict) -> None:
        values = {
            wid: data_pool[src]
            for wid, src in self._mapping.items()
            if src in data_pool          # missing source → skip silently
        }
        if not self._send_frame({"cmd": "update", "values": values}):
            self._layout_sent = False
