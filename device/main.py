import os
import M5
from M5 import *
import m5ui
import lvgl as lv
import network
import socket
import json
import time


CONFIG_PATH = "/flash/config.json"


def load_config():
    defaults = {
        "wifi_ssid": "YOUR_SSID",
        "wifi_pass": "YOUR_PASSWORD",
        "tcp_port":  5555,
    }
    try:
        with open(CONFIG_PATH) as fh:
            stored = json.load(fh)
        defaults.update(stored)
    except Exception:
        pass
    return defaults


def save_config(updates):
    """Merge updates into the on-disk config and persist atomically."""
    try:
        with open(CONFIG_PATH) as fh:
            current = json.load(fh)
    except Exception:
        current = {}
    current.update(updates)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(current, fh)
    os.rename(tmp, CONFIG_PATH)


# Grayscale defaults — render the header immediately at boot before host connects.
# Overridden with real values when the host sends the layout frame.
palette = {
    "background":      0x000000,
    "border":          0x444444,
    "secondary_light": 0x888888,
    "primary_dark":    0xaaaaaa,
    "primary_light":   0xffffff,
    "secondary_dark":  0x222222,
}
fonts = {}
SCREEN_W, SCREEN_H = 320, 240

widget_registry = {}
group_cards: list = []
label_title  = None
label_time   = None
label_bat    = None
label_wifi   = None
header_hline = None
header       = None
screen       = None


def format_reset_time(minutes):
    if minutes <= 0: return "now"
    if minutes < 60: return "{}m".format(minutes)
    hours, mins = divmod(minutes, 60)
    return "{}h{:02d}m".format(hours, mins)


def local_time_string():
    t = time.localtime()
    return "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])


# ── LVGL primitives ───────────────────────────────────────────────────────────

def make_label(parent, x, y, text, color, font):
    label = lv.label(parent)
    label.set_pos(x, y)
    label.set_style_text_color(lv.color_hex(color), 0)
    label.set_style_text_font(font, 0)
    label.set_style_bg_opa(lv.OPA.TRANSP, 0)
    label.set_style_text_align(lv.TEXT_ALIGN.LEFT, 0)
    label.set_text(text)
    return label


def make_bar_track(parent, x, y, width, height, bg_color, fill_color, radius=4):
    """Track + fill child. Returns fill — caller drives its width to show progress."""
    track = lv.obj(parent)
    track.set_size(width, height)
    track.set_pos(x, y)
    track.set_style_bg_color(lv.color_hex(bg_color), 0)
    track.set_style_border_width(0, 0)
    track.set_style_pad_all(0, 0)
    track.set_style_radius(radius, 0)
    track.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    track.set_scroll_dir(lv.DIR.NONE)

    fill = lv.obj(track)
    fill.set_size(0, height)
    fill.set_pos(0, 0)
    fill.set_style_bg_color(lv.color_hex(fill_color), 0)
    fill.set_style_border_width(0, 0)
    fill.set_style_pad_all(0, 0)
    fill.set_style_radius(radius, 0)
    fill.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    fill.set_scroll_dir(lv.DIR.NONE)
    return fill


def set_bar_value(fill, percent, color):
    max_width = fill.get_parent().get_width()
    width = int(max_width * min(max(percent, 0), 100) / 100)
    fill.set_size(max(width, 0), fill.get_height())
    fill.set_style_bg_color(lv.color_hex(color), 0)


def make_card(parent, x, y, width, height):
    card = lv.obj(parent)
    card.set_size(width, height)
    card.set_pos(x, y)
    card.set_style_bg_color(lv.color_hex(palette["background"]), 0)
    card.set_style_border_color(lv.color_hex(palette["border"]), 0)
    card.set_style_border_width(1, 0)
    card.set_style_radius(6, 0)
    card.set_style_pad_all(0, 0)
    card.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    card.set_scroll_dir(lv.DIR.NONE)
    return card


def make_hline(parent, x, y, width):
    line = lv.obj(parent)
    line.set_size(width, 1)
    line.set_pos(x, y)
    line.set_style_bg_color(lv.color_hex(palette["border"]), 0)
    line.set_style_border_width(0, 0)
    line.set_style_pad_all(0, 0)
    line.set_style_radius(0, 0)
    line.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    line.set_scroll_dir(lv.DIR.NONE)
    return line


# ── Widget factory ────────────────────────────────────────────────────────────

def resolve_color(value, default_key):
    """Resolve a color field: palette name string → int, or pass int through."""
    if isinstance(value, str):
        return palette[value]
    if isinstance(value, int):
        return value
    return palette[default_key]


def build_widget(parent, cfg):
    widget_id   = cfg["id"]
    widget_type = cfg["type"]
    x     = cfg.get("x", 0)
    y     = cfg.get("y", 0)
    color = resolve_color(cfg.get("color"), "primary_light")
    size  = widget_type[-1]
    font  = fonts[12 if size == "s" else 24]

    if widget_type in ("static_s", "static_l"):
        make_label(parent, x, y, cfg.get("text", ""), color, font)

    elif widget_type in ("label_s", "label_l"):
        label = make_label(parent, x, y, "--", color, font)
        widget_registry[widget_id] = {"type": widget_type, "cfg": cfg, "label": label}

    elif widget_type in ("named_label_s", "named_label_l"):
        name_offset = 36 if size == "s" else 60
        name_color  = resolve_color(cfg.get("name_color"), "border")
        make_label(parent, x, y, cfg.get("name", ""), name_color, font)
        label = make_label(parent, x + name_offset, y, "--", color, font)
        widget_registry[widget_id] = {"type": widget_type, "cfg": cfg, "label": label}

    elif widget_type == "bar":
        fill = make_bar_track(parent, x, y, cfg.get("w", 100), 8,
                              resolve_color(cfg.get("bg"), "secondary_dark"), color)
        widget_registry[widget_id] = {"type": widget_type, "cfg": cfg, "fill": fill}


def apply_header_palette():
    """Re-apply palette colors to header and screen after palette update."""
    bg     = lv.color_hex(palette["background"])
    border = lv.color_hex(palette["border"])
    if screen:       screen.set_style_bg_color(bg, 0)
    if header:       header.set_style_bg_color(bg, 0)
    if header_hline: header_hline.set_style_bg_color(border, 0)
    if label_title:  label_title.set_style_text_color(lv.color_hex(palette["primary_light"]), 0)
    for label in (label_time, label_wifi, label_bat):
        if label: label.set_style_text_color(border, 0)


def build_layout(groups, new_palette=None):
    """Rebuild all dynamic widgets from the descriptor received from the host.
    Groups are plain containers — titles are static_s widgets inside them.
    If new_palette is provided, it overrides the boot-time defaults and
    re-colors the header."""
    if new_palette:
        palette.update(new_palette)
        apply_header_palette()
    for card in group_cards:
        card.delete()
    group_cards.clear()
    widget_registry.clear()
    for group in groups:
        card = make_card(screen, group["x"], group["y"], group["w"], group["h"])
        group_cards.append(card)
        for widget_cfg in group.get("widgets", []):
            build_widget(card, widget_cfg)


# ── Widget updaters ───────────────────────────────────────────────────────────

def update_label_widget(entry, value):
    unit = entry["cfg"].get("unit", "")
    if value is None:
        entry["label"].set_text("--")
    else:
        text = "{}{}".format(int(value) if isinstance(value, float) else value, unit)
        entry["label"].set_text(text)


def update_widget(widget_id, value):
    entry = widget_registry.get(widget_id)
    if not entry:
        return
    widget_type = entry["type"]
    if widget_type in ("label_s", "label_l", "named_label_s", "named_label_l"):
        update_label_widget(entry, value)
    elif widget_type == "bar":
        color = resolve_color(entry["cfg"].get("color"), "primary_dark")
        set_bar_value(entry["fill"], float(value) if value is not None else 0, color)


def update_values(values):
    for widget_id, value in values.items():
        update_widget(widget_id, value)


# ── Wi-Fi ─────────────────────────────────────────────────────────────────────

def connect_wifi(cfg):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(cfg["wifi_ssid"], cfg["wifi_pass"])
        deadline = time.time() + 20
        while not wlan.isconnected():
            if time.time() > deadline:
                return None
            M5.update()
            time.sleep(0.5)
    try:
        import ntptime
        ntptime.settime()
    except Exception:
        pass
    return wlan



# ── TCP ───────────────────────────────────────────────────────────────────────

def receive_line(conn):
    buf = b""
    while True:
        chunk = conn.recv(1024)
        if not chunk:
            break
        buf += chunk
        if b"\n" in buf:
            break
        if len(buf) > 8192:
            break
    return buf.split(b"\n")[0].strip()


# ── Setup ─────────────────────────────────────────────────────────────────────

def init_framework():
    """M5/LVGL boot + screen surface. Sets `screen` global."""
    global screen
    M5.begin()
    Widgets.setRotation(1)  # noqa: F821 — M5Stack firmware global
    m5ui.init()
    page = m5ui.M5Page(bg_c=palette["background"])
    page.screen_load()
    screen = lv.screen_active()
    screen.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    screen.set_scroll_dir(lv.DIR.NONE)


def init_fonts():
    global fonts
    fonts = {
        12: lv.font_montserrat_12,
        14: lv.font_montserrat_14,
        16: lv.font_montserrat_16,
        24: lv.font_montserrat_24,
    }


def build_header():
    """Two-row 40 px header: title + clock above, wifi + battery below."""
    global label_title, label_time, label_bat, label_wifi, header_hline, header
    header = lv.obj(screen)
    header.set_size(SCREEN_W, 40)
    header.set_pos(0, 0)
    header.set_style_bg_color(lv.color_hex(palette["background"]), 0)
    header.set_style_border_width(0, 0)
    header.set_style_pad_all(0, 0)
    header.set_style_radius(0, 0)
    header.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    header.set_scroll_dir(lv.DIR.NONE)

    label_title = make_label(header, 8,             4,  "CLAUDE METER",  palette["primary_light"], fonts[16])
    label_bat   = make_label(header, SCREEN_W - 68, 6,  "BAT:--%",       palette["border"],        fonts[12])
    label_wifi  = make_label(header, 8,             22, "connecting...", palette["border"],        fonts[12])
    label_time  = make_label(header, SCREEN_W - 62, 22, "--:--:--",      palette["border"],        fonts[12])

    header_hline = make_hline(screen, 0, 40, SCREEN_W)


def setup():
    init_framework()
    init_fonts()
    build_header()


# ── Brightness control ────────────────────────────────────────────────────────

_brightness_last_ms = 0   # 0 = no button held; >0 = timestamp of last step

def handle_brightness_buttons():
    """A decreases, C increases brightness by 10 (clamped 10–100).
    Fires immediately on press, then repeats every 100 ms while held."""
    global _brightness_last_ms
    a_held = BtnA.isPressed()  # noqa: F821 — M5Stack firmware global
    c_held = BtnC.isPressed()  # noqa: F821 — M5Stack firmware global

    if not a_held and not c_held:
        _brightness_last_ms = 0
        return

    now = time.ticks_ms()
    if _brightness_last_ms == 0:
        _brightness_last_ms = now  # start hold timer, don't fire yet
        return

    if time.ticks_diff(now, _brightness_last_ms) >= 100:
        current = M5.Lcd.getBrightness()
        if a_held:
            M5.Lcd.setBrightness(max(current - 10, 10))
        if c_held:
            M5.Lcd.setBrightness(min(current + 10, 100))
        _brightness_last_ms = now


# ── Header updaters ───────────────────────────────────────────────────────────

def update_header_bat():
    try:
        level = Power.getBatteryLevel()  # noqa: F821 — M5Stack firmware global
        label_bat.set_text("BAT:{}%".format(level))
        color = palette["primary_dark"] if level < 20 else palette["primary_light"]
        label_bat.set_style_text_color(lv.color_hex(color), 0)
    except Exception:
        pass


def update_header_time():
    label_time.set_text(local_time_string())


def get_rssi(wlan):
    try:
        return wlan.config('rssi')
    except Exception:
        try:
            return wlan.status('rssi')
        except Exception as error:
            return "[{}]".format(str(error)[:8])


def update_header_wifi(ssid, rssi, ip):
    label_wifi.set_text("{} {} {}dB ".format(ssid, ip, rssi))


# ── Server ────────────────────────────────────────────────────────────────────

def _tick_ui(wlan, ssid, ip, last_rssi_update):
    """One iteration of the per-frame UI refresh. Returns updated `last_rssi_update`."""
    M5.update()
    handle_brightness_buttons()
    update_header_bat()
    update_header_time()
    now = time.time()
    if now - last_rssi_update >= 5:
        update_header_wifi(ssid, get_rssi(wlan), ip)
        last_rssi_update = now
    return last_rssi_update


def _handle_client(conn):
    """Receive one framed JSON command, dispatch, ack."""
    try:
        conn.settimeout(2)
        raw = receive_line(conn)
        if not raw:
            return
        data = json.loads(raw.decode("utf-8"))
        cmd  = data.get("cmd")
        if cmd == "layout":
            build_layout(data.get("groups", []), data.get("palette"))
            conn.send(b"OK\n")
        elif cmd == "update":
            update_values(data.get("values", {}))
            conn.send(b"OK\n")
        elif cmd == "wifi":
            save_config({"wifi_ssid": data["ssid"], "wifi_pass": data["password"]})
            conn.send(b"OK\n")
            try:
                conn.close()
            except Exception:
                pass
            time.sleep(0.2)
            import machine
            machine.reset()
    except Exception as error:
        print("ERR: {}".format(error))
    finally:
        try:
            conn.close()
        except Exception:
            pass


def run_server(wlan, tcp_port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("", tcp_port))
    server_socket.listen(1)
    server_socket.settimeout(0.05)

    ssid = wlan.config('essid')[:8]
    ip   = wlan.ifconfig()[0]
    update_header_wifi(ssid, "--", ip)
    last_rssi_update = 0

    while True:
        last_rssi_update = _tick_ui(wlan, ssid, ip, last_rssi_update)
        try:
            conn, _ = server_socket.accept()
        except OSError:
            continue
        _handle_client(conn)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    try:
        cfg = load_config()
        setup()
        wlan = connect_wifi(cfg)
        if wlan:
            run_server(wlan, cfg["tcp_port"])
        else:
            label_wifi.set_text("no wifi")
            label_wifi.set_style_text_color(lv.color_hex(palette["primary_dark"]), 0)
            while True:
                M5.update()
                handle_brightness_buttons()
    except (Exception, KeyboardInterrupt) as error:
        try:
            m5ui.deinit()
            from utility import print_error_msg
            print_error_msg(error)
        except ImportError:
            print("please update to latest firmware")
