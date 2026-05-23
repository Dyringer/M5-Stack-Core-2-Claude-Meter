import os, sys, io
import M5
from M5 import *
import m5ui
import lvgl as lv
import network
import socket
import json
import time

# ── Wi-Fi config ─────────────────────────────────────────────────────────────
WIFI_SSID = "YOUR_SSID"
WIFI_PASS = "YOUR_PASSWORD"
TCP_PORT  = 5555

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = 0x000000
CARD     = 0x0f0a08
BORDER   = 0x622b14
DARK     = 0x622b14
MID      = 0x995f2f
SAND     = 0x978f66
CREAM    = 0xe4d6a9
GREY     = 0x60503a
BAR_BG   = 0x1a0e08
RED      = 0xff1744
YELLOW   = 0xffea00

# ── Layout ────────────────────────────────────────────────────────────────────
W, H = 320, 240

# Globals
page0      = None
lbl_5h_val = None
lbl_5h_rst = None
lbl_7d_val = None
lbl_7d_rst = None
lbl_time   = None
lbl_bat    = None
lbl_cpu    = None
lbl_ram    = None
lbl_disk   = None
lbl_ip     = None
fill_5h    = None
fill_7d    = None
fill_cpu   = None
fill_ram   = None
fill_disk  = None


def color_for(pct, lo=CREAM):
    if pct >= 90: return RED
    if pct >= 70: return MID
    if pct >= 50: return SAND
    return lo


def fmt_reset(mins):
    if mins <= 0:   return "now"
    if mins < 60:   return "{}m".format(mins)
    h, m = divmod(mins, 60)
    return "{}h{:02d}m".format(h, m)


# ── Widget helpers ────────────────────────────────────────────────────────────

def mklabel(parent, x, y, text, color, font=lv.font_montserrat_14, align=lv.TEXT_ALIGN.LEFT):
    lbl = lv.label(parent)
    lbl.set_pos(x, y)
    lbl.set_style_text_color(lv.color_hex(color), 0)
    lbl.set_style_text_font(font, 0)
    lbl.set_style_bg_opa(lv.OPA.TRANSP, 0)
    lbl.set_style_text_align(align, 0)
    lbl.set_text(text)
    return lbl


def mkbar(parent, x, y, w, h, bg=BAR_BG, radius=4):
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


def mkcard(parent, x, y, w, h):
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


def hline(parent, x, y, w):
    line = lv.obj(parent)
    line.set_size(w, 1)
    line.set_pos(x, y)
    line.set_style_bg_color(lv.color_hex(BORDER), 0)
    line.set_style_border_width(0, 0)
    line.set_style_pad_all(0, 0)
    line.set_style_radius(0, 0)
    line.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    line.set_scroll_dir(lv.DIR.NONE)


# ── UI update ─────────────────────────────────────────────────────────────────

def update_ui(data):
    pct_5h = data.get("5h_utilization_pct", 0)
    pct_7d = data.get("7d_utilization_pct", 0)
    rst_5h = data.get("5h_reset_minutes", 0)
    rst_7d = data.get("7d_reset_minutes", 0)
    cpu    = data.get("pc_cpu", 0)
    ram    = data.get("pc_ram", 0)
    disk   = data.get("pc_disk", 0)
    ts     = data.get("_ts", "--:--:--")

    c5 = color_for(pct_5h, CREAM)
    c7 = color_for(pct_7d, MID)
    cc = color_for(cpu, SAND)
    cr = color_for(ram, SAND)
    cd = color_for(disk, SAND)

    lbl_5h_val.set_text("{}%".format(pct_5h))
    lbl_5h_val.set_style_text_color(lv.color_hex(c5), 0)
    lbl_5h_rst.set_text("rst {}".format(fmt_reset(rst_5h)))
    set_bar(fill_5h, pct_5h, c5)

    lbl_7d_val.set_text("{}%".format(pct_7d))
    lbl_7d_val.set_style_text_color(lv.color_hex(c7), 0)
    lbl_7d_rst.set_text("rst {}".format(fmt_reset(rst_7d)))
    set_bar(fill_7d, pct_7d, c7)

    lbl_cpu.set_text("{}%".format(int(cpu)))
    lbl_cpu.set_style_text_color(lv.color_hex(cc), 0)
    set_bar(fill_cpu, cpu, cc)

    lbl_ram.set_text("{}%".format(int(ram)))
    lbl_ram.set_style_text_color(lv.color_hex(cr), 0)
    set_bar(fill_ram, ram, cr)

    lbl_disk.set_text("{}%".format(int(disk)))
    lbl_disk.set_style_text_color(lv.color_hex(cd), 0)
    set_bar(fill_disk, disk, cd)

    lbl_time.set_text(ts)


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


# ── Setup ─────────────────────────────────────────────────────────────────────

def setup():
    global page0
    global lbl_5h_val, lbl_5h_rst, lbl_7d_val, lbl_7d_rst
    global lbl_time, lbl_bat, lbl_cpu, lbl_ram, lbl_disk
    global lbl_ip
    global fill_5h, fill_7d, fill_cpu, fill_ram, fill_disk

    M5.begin()
    Widgets.setRotation(1)
    m5ui.init()
    page0 = m5ui.M5Page(bg_c=BG)
    page0.screen_load()
    scr = lv.screen_active()
    scr.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    scr.set_scroll_dir(lv.DIR.NONE)

    F12 = lv.font_montserrat_12
    F14 = lv.font_montserrat_14
    F16 = lv.font_montserrat_16
    F24 = lv.font_montserrat_24

    # ── Header ────────────────────────────────────────────────────────────────
    hdr = lv.obj(scr)
    hdr.set_size(W, 30)
    hdr.set_pos(0, 0)
    hdr.set_style_bg_color(lv.color_hex(CARD), 0)
    hdr.set_style_border_width(0, 0)
    hdr.set_style_pad_all(0, 0)
    hdr.set_style_radius(0, 0)
    hdr.set_scrollbar_mode(lv.SCROLLBAR_MODE.OFF)
    hdr.set_scroll_dir(lv.DIR.NONE)

    mklabel(hdr, 8, 6, "CLAUDE METER", CREAM, F16)
    lbl_time = mklabel(hdr, W - 62, 8, "--:--:--", GREY, F12)
    lbl_bat  = mklabel(hdr, W - 130, 8, "BAT:--%", GREY, F12)

    hline(scr, 0, 30, W)

    # ── Claude 5h card ────────────────────────────────────────────────────────
    c1 = mkcard(scr, 6, 36, 148, 90)
    mklabel(c1, 8, 6,  "5H LIMIT",  GREY,   F12)
    lbl_5h_val = mklabel(c1, 8, 22, "--%",  CREAM,  F24)
    lbl_5h_rst = mklabel(c1, 8, 52, "",     GREY,   F12)
    fill_5h    = mkbar(c1, 8, 68, 132, 8, BAR_BG, 4)

    # ── Claude 7d card ────────────────────────────────────────────────────────
    c2 = mkcard(scr, 162, 36, 152, 90)
    mklabel(c2, 8, 6,  "7D LIMIT",  GREY,   F12)
    lbl_7d_val = mklabel(c2, 8, 22, "--%",  MID,    F24)
    lbl_7d_rst = mklabel(c2, 8, 52, "",     GREY,   F12)
    fill_7d    = mkbar(c2, 8, 68, 136, 8, BAR_BG, 4)

    hline(scr, 0, 132, W)

    # ── PC stats row ──────────────────────────────────────────────────────────
    pc = mkcard(scr, 6, 138, 308, 82)

    mklabel(pc, 8,   8,  "CPU",  GREY, F12)
    lbl_cpu  = mklabel(pc, 44,   6,  "--%", SAND, F14)
    fill_cpu = mkbar(pc, 8,   24, 136, 8, BAR_BG, 4)

    mklabel(pc, 156, 8,  "RAM",  GREY, F12)
    lbl_ram  = mklabel(pc, 192,  6,  "--%", SAND, F14)
    fill_ram = mkbar(pc, 156, 24, 144, 8, BAR_BG, 4)

    mklabel(pc, 8,   42, "DISK", GREY, F12)
    lbl_disk  = mklabel(pc, 50,  40, "--%", SAND, F14)
    fill_disk = mkbar(pc, 8,   58, 292, 8, BAR_BG, 4)

    # ── IP address footer ─────────────────────────────────────────────────────
    lbl_ip = mklabel(scr, 0, 226, "IP: connecting...", DARK, F12, lv.TEXT_ALIGN.CENTER)
    lbl_ip.set_width(W)


def loop():
    M5.update()


def run_server(wlan):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("", TCP_PORT))
    srv.listen(1)
    srv.settimeout(0.05)

    ip   = wlan.ifconfig()[0]
    ssid = wlan.config('essid')
    lbl_ip.set_text("{} --dB  {}:{}".format(ssid, ip, TCP_PORT))
    last_rssi = 0

    while True:
        M5.update()
        try:
            bat = Power.getBatteryLevel()
            lbl_bat.set_text("BAT:{}%".format(bat))
            lbl_bat.set_style_text_color(lv.color_hex(RED if bat < 20 else SAND), 0)
        except Exception:
            pass
        now = time.time()
        if now - last_rssi >= 5:
            try:
                try:
                    rssi = wlan.config('rssi')
                except Exception:
                    rssi = wlan.status('rssi')
                lbl_ip.set_text("{} {}dB  {}:{}".format(ssid, rssi, ip, TCP_PORT))
            except Exception as e:
                lbl_ip.set_text("{} [{}] {}:{}".format(ssid, str(e)[:8], ip, TCP_PORT))
            last_rssi = now
        try:
            conn, _ = srv.accept()
        except OSError:
            continue  # no connection this tick, loop again
        try:
            conn.settimeout(2)
            raw = recv_line(conn)
            if raw:
                data = json.loads(raw.decode("utf-8"))
                t = time.localtime()
                data["_ts"] = "{:02d}:{:02d}:{:02d}".format(t[3], t[4], t[5])
                update_ui(data)
                conn.send(b"OK\n")
        except Exception as e:
            print("ERR: {}".format(e))
        finally:
            conn.close()


if __name__ == '__main__':
    try:
        setup()
        wlan = connect_wifi()
        if wlan:
            run_server(wlan)
        else:
            lbl_ip.set_text("no wifi")
            lbl_ip.set_style_text_color(lv.color_hex(RED), 0)
            while True:
                loop()
    except (Exception, KeyboardInterrupt) as e:
        try:
            m5ui.deinit()
            from utility import print_error_msg
            print_error_msg(e)
        except ImportError:
            print("please update to latest firmware")
