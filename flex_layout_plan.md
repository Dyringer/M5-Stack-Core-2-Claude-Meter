# Flexible Layout Plan

## Goal

Decouple host code from widget IDs in `layout.json`. The layout file becomes the
single source of truth for both the device UI and the host-to-widget data wiring.

---

## Data source registry

A flat dict of source keys → values. Each data point has two keys: `.int` and `.str`.
Built fresh each cycle from `pc_stats` and `claude_api` results.

```
pc.cpu.usage.int        45
pc.cpu.usage.str        "45%"
pc.ram.usage.int        72
pc.ram.usage.str        "72%"
pc.disk.usage.int       55
pc.disk.usage.str       "55%"
pc.bat.level.int        80          (0 when no battery)
pc.bat.level.str        "80%"       ("--" when no battery)

claude.5h.usage.int     45
claude.5h.usage.str     "45%"
claude.5h.reset.int     120         (minutes)
claude.5h.reset.str     "rst 2h00m"
claude.5h.status.str    "ok"        (string-only, no .int)
claude.5h.tokens.remaining.int  50000
claude.5h.tokens.limit.int      100000

claude.7d.usage.int     30
claude.7d.usage.str     "30%"
claude.7d.reset.int     4320
claude.7d.reset.str     "rst 3d0h"
claude.7d.status.str    "ok"
claude.7d.tokens.remaining.int  200000
claude.7d.tokens.limit.int      500000
```

Fields that have no meaningful int (status) only get a `.str` key.
The pool builds everything each cycle — cost is negligible at 14 fields.

---

## `layout.json` changes

Add a single `"source"` field to every dynamic widget.
Static widgets (`static_s`) get nothing — they never change.

The source key is the full path including `.int` or `.str`.
No separate `"format"` field — type is baked into the key.

```json
{ "id": "5h_val",  "type": "label_l", "source": "claude.5h.usage.str" },
{ "id": "5h_rst",  "type": "label_s", "source": "claude.5h.reset.str" },
{ "id": "5h_bar",  "type": "bar",     "source": "claude.5h.usage.int" },

{ "id": "cpu",     "type": "named_label_s", "source": "pc.cpu.usage.str" },
{ "id": "cpu_bar", "type": "bar",           "source": "pc.cpu.usage.int" }
```

`"source"` is host-only — stripped before sending to device.

---

## Missing sources: skip silently

If a widget's `source` key is not in the data pool, the widget is skipped on that
push (no entry in the update frame). The device keeps its last value for that
widget. No error, no warning.

This means typos in `layout.json` will manifest as "this widget never updates"
rather than a crash. Acceptable trade-off for simplicity.

---

## `device.py` changes

### Layout send (once per session)

1. Load `layout.json`
2. Walk all widgets, build `{widget_id: source_key}` → store as `self._mapping`
3. Strip `"source"` from every widget
4. Send clean layout to device
5. Drop the layout object — only `self._mapping` survives

### Value push (every cycle)

1. Receive `data_pool: dict[str, any]`
2. Walk `self._mapping`, build `{widget_id: data_pool[source]}` for sources that exist
3. Send `{"cmd": "update", "values": {...}}`

### `--layout` CLI arg

Layout path configurable via `--layout FILE`, defaulting to
`layout.json` next to the script.

---

## `main.py` changes

- Remove `build_values()`
- Add `data_sources.collect(api_payload) -> dict` returning the flat pool
- Pass pool to `dev.push(pool)`

---

## Files touched

| File | Change |
|---|---|
| `host/layout.json` | Add `source` to all dynamic widgets |
| `host/data_sources.py` | New — `collect()` returns flat dict |
| `host/device.py` | Extract mapping on send; strip `source`; resolve on push; `--layout` arg |
| `host/main.py` | Remove `build_values()`; call `data_sources.collect()`; `--layout` |

---

## What stays the same

- Device firmware (`device/main.py`)
- TCP protocol framing
- `pc_stats.py`, `claude_api.py`
- Poll intervals, signal handling, logging
