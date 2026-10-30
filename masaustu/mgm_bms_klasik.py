# -*- coding: utf-8 -*-
"""
MGM BMS – JK-BMS Android uygulamasının (v6.3.01) PC karşılığı.
Bilgisayarın Bluetooth'u (BLE) ile JK BMS'e bağlanır; hücre gerilimleri, akım,
SOC, sıcaklıklar, alarmlar, cihaz bilgisi ve ayarları gösterir.

Gereksinim:  pip install bleak
Çalıştır:    python mgm_bms.py
"""
import asyncio
import csv
import datetime as dt
import math
import queue
import time
import tkinter as tk
import tkinter.font as tkfont
from collections import deque
from tkinter import messagebox, filedialog

import jk_protocol as jk
from ble_worker import BleWorker, HAVE_BLEAK

APP_TITLE = "MGM BMS"

# ============================================================================= tema
BG = "#0b0f17"
SIDEBAR = "#0e1420"
CARD = "#141b27"
CARD2 = "#1b2433"
CARD3 = "#222d3f"
BORDER = "#1f2a3a"
TEXT = "#e9eef6"
MUTED = "#7f8ba1"
DIM = "#4d596d"
ACCENT = "#22d3a6"      # yeşil-turkuaz
BLUE = "#5b8cff"
AMBER = "#f5b84b"
RED = "#ff5d6c"
PURPLE = "#a78bfa"
CYAN = "#38bdf8"

FONT = "Segoe UI"
MONO = "Consolas"


def _pick_fonts(root):
    global FONT, MONO
    fam = set(tkfont.families(root))
    for f in ("Segoe UI Variable Text", "Segoe UI", "Inter", "SF Pro Text", "Helvetica Neue", "DejaVu Sans"):
        if f in fam:
            FONT = f
            break
    for f in ("Cascadia Mono", "Consolas", "JetBrains Mono", "Menlo", "DejaVu Sans Mono"):
        if f in fam:
            MONO = f
            break


def F(size, bold=False):
    return (FONT, size, "bold" if bold else "normal")


def M(size, bold=False):
    return (MONO, size, "bold" if bold else "normal")


def blend(c1, c2, t):
    """c1 ile c2 arasında t oranında renk karışımı (tk'de saydamlık yok)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{int(x + (y - x) * t):02x}" for x, y in zip(a, b))


def rrect(c, x1, y1, x2, y2, r, **kw):
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return c.create_polygon(pts, smooth=True, **kw)


def soc_color(soc):
    return RED if soc < 15 else (AMBER if soc < 35 else ACCENT)


# ============================================================================= widget'lar
class Card(tk.Canvas):
    """Yuvarlak köşeli kart; içeriği render(canvas, w, h) ile çizilir."""

    def __init__(self, parent, render=None, radius=18, fill=CARD, outer=BG, height=None):
        super().__init__(parent, bg=outer, highlightthickness=0, bd=0, height=height or 100, width=60)
        self.render, self.radius, self.fill = render, radius, fill
        self.bind("<Configure>", lambda e: self.redraw())

    def redraw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 20 or h < 20:
            return
        rrect(self, 1, 1, w - 1, h - 1, self.radius, fill=self.fill, outline=BORDER)
        if self.render:
            self.render(self, w, h)


class Button(tk.Canvas):
    STYLES = {
        "primary": (ACCENT, "#2ee6b8", "#04241c"),
        "ghost": (CARD2, CARD3, TEXT),
        "danger": (blend(RED, CARD, .75), blend(RED, CARD, .6), RED),
    }

    def __init__(self, parent, text, command, kind="ghost", width=150, height=38, outer=SIDEBAR, font=None):
        super().__init__(parent, width=width, height=height, bg=outer, highlightthickness=0, bd=0,
                         cursor="hand2")
        self.text, self.command, self.kind = text, command, kind
        self.font = font or F(10, True)
        self.hover = False
        self.enabled = True
        self.bind("<Enter>", lambda e: self._h(True))
        self.bind("<Leave>", lambda e: self._h(False))
        self.bind("<ButtonRelease-1>", lambda e: self.enabled and self.command and self.command())
        self.bind("<Configure>", lambda e: self.draw())

    def _h(self, v):
        self.hover = v
        self.draw()

    def config_btn(self, text=None, kind=None, enabled=None):
        if text is not None:
            self.text = text
        if kind is not None:
            self.kind = kind
        if enabled is not None:
            self.enabled = enabled
            self.configure(cursor="hand2" if enabled else "arrow")
        self.draw()

    def draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        base, hov, fg = self.STYLES[self.kind]
        if not self.enabled:
            base, hov, fg = CARD2, CARD2, DIM
        rrect(self, 1, 1, w - 1, h - 1, h / 2 - 1, fill=hov if self.hover else base, outline="")
        self.create_text(w / 2, h / 2, text=self.text, fill=fg, font=self.font)


def draw_switch(c, x, y, on, tag, w=42, h=24, color=ACCENT):
    rrect(c, x, y, x + w, y + h, h / 2, fill=color if on else CARD3, outline="", tags=tag)
    k = x + w - h / 2 if on else x + h / 2
    c.create_oval(k - h / 2 + 3, y + 3, k + h / 2 - 3, y + h - 3, fill="#ffffff" if on else MUTED,
                  outline="", tags=tag)
    c.tag_bind(tag, "<Enter>", lambda e: c.configure(cursor="hand2"))
    c.tag_bind(tag, "<Leave>", lambda e: c.configure(cursor=""))


def draw_chip(c, x, y, text, color, font=None, anchor="w"):
    font = font or F(9, True)
    fnt = tkfont.Font(family=font[0], size=font[1], weight=font[2])
    tw = fnt.measure(text) + 20
    if anchor == "e":
        x -= tw
    elif anchor == "center":
        x -= tw / 2
    rrect(c, x, y, x + tw, y + 24, 12, fill=blend(color, CARD, .82), outline="")
    c.create_text(x + tw / 2, y + 12, text=text, fill=color, font=font)
    return tw


def sparkline(c, x1, y1, x2, y2, vals, color, fill_bg=CARD):
    vals = [v for v in vals if v is not None]
    if len(vals) < 2:
        return
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        lo, hi = lo - 1, hi + 1
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        pts += [x1 + (x2 - x1) * i / (n - 1), y2 - (y2 - y1) * (v - lo) / (hi - lo)]
    c.create_polygon([x1, y2] + pts + [x2, y2], fill=blend(color, fill_bg, .86), outline="")
    c.create_line(pts, fill=color, width=2, smooth=True)
    c.create_oval(pts[-2] - 3, pts[-1] - 3, pts[-2] + 3, pts[-1] + 3, fill=color, outline="")


# ============================================================================= uygulama
class App(tk.Tk):
    PAGES = [("panel", "◐", "Panel"), ("cells", "▥", "Hücreler"), ("charts", "∿", "Grafikler"),
             ("settings", "⚙", "Ayarlar"), ("device", "ⓘ", "Cihaz"), ("console", "›_", "Konsol")]

    def __init__(self):
        super().__init__()
        _pick_fonts(self)
        self.title(APP_TITLE)
        self.geometry("1320x840")
        self.minsize(1100, 720)
        self.configure(bg=BG)
        self.events = queue.Queue()
        self.worker = BleWorker(self.events) if HAVE_BLEAK else None
        self.devices = []
        self.connected = False
        self.demo_on = False
        self.settings = {}
        self.info = {}
        self.d = None                  # son hücre verisi
        self.hist = deque(maxlen=900)  # ~15 dk
        self.last_update = 0
        self.csv_file = self.csv_writer = None
        self.status_text = "Bağlı değil"
        self.page = "panel"
        self.page_cards = {}
        self.scan_win = None
        self.raw_paused = False
        self.settings_unlocked = False
        self.pending = {}              # ofset -> (yeni ham değer, gönderim zamanı)
        self._build()
        self.show_page("panel")
        self.after(100, self._poll)
        self.after(1000, self._tick)
        if not HAVE_BLEAK:
            self.toast("bleak yüklü değil – 'pip install bleak'. Şimdilik Demo kullanılabilir.", AMBER)

    # ------------------------------------------------------------------ iskelet
    def _build(self):
        self.side = tk.Frame(self, bg=SIDEBAR, width=236)
        self.side.pack(side="left", fill="y")
        self.side.pack_propagate(False)
        self._build_sidebar()

        self.main = tk.Frame(self, bg=BG)
        self.main.pack(side="left", fill="both", expand=True)
        self.header = tk.Canvas(self.main, bg=BG, height=78, highlightthickness=0)
        self.header.pack(fill="x", padx=24, pady=(14, 0))
        self.header.bind("<Configure>", lambda e: self._draw_header())

        self.content = tk.Frame(self.main, bg=BG)
        self.content.pack(fill="both", expand=True, padx=24, pady=(6, 24))
        self.pages = {}
        for key, _, _ in self.PAGES:
            f = tk.Frame(self.content, bg=BG)
            self.pages[key] = f
        self._page_panel(self.pages["panel"])
        self._page_cells(self.pages["cells"])
        self._page_charts(self.pages["charts"])
        self._page_settings(self.pages["settings"])
        self._page_device(self.pages["device"])
        self._page_console(self.pages["console"])

        self.toast_lbl = tk.Label(self.main, bg=CARD3, fg=TEXT, font=F(10), padx=16, pady=10)

    def _build_sidebar(self):
        s = self.side
        logo = tk.Canvas(s, bg=SIDEBAR, height=86, highlightthickness=0)
        logo.pack(fill="x", padx=20, pady=(22, 6))

        def draw_logo(e=None):
            logo.delete("all")
            rrect(logo, 0, 14, 46, 60, 14, fill=blend(ACCENT, SIDEBAR, .8), outline="")
            rrect(logo, 13, 24, 33, 52, 4, fill="", outline=ACCENT, width=2)
            logo.create_rectangle(19, 20, 27, 24, fill=ACCENT, outline="")
            logo.create_rectangle(16, 38, 30, 49, fill=ACCENT, outline="")
            logo.create_text(60, 26, text="MGM BMS", anchor="w", fill=TEXT, font=F(16, True))
            logo.create_text(60, 49, text="JK BMS Monitör", anchor="w", fill=MUTED, font=F(10))
        logo.bind("<Configure>", draw_logo)

        self.nav = tk.Canvas(s, bg=SIDEBAR, highlightthickness=0, height=len(self.PAGES) * 48 + 10)
        self.nav.pack(fill="x", padx=14, pady=(14, 0))
        self.nav.bind("<Configure>", lambda e: self._draw_nav())
        self.nav.bind("<Motion>", self._nav_motion)
        self.nav.bind("<Leave>", lambda e: self._nav_motion(None))
        self.nav.bind("<Button-1>", self._nav_click)
        self.nav_hover = None

        # alt: bağlantı kartı
        bottom = tk.Frame(s, bg=SIDEBAR)
        bottom.pack(side="bottom", fill="x", padx=14, pady=18)
        self.conn_card = Card(bottom, self._render_conn, radius=16, fill=CARD, outer=SIDEBAR, height=112)
        self.conn_card.pack(fill="x")
        self.btn_connect = Button(bottom, "Cihaz Bul", self.on_connect_btn, "primary", width=208, height=40)
        self.btn_connect.pack(fill="x", pady=(12, 0))
        self.btn_demo = Button(bottom, "Demo modu", self.on_demo, "ghost", width=208, height=36)
        self.btn_demo.pack(fill="x", pady=(8, 0))
        self.csv_canvas = tk.Canvas(bottom, bg=SIDEBAR, height=34, highlightthickness=0)
        self.csv_canvas.pack(fill="x", pady=(10, 0))
        self.csv_canvas.bind("<Configure>", lambda e: self._draw_csv())

    def _draw_csv(self):
        c = self.csv_canvas
        c.delete("all")
        c.create_text(4, 17, text="CSV kaydı", anchor="w", fill=MUTED, font=F(10))
        w = c.winfo_width()
        draw_switch(c, w - 48, 5, self.csv_writer is not None, "csv")
        c.tag_bind("csv", "<Button-1>", lambda e: self.on_csv())

    def _draw_nav(self):
        c = self.nav
        c.delete("all")
        w = c.winfo_width()
        for i, (key, icon, name) in enumerate(self.PAGES):
            y = 4 + i * 48
            active = key == self.page
            if active or self.nav_hover == i:
                rrect(c, 0, y, w, y + 42, 12, fill=CARD2 if active else CARD, outline="")
            if active:
                rrect(c, 0, y + 11, 4, y + 31, 2, fill=ACCENT, outline="")
            col = TEXT if active else MUTED
            c.create_text(26, y + 21, text=icon, fill=ACCENT if active else MUTED, font=F(13, True))
            c.create_text(52, y + 21, text=name, anchor="w", fill=col, font=F(11, active))

    def _nav_motion(self, e):
        i = None if e is None else int((e.y - 4) // 48)
        if i is not None and not (0 <= i < len(self.PAGES)):
            i = None
        if i != self.nav_hover:
            self.nav_hover = i
            self.nav.configure(cursor="hand2" if i is not None else "")
            self._draw_nav()

    def _nav_click(self, e):
        i = int((e.y - 4) // 48)
        if 0 <= i < len(self.PAGES):
            self.show_page(self.PAGES[i][0])

    def show_page(self, key):
        self.pages[self.page].pack_forget()
        self.page = key
        self.pages[key].pack(fill="both", expand=True)
        self._draw_nav()
        self._draw_header()
        self.after(10, self.refresh_page)

    def refresh_page(self):
        for c in self.page_cards.get(self.page, []):
            c.redraw()

    def _add(self, page, card, **grid):
        card.grid(**grid)
        self.page_cards.setdefault(page, []).append(card)
        return card

    # ------------------------------------------------------------------ başlık + bağlantı kartı
    def _draw_header(self):
        c = self.header
        c.delete("all")
        w = c.winfo_width()
        title = dict((k, n) for k, _, n in self.PAGES)[self.page]
        c.create_text(0, 26, text=title, anchor="w", fill=TEXT, font=F(22, True))
        sub = "Bir JK BMS'e bağlanın ya da demo modunu deneyin"
        if self.info:
            sub = f"{self.info.get('name') or '—'}  ·  {self.info.get('model', '')}  ·  yazılım {self.info.get('sw', '')}"
        c.create_text(0, 58, text=sub, anchor="w", fill=MUTED, font=F(10))
        if self.demo_on:
            label, col = "●  DEMO", PURPLE
        elif self.connected:
            label, col = "●  CANLI", ACCENT
        else:
            label, col = "●  Bağlı değil", MUTED
        x = w
        x -= draw_chip(c, x, 18, label, col, anchor="e") + 10
        if self.last_update and (self.connected or self.demo_on):
            age = int(time.time() - self.last_update)
            c.create_text(x, 30, text=f"son veri {age} sn önce" if age > 1 else "güncel",
                          anchor="e", fill=DIM, font=F(9))

    def _render_conn(self, c, w, h):
        col = PURPLE if self.demo_on else (ACCENT if self.connected else DIM)
        c.create_oval(18, 22, 28, 32, fill=col, outline="")
        if self.connected or self.demo_on:
            c.create_oval(14, 18, 32, 36, outline=blend(col, CARD, .5), width=1)
        c.create_text(40, 27, text="Bağlantı", anchor="w", fill=MUTED, font=F(9))
        name = (self.info.get("name") or self.info.get("model")) if (self.connected or self.demo_on) and self.info else None
        c.create_text(18, 56, text=name or ("Bağlı" if self.connected else "Cihaz yok"), anchor="w",
                      fill=TEXT, font=F(12, True), width=w - 30)
        c.create_text(18, 84, text=self.status_text, anchor="w", fill=MUTED, font=F(9), width=w - 30)

    def set_status(self, s):
        self.status_text = s
        self.conn_card.redraw()

    def toast(self, msg, color=RED):
        self.toast_lbl.config(text=msg, fg=color)
        self.toast_lbl.place(relx=1.0, rely=1.0, x=-28, y=-28, anchor="se")
        if hasattr(self, "_toast_job"):
            self.after_cancel(self._toast_job)
        self._toast_job = self.after(4500, self.toast_lbl.place_forget)

    # ================================================================== PANEL
    def _page_panel(self, p):
        p.columnconfigure(0, weight=0, minsize=310)
        p.columnconfigure(1, weight=1)
        p.columnconfigure(2, weight=1)
        p.columnconfigure(3, weight=0, minsize=330)
        p.rowconfigure(0, weight=0, minsize=158)
        p.rowconfigure(1, weight=0, minsize=158)
        p.rowconfigure(2, weight=1)
        g = dict(padx=7, pady=7, sticky="nsew")
        self._add("panel", Card(p, self._r_gauge), row=0, column=0, rowspan=2, **g)
        self._add("panel", Card(p, lambda c, w, h: self._r_stat(c, w, h, "Toplam gerilim", "voltage", "V", BLUE, 2)),
                  row=0, column=1, **g)
        self._add("panel", Card(p, lambda c, w, h: self._r_stat(c, w, h, "Akım", "current", "A", ACCENT, 2, signed=True)),
                  row=0, column=2, **g)
        self._add("panel", Card(p, lambda c, w, h: self._r_stat(c, w, h, "Güç", "power", "W", AMBER, 0)),
                  row=1, column=1, **g)
        self._add("panel", Card(p, lambda c, w, h: self._r_stat(c, w, h, "Hücre farkı", "delta", "mV", PURPLE, 0)),
                  row=1, column=2, **g)
        self._add("panel", Card(p, self._r_status), row=0, column=3, rowspan=3, **g)
        self._add("panel", Card(p, self._r_cellbars), row=2, column=0, columnspan=3, **g)

    def _no_data(self, c, w, h, y=None):
        c.create_text(w / 2, y or h / 2, text="Veri bekleniyor…", fill=DIM, font=F(11))

    def _r_gauge(self, c, w, h):
        d = self.d
        soc = d["soc"] if d else 0
        cx, cy = w / 2, h / 2 - 22
        R = min(w - 60, h - 110) / 2
        th = 16
        box = (cx - R, cy - R, cx + R, cy + R)
        c.create_arc(*box, start=225, extent=-270, style="arc", outline=CARD3, width=th)
        col = soc_color(soc)

        def cap(a, color):
            rad = math.radians(a)
            x, y = cx + R * math.cos(rad), cy - R * math.sin(rad)
            c.create_oval(x - th / 2, y - th / 2, x + th / 2, y + th / 2, fill=color, outline="")
        cap(225, CARD3)
        cap(-45, CARD3)
        if d and soc > 0:
            ext = -270 * soc / 100
            # yumuşak geçişli segmentler
            steps = max(1, int(abs(ext) / 6))
            for i in range(steps):
                a0 = 225 + ext * i / steps
                seg = ext / steps - (0.4 if i < steps - 1 else 0)
                c.create_arc(*box, start=a0, extent=seg, style="arc",
                             outline=blend(blend(col, "#ffffff", .25), col, i / steps), width=th)
            cap(225, blend(col, "#ffffff", .25))
            cap(225 + ext, col)
        c.create_text(cx, cy - 6, text=f"{soc}" if d else "--", fill=TEXT, font=F(40, True))
        c.create_text(cx, cy + 34, text="% şarj (SOC)", fill=MUTED, font=F(10))
        if not d:
            return
        c.create_text(cx, h - 70, text=f"{d['remain_ah']:.1f} / {d['full_ah']:.1f} Ah", fill=TEXT, font=F(12, True))
        cur = d["current"]
        if cur > 0.05:
            st, sc = "⚡ Şarj oluyor", ACCENT
            eta = (d["full_ah"] - d["remain_ah"]) / cur if cur else 0
            extra = f"dolmasına ~{eta:.1f} sa"
        elif cur < -0.05:
            st, sc = "↓ Deşarj", AMBER
            extra = f"bitmesine ~{d['remain_ah'] / -cur:.1f} sa"
        else:
            st, sc, extra = "● Beklemede", MUTED, ""
        draw_chip(c, cx, h - 46, st, sc, anchor="center")
        if extra:
            c.create_text(cx, h - 12, text=extra, fill=DIM, font=F(9))

    def _hist(self, key):
        return [r.get(key) for r in list(self.hist)[-120:]]

    def _r_stat(self, c, w, h, title, key, unit, color, dec, signed=False):
        c.create_oval(20, 22, 30, 32, fill=color, outline="")
        c.create_text(38, 27, text=title, anchor="w", fill=MUTED, font=F(10))
        d = self.d
        if not d:
            c.create_text(20, 72, text="--", anchor="w", fill=DIM, font=F(26, True))
            return
        val = {"voltage": d["voltage"], "current": d["current"], "power": d["power"],
               "delta": d["delta_cell"] * 1000}[key]
        txt = f"{val:+.{dec}f}" if signed else f"{val:.{dec}f}"
        vcol = TEXT
        if key == "delta":
            vcol = RED if val > 50 else (AMBER if val > 20 else TEXT)
        t = c.create_text(20, 72, text=txt, anchor="w", fill=vcol, font=F(26, True))
        x2 = c.bbox(t)[2]
        c.create_text(x2 + 6, 80, text=unit, anchor="w", fill=MUTED, font=F(11))
        # sağ üst ek bilgi
        if key == "voltage":
            extra = f"ort. hücre {d['avg_cell']:.3f} V"
        elif key == "current":
            extra = "şarj" if val > 0.05 else ("deşarj" if val < -0.05 else "boşta")
        elif key == "power":
            extra = f"{val / 1000:.2f} kW"
        else:
            extra = f"maks #{d['max_idx'] + 1} · min #{d['min_idx'] + 1}"
        f9 = tkfont.Font(family=FONT, size=9)
        f10 = tkfont.Font(family=FONT, size=10)
        if 38 + f10.measure(title) + 16 + f9.measure(extra) < w - 20:
            c.create_text(w - 20, 27, text=extra, anchor="e", fill=DIM, font=F(9))
        hv = self._hist(key)
        sparkline(c, 20, h - 46, w - 20, h - 16, hv, color)

    def _r_status(self, c, w, h):
        y = 26
        c.create_text(22, y, text="Kontrol", anchor="w", fill=TEXT, font=F(13, True))
        y += 34
        s, d = self.settings, self.d
        rows = [("Şarj", "_charge_on", "charge", d["charge_mos"] if d else None),
                ("Deşarj", "_discharge_on", "discharge", d["discharge_mos"] if d else None),
                ("Dengeleyici", "_balance_on", "balance", None)]
        for name, key, act, mos in rows:
            rrect(c, 16, y - 4, w - 16, y + 44, 12, fill=CARD2, outline="")
            c.create_text(32, y + 12, text=name, anchor="w", fill=TEXT, font=F(11, True))
            if mos is not None:
                sub, scol = ("MOS iletimde", ACCENT) if mos else ("MOS kapalı", MUTED)
            elif act == "balance" and d:
                sub = {0: "beklemede", 1: "şarj dengeleme", 2: "deşarj dengeleme"}.get(d["balance_action"], "")
                sub += f" · {abs(d['balance_current']):.2f} A" if d["balance_action"] else ""
                scol = AMBER if d["balance_action"] else MUTED
            else:
                sub, scol = "—", DIM
            c.create_text(32, y + 30, text=sub, anchor="w", fill=scol, font=F(9))
            tag = "sw_" + act
            draw_switch(c, w - 70, y + 8, bool(s.get(key)), tag)
            c.tag_bind(tag, "<Button-1>", lambda e, a=act: self.toggle(a))
            y += 56

        y += 10
        c.create_text(22, y, text="Sıcaklıklar", anchor="w", fill=TEXT, font=F(13, True))
        y += 22
        temps = []
        if d:
            if d["mos_temp"] is not None:
                temps.append(("MOS", d["mos_temp"]))
            temps += [(f"T{i + 1}", t) for i, t in enumerate(d["temps"]) if t is not None]
        if not temps:
            c.create_text(22, y + 14, text="--", anchor="w", fill=DIM, font=F(10))
            y += 34
        else:
            cols = 3
            tw = (w - 32 - (cols - 1) * 8) / cols
            for i, (n, t) in enumerate(temps):
                x = 16 + (i % cols) * (tw + 8)
                yy = y + (i // cols) * 58
                tc = RED if t >= 55 else (AMBER if t >= 42 else (CYAN if t < 5 else TEXT))
                rrect(c, x, yy, x + tw, yy + 50, 12, fill=CARD2, outline="")
                c.create_text(x + 12, yy + 15, text=n, anchor="w", fill=MUTED, font=F(9))
                c.create_text(x + 12, yy + 34, text=f"{t:.1f}°", anchor="w", fill=tc, font=F(13, True))
            y += ((len(temps) + cols - 1) // cols) * 58 + 4

        y += 12
        c.create_text(22, y, text="Bilgi", anchor="w", fill=TEXT, font=F(13, True))
        y += 26
        if d:
            info = [("Döngü sayısı", f"{d['cycles']}"), ("Sağlık (SOH)", f"%{d['soh']}"),
                    ("Toplam döngü kap.", f"{d['cycle_ah']:.0f} Ah"),
                    ("Çalışma süresi", jk.secs_to_text(d["runtime_s"]))]
            for k, v in info:
                c.create_text(22, y, text=k, anchor="w", fill=MUTED, font=F(10))
                c.create_text(w - 22, y, text=v, anchor="e", fill=TEXT, font=F(10, True))
                y += 25
        y += 10
        al = (d["alarms"] + d["user_alarms"]) if d else []
        if y < h - 50:
            c.create_text(22, y, text="Alarmlar", anchor="w", fill=TEXT, font=F(13, True))
            if d:
                draw_chip(c, w - 20, y - 12, f"{len(al)}" if al else "Yok ✓", RED if al else ACCENT, anchor="e")
            y += 24
            for a in al:
                if y > h - 30:
                    c.create_text(22, y, text="…", anchor="w", fill=MUTED)
                    break
                rrect(c, 16, y - 2, w - 16, y + 28, 10, fill=blend(RED, CARD, .85), outline="")
                c.create_text(28, y + 13, text="⚠ " + a, anchor="w", fill=RED, font=F(9, True), width=w - 50)
                y += 34

    def _r_cellbars(self, c, w, h):
        c.create_text(22, 28, text="Hücre gerilimleri", anchor="w", fill=TEXT, font=F(13, True))
        d = self.d
        if not d or not d["cells"]:
            self._no_data(c, w, h)
            return
        cells = d["cells"]
        n = len(cells)
        vmax, vmin = max(cells), min(cells)
        x = w - 20
        for txt, col in ((f"Δ {d['delta_cell'] * 1000:.0f} mV", PURPLE), (f"min {vmin:.3f}", BLUE),
                         (f"maks {vmax:.3f}", RED), (f"{n} hücre", MUTED)):
            x -= draw_chip(c, x, 16, txt, col, anchor="e") + 8
        top, bot, left, right = 66, h - 40, 58, w - 20
        mid = (vmax + vmin) / 2
        span = max(0.06, (vmax - vmin) * 1.6)
        lo, hi = mid - span / 2, mid + span / 2
        # ızgara
        for i in range(5):
            v = lo + (hi - lo) * i / 4
            yy = bot - (bot - top) * i / 4
            c.create_line(left, yy, right, yy, fill=BORDER)
            c.create_text(left - 8, yy, text=f"{v:.3f}", anchor="e", fill=DIM, font=F(8))
        ya = bot - (bot - top) * (d["avg_cell"] - lo) / (hi - lo)
        slot = (right - left) / n
        bw = max(4, min(42, slot * 0.62))
        for i, v in enumerate(cells):
            cx = left + slot * (i + .5)
            yv = bot - (bot - top) * (v - lo) / (hi - lo)
            is_max = vmax != vmin and abs(v - vmax) < 1e-6
            is_min = vmax != vmin and abs(v - vmin) < 1e-6
            col = RED if is_max else (BLUE if is_min else ACCENT)
            rrect(c, cx - bw / 2, top, cx + bw / 2, bot, min(8, bw / 2), fill=blend(col, CARD, .9), outline="")
            rrect(c, cx - bw / 2, yv, cx + bw / 2, bot, min(8, bw / 2), fill=col, outline="")
            c.create_text(cx, bot + 14, text=str(d["cell_index"][i]), fill=MUTED, font=F(8))
            if slot >= 40:
                c.create_text(cx, yv - 10, text=f"{v:.3f}", fill=TEXT if (is_max or is_min) else MUTED, font=F(8, True))
            bal = d["balance_action"] and ((is_max and d["balance_action"] == 2) or (is_min and d["balance_action"] == 1))
            if bal:
                c.create_text(cx, top - 10, text="⚖", fill=AMBER, font=F(10))
        c.create_line(left, ya, right, ya, fill=AMBER, dash=(5, 4))
        c.create_text(right, ya - 9, text=f"ort {d['avg_cell']:.3f}", anchor="e", fill=AMBER, font=F(8, True))

    # ================================================================== HÜCRELER
    def _page_cells(self, p):
        p.columnconfigure(0, weight=1)
        p.rowconfigure(0, weight=1)
        self._add("cells", Card(p, self._r_cell_tiles), row=0, column=0, sticky="nsew", padx=7, pady=7)

    def _r_cell_tiles(self, c, w, h):
        c.create_text(24, 30, text="Hücre ayrıntıları", anchor="w", fill=TEXT, font=F(13, True))
        c.create_text(24, 52, text="gerilim · denge kablosu direnci · sapma", anchor="w", fill=MUTED, font=F(9))
        d = self.d
        if not d or not d["cells"]:
            self._no_data(c, w, h)
            return
        cells = d["cells"]
        n = len(cells)
        vmax, vmin, avg = max(cells), min(cells), d["avg_cell"]
        cols = max(2, int((w - 40) // 210))
        gap = 12
        tw = (w - 40 - gap * (cols - 1)) / cols
        th = 88
        lo, hi = (2.5, 3.65) if vmax < 3.7 else (3.0, 4.25)
        for k, v in enumerate(cells):
            x = 20 + (k % cols) * (tw + gap)
            y = 76 + (k // cols) * (th + gap)
            if y + th > h - 10:
                break
            is_max = vmax != vmin and abs(v - vmax) < 1e-6
            is_min = vmax != vmin and abs(v - vmin) < 1e-6
            col = RED if is_max else (BLUE if is_min else ACCENT)
            rrect(c, x, y, x + tw, y + th, 14, fill=CARD2,
                  outline=AMBER if d["res_alarm"][k] else (col if (is_max or is_min) else ""))
            rrect(c, x + 12, y + 12, x + 46, y + 32, 10, fill=blend(col, CARD2, .78), outline="")
            c.create_text(x + 29, y + 22, text=f"{d['cell_index'][k]:02d}", fill=col, font=F(9, True))
            dev = (v - avg) * 1000
            c.create_text(x + tw - 14, y + 22, text=f"{dev:+.0f} mV", anchor="e",
                          fill=RED if abs(dev) > 20 else MUTED, font=F(9))
            c.create_text(x + 14, y + 52, text=f"{v:.3f}", anchor="w", fill=TEXT, font=M(17, True))
            c.create_text(x + tw - 14, y + 54, text=f"{d['resistances'][k] * 1000:.0f} mΩ", anchor="e",
                          fill=AMBER if d["res_alarm"][k] else DIM, font=F(9))
            frac = min(1, max(0.02, (v - lo) / (hi - lo)))
            rrect(c, x + 14, y + th - 16, x + tw - 14, y + th - 10, 3, fill=CARD3, outline="")
            rrect(c, x + 14, y + th - 16, x + 14 + (tw - 28) * frac, y + th - 10, 3, fill=col, outline="")

    # ================================================================== GRAFİKLER
    def _page_charts(self, p):
        for i in range(2):
            p.columnconfigure(i, weight=1)
            p.rowconfigure(i, weight=1)
        g = dict(padx=7, pady=7, sticky="nsew")
        self._add("charts", Card(p, lambda c, w, h: self._r_chart(c, w, h, "Toplam gerilim", "V",
                                                                 [("Gerilim", "voltage", BLUE)])), row=0, column=0, **g)
        self._add("charts", Card(p, lambda c, w, h: self._r_chart(c, w, h, "Akım", "A",
                                                                 [("Akım", "current", ACCENT)], zero=True)), row=0, column=1, **g)
        self._add("charts", Card(p, lambda c, w, h: self._r_chart(c, w, h, "Hücre farkı", "mV",
                                                                 [("Δ", "delta", PURPLE)])), row=1, column=0, **g)
        self._add("charts", Card(p, lambda c, w, h: self._r_chart(c, w, h, "Sıcaklıklar", "°C",
                                                                 [("MOS", "mos", AMBER), ("T1", "t1", CYAN),
                                                                  ("T2", "t2", PURPLE)])), row=1, column=1, **g)

    def _r_chart(self, c, w, h, title, unit, series, zero=False):
        c.create_text(22, 28, text=title, anchor="w", fill=TEXT, font=F(13, True))
        span_s = (self.hist[-1]["t"] - self.hist[0]["t"]) if len(self.hist) > 1 else 0
        c.create_text(22, 50, text=(f"son {span_s / 60:.0f} dk" if span_s >= 120 else f"son {span_s:.0f} sn") + f" · {unit}",
                      anchor="w", fill=DIM, font=F(9))
        lx = w - 20
        for name, key, col in reversed(series):
            t = c.create_text(lx, 30, text=name, anchor="e", fill=MUTED, font=F(9))
            lx = c.bbox(t)[0] - 8
            c.create_oval(lx - 8, 26, lx, 34, fill=col, outline="")
            lx -= 16
        hist = list(self.hist)
        left, right, top, bot = 60, w - 22, 70, h - 36
        allv = [r[k] for r in hist for _, k, _ in series if r.get(k) is not None]
        if len(hist) < 2 or not allv:
            self._no_data(c, w, h)
            return
        lo, hi = min(allv), max(allv)
        if zero:
            lo, hi = min(lo, 0), max(hi, 0)
        pad = (hi - lo) * 0.12 or 1
        lo, hi = lo - pad, hi + pad
        for i in range(5):
            v = lo + (hi - lo) * i / 4
            yy = bot - (bot - top) * i / 4
            c.create_line(left, yy, right, yy, fill=BORDER)
            c.create_text(left - 8, yy, text=f"{v:.1f}" if abs(hi - lo) > 4 else f"{v:.2f}", anchor="e",
                          fill=DIM, font=F(8))
        t0, t1 = hist[0]["t"], hist[-1]["t"]
        span = max(1, t1 - t0)
        for i in range(5):
            tx = left + (right - left) * i / 4
            secs = span * (1 - i / 4)
            c.create_text(tx, bot + 16, text="şimdi" if i == 4 else f"-{secs / 60:.0f} dk" if secs >= 120 else f"-{secs:.0f} sn",
                          fill=DIM, font=F(8))
        if zero and lo < 0 < hi:
            yz = bot - (bot - top) * (0 - lo) / (hi - lo)
            c.create_line(left, yz, right, yz, fill=DIM, dash=(3, 3))
        nb = max(2, int((right - left) / 4))   # ~4 px'lik kovalarda ortalama → pürüzsüz çizgi
        for si, (name, key, col) in enumerate(series):
            buckets = {}
            for r in hist:
                v = r.get(key)
                if v is None:
                    continue
                b = min(nb - 1, int((r["t"] - t0) / span * nb))
                buckets.setdefault(b, []).append(v)
            pts = []
            for b in sorted(buckets):
                v = sum(buckets[b]) / len(buckets[b])
                pts += [left + (right - left) * (b + .5) / nb, bot - (bot - top) * (v - lo) / (hi - lo)]
            if len(pts) >= 4:
                if si == 0 and len(series) == 1:
                    base = bot if not zero else bot - (bot - top) * (max(lo, 0) - lo) / (hi - lo)
                    c.create_polygon([pts[0], base] * 3 + pts + [pts[-2], base] * 3, fill=blend(col, CARD, .88),
                                     outline="", smooth=True)
                c.create_line(pts, fill=col, width=2, smooth=True)
                c.create_oval(pts[-2] - 4, pts[-1] - 4, pts[-2] + 4, pts[-1] + 4, fill=col, outline=CARD, width=2)

    # ================================================================== AYARLAR
    def _page_settings(self, p):
        p.columnconfigure(0, weight=1)
        p.columnconfigure(1, weight=1)
        p.rowconfigure(0, weight=0, minsize=84)
        p.rowconfigure(1, weight=13)
        p.rowconfigure(2, weight=9)
        self._add("settings", Card(p, self._r_set_header), row=0, column=0, columnspan=2,
                  padx=7, pady=7, sticky="nsew")
        groups = [("Gerilim koruma", "V", BLUE), ("Akım ve süreler", ("A", "s", "µs"), AMBER),
                  ("Sıcaklık koruma", "°C", RED), ("Genel", ("", "Ah"), ACCENT)]
        for i, (title, units, col) in enumerate(groups):
            self._add("settings", Card(p, lambda c, w, h, t=title, u=units, k=col: self._r_set_group(c, w, h, t, u, k)),
                      row=1 + i // 2, column=i % 2, padx=7, pady=7, sticky="nsew")

    def _r_set_header(self, c, w, h):
        locked = not self.settings_unlocked
        c.create_text(24, h / 2 - 11, text="Koruma parametreleri", anchor="w", fill=TEXT, font=F(13, True))
        warns = jk.settings_sanity(self.settings.get("_raw", {})) if self.settings else []
        if warns:
            sub, scol = "⚠ " + warns[0] + (f"  (+{len(warns) - 1})" if len(warns) > 1 else ""), AMBER
        elif locked:
            sub, scol = "Değiştirmek için sağdaki kilidi açın", MUTED
        else:
            sub, scol = "Bir satıra tıklayıp yeni değeri girin · değişiklik BMS'e hemen yazılır", ACCENT
        c.create_text(24, h / 2 + 13, text=sub, anchor="w", fill=scol, font=F(9))
        # kilit anahtarı
        x = w - 24
        draw_switch(c, x - 46, h / 2 - 12, not locked, "lock", color=AMBER)
        c.tag_bind("lock", "<Button-1>", lambda e: self.toggle_settings_lock())
        t = c.create_text(x - 58, h / 2, text="Düzenleme açık" if not locked else "🔒 Kilitli", anchor="e",
                          fill=AMBER if not locked else MUTED, font=F(10, True))
        x = c.bbox(t)[0] - 22
        # yenile düğmesi
        rrect(c, x - 96, h / 2 - 17, x, h / 2 + 17, 17, fill=CARD2, outline=BORDER, tags=("rf", "rfbg"))
        c.create_text(x - 48, h / 2, text="↻  Yenile", fill=TEXT, font=F(10, True), tags="rf")
        c.tag_bind("rf", "<Button-1>", lambda e: self.refresh_settings())
        c.tag_bind("rf", "<Enter>", lambda e: (c.itemconfig("rfbg", fill=CARD3), c.configure(cursor="hand2")))
        c.tag_bind("rf", "<Leave>", lambda e: (c.itemconfig("rfbg", fill=CARD2), c.configure(cursor="")))

    def _r_set_group(self, c, w, h, title, units, col):
        units = (units,) if isinstance(units, str) else units
        c.create_oval(22, 24, 32, 34, fill=col, outline="")
        c.create_text(42, 29, text=title, anchor="w", fill=TEXT, font=F(13, True))
        if not self.settings:
            self._no_data(c, w, h)
            return
        raw = self.settings.get("_raw", {})
        rows = [f for f in jk.SETTING_FIELDS if f[4] in units]
        y = 66
        rh = min(30, max(22, (h - 80) / max(1, len(rows))))
        editable = self.settings_unlocked
        for i, (off, name, typ, scale, unit, lo, hi) in enumerate(rows):
            if y > h - 14:
                break
            tag = f"p{off}"
            base = CARD2 if i % 2 == 0 else CARD
            rrect(c, 14, y - rh / 2, w - 14, y + rh / 2, 8, fill=base, outline="", tags=(tag, tag + "bg"))
            c.create_text(26, y, text=name, anchor="w", fill=MUTED, font=F(10), tags=tag)
            if off in self.pending:
                vtxt, vc = "gönderiliyor…", AMBER
            else:
                v = jk.fmt_setting(off, raw.get(off, 0))
                vtxt = f"{v} {unit}".strip()
                vc = ACCENT if v == "Açık" else (RED if v == "Kapalı" else TEXT)
            right = w - 26 - (22 if editable else 0)
            c.create_text(right, y, text=vtxt, anchor="e", fill=vc, font=F(10, True), tags=tag)
            if editable:
                c.create_text(w - 26, y, text="⇄" if typ == "bool" else "✎", anchor="e", fill=DIM,
                              font=F(10, True), tags=(tag, tag + "ic"))
                c.tag_bind(tag, "<Button-1>", lambda e, o=off: self.edit_param(o))
                c.tag_bind(tag, "<Enter>", lambda e, t=tag: (c.itemconfig(t + "bg", fill=CARD3),
                                                             c.itemconfig(t + "ic", fill=AMBER),
                                                             c.configure(cursor="hand2")))
                c.tag_bind(tag, "<Leave>", lambda e, t=tag, b=base: (c.itemconfig(t + "bg", fill=b),
                                                                     c.itemconfig(t + "ic", fill=DIM),
                                                                     c.configure(cursor="")))
            y += rh

    # ------------------------------------------------------------------ ayar düzenleme
    def refresh_settings(self):
        if self.connected:
            self.worker.submit(self.worker.write(jk.build_command(jk.CMD_SETTINGS_AND_DATA)))
            self.toast("Ayarlar yeniden okunuyor…", MUTED)
        elif not self.demo_on:
            self.toast("Önce BMS'e bağlanın.", AMBER)

    def toggle_settings_lock(self):
        if self.settings_unlocked:
            self.settings_unlocked = False
            self.refresh_page()
            return
        if not (self.connected or self.demo_on) or not self.settings:
            self.toast("Önce BMS'e bağlanın ve ayarların okunmasını bekleyin.", AMBER)
            return
        pwd = self.info.get("setting_password", "")
        if self.info.get("password_protected") and pwd:
            self._ask_password(pwd)
        else:
            self._unlock()

    def _unlock(self):
        self.settings_unlocked = True
        self.refresh_page()
        self.toast("Düzenleme açıldı – değişiklikler BMS'e anında yazılır", AMBER)

    def _ask_password(self, pwd):
        win, body, foot = self._dialog("Ayar şifresi", 400, 270)
        tk.Label(body, text="Bu BMS'te ayar şifresi tanımlı.", bg=CARD, fg=MUTED, font=F(10)).pack(anchor="w")
        var = tk.StringVar()
        box, ent = self._entry(body, var, show="●")
        ent.focus_set()
        err = tk.Label(body, text="", bg=CARD, fg=RED, font=F(9))
        err.pack(anchor="w", pady=(6, 0))

        def ok(*_):
            if var.get() == pwd:
                win.destroy()
                self._unlock()
            else:
                err.config(text="Şifre yanlış")
                box.config(highlightbackground=RED)
        Button(foot, "Aç", ok, "primary", width=110, height=40, outer=CARD).pack(side="right")
        Button(foot, "Vazgeç", win.destroy, "ghost", width=110, height=40, outer=CARD).pack(side="right", padx=10)
        ent.bind("<Return>", ok)

    def _dialog(self, title, w, h):
        win = tk.Toplevel(self, bg=CARD)
        win.title(title)
        win.geometry(f"{w}x{h}+{self.winfo_rootx() + (self.winfo_width() - w) // 2}+{self.winfo_rooty() + 150}")
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        win.bind("<Escape>", lambda e: win.destroy())
        tk.Label(win, text=title, bg=CARD, fg=TEXT, font=F(16, True)).pack(anchor="w", padx=26, pady=(22, 4))
        body = tk.Frame(win, bg=CARD)
        body.pack(fill="both", expand=True, padx=26)
        foot = tk.Frame(win, bg=CARD)
        foot.pack(side="bottom", fill="x", padx=26, pady=20)
        return win, body, foot

    def _entry(self, parent, var, show=None, unit=None):
        box = tk.Frame(parent, bg=CARD2, highlightthickness=2, highlightbackground=BORDER, highlightcolor=ACCENT)
        box.pack(fill="x", pady=(14, 4))
        ent = tk.Entry(box, textvariable=var, bg=CARD2, fg=TEXT, insertbackground=ACCENT, relief="flat",
                       font=F(15, True), highlightthickness=0, show=show or "")
        ent.pack(side="left", fill="x", expand=True, padx=14, pady=10)
        if unit:
            tk.Label(box, text=unit, bg=CARD2, fg=MUTED, font=F(12)).pack(side="right", padx=14)
        return box, ent

    def edit_param(self, off):
        f = jk.FIELD_BY_OFF[off]
        _, name, typ, scale, unit, lo, hi = f
        if typ == "bool":
            self.toggle({112: "charge", 116: "discharge", 120: "balance"}[off])
            return
        if off in self.pending:
            return
        cur_raw = self.settings["_raw"].get(off, 0)
        win, body, foot = self._dialog(name, 470, 380)
        cur_txt = f"{jk.fmt_setting(off, cur_raw)} {unit}".strip()
        tk.Label(body, text=f"Şu anki değer:  {cur_txt}", bg=CARD, fg=MUTED, font=F(10)).pack(anchor="w")
        var = tk.StringVar(value=jk.fmt_setting(off, cur_raw))
        box, ent = self._entry(body, var, unit=unit or None)
        ent.focus_set()
        ent.select_range(0, "end")
        rng = f"İzin verilen: {jk.fmt_setting(off, lo)} – {jk.fmt_setting(off, hi)} {unit}".strip()
        rng += f"   ·   kayıt 0x{jk.setting_register(off):02X}"
        msg = tk.Label(body, text=rng, bg=CARD, fg=MUTED, font=F(9), anchor="w")
        msg.pack(fill="x")
        warn = tk.Label(body, text="", bg=CARD, fg=AMBER, font=F(9), anchor="w", justify="left", wraplength=410)
        warn.pack(fill="x", pady=(10, 0))
        if off == 108:
            tk.Label(body, text="⚠ Hücre sayısı gerçek seri hücre sayısıyla aynı olmalı.", bg=CARD, fg=RED,
                     font=F(9, True)).pack(anchor="w", pady=(4, 0))
        save = Button(foot, "BMS'e yaz", None, "primary", width=130, height=40, outer=CARD)
        save.pack(side="right")
        Button(foot, "Vazgeç", win.destroy, "ghost", width=110, height=40, outer=CARD).pack(side="right", padx=10)
        state = {"raw": None}

        def validate(*_):
            txt = var.get().strip().replace(",", ".")
            try:
                val = float(txt)
            except ValueError:
                msg.config(text="Sayı girin", fg=RED)
                box.config(highlightbackground=RED)
                save.config_btn(enabled=False)
                return
            raw = int(round(val / scale)) if scale != 1 else int(round(val))
            if not lo <= raw <= hi:
                msg.config(text=rng.split("   ·")[0] + "  ← aralık dışında", fg=RED)
                box.config(highlightbackground=RED)
                save.config_btn(enabled=False)
                return
            msg.config(text=rng, fg=MUTED)
            box.config(highlightbackground=BORDER)
            state["raw"] = raw
            new_raw = {**self.settings["_raw"], off: raw}
            before = set(jk.settings_sanity(self.settings["_raw"]))
            new_w = [x for x in jk.settings_sanity(new_raw) if x not in before]
            warn.config(text="\n".join("⚠ " + x for x in new_w))
            save.config_btn(enabled=raw != cur_raw)

        def commit(*_):
            if not save.enabled or state["raw"] is None:
                return
            raw = state["raw"]
            win.destroy()
            self.write_param(off, raw)
        save.command = commit
        var.trace_add("write", validate)
        validate()
        ent.bind("<Return>", commit)

    def write_param(self, off, raw):
        name = jk.FIELD_BY_OFF[off][1]
        if self.demo_on:
            self._apply_local(off, raw)
            self.toast(f"Demo: {name} = {jk.fmt_setting(off, raw)}", PURPLE)
            return
        try:
            frame = jk.build_setting_write(off, raw)
        except ValueError as e:
            self.toast(str(e))
            return
        self.pending[off] = (raw, time.time())
        self.refresh_page()

        async def go():
            await self.worker.write(frame)
            await asyncio.sleep(0.6)
            await self.worker.write(jk.build_command(jk.CMD_SETTINGS_AND_DATA))
        self.worker.submit(go())
        self.after(5000, lambda: self._pending_timeout(off))

    def _pending_timeout(self, off):
        if off in self.pending and time.time() - self.pending[off][1] >= 4.9:
            del self.pending[off]
            cur = jk.fmt_setting(off, self.settings.get("_raw", {}).get(off, 0))
            self.toast(f"{jk.FIELD_BY_OFF[off][1]}: BMS değeri kabul etmedi (şu an {cur})")
            self.refresh_page()

    def _apply_local(self, off, raw):
        s = self.settings
        s["_raw"][off] = raw
        f = jk.FIELD_BY_OFF[off]
        s[f[1]] = (jk.fmt_setting(off, raw), f[4])
        key = {112: "_charge_on", 116: "_discharge_on", 120: "_balance_on"}.get(off)
        if key:
            s[key] = bool(raw)
        self.refresh_page()

    # ================================================================== CİHAZ
    def _page_device(self, p):
        p.columnconfigure(0, weight=1)
        p.rowconfigure(0, weight=1)
        self._add("device", Card(p, self._r_device), row=0, column=0, sticky="nsew", padx=7, pady=7)

    def _r_device(self, c, w, h):
        i = self.info
        if not i:
            self._no_data(c, w, h)
            return
        rrect(c, 28, 28, 108, 108, 22, fill=blend(ACCENT, CARD, .8), outline="")
        rrect(c, 52, 44, 84, 96, 6, fill="", outline=ACCENT, width=3)
        c.create_rectangle(60, 38, 76, 44, fill=ACCENT, outline="")
        c.create_text(128, 50, text=i.get("name") or i.get("model"), anchor="w", fill=TEXT, font=F(20, True))
        c.create_text(128, 82, text=i.get("model", ""), anchor="w", fill=MUTED, font=F(11))
        # "Adı değiştir" düğmesi
        bx2, by = w - 28, 50
        bx1 = bx2 - 150
        rrect(c, bx1, by - 19, bx2, by + 19, 19, fill=CARD2, outline=BORDER, tags=("rn", "rnbg"))
        c.create_text((bx1 + bx2) / 2, by, text="✎  Adı değiştir", fill=TEXT, font=F(10, True), tags="rn")
        c.tag_bind("rn", "<Button-1>", lambda e: self.open_rename())
        c.tag_bind("rn", "<Enter>", lambda e: (c.itemconfig("rnbg", fill=CARD3), c.configure(cursor="hand2")))
        c.tag_bind("rn", "<Leave>", lambda e: (c.itemconfig("rnbg", fill=CARD2), c.configure(cursor="")))
        rows = [("Model", i["model"]), ("Cihaz adı", i["name"]), ("Donanım sürümü", i["hw"]),
                ("Yazılım sürümü", i["sw"]), ("Seri numarası", i["serial"]), ("Üretim tarihi", i["mfg_date"]),
                ("Çalışma süresi", jk.secs_to_text(i["uptime_s"])), ("Açılış sayısı", str(i["power_on_count"])),
                ("Protokol", str(i["protocol"]))]
        cols = 3 if w > 900 else 2
        tw = (w - 56 - (cols - 1) * 14) / cols
        for k, (a, b) in enumerate(rows):
            x = 28 + (k % cols) * (tw + 14)
            y = 136 + (k // cols) * 84
            rrect(c, x, y, x + tw, y + 70, 14, fill=CARD2, outline="")
            c.create_text(x + 18, y + 22, text=a, anchor="w", fill=MUTED, font=F(9))
            c.create_text(x + 18, y + 46, text=b or "—", anchor="w", fill=TEXT, font=F(13, True))

    # ================================================================== AD DEĞİŞTİR
    def open_rename(self):
        if not (self.connected or self.demo_on) or not self.info:
            self.toast("Ad değiştirmek için önce BMS'e bağlanın.", AMBER)
            return
        if getattr(self, "rename_win", None) and self.rename_win.winfo_exists():
            self.rename_win.lift()
            return
        win = tk.Toplevel(self, bg=CARD)
        win.title("Cihaz adını değiştir")
        win.geometry(f"440x330+{self.winfo_rootx() + 420}+{self.winfo_rooty() + 180}")
        win.transient(self)
        win.resizable(False, False)
        win.grab_set()
        self.rename_win = win
        cur = self.info.get("name", "")
        tk.Label(win, text="Cihaz adını değiştir", bg=CARD, fg=TEXT, font=F(17, True)).pack(anchor="w", padx=26, pady=(24, 2))
        tk.Label(win, text=f"Şu anki ad:  {cur or '—'}", bg=CARD, fg=MUTED, font=F(10)).pack(anchor="w", padx=26)
        var = tk.StringVar(value=cur)
        box = tk.Frame(win, bg=CARD2, highlightthickness=2, highlightbackground=BORDER, highlightcolor=ACCENT)
        box.pack(fill="x", padx=26, pady=(20, 6))
        ent = tk.Entry(box, textvariable=var, bg=CARD2, fg=TEXT, insertbackground=ACCENT, relief="flat",
                       font=F(15, True), highlightthickness=0)
        ent.pack(fill="x", padx=14, pady=10)
        ent.focus_set()
        ent.select_range(0, "end")
        info = tk.Label(win, bg=CARD, fg=MUTED, font=F(9), anchor="w", justify="left")
        info.pack(fill="x", padx=26)
        note = ("BMS yeni adı kaydeder; Bluetooth listesinde yeni ad bağlantı\nkesilip yeniden tarandığında görünür.")
        if not self.info.get("can_rename", True):
            note = "⚠ Bu BMS ad değiştirmeyi desteklemiyor olabilir (cihaz bayrağı kapalı)."
        tk.Label(win, text=note, bg=CARD, fg=AMBER if "⚠" in note else DIM, font=F(9), justify="left").pack(anchor="w", padx=26, pady=(10, 0))
        foot = tk.Frame(win, bg=CARD)
        foot.pack(side="bottom", fill="x", padx=26, pady=22)
        save = Button(foot, "Kaydet", lambda: self._do_rename(var.get()), "primary", width=130, height=40, outer=CARD)
        save.pack(side="right")
        Button(foot, "Vazgeç", win.destroy, "ghost", width=110, height=40, outer=CARD).pack(side="right", padx=10)

        def validate(*_):
            name = var.get()
            try:
                jk.build_rename(name)
                ok, msg = True, f"{len(name.strip())}/{jk.NAME_MAX_LEN} karakter · harf, rakam, - _ . boşluk"
            except ValueError as e:
                ok, msg = False, str(e)
            if ok and name.strip() == cur:
                ok, msg = False, "Yeni bir ad yazın"
            info.config(text=msg, fg=MUTED if ok else RED)
            box.config(highlightbackground=BORDER if ok else RED)
            save.config_btn(enabled=ok)
        var.trace_add("write", validate)
        validate()
        ent.bind("<Return>", lambda e: save.enabled and self._do_rename(var.get()))
        win.bind("<Escape>", lambda e: win.destroy())

    def _do_rename(self, name):
        name = name.strip()
        if self.rename_win and self.rename_win.winfo_exists():
            self.rename_win.destroy()
        if self.demo_on:
            self.info = dict(self.info, name=name)
            self._ev_info(self.info)
            self.toast(f"Demo: ad '{name}' olarak değiştirildi", PURPLE)
            return
        self.worker.submit(self.worker.rename(name))
        self.toast(f"Yeni ad gönderildi: {name}", ACCENT)

    # ================================================================== KONSOL
    def _page_console(self, p):
        bar = tk.Frame(p, bg=BG)
        bar.pack(fill="x", padx=7, pady=(7, 10))
        self.btn_pause = Button(bar, "Durdur", self._toggle_pause, "ghost", width=100, height=34, outer=BG)
        self.btn_pause.pack(side="left")
        Button(bar, "Temizle", lambda: self.raw_txt.delete("1.0", "end"), "ghost", width=100, height=34,
               outer=BG).pack(side="left", padx=8)
        Button(bar, "Gönder", self.on_send_cmd, "primary", width=100, height=34, outer=BG).pack(side="right")
        self.cmd_var = tk.StringVar(value="97")
        ent = tk.Entry(bar, textvariable=self.cmd_var, width=8, bg=CARD2, fg=TEXT, insertbackground=TEXT,
                       relief="flat", font=M(11), justify="center", highlightthickness=1,
                       highlightbackground=BORDER, highlightcolor=ACCENT)
        ent.pack(side="right", padx=8, ipady=6)
        tk.Label(bar, text="Komut (hex)", bg=BG, fg=MUTED, font=F(10)).pack(side="right")
        wrap = tk.Frame(p, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        wrap.pack(fill="both", expand=True, padx=7, pady=(0, 7))
        self.raw_txt = tk.Text(wrap, bg=CARD, fg=MUTED, relief="flat", font=M(9), highlightthickness=0,
                               padx=14, pady=12, insertbackground=TEXT, selectbackground=CARD3)
        self.raw_txt.pack(fill="both", expand=True)
        self.raw_txt.tag_config("tx", foreground=AMBER)
        self.raw_txt.tag_config("rx", foreground=ACCENT)
        self.raw_txt.tag_config("ts", foreground=DIM)

    def _toggle_pause(self):
        self.raw_paused = not self.raw_paused
        self.btn_pause.config_btn(text="Devam" if self.raw_paused else "Durdur")

    # ================================================================== tarama penceresi
    def open_scan(self):
        if not self.worker:
            self.toast("BLE için önce 'pip install bleak' komutunu çalıştırın.", AMBER)
            return
        if self.scan_win and self.scan_win.winfo_exists():
            self.scan_win.lift()
            return
        win = tk.Toplevel(self, bg=CARD)
        win.title("Cihaz bul")
        win.geometry(f"480x560+{self.winfo_rootx() + 260}+{self.winfo_rooty() + 90}")
        win.transient(self)
        win.resizable(False, True)
        self.scan_win = win
        hdr = tk.Canvas(win, bg=CARD, height=84, highlightthickness=0)
        hdr.pack(fill="x", padx=22, pady=(18, 0))
        self.scan_hdr = hdr
        self.scan_list = tk.Canvas(win, bg=CARD, highlightthickness=0)
        self.scan_list.pack(fill="both", expand=True, padx=22, pady=8)
        self.scan_list.bind("<Configure>", lambda e: self._draw_scan_list())
        self.scan_list.bind("<MouseWheel>", lambda e: self.scan_list.yview_scroll(-e.delta // 120, "units"))
        foot = tk.Frame(win, bg=CARD)
        foot.pack(fill="x", padx=22, pady=(0, 20))
        self.btn_rescan = Button(foot, "Yeniden tara", self._start_scan, "ghost", width=140, height=38, outer=CARD)
        self.btn_rescan.pack(side="left")
        Button(foot, "Kapat", win.destroy, "ghost", width=100, height=38, outer=CARD).pack(side="right")
        self.devices = []
        self._start_scan()

    def _start_scan(self):
        self.scanning = True
        self.scan_anim = 0
        self.btn_rescan.config_btn(enabled=False)
        self._draw_scan_list()
        self._animate_scan()
        self.worker.submit(self.worker.scan(6.0))

    def _animate_scan(self):
        if not (self.scan_win and self.scan_win.winfo_exists()):
            return
        c = self.scan_hdr
        c.delete("all")
        c.create_text(0, 22, text="Yakındaki cihazlar", anchor="w", fill=TEXT, font=F(17, True))
        if self.scanning:
            dots = "●" * (self.scan_anim % 4) + "○" * (3 - self.scan_anim % 4)
            c.create_text(0, 56, text=f"Bluetooth taranıyor  {dots}", anchor="w", fill=ACCENT, font=F(10))
            self.scan_anim += 1
            self.after(300, self._animate_scan)
        else:
            c.create_text(0, 56, text=f"{len(self.devices)} cihaz bulundu · ★ işaretliler JK BMS",
                          anchor="w", fill=MUTED, font=F(10))

    def _draw_scan_list(self):
        c = self.scan_list
        c.delete("all")
        w = c.winfo_width()
        if not self.devices:
            c.create_text(w / 2, 80, text="Taranıyor…" if getattr(self, "scanning", False) else "Cihaz bulunamadı",
                          fill=DIM, font=F(11))
            return
        y = 0
        for i, (is_jk, rssi, name, addr) in enumerate(self.devices):
            tag = f"dev{i}"
            rrect(c, 0, y, w - 2, y + 64, 14, fill=CARD2, outline=ACCENT if is_jk else "", tags=(tag, "bg" + tag))
            c.create_text(18, y + 22, text=("★ " if is_jk else "") + name, anchor="w",
                          fill=TEXT if is_jk else MUTED, font=F(11, True), tags=tag)
            c.create_text(18, y + 44, text=addr, anchor="w", fill=DIM, font=M(9), tags=tag)
            # sinyal çubukları
            lvl = 4 if rssi > -60 else 3 if rssi > -70 else 2 if rssi > -80 else 1
            for b in range(4):
                bx = w - 70 + b * 9
                bh = 6 + b * 5
                c.create_rectangle(bx, y + 42 - bh, bx + 5, y + 42, outline="",
                                   fill=ACCENT if b < lvl else CARD3, tags=tag)
            c.create_text(w - 18, y + 52, text=f"{rssi} dBm", anchor="e", fill=DIM, font=F(8), tags=tag)
            c.tag_bind(tag, "<Button-1>", lambda e, a=addr: self._pick_device(a))
            c.tag_bind(tag, "<Enter>", lambda e, t=tag: (c.itemconfig("bg" + t, fill=CARD3), c.configure(cursor="hand2")))
            c.tag_bind(tag, "<Leave>", lambda e, t=tag: (c.itemconfig("bg" + t, fill=CARD2), c.configure(cursor="")))
            y += 74
        c.configure(scrollregion=(0, 0, w, y))

    def _pick_device(self, addr):
        if self.scan_win:
            self.scan_win.destroy()
        self.stop_demo()
        self.btn_connect.config_btn(text="Bağlanıyor…", enabled=False)
        self.worker.submit(self.worker.connect(addr))

    # ================================================================== eylemler
    def on_connect_btn(self):
        if self.connected:
            self.worker.submit(self.worker.disconnect())
        else:
            self.open_scan()

    def on_demo(self):
        if self.demo_on:
            self.stop_demo()
            return
        if self.connected:
            self.toast("Demo için önce bağlantıyı kesin.", AMBER)
            return
        self.demo_on = True
        self.hist.clear()
        self.btn_demo.config_btn(text="Demoyu durdur", kind="danger")
        self.set_status("Sahte veri gösteriliyor")
        self._demo_t0 = time.time()
        self._demo_first = True
        self._demo_tick()

    def stop_demo(self):
        if self.demo_on:
            self.demo_on = False
            self.btn_demo.config_btn(text="Demo modu", kind="ghost")
            self.settings_unlocked = False
            self.set_status("Demo durduruldu")
            self._draw_header()

    def _demo_tick(self):
        if not self.demo_on:
            return
        info, sett, cells = jk.make_demo_frames(time.time() - self._demo_t0)
        frames = ([info, sett] if self._demo_first else []) + [cells]
        self._demo_first = False
        for fr in frames:
            self.events.put(("raw", "RX", fr))
            t = fr[4]
            if t == 3:
                self.events.put(("info", jk.parse_device_info(fr)))
            elif t == 1:
                self.events.put(("settings", jk.parse_settings(fr)))
            else:
                self.events.put(("cells", jk.parse_cell_info(fr)))
        self.after(1000, self._demo_tick)

    def on_send_cmd(self):
        if not self.connected:
            self.toast("Komut göndermek için BMS'e bağlı olun.", AMBER)
            return
        try:
            cmd = int(self.cmd_var.get().strip(), 16)
        except ValueError:
            self.toast("Geçersiz hex komut")
            return
        self.worker.submit(self.worker.write(jk.build_command(cmd)))

    def toggle(self, which):
        if self.demo_on and self.settings:
            off = {"charge": 112, "discharge": 116, "balance": 120}[which]
            self._apply_local(off, 0 if self.settings["_raw"].get(off) else 1)
            return
        if not self.connected or not self.settings:
            self.toast("Önce BMS'e bağlanın.", AMBER)
            return
        key = {"charge": "_charge_on", "discharge": "_discharge_on", "balance": "_balance_on"}[which]
        reg = {"charge": jk.REG_CHARGE_SWITCH, "discharge": jk.REG_DISCHARGE_SWITCH,
               "balance": jk.REG_BALANCE_SWITCH}[which]
        name = {"charge": "Şarj", "discharge": "Deşarj", "balance": "Dengeleyici"}[which]
        new = 0 if self.settings.get(key) else 1
        if not messagebox.askyesno(APP_TITLE, f"{name} anahtarı {'AÇILSIN' if new else 'KAPATILSIN'} mı?"):
            return

        async def go():
            await self.worker.write(jk.build_command(reg, new, 4))
            await asyncio.sleep(0.5)
            await self.worker.write(jk.build_command(jk.CMD_SETTINGS_AND_DATA))
        self.worker.submit(go())

    def on_csv(self):
        if self.csv_writer is None:
            path = filedialog.asksaveasfilename(
                defaultextension=".csv", filetypes=[("CSV", "*.csv")],
                initialfile=f"mgmbms_{dt.datetime.now():%Y%m%d_%H%M%S}.csv")
            if not path:
                return
            self.csv_file = open(path, "w", newline="", encoding="utf-8-sig")
            self.csv_writer = csv.writer(self.csv_file, delimiter=";")
            self.csv_writer.writerow(["zaman", "gerilim_V", "akim_A", "guc_W", "SOC_%", "kalan_Ah",
                                      "fark_V", "MOS_C", "T1_C", "T2_C"] + [f"hucre{i}" for i in range(1, 33)])
            self.toast(f"CSV kaydı başladı: {path}", ACCENT)
        else:
            self.csv_file.close()
            self.csv_file = self.csv_writer = None
            self.toast("CSV kaydı durduruldu", MUTED)
        self._draw_csv()

    # ================================================================== olay kuyruğu
    def _poll(self):
        try:
            while True:
                ev = self.events.get_nowait()
                getattr(self, "_ev_" + ev[0])(*ev[1:])
        except queue.Empty:
            pass
        self.after(80, self._poll)

    def _tick(self):
        self._draw_header()
        self.after(1000, self._tick)

    def _ev_logframe(self, *_):     # arıza kaydı yalnızca yeni arayüzde
        pass

    def _ev_status(self, s):
        self.set_status(s)

    def _ev_error(self, s):
        self.set_status(s)
        self.toast(s)
        if not self.connected:
            self.btn_connect.config_btn(text="Cihaz Bul", kind="primary", enabled=True)
        if self.scan_win and self.scan_win.winfo_exists():
            self.scanning = False
            self.btn_rescan.config_btn(enabled=True)
            self._draw_scan_list()

    def _ev_scan(self, devs):
        self.devices = [d for d in devs if d[0]]   # yalnızca JK BMS
        self.scanning = False
        if self.scan_win and self.scan_win.winfo_exists():
            self.btn_rescan.config_btn(enabled=True)
            self._draw_scan_list()

    def _ev_connected(self, ok):
        self.connected = ok
        self.settings_unlocked = False
        self.pending.clear()
        if ok:
            self.hist.clear()
            self.btn_connect.config_btn(text="Bağlantıyı kes", kind="danger", enabled=True)
        else:
            self.btn_connect.config_btn(text="Cihaz Bul", kind="primary", enabled=True)
        self.conn_card.redraw()
        self._draw_header()

    def _ev_raw(self, direction, data):
        if self.raw_paused:
            return
        t = self.raw_txt
        ts = dt.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        t.insert("end", ts + "  ", "ts")
        t.insert("end", f"{direction} ", direction.lower())
        t.insert("end", f"[{len(data)}]  {data.hex(' ').upper()}\n\n")
        if int(t.index("end-1c").split(".")[0]) > 600:
            t.delete("1.0", "150.0")
        t.see("end")

    def _ev_info(self, info):
        self.info = info
        self.title(f"{APP_TITLE} – {info['name'] or info['model']}")
        self.conn_card.redraw()
        self._draw_header()
        self.refresh_page()

    def _ev_settings(self, s):
        self.settings = s
        for off, (want, _) in list(self.pending.items()):
            got = s["_raw"].get(off)
            if got == want:     # eşleşmezse zaman aşımına kadar sonraki paketi bekle
                del self.pending[off]
                self.toast(f"✓ {jk.FIELD_BY_OFF[off][1]} = {jk.fmt_setting(off, got)} kaydedildi", ACCENT)
        self.refresh_page()

    def _ev_cells(self, d):
        self.d = d
        self.last_update = time.time()
        t = d["temps"]
        self.hist.append({"t": self.last_update, "voltage": d["voltage"], "current": d["current"],
                          "power": d["power"], "delta": d["delta_cell"] * 1000, "soc": d["soc"],
                          "mos": d["mos_temp"], "t1": t[0], "t2": t[1]})
        self.refresh_page()
        if self.csv_writer:
            self.csv_writer.writerow(
                [dt.datetime.now().isoformat(timespec="seconds"), f"{d['voltage']:.3f}", f"{d['current']:.3f}",
                 f"{d['power']:.1f}", d["soc"], f"{d['remain_ah']:.3f}", f"{d['delta_cell']:.3f}",
                 d["mos_temp"], t[0], t[1]] + [f"{c:.3f}" for c in d["cells"]])
            self.csv_file.flush()

    def destroy(self):
        if self.worker:
            try:
                self.worker.submit(self.worker.disconnect()).result(timeout=3)
            except Exception:
                pass
        if self.csv_file:
            self.csv_file.close()
        super().destroy()


if __name__ == "__main__":
    try:  # Windows'ta keskin yazı (yüksek DPI)
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    import lisans
    if lisans.tk_gate():
        App().mainloop()
