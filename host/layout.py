import json
import pathlib

_LAYOUT_FILE = pathlib.Path(__file__).parent.parent / "layout.json"
_cached: dict | None = None
_cached_mtime: float = 0.0


def _resolve_palette(obj, palette: dict):
    if isinstance(obj, dict):
        return {k: _resolve_palette(v, palette) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_palette(v, palette) for v in obj]
    if isinstance(obj, str) and obj in palette:
        return palette[obj]
    return obj


def load_layout() -> dict:
    """
    Return the ready-to-send layout frame: {"cmd": "layout", "palette": {...}, "groups": [...]}.
    Palette is included so the device can override its boot-time grayscale defaults.
    Palette name strings in groups are resolved to integers.
    Result is cached until layout.json changes on disk.
    """
    global _cached, _cached_mtime
    mtime = _LAYOUT_FILE.stat().st_mtime
    if _cached is None or mtime != _cached_mtime:
        raw = json.loads(_LAYOUT_FILE.read_text(encoding="utf-8"))
        palette = {name: int(value, 16) for name, value in raw["palette"].items()}
        _cached = {
            "cmd":     "layout",
            "palette": palette,
            "groups":  _resolve_palette(raw["groups"], palette),
        }
        _cached_mtime = mtime
    return _cached
