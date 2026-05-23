# Claude Meter

A physical dashboard for your Claude Code rate-limit usage. Runs a Python poller on your PC/Mac/Linux machine and pushes live stats to an **M5Stack Core2** over Wi-Fi, where they are displayed in a colour-coded UI.

NOTE: It is fully vibe-coded. It might be ugly, it might be not optimal, but it works for me :)

![Claude Meter on M5Stack Core2](media/photo.jpg)

## How it works

```txt
  api.anthropic.com          Your PC                M5Stack Core2
  ─────────────────          ───────────────────    ─────────────────
                             main.py
                               ├── claude_api.py
  ◄── POST tiny prompt ────────┤                
  ──── rate-limit headers ────►┤                
                               ├── psutil
                               │   CPU/RAM/disk
                               │                    m5stack_server.py
                               ├────── JSON ───────►├── parse frame
                               │◄───── OK ──────────┤
                                                    └── LVGL display
```

1. `main.py` fires a minimal API call to `api.anthropic.com` every 30 seconds and extracts the `anthropic-ratelimit-unified-*` response headers — no prompt is processed, only headers are read.
2. Every 5 seconds it packages Claude usage + live PC stats into a single JSON frame and sends it to the M5Stack over TCP.
3. The M5Stack listens on port 5555, parses the frame, and refreshes the display. It also shows Wi-Fi SSID, signal strength, IP, and battery level.

## Requirements

### PC side

- Python 3.11+
- Claude Code installed and signed in (token auto-detected from `~/.claude/.credentials.json` on Linux/Windows, or macOS Keychain)

```sh
pip install httpx psutil
```

### M5Stack side

- M5Stack Core2 running **UIFlow 2** firmware
- Upload `m5stack_server.py` via the UIFlow IDE or `mpremote`

## Setup

### 1. Configure Wi-Fi on the M5Stack

Edit the top of [m5stack_server.py](m5stack_server.py):

```python
WIFI_SSID = "your-network"
WIFI_PASS = "your-password"
```

### 2. Find the M5Stack IP

Boot the device — the IP address is shown at the bottom of the screen once connected.

### 3. Configure the PC poller

The M5Stack host defaults to `192.168.50.157`. Override with an environment variable:

```bash
# Linux / macOS
export M5_HOST=192.168.1.42

# Windows PowerShell
$env:M5_HOST = "192.168.1.42"
```

Or edit `M5STACK_HOST` directly in [main.py](main.py).

### 4. Run

```bash
python main.py
```

Output looks like:

```txt
Running — Ctrl+C to stop
5h  utilization : 42%  (resets in 83 min)  status=ok
5h  remaining   : 11600 / 20000
7d  utilization : 18%  (resets in 9603 min)  status=ok
7d  remaining   : 82000 / 100000
[M5] Sent to 192.168.1.42:5555
```

The M5Stack is optional — the poller prints stats to the terminal regardless of whether a device is reachable.

## Device controls

| Button | Short press | Long press |
| --- | --- | --- |
| **A** (left) | Decrease brightness | — |
| **B** (middle) | Toggle screen on/off | Open / close settings |
| **C** (right) | Increase brightness | — |

### Settings popup

Long-press **B** to open the settings overlay. From there you can:

- **Theme** — choose from 6 colour themes (Ember, Ocean, Void, Dusk, B&W, Light). The active theme is highlighted. Changes apply immediately and are saved to the device's NVS flash.
- **Brightness** — use the **−** / **+** buttons to adjust. Also saved to NVS.

Tap outside the popup or long-press **B** again to close it.

## Configuration reference

| Variable | Default | Description |
| --- | --- | --- |
| `M5_HOST` env / `M5STACK_HOST` | `192.168.50.157` | M5Stack IP address |
| `M5_PORT` env / `M5STACK_PORT` | `5555` | TCP port on the device |
| `CLAUDE_POLL_INTERVAL` | `30` s | How often to hit the Claude API |
| `M5STACK_RETRY_INTERVAL` | `5` s | How often to push to the device |

## Protocol

Newline-delimited JSON (NDJSON) over a raw TCP socket. The PC sends one frame per push; the device replies `OK\n`.

```json
{
  "v": 1,
  "5h_utilization_pct": 42,
  "5h_reset_minutes": 83,
  "5h_status": "ok",
  "7d_utilization_pct": 18,
  "7d_reset_minutes": 9603,
  "7d_status": "ok",
  "tokens_remaining_5h": 11600,
  "tokens_limit_5h": 20000,
  "tokens_remaining_7d": 82000,
  "tokens_limit_7d": 100000,
  "pc_time": "14:32:01",
  "pc_cpu": 22.4,
  "pc_ram": 61.0,
  "pc_disk": 48.2
}
```

`v` is a schema version integer. Adding new fields is always backwards-compatible. If a breaking change is needed, `v` is incremented so the device firmware can detect and handle it.

## Linux / macOS notes

Works out of the box. The disk usage path is automatically set to `/` on non-Windows systems. Token is read from `~/.claude/.credentials.json` (Linux) or the macOS Keychain.
