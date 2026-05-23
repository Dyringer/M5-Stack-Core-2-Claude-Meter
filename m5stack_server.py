import M5
from M5 import *
import m5ui
import lvgl as lv
import network
import socket
import json
import time
from esp32 import NVS

# ── Wi-Fi config ─────────────────────────────────────────────────────────────
WIFI_SSID = "YOUR_SSID"
WIFI_PASS = "YOUR_PASSWORD"
TCP_PORT  = 5555

# ── Palette ───────────────────────────────────────────────────────────────────
BG     = 0x000000
CARD   = 0x0f0a08
BORDER = 0x622b14
DARK   = 0x622b14
MID    = 0x995f2f
SAND   = 0x978f66
CREAM  = 0xe4d6a9
GREY   = 0x60503a
BAR_BG = 0x1a0e08
RED    = 0xff1744

# ── Layout ────────────────────────────────────────────────────────────────────
W, H = 320, 240

# ── Brightness ────────────────────────────────────────────────────────────────
BRIGHTNESS_LEVELS = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]  # percentages
brightness_index    = 4  # start at 50%

THEMES = [
    dict(BG=0x000000, CARD=0x0f0a08, BORDER=0x622b14, DARK=0x622b14, MID=0x995f2f, SAND=0x978f66, CREAM=0xe4d6a9, GREY=0x60503a, BAR_BG=0x1a0e08, RED=0xff1744),  # Ember
    dict(BG=0x00080f, CARD=0x050d17, BORDER=0x0d3d5e, DARK=0x0d3d5e, MID=0x1a6fa0, SAND=0x4ea8c8, CREAM=0xa8ddf0, GREY=0x1a4a66, BAR_BG=0x020810, RED=0xff3355),  # Ocean
    dict(BG=0x000000, CARD=0x020502, BORDER=0x0f2e0f, DARK=0x0f2e0f, MID=0x1a5e1a, SAND=0x38924a, CREAM=0x76c442, GREY=0x1a3a1a, BAR_BG=0x040904, RED=0xff3333),  # Void
    dict(BG=0x050008, CARD=0x0c0414, BORDER=0x3a1260, DARK=0x3a1260, MID=0x7a2ebc, SAND=0xa06ad0, CREAM=0xd8a8f8, GREY=0x4a1880, BAR_BG=0x0e061a, RED=0xff1177),  # Dusk
    dict(BG=0x000000, CARD=0x0d0d0d, BORDER=0xffffff, DARK=0x555555, MID=0xdddddd, SAND=0xaaaaaa, CREAM=0xffffff, GREY=0x777777, BAR_BG=0x2a2a2a, RED=0xff2200),  # B&W
    dict(BG=0xf5f0e8, CARD=0xffffff, BORDER=0xd0c0a8, DARK=0xb8a888, MID=0x7a5010, SAND=0x4a7030, CREAM=0x1a100a, GREY=0x806050, BAR_BG=0xe0d8c8, RED=0xcc1122),  # Light
]
THEME_NAMES = ["EM", "OC", "VO", "DU", "BW", "LT"]
theme_index = 0

# Globals
page0               = None
label_5h_percent    = None
label_5h_reset      = None
label_7d_percent    = None
label_7d_reset      = None
label_status        = None
label_cpu           = None
label_ram           = None
label_disk          = None
label_ip            = None
bar_5h              = None
bar_7d              = None
bar_cpu             = None
bar_ram             = None
bar_disk            = None
header              = None
divider_top         = None
divider_mid         = None
card_5h             = None
card_7d             = None
card_pc             = None
label_title         = None
label_theme         = None
popup               = None
dim_overlay         = None
theme_buttons       = []
theme_button_labels = []
label_brightness    = None
static_labels       = []
last_data           = None

battery_percent     = "--"
time_str            = "--:--:--"
screen_off          = False
brightness_saved    = brightness_index


def refresh_status():
    if label_status is not None:
        label_status.set_text("{} BRT:{}% BAT:{}%".format(
            time_str, BRIGHTNESS_LEVELS[brightness_index], battery_percent))


def save_settings():
    try:
        nvs = NVS("meter")
        nvs.set_i32("theme", theme_index)
        nvs.set_i32("bright", brightness_index)
        nvs.commit()
    except Exception:
        pass


def set_brightness(index):
    global brightness_index
    brightness_index = max(0, min(index, len(BRIGHTNESS_LEVELS) - 1))
    M5.Lcd.setBrightness(BRIGHTNESS_LEVELS[brightness_index] * 255 // 100)
    refresh_status()
    save_settings()
    update_popup_brightness()


def button_dim(state):
    if not screen_off:
        set_brightness(brightness_index - 1)


def button_bright(state):
    if not screen_off:
        set_brightness(brightness_index + 1)


def button_toggle(state):
    global screen_off, brightness_saved
    if screen_off:
        set_brightness(brightness_saved)
        screen_off = False
    else:
        brightness_saved = brightness_index
        M5.Lcd.setBrightness(0)
        screen_off = True



def apply_theme():
    global BG, CARD, BORDER, DARK, MID, SAND, CREAM, GREY, BAR_BG, RED
    t = THEMES[theme_index]
    BG = t["BG"]; CARD = t["CARD"]; BORDER = t["BORDER"]; DARK = t["DARK"]
    MID = t["MID"]; SAND = t["SAND"]; CREAM = t["CREAM"]; GREY = t["GREY"]
    BAR_BG = t["BAR_BG"]; RED = t["RED"]
    scr = lv.screen_active()
    scr.set_style_bg_color(lv.color_hex(BG), 0)
    header.set_style_bg_color(lv.color_hex(CARD), 0)
    divider_top.set_style_bg_color(lv.color_hex(BORDER), 0)
    divider_mid.set_style_bg_color(lv.color_hex(BORDER), 0)
    for card in (card_5h, card_7d, card_pc):
        card.set_style_bg_color(lv.color_hex(CARD), 0)
        card.set_style_border_color(lv.color_hex(BORDER), 0)
    for track in (bar_5h.get_parent(), bar_7d.get_parent(),
                  bar_cpu.get_parent(), bar_ram.get_parent(), bar_disk.get_parent()):
        track.set_style_bg_color(lv.color_hex(BAR_BG), 0)
    label_title.set_style_text_color(lv.color_hex(CREAM), 0)
    label_status.set_style_text_color(lv.color_hex(GREY), 0)
    label_5h_percent.set_style_text_color(lv.color_hex(CREAM), 0)
    label_5h_reset.set_style_text_color(lv.color_hex(GREY), 0)
    label_7d_percent.set_style_text_color(lv.color_hex(MID), 0)
    label_7d_reset.set_style_text_color(lv.color_hex(GREY), 0)
    label_cpu.set_style_text_color(lv.color_hex(SAND), 0)
    label_ram.set_style_text_color(lv.color_hex(SAND), 0)
    label_disk.set_style_text_color(lv.color_hex(SAND), 0)
    label_ip.set_style_text_color(lv.color_hex(DARK), 0)
    for label in static_labels:
        label.set_style_text_color(lv.color_hex(GREY), 0)
    if label_theme is not None:
        label_theme.set_text(THEME_NAMES[theme_index])
        label_theme.set_style_text_color(lv.color_hex(GREY), 0)
    if last_data is not None:
        update_ui(last_data)
    else:
        refresh_status()


def color_for(percent, lo=None):
    if lo is None: lo = CREAM
    if percent >= 90: return RED
    if percent >= 70: return MID
    if percent >= 50: return SAND
    return lo


def format_reset(mins):
    if mins <= 0:   return "now"
    if mins < 60:   return "{}m".format(mins)
    if mins < 1440:
        h, m = divmod(mins, 60)
        return "{}h{:02d}m".format(h, m)
    d, rem = divmod(mins, 1440)
    h, m = divmod(rem, 60)
    return "{}d{}h{:02d}m".format(d, h, m)


# ── Widget helpers ────────────────────────────────────────────────────────────

def make_label(parent, x, y, text, color, font=lv.font_montserrat_14, align=lv.TEXT_ALIGN.LEFT):
    label = lv.label(parent)
    label.set_pos(x, y)
    label.set_style_text_color(lv.color_hex(color), 0)
    label.set_style_text_font(font, 0)
    label.set_style_bg_opa(lv.OPA.TRANSP, 0)
    label.set_style_text_align(align, 0)
    label.set_text(text)
    return label


def make_bar(parent, x, y, w, h, bg=BAR_BG, radius=4):
    track = lv.obj(parent)
    track.set_size(w, h)
    track.set_pos(x, y)
    track.set_style_bg_color(lv.color_hex(bg), 0)
    track.set_style_border_width(0, 0)
    track.set_style_pad_all(0, 0)
    track.set_style_radius(radius, 0)
    track.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    track.set_scroll_dir(lv.DIR.NONE)

    fill = lv.obj(track)
    fill.set_size(0, h)
    fill.set_pos(0, 0)
    fill.set_style_bg_color(lv.color_hex(CREAM), 0)
    fill.set_style_border_width(0, 0)
    fill.set_style_pad_all(0, 0)
    fill.set_style_radius(radius, 0)
    fill.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    fill.set_scroll_dir(lv.DIR.NONE)
    return fill


def set_bar(fill, pct, color):
    max_w = fill.get_parent().get_width()
    w = int(max_w * min(max(pct, 0), 100) / 100)
    fill.set_size(max(w, 0), fill.get_height())
    fill.set_style_bg_color(lv.color_hex(color), 0)


def make_card(parent, x, y, w, h):
    card = lv.obj(parent)
    card.set_size(w, h)
    card.set_pos(x, y)
    card.set_style_bg_color(lv.color_hex(CARD), 0)
    card.set_style_border_color(lv.color_hex(BORDER), 0)
    card.set_style_border_width(1, 0)
    card.set_style_radius(6, 0)
    card.set_style_pad_all(0, 0)
    card.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    card.set_scroll_dir(lv.DIR.NONE)
    return card


def make_horizontal_line(parent, x, y, w):
    line = lv.obj(parent)
    line.set_size(w, 1)
    line.set_pos(x, y)
    line.set_style_bg_color(lv.color_hex(BORDER), 0)
    line.set_style_border_width(0, 0)
    line.set_style_pad_all(0, 0)
    line.set_style_radius(0, 0)
    line.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    line.set_scroll_dir(lv.DIR.NONE)
    return line


# ── UI update ─────────────────────────────────────────────────────────────────

def update_ui(data):
    percent_5h    = data.get("5h_utilization_pct", 0)
    percent_7d    = data.get("7d_utilization_pct", 0)
    reset_5h      = data.get("5h_reset_minutes", 0)
    reset_7d      = data.get("7d_reset_minutes", 0)
    cpu           = data.get("pc_cpu", 0)
    ram           = data.get("pc_ram", 0)
    disk          = data.get("pc_disk", 0)
    received_time = data.get("_ts", "--:--:--")

    color_5h   = color_for(percent_5h, CREAM)
    color_7d   = color_for(percent_7d, MID)
    color_cpu  = color_for(cpu, SAND)
    color_ram  = color_for(ram, SAND)
    color_disk = color_for(disk, SAND)

    label_5h_percent.set_text("{}%".format(percent_5h))
    label_5h_percent.set_style_text_color(lv.color_hex(color_5h), 0)
    label_5h_reset.set_text(format_reset(reset_5h))
    set_bar(bar_5h, percent_5h, color_5h)

    label_7d_percent.set_text("{}%".format(percent_7d))
    label_7d_percent.set_style_text_color(lv.color_hex(color_7d), 0)
    label_7d_reset.set_text(format_reset(reset_7d))
    set_bar(bar_7d, percent_7d, color_7d)

    label_cpu.set_text("{}%".format(int(cpu)))
    label_cpu.set_style_text_color(lv.color_hex(color_cpu), 0)
    set_bar(bar_cpu, cpu, color_cpu)

    label_ram.set_text("{}%".format(int(ram)))
    label_ram.set_style_text_color(lv.color_hex(color_ram), 0)
    set_bar(bar_ram, ram, color_ram)

    label_disk.set_text("{}%".format(int(disk)))
    label_disk.set_style_text_color(lv.color_hex(color_disk), 0)
    set_bar(bar_disk, disk, color_disk)

    global time_str
    time_str = received_time
    refresh_status()


# ── Wi-Fi ─────────────────────────────────────────────────────────────────────

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASS)
        deadline = time.time() + 20
        while not wlan.isconnected():
            if time.time() > deadline:
                return None
            M5.update()
            time.sleep(0.5)
    return wlan


def recv_line(conn):
    buf = b""
    while True:
        chunk = conn.recv(1024)
        if not chunk:
            break
        buf += chunk
        if b"\n" in buf:
            break
        if len(buf) > 8192:   # safety: drop oversized frames
            break
    return buf.split(b"\n")[0].strip()


# ── Settings popup ────────────────────────────────────────────────────────────

def close_settings(evt=None):
    global popup, dim_overlay
    if popup is not None:
        popup.delete()
        popup = None
    if dim_overlay is not None:
        dim_overlay.delete()
        dim_overlay = None


def make_theme_cb(i):
    def _cb(evt):
        global theme_index
        theme_index = i
        close_settings()
        apply_theme()
        save_settings()
        open_settings()
    return _cb


def update_popup_theme_boxes():
    for i, (btn, lbl) in enumerate(zip(theme_buttons, theme_button_labels)):
        active = i == theme_index
        btn.set_style_border_color(lv.color_hex(CREAM if active else BORDER), 0)
        btn.set_style_border_width(2 if active else 1, 0)
        lbl.set_style_text_color(lv.color_hex(CREAM if active else GREY), 0)


def update_popup_brightness():
    if label_brightness is not None:
        label_brightness.set_text("{}%".format(BRIGHTNESS_LEVELS[brightness_index]))


def popup_dim(evt):
    set_brightness(brightness_index - 1)


def popup_bright(evt):
    set_brightness(brightness_index + 1)


def toggle_settings(state=None):
    if popup is not None:
        close_settings()
    else:
        open_settings()


def open_settings(state=None):
    global popup, dim_overlay, theme_buttons, theme_button_labels, label_brightness
    if popup is not None:
        return
    theme_buttons       = []
    theme_button_labels = []
    scr = lv.screen_active()

    F12 = lv.font_montserrat_12
    F14 = lv.font_montserrat_14
    F16 = lv.font_montserrat_16

    # Dim overlay — tap outside popup to dismiss
    dim_overlay = lv.obj(scr)
    dim_overlay.set_size(W, H)
    dim_overlay.set_pos(0, 0)
    dim_overlay.set_style_bg_color(lv.color_hex(0x000000), 0)
    dim_overlay.set_style_bg_opa(160, 0)
    dim_overlay.set_style_radius(0, 0)
    dim_overlay.set_style_border_width(0, 0)
    dim_overlay.set_style_pad_all(0, 0)
    dim_overlay.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    dim_overlay.set_scroll_dir(lv.DIR.NONE)
    dim_overlay.add_event_cb(close_settings, lv.EVENT.CLICKED, None)

    # Modal card: 280×140, centered
    POPUP_W, POPUP_H = 280, 140
    popup = lv.obj(scr)
    popup.set_size(POPUP_W, POPUP_H)
    popup.set_pos((W - POPUP_W) // 2, (H - POPUP_H) // 2)
    popup.set_style_bg_color(lv.color_hex(CARD), 0)
    popup.set_style_border_color(lv.color_hex(BORDER), 0)
    popup.set_style_border_width(1, 0)
    popup.set_style_radius(8, 0)
    popup.set_style_pad_all(0, 0)
    popup.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    popup.set_scroll_dir(lv.DIR.NONE)

    make_label(popup, 10, 8, "SETTINGS", CREAM, F16)
    x_button = lv.obj(popup)
    x_button.set_size(20, 20)
    x_button.set_pos(POPUP_W - 26, 6)
    x_button.set_style_bg_opa(lv.OPA.TRANSP, 0)
    x_button.set_style_border_width(0, 0)
    x_button.set_style_pad_all(0, 0)
    x_button.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    x_button.set_scroll_dir(lv.DIR.NONE)
    x_button.add_event_cb(close_settings, lv.EVENT.CLICKED, None)
    x_label = lv.label(x_button)
    x_label.set_text("X")
    x_label.set_style_text_color(lv.color_hex(GREY), 0)
    x_label.set_style_text_font(F14, 0)
    x_label.set_style_bg_opa(lv.OPA.TRANSP, 0)
    x_label.align(lv.ALIGN.CENTER, 0, 0)
    make_horizontal_line(popup, 8, 30, POPUP_W - 16)

    # ── Theme ─────────────────────────────────────────────────────────────────
    make_label(popup, 10, 36, "THEME", GREY, F12)
    button_w, button_h = 40, 26
    for i, name in enumerate(THEME_NAMES):
        button = lv.obj(popup)
        button.set_size(button_w, button_h)
        button.set_pos(10 + i * (button_w + 4), 52)
        button.set_style_bg_color(lv.color_hex(CARD), 0)
        button.set_style_radius(4, 0)
        button.set_style_pad_all(0, 0)
        button.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        button.set_scroll_dir(lv.DIR.NONE)
        button.add_event_cb(make_theme_cb(i), lv.EVENT.CLICKED, None)
        label = lv.label(button)
        label.set_text(name)
        label.set_style_text_color(lv.color_hex(GREY), 0)
        label.set_style_text_font(F12, 0)
        label.set_style_bg_opa(lv.OPA.TRANSP, 0)
        label.align(lv.ALIGN.CENTER, 0, 0)
        theme_buttons.append(button)
        theme_button_labels.append(label)
    update_popup_theme_boxes()

    make_horizontal_line(popup, 8, 85, POPUP_W - 16)

    # ── Brightness ────────────────────────────────────────────────────────────
    make_label(popup, 10, 95, "BRT", GREY, F12)

    def make_button(x, text, callback):
        button = lv.obj(popup)
        button.set_size(28, 24)
        button.set_pos(x, 90)
        button.set_style_bg_color(lv.color_hex(CARD), 0)
        button.set_style_border_color(lv.color_hex(BORDER), 0)
        button.set_style_border_width(1, 0)
        button.set_style_radius(4, 0)
        button.set_style_pad_all(0, 0)
        button.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
        button.set_scroll_dir(lv.DIR.NONE)
        button.add_event_cb(callback, lv.EVENT.CLICKED, None)
        label = lv.label(button)
        label.set_text(text)
        label.set_style_text_color(lv.color_hex(CREAM), 0)
        label.set_style_text_font(F16, 0)
        label.set_style_bg_opa(lv.OPA.TRANSP, 0)
        label.align(lv.ALIGN.CENTER, 0, 0)

    make_button(48, "-", popup_dim)
    label_brightness = make_label(popup, 82, 95, "{}%".format(BRIGHTNESS_LEVELS[brightness_index]), CREAM, F14)
    label_brightness.set_width(50)
    label_brightness.set_style_text_align(lv.TEXT_ALIGN.CENTER, 0)
    make_button(138, "+", popup_bright)


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup():
    global page0
    global label_5h_percent, label_5h_reset, label_7d_percent, label_7d_reset
    global label_status, label_cpu, label_ram, label_disk
    global label_ip
    global bar_5h, bar_7d, bar_cpu, bar_ram, bar_disk
    global header, divider_top, divider_mid, card_5h, card_7d, card_pc, label_title, label_theme
    global theme_index, brightness_index

    M5.begin()
    Widgets.setRotation(1)
    M5.Lcd.setBrightness(BRIGHTNESS_LEVELS[brightness_index] * 255 // 100)
    m5ui.init()
    page0 = m5ui.M5Page(bg_c=BG)

    BtnA.setCallback(type=BtnA.CB_TYPE.WAS_CLICKED, cb=button_dim)
    BtnB.setCallback(type=BtnB.CB_TYPE.WAS_CLICKED, cb=button_toggle)
    BtnB.setCallback(type=BtnB.CB_TYPE.WAS_HOLD,    cb=toggle_settings)
    BtnC.setCallback(type=BtnC.CB_TYPE.WAS_CLICKED, cb=button_bright)

    page0.screen_load()
    scr = lv.screen_active()
    scr.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    scr.set_scroll_dir(lv.DIR.NONE)

    F12 = lv.font_montserrat_12
    F14 = lv.font_montserrat_14
    F16 = lv.font_montserrat_16
    F24 = lv.font_montserrat_24

    # ── Header ────────────────────────────────────────────────────────────────
    header = lv.obj(scr)
    header.set_size(W, 30)
    header.set_pos(0, 0)
    header.set_style_bg_color(lv.color_hex(CARD), 0)
    header.set_style_border_width(0, 0)
    header.set_style_pad_all(0, 0)
    header.set_style_radius(0, 0)
    header.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    header.set_scroll_dir(lv.DIR.NONE)

    label_title = make_label(header, 8, 6, "CLAUDE METER", CREAM, F16)
    label_status = make_label(header, 130, 8, "", GREY, F12, lv.TEXT_ALIGN.RIGHT)
    label_status.set_width(W - 138)
    refresh_status()

    divider_top = make_horizontal_line(scr, 0, 30, W)

    # ── Claude 5h card ────────────────────────────────────────────────────────
    card_5h = make_card(scr, 6, 36, 148, 78)
    static_labels.append(make_label(card_5h, 8, 6, "5H LIMIT", GREY, F14))
    label_5h_percent   = make_label(card_5h, 8, 22, "--%", CREAM, F24)
    label_5h_reset = make_label(card_5h, 8, 28, "", GREY, F16, lv.TEXT_ALIGN.RIGHT)
    label_5h_reset.set_width(132)
    bar_5h = make_bar(card_5h, 8, 62, 132, 8, BAR_BG, 4)

    # ── Claude 7d card ────────────────────────────────────────────────────────
    card_7d = make_card(scr, 162, 36, 152, 78)
    static_labels.append(make_label(card_7d, 8, 6, "7D LIMIT", GREY, F14))
    label_7d_percent   = make_label(card_7d, 8, 22, "--%", MID, F24)
    label_7d_reset = make_label(card_7d, 8, 28, "", GREY, F16, lv.TEXT_ALIGN.RIGHT)
    label_7d_reset.set_width(136)
    bar_7d = make_bar(card_7d, 8, 62, 136, 8, BAR_BG, 4)

    divider_mid = make_horizontal_line(scr, 0, 120, W)

    # ── PC stats row ──────────────────────────────────────────────────────────
    card_pc = make_card(scr, 6, 126, 308, 90)

    static_labels.append(make_label(card_pc, 8,   8,  "CPU",  GREY, F14))
    label_cpu  = make_label(card_pc, 46,  5,  "--%", SAND, F16)
    bar_cpu = make_bar(card_pc, 8,   28, 136, 8, BAR_BG, 4)

    static_labels.append(make_label(card_pc, 156, 8,  "RAM",  GREY, F14))
    label_ram  = make_label(card_pc, 194, 5,  "--%", SAND, F16)
    bar_ram = make_bar(card_pc, 156, 28, 144, 8, BAR_BG, 4)

    static_labels.append(make_label(card_pc, 8,   50, "DISK", GREY, F14))
    label_disk  = make_label(card_pc, 52, 47, "--%", SAND, F16)
    bar_disk = make_bar(card_pc, 8,   68, 292, 8, BAR_BG, 4)

    # ── IP address footer ─────────────────────────────────────────────────────
    label_ip = make_label(scr, 0, 226, "IP: connecting...", DARK, F12, lv.TEXT_ALIGN.CENTER)
    label_ip.set_width(W)

    # ── Theme indicator (bottom right) ───────────────────────────────────────
    label_theme = make_label(scr, 272, 226, THEME_NAMES[theme_index], GREY, F12, lv.TEXT_ALIGN.RIGHT)
    label_theme.set_width(46)

    poll_battery()

    try:
        nvs = NVS("meter")
        theme_index      = max(0, min(nvs.get_i32("theme"),  len(THEMES) - 1))
        brightness_index = max(0, min(nvs.get_i32("bright"), len(BRIGHTNESS_LEVELS) - 1))
        M5.Lcd.setBrightness(BRIGHTNESS_LEVELS[brightness_index] * 255 // 100)
    except Exception:
        pass
    apply_theme()


def loop():
    M5.update()


def poll_battery():
    global battery_percent
    try:
        battery_percent = str(Power.getBatteryLevel())
        refresh_status()
    except Exception:
        pass


def poll_rssi(wlan, ssid, ip):
    try:
        try:
            rssi = wlan.config('rssi')
        except Exception:
            rssi = wlan.status('rssi')
        label_ip.set_text("{} {}dB  {}:{}".format(ssid, rssi, ip, TCP_PORT))
    except Exception as e:
        label_ip.set_text("{} [{}] {}:{}".format(ssid, str(e)[:8], ip, TCP_PORT))


def start_server():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", TCP_PORT))
    srv.listen(1)
    srv.settimeout(0)
    return srv


def handle_connection(srv):
    try:
        conn, _ = srv.accept()
    except OSError:
        return
    try:
        conn.settimeout(2)
        raw = recv_line(conn)
        if raw:
            global last_data
            data = json.loads(raw.decode("utf-8"))
            t = time.localtime()
            data["_ts"] = "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])
            last_data = data
            update_ui(data)
            conn.send(b"OK\n")
    except Exception as e:
        print("ERR: {}".format(e))
    finally:
        conn.close()


def poll_tick(wlan, ssid, ip, last_battery, last_rssi):
    now = time.time()
    if now - last_battery >= 60:
        poll_battery()
        last_battery = now
    if now - last_rssi >= 5:
        poll_rssi(wlan, ssid, ip)
        last_rssi = now
    return last_battery, last_rssi


def run(wlan):
    srv  = start_server()
    ip   = wlan.ifconfig()[0]
    ssid = wlan.config('essid')
    label_ip.set_text("{} --dB  {}:{}".format(ssid, ip, TCP_PORT))
    last_battery = last_rssi = 0

    while True:
        M5.update()
        last_battery, last_rssi = poll_tick(wlan, ssid, ip, last_battery, last_rssi)
        handle_connection(srv)


if __name__ == '__main__':
    try:
        setup()
        wlan = connect_wifi()
        if wlan:
            run(wlan)
        else:
            label_ip.set_text("no wifi")
            label_ip.set_style_text_color(lv.color_hex(RED), 0)
            while True:
                loop()
    except (Exception, KeyboardInterrupt) as e:
        try:
            m5ui.deinit()
            from utility import print_error_msg
            print_error_msg(e)
        except ImportError:
            print("please update to latest firmware")
