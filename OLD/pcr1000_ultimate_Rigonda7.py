import sys
import threading
import time
import json
import os
import csv
import math
import re
import queue
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import serial
import serial.tools.list_ports

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "pcr1000_profiles.json"

# ============================================================================
# ПАЛИТРЫ ТЕМ (Дневная и Ночная)
# ============================================================================
THEMES = {
    "night": {
        "bg": "#181916", "panel": "#1F201C", "wood_dark": "#2B160A",
        "glass_bg": "#0D0E0B", "glass_green": "#5EB063", "glass_text": "#D4B46A",
        "brass": "#B8963D", "brass_shadow": "#69531D", "needle": "#D62B2B",
        "p2k_ivory": "#FDFCFA", "p2k_shadow": "#A8A499", "magic_eye": "#24FF55",
        "magic_eye_bg": "#0A140B", "text": "#fffae0", "muted": "#a18262",
        "accent": "#d4af37", "accent_hover": "#f3e5ab", "danger": "#c0392b",
        "success": "#2ecc71", "entry_bg": "#1f110a", "border": "#5c3a21",
        "btn_bg": "#fffff0", "btn_hover": "#f5f5dc", "on": "#2ecc71", "off": "#555555",
    },
    "day": {
        "bg": "#E8DDBD", "panel": "#D8C9A5", "wood_dark": "#49301F",
        "glass_bg": "#F5F0E1", "glass_green": "#263B2C", "glass_text": "#263B2C",
        "brass": "#A47B3C", "brass_shadow": "#7A5A2A", "needle": "#8B0000",
        "p2k_ivory": "#FFF8E7", "p2k_shadow": "#C5B184", "magic_eye": "#1A8F1A",
        "magic_eye_bg": "#E0E8D0", "text": "#263B2C", "muted": "#5A4A3A",
        "accent": "#8B6914", "accent_hover": "#A67C00", "danger": "#A52A2A",
        "success": "#228B22", "entry_bg": "#F0E6D2", "border": "#8B7355",
        "btn_bg": "#F5F5DC", "btn_hover": "#E6DCC3", "on": "#228B22", "off": "#888888",
    }
}

MODE_CODES = {"LSB": 0, "USB": 1, "AM": 2, "CW": 3, "NFM": 5, "WFM": 6}
FILTER_CODES = {"2.8k": 0, "6k": 1, "15k": 2, "50k": 3, "230k": 4}
VFO_STEPS = {
    "10 Гц": 0.00001, "50 Гц": 0.00005, "100 Гц": 0.0001, "500 Гц": 0.0005,
    "1 кГц": 0.001, "10 кГц": 0.01, "25 кГц": 0.025, "100 кГц": 0.1, "1 МГц": 1.0
}
CTCSS_TONES = {
    "OFF": 0, "67.0": 1, "69.3": 2, "71.9": 3, "74.4": 4, "77.0": 5, "79.7": 6,
    "82.5": 7, "85.4": 8, "88.5": 9, "91.5": 10, "94.8": 11, "97.4": 12,
    "100.0": 13, "103.5": 14, "107.2": 15, "110.9": 16, "114.8": 17, "118.8": 18,
    "123.0": 19, "127.3": 20, "131.8": 21, "136.5": 22, "141.3": 23, "146.2": 24,
    "151.4": 25, "156.7": 26, "159.8": 27, "162.2": 28, "165.5": 29, "167.9": 30,
    "171.3": 31, "173.8": 32, "177.3": 33, "179.9": 34, "183.5": 35, "186.2": 36,
    "189.9": 37, "192.8": 38, "196.6": 39, "199.5": 40, "203.5": 41, "206.5": 42,
    "210.7": 43, "218.1": 44, "225.7": 45, "229.1": 46, "233.6": 47, "241.8": 48,
    "250.3": 49, "254.1": 50
}
DEFAULT_PROFILES = {
    "FM Radio": {"start": 87.5, "end": 108.0, "step": 100, "threshold": 0.3, "mode": "WFM", "filter": "230k"},
    "Air Band": {"start": 118.0, "end": 136.0, "step": 25, "threshold": 0.2, "mode": "AM", "filter": "6k"},
    "Amateur 2m": {"start": 144.0, "end": 148.0, "step": 12.5, "threshold": 0.15, "mode": "NFM", "filter": "15k"},
    "PMR/LPD": {"start": 433.0, "end": 434.8, "step": 12.5, "threshold": 0.15, "mode": "NFM", "filter": "15k"},
}

DIAL_PIXELS_PER_STEP = 3.0
DIAL_STEP_MHZ = 0.00005

SMETER_CALIBRATION = [
    (0, 0), (20, 1), (40, 2), (60, 3), (80, 4),
    (100, 5), (120, 6), (140, 7), (160, 8), (180, 9),
    (205, 20), (225, 40), (245, 60),
]

def calibrate_smeter(raw):
    raw = max(SMETER_CALIBRATION[0][0], min(SMETER_CALIBRATION[-1][0], raw))
    for i in range(len(SMETER_CALIBRATION) - 1):
        x1, y1 = SMETER_CALIBRATION[i]
        x2, y2 = SMETER_CALIBRATION[i + 1]
        if x1 <= raw <= x2:
            part = (raw - x1) / (x2 - x1)
            return y1 + part * (y2 - y1)
    return SMETER_CALIBRATION[-1][1]

# ============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================================
def add_tooltip(widget, message):
    tip = None
    def show(event):
        nonlocal tip
        tip = tk.Toplevel(widget)
        tip.wm_overrideredirect(True)
        tip.wm_geometry(f"+{event.x_root+15}+{event.y_root+10}")
        label = tk.Label(tip, text=message, bg="#E8DDBD", fg="#263B2C",
                         relief="solid", borderwidth=1, padx=6, pady=3, font=("Arial", 9))
        label.pack()
    def hide(event):
        nonlocal tip
        if tip:
            tip.destroy()
            tip = None
    widget.bind("<Enter>", show)
    widget.bind("<Leave>", hide)


# ============================================================================
# ЛАМПА 6Е5С
# ============================================================================
class MagicEyeMeter(tk.Canvas):
    def __init__(self, master, theme, width=280, height=240, **kwargs):
        super().__init__(master, width=width, height=height, highlightthickness=0,
                         bg=theme["panel"], **kwargs)
        self.theme = theme
        self.value = 0
        self.smooth_value = 0.0
        self.bind("<Configure>", lambda e: self.draw())
        self.draw()

    def update_theme(self, new_theme):
        self.theme = new_theme
        self.configure(bg=self.theme["panel"])
        self.draw()

    def set_value(self, value):
        self.value = max(0, min(255, value))
        self.smooth_value += (self.value - self.smooth_value) * 0.35
        self.draw()

    def draw(self):
        self.delete("all")
        w = self.winfo_width() or 280
        h = self.winfo_height() or 240
        if w < 50 or h < 50: return
        t = self.theme
        cx, cy = w // 2, h // 2
        r = min(w, h) // 2 - 30
        if r < 30: r = 30

        self.create_oval(cx - r - 15, cy - r - 15, cx + r + 15, cy + r + 15,
                         fill="#261A15", outline=t["accent"], width=3)
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=t["magic_eye_bg"], outline="")
        
        fraction = max(0.0, min(1.0, self.smooth_value / 255.0))
        # У 6Е5С с ростом сигнала тёмный сектор сужается, а зелёные
        # флуоресцирующие «крылья» сходятся навстречу друг другу.
        shadow_angle = max(1.0, 86.0 * ((1.0 - fraction) ** 0.82))

        # Мягкий ореол люминофора (имитация свечения стеклянной лампы).
        self.create_oval(cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5,
                         outline="#164D25" if fraction < 0.75 else "#1E7A32", width=5)
        self.create_arc(cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2,
                        start=90, extent=180, fill=t["magic_eye"], outline="")
        self.create_arc(cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2,
                        start=270, extent=180, fill=t["magic_eye"], outline="")
        self.create_arc(cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1,
                        start=90 - shadow_angle, extent=shadow_angle * 2,
                        fill=t["magic_eye_bg"], outline="")
        self.create_arc(cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1,
                        start=270 - shadow_angle, extent=shadow_angle * 2,
                        fill=t["magic_eye_bg"], outline="")
        
        inner_r = max(8, r // 3)
        self.create_oval(cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r,
                         fill="#261A15", outline=t["accent"], width=1)
        self.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=t["accent"], outline="")

        s_level = "S9+60" if self.smooth_value > 240 else "S9+40" if self.smooth_value > 200 else \
                  "S9+20" if self.smooth_value > 160 else "S9" if self.smooth_value > 120 else \
                  f"S{int(self.smooth_value / 15)}" if self.smooth_value > 15 else "S0"
        self.create_text(cx, h - 20, text=f"{s_level} ({int(self.smooth_value)})",
                         fill=t["text"], font=("Arial", 10, "bold"))


# ============================================================================
# S-МЕТР (Раздельная отрисовка + калибровка)
# ============================================================================
class ClassicSMeter(tk.Canvas):
    def __init__(self, master, theme, width=300, height=220, **kwargs):
        super().__init__(master, width=width, height=height, highlightthickness=0,
                         bg=theme["panel"], **kwargs)
        self.theme = theme
        self.value = 0
        self.smooth_value = 0.0
        self.needle_id = None
        self.needle_pivot_id = None
        self.bind("<Configure>", self.on_resize)
        self.draw_face()

    def update_theme(self, new_theme):
        self.theme = new_theme
        self.configure(bg=self.theme["panel"])
        self.draw_face()

    def on_resize(self, event=None):
        self.draw_face()

    def draw_face(self):
        self.delete("all")
        w = self.winfo_width() or 300
        h = self.winfo_height() or 220
        if w < 100 or h < 100: return
        t = self.theme
        cx, cy = w // 2, h - 15
        r = min(w // 2 - 20, h - 40)
        if r < 50: r = 50

        self.create_oval(cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8,
                         fill=t["wood_dark"], outline=t["accent"], width=3)
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#FFF8E1", outline="")
        self.create_rectangle(0, cy + 2, w, h + 10, fill=t["panel"], outline="")
        self.create_line(cx - r - 8, cy, cx + r + 8, cy, fill=t["accent"], width=2)

        labels = ["0", "1", "3", "5", "7", "9", "+20", "+40", "+60"]
        n = len(labels)
        for i, label in enumerate(labels):
            angle_deg = 180 - i * (180.0 / (n - 1))
            angle_rad = math.radians(angle_deg)
            cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
            
            self.create_line(cx + (r - 10) * cos_a, cy - (r - 10) * sin_a,
                             cx + (r - 18) * cos_a, cy - (r - 18) * sin_a, fill="#3E2723", width=2)
            self.create_text(cx + (r - 30) * cos_a, cy - (r - 30) * sin_a,
                             text=label, fill="#3E2723", font=("Arial", 9, "bold"))

        # Красная зона начинается с +20 dB над S9 и заканчивается на +60.
        # Она нанесена по дуге шкалы, чтобы сильный сигнал читался однозначно.
        red_points = []
        for i in range(41):
            db = 20.0 + i * (40.0 / 40.0)
            angle_rad = math.radians(180.0 - (db / 60.0) * 180.0)
            red_points.extend([cx + (r - 14) * math.cos(angle_rad),
                               cy - (r - 14) * math.sin(angle_rad)])
        if len(red_points) >= 4:
            self.create_line(red_points, fill="#C62828", width=7,
                             capstyle=tk.ROUND, smooth=True)
        
        self.create_arc(cx - r + 10, cy - r + 10, cx + r - 10, cy + r - 10,
                        start=160, extent=40, outline="#FFFFFF", width=2, style=tk.ARC)
        self.draw_needle()

    def draw_needle(self):
        w = self.winfo_width() or 300
        h = self.winfo_height() or 220
        if w < 100 or h < 100: return
        cx, cy = w // 2, h - 15
        r = min(w // 2 - 20, h - 40)
        if r < 50: r = 50

        if self.needle_id: self.delete(self.needle_id)
        if self.needle_pivot_id: self.delete(self.needle_pivot_id)

        calibrated = calibrate_smeter(self.smooth_value)
        angle_rad = math.radians(180 - (calibrated / 60.0) * 180)
        
        x_tip, y_tip = cx + (r - 15) * math.cos(angle_rad), cy - (r - 15) * math.sin(angle_rad)
        x_tail, y_tail = cx - (r // 4) * math.cos(angle_rad), cy + (r // 4) * math.sin(angle_rad)

        self.needle_id = self.create_line(x_tail, y_tail, x_tip, y_tip,
                                          fill=self.theme["needle"], width=3, capstyle=tk.ROUND)
        self.needle_pivot_id = self.create_oval(cx - 7, cy - 7, cx + 7, cy + 7,
                                                fill="#3E2723", outline=self.theme["accent"], width=1)

    def set_value(self, value):
        self.value = max(0, min(255, int(value)))
        self.smooth_value += (self.value - self.smooth_value) * 0.25
        self.draw_needle()


# ============================================================================
# ДЕРЕВЯННАЯ ПАНЕЛЬ
# ============================================================================
class PhotoRealWoodPanel(tk.Canvas):
    def __init__(self, master, theme, height=40, **kwargs):
        super().__init__(master, height=height, highlightthickness=0, bg=theme["wood_dark"], **kwargs)
        self.theme = theme
        self.h = height
        self.bind("<Configure>", self.draw)

    def update_theme(self, new_theme):
        self.theme = new_theme
        self.configure(bg=self.theme["wood_dark"])
        self.draw()

    def draw(self, event=None):
        self.delete("all")
        w = self.winfo_width() or 1100
        h = self.h
        for i in range(0, h, 2):
            f = math.sin(i / 8.0) * 0.3 + 0.5
            r, g, b = int(43 + f * 41), int(22 + f * 23), int(10 + f * 14)
            self.create_rectangle(0, i, w, i + 2, fill=f"#{r:02x}{g:02x}{b:02x}", outline="")
        self.create_line(0, 1, w, 1, fill="#FFFFFF", width=1, stipple="gray25")
        self.create_line(0, h - 1, w, h - 1, fill="#150B05", width=2)


# ============================================================================
# КЛАВИША П2К
# ============================================================================
class PhotoRealP2KButton(tk.Canvas):
    def __init__(self, master, theme, text, command, **kwargs):
        super().__init__(master, width=72, height=38, highlightthickness=0, bg=theme["panel"], **kwargs)
        self.theme = theme
        self.text = text
        self.command = command
        self.is_pressed = False
        self.bind("<Button-1>", self._click)
        self.draw()

    def update_theme(self, new_theme):
        self.theme = new_theme
        self.configure(bg=self.theme["panel"])
        self.draw()

    def _click(self, e=None):
        if self.command: self.command(self.text)

    def set_pressed(self, state):
        self.is_pressed = bool(state)
        self.draw()

    def draw(self):
        self.delete("all")
        t = self.theme
        if not self.is_pressed:
            self.create_rectangle(4, 4, 68, 34, fill=t["p2k_shadow"], outline="")
            self.create_rectangle(2, 2, 66, 32, fill=t["p2k_ivory"], outline="")
            self.create_line(3, 3, 65, 3, fill="#FFFFFF", width=2)
            self.create_text(36, 18, text=self.text, fill="#263B2C", font=("Arial", 10, "bold"))
        else:
            self.create_rectangle(2, 2, 68, 34, fill="#121310", outline="")
            self.create_rectangle(5, 5, 65, 31, fill=t["accent"], outline="")
            self.create_line(5, 5, 65, 5, fill="#6E6A61", width=2)
            self.create_text(36, 19, text=self.text, fill="#FFF4D5", font=("Arial", 10, "bold"))


# ============================================================================
# ВАЛКОДЕР
# ============================================================================
class RigondaVFO_Dial(tk.Canvas):
    def __init__(self, master, theme, command, width=120, height=120, **kwargs):
        super().__init__(master, width=width, height=height, highlightthickness=0, bg=theme["panel"], **kwargs)
        self.theme = theme
        self.command = command
        self.width, self.height = width, height
        self.angle = 0
        self.last_y = 0
        self.dragging = False
        self.accumulated_px = 0.0
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.draw()

    def update_theme(self, new_theme):
        self.theme = new_theme
        self.configure(bg=self.theme["panel"])
        self.draw()

    def draw(self):
        self.delete("all")
        cx, cy = self.width // 2, self.height // 2
        r = min(self.width, self.height) // 2 - 8
        self.create_oval(cx - r + 2, cy - r + 2, cx + r + 2, cy + r + 2, fill="#120a05", outline="")
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill="#fffff0", outline=self.theme["brass"], width=2)
        self.create_oval(cx - r + 15, cy - r + 15, cx + r - 15, cy + r - 15, fill=self.theme["brass"], outline=self.theme["brass_shadow"])
        self.create_oval(cx - r + 32, cy - r + 32, cx + r - 32, cy + r - 32, fill="#fffff0", outline="#120a05")
        for i in range(12):
            ang = math.radians(i * 30)
            self.create_line(cx + (r - 30) * math.cos(ang), cy + (r - 30) * math.sin(ang),
                             cx + (r - 16) * math.cos(ang), cy + (r - 16) * math.sin(ang),
                             fill=self.theme["brass_shadow"], width=1)
        angle_rad = math.radians(self.angle - 90)
        self.create_oval(cx + (r - 8) * math.cos(angle_rad) - 4, cy + (r - 8) * math.sin(angle_rad) - 4,
                         cx + (r - 8) * math.cos(angle_rad) + 4, cy + (r - 8) * math.sin(angle_rad) + 4,
                         fill="#b3392b", outline="")

    def on_press(self, event): self.dragging = True; self.last_y = event.y
    def on_drag(self, event):
        if not self.dragging: return
        dy = event.y - self.last_y
        self.last_y = event.y
        self.angle = (self.angle - dy * 0.5) % 360
        self.draw()
        self.accumulated_px += dy
        while abs(self.accumulated_px) >= DIAL_PIXELS_PER_STEP:
            self.command(1 if self.accumulated_px > 0 else -1)
            self.accumulated_px -= DIAL_PIXELS_PER_STEP * (1 if self.accumulated_px > 0 else -1)
    def on_release(self, event): self.dragging = False; self.accumulated_px = 0.0


# ============================================================================
# ШКАЛА С ГОРОДАМИ
# ============================================================================
class PhotoRealDialDashboard(tk.Canvas):
    def __init__(self, master, theme, **kwargs):
        super().__init__(master, height=260, highlightthickness=0, bg=theme["glass_bg"], **kwargs)
        self.theme = theme
        self.current_freq = 99.6
        self.bind("<Configure>", self.draw)

    def update_theme(self, new_theme):
        self.theme = new_theme
        self.configure(bg=self.theme["glass_bg"])
        self.draw()

    def set_frequency(self, freq):
        self.current_freq = freq
        self.draw()

    def _band_for(self, f):
        if 0.5 <= f < 1.6: return 0.5, 1.6, True
        if 1.6 <= f < 3.0: return 1.6, 3.0, True
        if 3.0 <= f < 30.0: return 3.0, 30.0, True
        if 65.0 <= f < 74.0: return 65.0, 74.0, False
        if 87.5 <= f <= 108.0: return 87.5, 108.0, False
        return 0.5, 1300.0, True

    def get_active_band(self, freq):
        if 0.5 <= freq < 1.6: return "ДВ"
        if 1.6 <= freq < 3.0: return "КВI"
        if 3.0 <= freq < 30.0: return "КВII"
        if 65.0 <= freq < 74.0: return "УКВ"
        if 87.5 <= freq <= 108.0: return "УКВ"
        return "КВII"

    def draw(self, event=None):
        self.delete("all")
        w = self.winfo_width() or 1000
        h = 260
        t = self.theme

        # Имитация внутренней ламповой подсветки шкалы: тёплая янтарная
        # подложка и несколько мягких световых слоёв. Это визуальный эффект,
        # он не зависит от уровня сигнала и не меняет реальные показания.
        backlight = "#21190D" if self.theme is THEMES["night"] else "#F2E4B8"
        glow = "#5A3B12" if self.theme is THEMES["night"] else "#D8B96A"
        self.create_rectangle(0, 0, w, h, fill=backlight, outline="")
        for inset, stipple in ((5, "gray50"), (12, "gray25"), (22, "gray12")):
            self.create_rectangle(inset, inset, w - inset, h - inset,
                                  fill=glow, outline="", stipple=stipple)
        self.create_line(12, 12, w - 12, 12, fill="#F4D58A", width=2)
        self.create_line(12, h - 12, w - 12, h - 12, fill=t["brass_shadow"], width=2)
        self.create_rectangle(0, 0, w, h, outline=t["brass"], width=4)
        for (x, y) in [(8, 8), (w - 8, 8), (8, h - 8), (w - 8, h - 8)]:
            self.create_oval(x - 3, y - 3, x + 3, y + 3, fill=t["brass_shadow"], outline=t["brass"])
            
        font_size = 26 if w > 800 else 18
        self.create_text(w // 2, 35, text="Ригонда", fill=t["brass"], font=("Georgia", font_size, "bold", "italic"))
        
        bands_y = {"КВI": 75, "КВII": 105, "ДВ": 135, "СВ": 165, "УКВ": 205}
        for b_name, y in bands_y.items():
            self.create_line(80, y, w - 80, y, fill=t["glass_green"], width=2, stipple="gray50")
            self.create_text(45, y, text=b_name, fill=t["glass_green"], font=("Arial", 11, "bold"))
            self.create_text(w - 45, y, text=b_name, fill=t["glass_green"], font=("Arial", 11, "bold"))
            
        if w >= 700:
            fs = max(7, min(9, w // 120))
            cities_kv = ["МОСКВА", "МИНСК", "КИЕВ", "ТАШКЕНТ", "БАЛТИКА", "ПЕКИН", "ЛОНДОН", "ПАРИЖ"]
            cities_mw = ["БЕРЛИН", "ОДЕССА", "РИГА", "ВАРШАВА", "ПРАГА", "МАДРИД", "РИМ", "ЖЕНЕВА"]
            for i, city in enumerate(cities_kv):
                x = 140 + i * ((w - 280) // (len(cities_kv) - 1))
                self.create_text(x, 90, text=city, fill=t["glass_text"], font=("Arial", fs))
                self.create_line(x, 75, x, 80, fill=t["glass_green"])
            for i, city in enumerate(cities_mw):
                x = 120 + i * ((w - 240) // (len(cities_mw) - 1))
                self.create_text(x, 150, text=city, fill=t["glass_text"], font=("Arial", fs))
                self.create_line(x, 135, x, 140, fill=t["glass_green"])
                
        band_name = self.get_active_band(self.current_freq)
        y = bands_y.get(band_name, 105)
        fmin, fmax, logarithmic = self._band_for(self.current_freq)
        x_left, x_right = 100, w - 100
        
        if logarithmic:
            for i in range(9):
                fraction = i / 8
                freq_tick = math.exp(math.log(fmin) + fraction * (math.log(fmax) - math.log(fmin)))
                x = x_left + fraction * (x_right - x_left)
                self.create_line(x, y, x, y - 8, fill=t["brass"], width=1)
                if i % 2 == 0:
                    self.create_text(x, y - 17, text=f"{freq_tick:.2f}", fill=t["glass_text"], font=("Consolas", 8))
        else:
            for i in range(11):
                fraction = i / 10
                freq_tick = fmin + fraction * (fmax - fmin)
                x = x_left + fraction * (x_right - x_left)
                self.create_line(x, y, x, y - 8, fill=t["brass"], width=1)
                if i % 2 == 0:
                    self.create_text(x, y - 17, text=f"{freq_tick:.1f}", fill=t["glass_text"], font=("Consolas", 8))
                    
        position = (math.log(self.current_freq) - math.log(fmin)) / (math.log(fmax) - math.log(fmin)) if logarithmic else (self.current_freq - fmin) / (fmax - fmin)
        position = max(0.0, min(1.0, position))
        x = x_left + position * (x_right - x_left)
        
        self.create_line(x, y - 27, x, y + 12, fill="#F0B94D", width=8, stipple="gray50")
        self.create_line(x, y - 24, x, y + 10, fill="#3A0806", width=5)
        self.create_line(x, y - 24, x, y + 10, fill=t["needle"], width=3)
        self.create_line(x, y - 26, x, y - 22, fill="#FFE3A0", width=2)


# ============================================================================
# ГЛАВНОЕ ПРИЛОЖЕНИЕ
# ============================================================================
class PCR1000Pro(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Радиола Ригонда-Моно & IC-PCR1000")
        self.geometry("1360x900")
        self.minsize(1050, 760)

        self.current_theme_name = "night"
        self.theme = THEMES[self.current_theme_name]
        self.configure(fg_color=self.theme["bg"])
        
        self._ui_ready = False
        self._closing = False
        self._applying_settings = False
        self.ser = None
        self.is_connected = False
        self.scan_thread = None
        self.current_freq_mhz = 99.6
        self.frequency_step_mhz = 0.001
        self.current_mode = "WFM"
        self.current_filter = "230k"
        self.current_volume = 64
        self.current_squelch = 0
        self.if_shift_value = 128
        self.bfo_value = 128
        self.smeter_value = 0.0
        self.raw_smeter = 0
        self.is_busy = False
        self.has_dsp = False
        self.center_meter = 128
        self.is_scanning = False
        self.scan_start_mhz = 87.5
        self.scan_end_mhz = 108.0
        self.scan_step_khz = 100.0
        self.scan_threshold = 0.3
        self.scan_hold_time = 3.0
        self.scan_speed_ms = 350
        self.stop_event = threading.Event()
        self.found_freqs = []
        self.skipped_freqs = []
        self.dsp_attenuator = False
        self.dsp_agc = True
        self.dsp_nb = False
        self.dsp_afc = False
        self.dsp_vsc = False
        self.ctcss_code = 0
        self.debug_raw_log = False
        self.log_meter = False
        self.slider_interval = 0.12
        self.tune_interval = 0.20
        self.last_tune_time = 0.0
        self.tune_lock = threading.Lock()
        self._tune_timer = None
        self._tune_pending = False
        self._slider_state = {}
        self.com_lock = threading.RLock()
        self.reader_thread = None
        self.rx_buffer = ""
        self.rx_condition = threading.Condition()
        self.rx_tokens = []
        self.rx_dropped_bytes = 0
        self.smeter_seq = 0
        self.smeter_condition = threading.Condition()
        self.diag_running = False
        self._last_meter_log = 0.0
        self._watchdog_timer = None
        self.mode_keys = {}
        self._active_meter = None
        self.profiles = self._load_profiles()
        
        self.ui_queue = queue.Queue()

        self._build_ui()
        self._ui_ready = True
        self.refresh_ports()
        self._update_gui_indicators()
        self.after(40, self.process_ui_queue)
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.bind("<Up>", lambda e: self._step_freq(1))
        self.bind("<Down>", lambda e: self._step_freq(-1))
        self.bind("<Escape>", lambda e: self.stop_scan())
        self.bind("<F1>", lambda e: self._set_mode_from_key("AM"))
        self.bind("<F2>", lambda e: self._set_mode_from_key("USB"))
        self.bind("<F3>", lambda e: self._set_mode_from_key("LSB"))
        self.bind("<F4>", lambda e: self._set_mode_from_key("CW"))
        self.bind("<space>", self._on_space_key)
        self.bind("<Control-s>", lambda e: self._save_custom_profile())
        
        self.bind("<MouseWheel>", self.on_vfo_wheel)
        self.bind("<Button-4>", self.on_vfo_wheel)
        self.bind("<Button-5>", self.on_vfo_wheel)

    def process_ui_queue(self):
        if getattr(self, "_closing", False): return
        try:
            while True:
                event = self.ui_queue.get_nowait()
                kind = event[0]
                if kind == "frequency":
                    self.current_freq_mhz = event[1]
                    self._update_freq_widgets()
                elif kind == "found":
                    self.found_freqs.append({"freq": event[1], "smeter": event[2]})
                    self._update_found_list()
                elif kind == "scan_info":
                    self.lbl_scan_info.configure(text=event[1])
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.after(40, self.process_ui_queue)

    def on_vfo_wheel(self, event):
        focused = self.focus_get()
        if focused and focused.winfo_class() in ('Entry', 'Text', 'TEntry', 'CTkEntry', 'CTkComboBox'):
            return
        if event.delta > 0 or event.num == 4:
            self._step_freq(1)
        elif event.delta < 0 or event.num == 5:
            self._step_freq(-1)

    def _on_space_key(self, event=None):
        focused = self.focus_get()
        if focused and focused.winfo_class() in ("Entry", "Text", "TEntry", "CTkEntry"):
            return
        self.toggle_scan()
        return "break"

    def _set_mode_from_key(self, mode):
        self._on_mode_key_press(mode)

    def stop_scan(self):
        if self.is_scanning:
            self.toggle_scan()

    def _load_profiles(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data: return data
            except Exception: pass
        return DEFAULT_PROFILES.copy()

    def _save_profiles(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.profiles, f, indent=2, ensure_ascii=False)
        except Exception: pass

    def toggle_theme(self):
        self.current_theme_name = "day" if self.current_theme_name == "night" else "night"
        self.theme = THEMES[self.current_theme_name]
        self.apply_theme()

    def apply_theme(self):
        t = self.theme
        self.configure(fg_color=t["bg"])

        def update_ctk_colors(widget):
            if isinstance(widget, (ctk.CTkFrame, ctk.CTk)):
                if widget.cget("fg_color") != "transparent":
                    widget.configure(fg_color=t["panel"])
            elif isinstance(widget, ctk.CTkLabel):
                if widget.cget("text_color") not in [t["brass"], t["danger"], t["success"], t["glass_green"]]:
                    widget.configure(text_color=t["text"])
            elif isinstance(widget, ctk.CTkButton):
                if widget.cget("fg_color") not in [t["brass"], t["danger"], t["btn_bg"], "transparent"]:
                    widget.configure(fg_color=t["panel"], text_color=t["text"], border_color=t["border"])
            elif isinstance(widget, ctk.CTkSlider):
                widget.configure(fg_color=t["entry_bg"], progress_color=t["brass"], button_color=t["brass"], button_hover_color=t["accent"])
            elif isinstance(widget, (ctk.CTkEntry, ctk.CTkComboBox, ctk.CTkTextbox)):
                widget.configure(fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"])
            elif isinstance(widget, ctk.CTkSwitch):
                widget.configure(fg_color=t["border"], progress_color=t["on"], text_color=t["text"])
            elif isinstance(widget, ctk.CTkSegmentedButton):
                widget.configure(fg_color=t["panel"], selected_color=t["accent"], text_color=t["text"])
            elif isinstance(widget, ctk.CTkProgressBar):
                widget.configure(fg_color=t["entry_bg"], progress_color=t["success"])

            for child in widget.winfo_children():
                update_ctk_colors(child)

        update_ctk_colors(self)

        self.top_wood.update_theme(t)
        self.bottom_wood.update_theme(t)
        self.magic_eye.update_theme(t)
        self.classic_meter.update_theme(t)
        self.dial_scale.update_theme(t)
        self.vfo_dial.update_theme(t)

        for key in self.mode_keys.values():
            key.update_theme(t)
        
        self.update_mode_buttons(self.current_mode)

    def _switch_meter_type(self, choice):
        if choice == "Лампа 6Е5С":
            self.classic_meter.grid_remove()
            self.magic_eye.grid(row=1, column=0, pady=(5, 10), padx=10, sticky="nsew")
            self._active_meter = self.magic_eye
        else:
            self.magic_eye.grid_remove()
            self.classic_meter.grid(row=1, column=0, pady=(5, 10), padx=10, sticky="nsew")
            self._active_meter = self.classic_meter
        if self._active_meter:
            self._active_meter.set_value(self.raw_smeter)

    def toggle_side_panel(self, panel, button, title, row, column):
        if panel.winfo_viewable():
            panel.grid_remove()
            button.configure(text=f"{title}  +")
        else:
            panel.grid(row=row, column=column, padx=4, pady=4, sticky="nsew")
            button.configure(text=f"{title}  −")

    def _build_ui(self):
        t = self.theme
        self.top_wood = PhotoRealWoodPanel(self, theme=t, height=35)
        self.top_wood.pack(fill="x", side="top")

        self.top_frame = ctk.CTkFrame(self, height=45, fg_color=t["panel"], corner_radius=0)
        self.top_frame.pack(fill="x")

        self.lbl_title = ctk.CTkLabel(self.top_frame, text="📻 РИГОНДА-МОНО (PCR1000)",
                                      font=("Arial", 18, "bold"), text_color=t["brass"])
        self.lbl_title.pack(side="left", padx=(15, 10))

        self.port_cb = ctk.CTkComboBox(self.top_frame, values=[], width=130, height=30,
                                       fg_color=t["entry_bg"], border_color=t["border"],
                                       text_color=t["text"], button_color=t["border"], button_hover_color=t["brass_shadow"])
        self.port_cb.pack(side="left", padx=5)

        self.btn_refresh = ctk.CTkButton(self.top_frame, text="⟳", width=32, height=30,
                                         fg_color=t["panel"], hover_color=t["border"], text_color=t["text"],
                                         border_color=t["border"], border_width=1, command=self.refresh_ports)
        self.btn_refresh.pack(side="left", padx=5)

        self.btn_connect = ctk.CTkButton(self.top_frame, text="ВКЛ РАДИО", width=120, height=30,
                                         fg_color=t["brass"], hover_color="#9E7F30", text_color="#000000",
                                         font=("Arial", 11, "bold"), command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=10)

        self.btn_theme = ctk.CTkButton(self.top_frame, text="☀/☾", width=40, height=30,
                                       fg_color=t["panel"], hover_color=t["border"], text_color=t["text"],
                                       border_color=t["border"], border_width=1, command=self.toggle_theme)
        self.btn_theme.pack(side="left", padx=5)
        add_tooltip(self.btn_theme, "Переключить дневную/ночную тему")

        self.lbl_status = ctk.CTkLabel(self.top_frame, text="● СЕТЬ ВЫКЛ", font=("Arial", 11, "bold"), text_color=t["danger"])
        self.lbl_status.pack(side="right", padx=15)

        center_frame = ctk.CTkFrame(self, fg_color="transparent")
        center_frame.pack(fill="both", expand=True, padx=15, pady=5)
        center_frame.grid_columnconfigure(0, weight=0, minsize=200)
        center_frame.grid_columnconfigure(1, weight=1)
        center_frame.grid_columnconfigure(2, weight=0, minsize=180)
        center_frame.grid_rowconfigure(0, weight=1)

        indicator_frame = ctk.CTkFrame(center_frame, fg_color=t["panel"], corner_radius=8, border_width=2, border_color=t["brass"])
        indicator_frame.grid(row=0, column=0, padx=(0, 10), pady=5, sticky="nsew")
        indicator_frame.grid_columnconfigure(0, weight=1)
        indicator_frame.grid_rowconfigure(0, weight=0)
        indicator_frame.grid_rowconfigure(1, weight=1)

        self.meter_toggle = ctk.CTkSegmentedButton(indicator_frame, values=["Лампа 6Е5С", "Стрелка"],
                                                   command=self._switch_meter_type, fg_color=t["panel"],
                                                   selected_color=t["accent"], text_color=t["text"], font=("Arial", 10, "bold"))
        self.meter_toggle.grid(row=0, column=0, pady=(10, 5), padx=10, sticky="ew")
        self.meter_toggle.set("Лампа 6Е5С")

        self.magic_eye = MagicEyeMeter(indicator_frame, theme=t, width=280, height=240)
        self.classic_meter = ClassicSMeter(indicator_frame, theme=t, width=300, height=220)
        self._switch_meter_type("Лампа 6Е5С")

        self.dial_scale = PhotoRealDialDashboard(center_frame, theme=t)
        self.dial_scale.grid(row=0, column=1, sticky="nsew", pady=5)
        add_tooltip(self.dial_scale, "Шкала настройки частоты")

        right_vfo = ctk.CTkFrame(center_frame, fg_color=t["panel"], corner_radius=4, border_width=1, border_color=t["brass"])
        right_vfo.grid(row=0, column=2, padx=(10, 0), pady=5, sticky="ns")

        vfo_text = ctk.CTkFrame(right_vfo, fg_color=t["entry_bg"], corner_radius=2, border_width=1, border_color=t["brass"])
        vfo_text.pack(padx=8, pady=(8, 4), fill="x")
        
        self.lbl_vfo = ctk.CTkLabel(vfo_text, text="99.60000", font=("Consolas", 32, "bold"), text_color=t["glass_green"])
        self.lbl_vfo.pack(pady=(5, 0))
        add_tooltip(self.lbl_vfo, "Текущая частота приёмника")
        
        self.lbl_vfo_info = ctk.CTkLabel(vfo_text, text="УКВ  |  Шаг: 1 кГц", font=("Arial", 9, "bold"), text_color=t["muted"])
        self.lbl_vfo_info.pack(pady=(0, 5))

        # Частоту можно вводить с клавиатуры в МГц; Enter применяет настройку.
        self.entry_freq = ctk.CTkEntry(
            vfo_text, width=145, height=28, justify="center",
            font=("Consolas", 14), placeholder_text="Частота, МГц"
        )
        self.entry_freq.insert(0, "99.60000")
        self.entry_freq.pack(pady=(2, 5))
        self.entry_freq.bind("<Return>", lambda event: self.apply_settings())
        self.btn_apply_freq = ctk.CTkButton(
            vfo_text, text="УСТАНОВИТЬ", width=120, height=26,
            command=self.apply_settings, fg_color=t["btn_bg"],
            hover_color=t["btn_hover"], text_color="#000000",
            font=("Arial", 10, "bold")
        )
        self.btn_apply_freq.pack(pady=(0, 6))

        step_row = ctk.CTkFrame(right_vfo, fg_color="transparent")
        step_row.pack(pady=4)
        
        self.btn_step_down = ctk.CTkButton(step_row, text="−", width=32, height=32, fg_color=t["btn_bg"],
                                           hover_color=t["btn_hover"], text_color="#000000", border_color=t["brass"],
                                           border_width=1, font=("Arial", 16, "bold"), command=lambda: self._step_freq(-1))
        self.btn_step_down.pack(side="left", padx=2)
        add_tooltip(self.btn_step_down, "Уменьшить частоту")

        self.step_vfo_cb = ctk.CTkComboBox(step_row, values=list(VFO_STEPS.keys()), width=80, height=26, font=("Arial", 9),
                                           fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"],
                                           button_color=t["border"], button_hover_color=t["brass_shadow"],
                                           command=self._on_step_change)
        self.step_vfo_cb.set("1 кГц")
        self.step_vfo_cb.pack(side="left", padx=2)

        self.btn_step_up = ctk.CTkButton(step_row, text="+", width=32, height=32, fg_color=t["btn_bg"],
                                         hover_color=t["btn_hover"], text_color="#000000", border_color=t["brass"],
                                         border_width=1, font=("Arial", 16, "bold"), command=lambda: self._step_freq(1))
        self.btn_step_up.pack(side="left", padx=2)
        add_tooltip(self.btn_step_up, "Увеличить частоту")

        self.vfo_dial = RigondaVFO_Dial(right_vfo, theme=t, command=self._on_dial_move, width=120, height=120)
        self.vfo_dial.pack(pady=(4, 8))
        add_tooltip(self.vfo_dial, "Покрутите колесом мыши или перетащите")

        p2k_deck = ctk.CTkFrame(self, fg_color=t["panel"], height=50, corner_radius=0, border_width=1, border_color=t["border"])
        p2k_deck.pack(fill="x", padx=15, pady=4)
        p2k_inner = tk.Frame(p2k_deck, bg=t["panel"])
        p2k_inner.pack(expand=True, pady=8)
        
        modes = ["LSB", "USB", "AM", "CW", "NFM", "WFM"]
        for i, mode in enumerate(modes):
            key = PhotoRealP2KButton(p2k_inner, theme=t, text=mode, command=self._on_mode_key_press)
            key.grid(row=0, column=i, padx=4)
            self.mode_keys[mode] = key
        self.update_mode_buttons("WFM")

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=15, pady=4)
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=0)
        main.grid_rowconfigure(1, weight=1)

        self.btn_adv_panel = ctk.CTkButton(main, text="НАСТРОЙКИ  −", height=26, fg_color=t["panel"],
                                           text_color=t["text"], border_color=t["brass"], border_width=1,
                                           command=lambda: self.toggle_side_panel(self.left_frame, self.btn_adv_panel, "НАСТРОЙКИ", 1, 0))
        self.btn_adv_panel.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self.btn_scan_panel = ctk.CTkButton(main, text="СКАНЕР  −", height=26, fg_color=t["panel"],
                                            text_color=t["text"], border_color=t["brass"], border_width=1,
                                            command=lambda: self.toggle_side_panel(self.right_frame, self.btn_scan_panel, "СКАНЕР", 1, 1))
        self.btn_scan_panel.grid(row=0, column=1, sticky="ew", padx=(2, 0))

        self.left_frame = ctk.CTkFrame(main, corner_radius=6, border_width=1, fg_color=t["panel"], border_color=t["border"])
        self.left_frame.grid(row=1, column=0, padx=(0, 2), pady=4, sticky="nsew")
        
        def add_left_label(text):
            lbl = ctk.CTkLabel(self.left_frame, text=text.upper(), font=("Arial", 9, "bold"), text_color=t["brass"])
            lbl.pack(anchor="w", padx=12, pady=(8, 2))

        add_left_label("Громкость НЧ (AF GAIN)")
        self.slider_vol = ctk.CTkSlider(self.left_frame, from_=0, to=255, width=260, height=12, fg_color=t["entry_bg"],
                                        progress_color=t["brass"], button_color=t["brass"], button_hover_color=t["accent"],
                                        command=self.set_volume)
        self.slider_vol.set(self.current_volume)
        self.slider_vol.pack(pady=2, padx=12, anchor="w")
        add_tooltip(self.slider_vol, "Управление громкостью приёмника")

        add_left_label("Подавление шумов (SQUELCH)")
        self.slider_sql = ctk.CTkSlider(self.left_frame, from_=0, to=255, width=260, height=12, fg_color=t["entry_bg"],
                                        progress_color=t["brass"], button_color=t["brass"], button_hover_color=t["accent"],
                                        command=self.set_squelch)
        self.slider_sql.set(self.current_squelch)
        self.slider_sql.pack(pady=2, padx=12, anchor="w")
        add_tooltip(self.slider_sql, "Порог шумоподавителя")

        add_left_label("Дополнительные функции")
        row_dsp = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        row_dsp.pack(fill="x", padx=12, pady=(0, 8))
        
        self.switch_att = ctk.CTkSwitch(row_dsp, text="АТТ", font=("Arial", 9), fg_color=t["border"], progress_color=t["on"], text_color=t["text"], command=self._toggle_att)
        self.switch_att.pack(side="left", padx=(0, 6))
        self.switch_agc = ctk.CTkSwitch(row_dsp, text="АРУ", font=("Arial", 9), fg_color=t["border"], progress_color=t["on"], text_color=t["text"], command=self._toggle_agc)
        self.switch_agc.pack(side="left", padx=(0, 6)); self.switch_agc.select()
        self.switch_nb = ctk.CTkSwitch(row_dsp, text="ПОШ", font=("Arial", 9), fg_color=t["border"], progress_color=t["on"], text_color=t["text"], command=self._toggle_nb)
        self.switch_nb.pack(side="left", padx=(0, 6))
        self.switch_afc = ctk.CTkSwitch(row_dsp, text="АПЧ", font=("Arial", 9), fg_color=t["border"], progress_color=t["on"], text_color=t["text"], command=self._toggle_afc)
        self.switch_afc.pack(side="left", padx=(0, 6))
        self.switch_vsc = ctk.CTkSwitch(row_dsp, text="ГОР", font=("Arial", 9), fg_color=t["border"], progress_color=t["on"], text_color=t["text"], command=self._toggle_vsc)
        self.switch_vsc.pack(side="left")

        self.right_frame = ctk.CTkFrame(main, corner_radius=6, border_width=1, fg_color=t["panel"], border_color=t["border"])
        self.right_frame.grid(row=1, column=1, padx=(2, 0), pady=4, sticky="nsew")
        
        def add_right_label(text):
            lbl = ctk.CTkLabel(self.right_frame, text=text.upper(), font=("Arial", 9, "bold"), text_color=t["brass"])
            lbl.pack(anchor="w", padx=12, pady=(8, 2))

        add_right_label("Автоматический поиск")
        row_band = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        row_band.pack(pady=2, padx=12, fill="x")
        
        self.band_cb = ctk.CTkComboBox(row_band, values=["Custom"] + list(self.profiles.keys()), width=160, height=30,
                                       fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"],
                                       button_color=t["border"], button_hover_color=t["brass_shadow"], command=self._on_band_change)
        self.band_cb.set("FM Radio")
        self.band_cb.pack(side="left", padx=(0, 6))
        
        self.btn_add_profile = ctk.CTkButton(row_band, text="+", width=32, height=32, fg_color=t["panel"], hover_color=t["border"],
                                             text_color=t["text"], border_width=1, border_color=t["border"], font=("Arial", 14), command=self._save_custom_profile)
        self.btn_add_profile.pack(side="left")

        row_range = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        row_range.pack(pady=2, padx=12, fill="x")
        self.entry_scan_start = ctk.CTkEntry(row_range, placeholder_text="Старт", width=80, height=30, justify="center", fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"])
        self.entry_scan_start.insert(0, "87.5")
        self.entry_scan_start.pack(side="left", padx=(0, 6))
        self.entry_scan_end = ctk.CTkEntry(row_range, placeholder_text="Стоп", width=80, height=30, justify="center", fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"])
        self.entry_scan_end.insert(0, "108.0")
        self.entry_scan_end.pack(side="left", padx=(0, 6))
        self.step_cb = ctk.CTkComboBox(row_range, values=["5", "10", "12.5", "25", "50", "100"], width=70, height=30, fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"], button_color=t["border"], button_hover_color=t["brass_shadow"])
        self.step_cb.set("100")
        self.step_cb.pack(side="left")

        add_right_label("Порог срабатывания")
        self.slider_threshold = ctk.CTkSlider(self.right_frame, from_=0.05, to=0.9, width=260, height=12, fg_color=t["entry_bg"], progress_color=t["brass"], button_color=t["brass"], button_hover_color=t["accent"])
        self.slider_threshold.set(0.3)
        self.slider_threshold.pack(pady=2, padx=12, anchor="w")

        self.btn_scan = ctk.CTkButton(self.right_frame, text="▶  СТАРТ ПОИСКА", height=38, fg_color=t["btn_bg"], hover_color=t["btn_hover"], text_color="#000000", font=("Arial", 12, "bold"), command=self.toggle_scan)
        self.btn_scan.pack(fill="x", padx=12, pady=(12, 4))
        add_tooltip(self.btn_scan, "Запуск или остановка сканирования (Space)")

        self.progress_scan = ctk.CTkProgressBar(self.right_frame, width=260, height=6, fg_color=t["entry_bg"], progress_color=t["success"])
        self.progress_scan.set(0)
        self.progress_scan.pack(padx=12, pady=(0, 4), anchor="w")

        self.lbl_scan_info = ctk.CTkLabel(self.right_frame, text="Приемник готов", font=("Arial", 10), text_color=t["text"])
        self.lbl_scan_info.pack(pady=(0, 8))

        self.action_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.action_frame.pack(fill="x", padx=12)
        self.btn_save_freq = ctk.CTkButton(self.action_frame, text="💾 Сохранить", height=30, state="disabled", fg_color=t["panel"], hover_color=t["border"], text_color=t["text"], border_width=1, border_color=t["border"], font=("Arial", 10), command=self.save_current_freq)
        self.btn_save_freq.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.btn_skip = ctk.CTkButton(self.action_frame, text="⏭ Пропустить", height=30, state="disabled", fg_color=t["panel"], hover_color=t["border"], text_color=t["text"], border_width=1, border_color=t["border"], font=("Arial", 10), command=self.skip_current_freq)
        self.btn_skip.pack(side="left", fill="x", expand=True, padx=(3, 0))

        add_right_label("Зафиксированные станции")
        self.found_list = ctk.CTkTextbox(self.right_frame, height=100, font=("Consolas", 10), fg_color=t["entry_bg"], border_color=t["border"], border_width=1, text_color=t["text"])
        self.found_list.pack(fill="both", expand=True, padx=12, pady=(2, 8))
        self.found_list.configure(state="disabled")

        self.btn_export = ctk.CTkButton(self.right_frame, text="📊 Экспорт в CSV", height=30, fg_color="transparent", hover_color=t["border"], text_color=t["text"], border_width=1, border_color=t["border"], font=("Arial", 10), command=self.export_csv)
        self.btn_export.pack(fill="x", padx=12, pady=(0, 12))

        self.bottom_wood = PhotoRealWoodPanel(self, theme=t, height=20)
        self.bottom_wood.pack(fill="x", side="bottom")

    def _on_step_change(self, val):
        self.frequency_step_mhz = VFO_STEPS.get(val, 0.001)
        self.lbl_vfo_info.configure(text=f"Шаг: {val}")

    def _update_freq_widgets(self):
        freq_text = f"{self.current_freq_mhz:.5f}"
        self.lbl_vfo.configure(text=freq_text)
        if hasattr(self, "entry_freq"):
            self.entry_freq.delete(0, "end")
            self.entry_freq.insert(0, freq_text)
        self.dial_scale.set_frequency(self.current_freq_mhz)

    def _on_mode_key_press(self, mode):
        self.update_mode_buttons(mode)
        self.current_mode = mode
        self.apply_settings()

    def update_mode_buttons(self, active_mode):
        for mode, btn in self.mode_keys.items():
            btn.set_pressed(mode == active_mode)

    def _on_dial_move(self, direction):
        if self.is_scanning: return
        self.current_freq_mhz = round(self.current_freq_mhz + direction * DIAL_STEP_MHZ, 6)
        self.current_freq_mhz = max(0.5, min(1300.0, self.current_freq_mhz))
        self._update_freq_widgets()
        if self.is_connected: self.sync_frequency()

    def _step_freq(self, direction):
        if self.is_scanning: return
        self.current_freq_mhz = round(self.current_freq_mhz + direction * self.frequency_step_mhz, 6)
        self.current_freq_mhz = max(0.5, min(1300.0, self.current_freq_mhz))
        self._update_freq_widgets()
        if self.is_connected: self.sync_frequency()

    def _on_band_change(self, band):
        if band == "Custom": return
        p = self.profiles.get(band)
        if not p: return
        self.entry_scan_start.delete(0, "end"); self.entry_scan_start.insert(0, str(p["start"]))
        self.entry_scan_end.delete(0, "end"); self.entry_scan_end.insert(0, str(p["end"]))
        self._on_mode_key_press(p["mode"])
        self.slider_threshold.set(p["threshold"])
        self.step_cb.set(str(p.get("step", 100)))

    def _save_custom_profile(self):
        name = ctk.CTkInputDialog(text="Введите имя профиля:", title="Новый профиль").get_input()
        if not name: return
        try:
            self.profiles[name] = {
                "start": float(self.entry_scan_start.get()), "end": float(self.entry_scan_end.get()),
                "step": float(self.step_cb.get()), "threshold": float(self.slider_threshold.get()),
                "mode": self.current_mode, "filter": "230k"
            }
            self._save_profiles()
            self.band_cb.configure(values=["Custom"] + list(self.profiles.keys()))
            self.band_cb.set(name)
        except ValueError:
            messagebox.showerror("Ошибка", "Проверьте введенные данные.")

    def save_current_freq(self):
        freq = self.current_freq_mhz
        if freq not in [f["freq"] for f in self.found_freqs]:
            self.found_freqs.append({"freq": freq, "smeter": self.raw_smeter})
            self._update_found_list()
            self.btn_save_freq.configure(state="disabled")

    def skip_current_freq(self):
        freq = self.current_freq_mhz
        if freq not in self.skipped_freqs:
            self.skipped_freqs.append(freq)
            self.btn_skip.configure(state="disabled")

    def _update_found_list(self):
        self.found_list.configure(state="normal")
        self.found_list.delete("1.0", "end")
        for item in self.found_freqs:
            self.found_list.insert("end", f"▶ {item['freq']:.5f} МГц (S={item['smeter']})\n")
        self.found_list.configure(state="disabled")

    def export_csv(self):
        if not self.found_freqs:
            messagebox.showinfo("Экспорт", "Нет данных.")
            return
        fname = time.strftime("scan_%Y%m%d_%H%M%S.csv")
        try:
            with open(fname, "w", newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Frequency (MHz)", "S-Meter"])
                for item in self.found_freqs:
                    writer.writerow([f"{item['freq']:.5f}", item['smeter']])
            messagebox.showinfo("Успех", f"Файл: {fname}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb.configure(values=ports)
        if ports: self.port_cb.set(ports[0])

    def toggle_connection(self):
        if self.is_connected: self.disconnect_radio()
        else: self.connect_radio()

    def connect_radio(self):
        port = self.port_cb.get()
        if not port: return
        try:
            self.ser = serial.Serial(port, 9600, timeout=0.1, write_timeout=1.0, dsrdtr=False, xonxoff=False)
            self.ser.rts = True
            self.is_connected = True
            self.stop_event.clear()
            self.rx_buffer = ""
            self.rx_dropped_bytes = 0
            with self.rx_condition: self.rx_tokens.clear()

            self.reader_thread = threading.Thread(target=self._serial_reader, daemon=True)
            self.reader_thread.start()

            self._log("Инициализация аудиотракта...")
            self.send_command("H101", wait_response=False); time.sleep(0.3)
            self.send_command("H1?", wait_response=False); time.sleep(0.3)
            self.send_command("G301", wait_response=False); time.sleep(0.2)
            self.send_command("G103", wait_response=False); time.sleep(0.2)
            self.send_command("J4380", wait_response=False)
            self.send_command("J4A80", wait_response=False); time.sleep(0.1)
            self.send_command("J4100", wait_response=False)
            self.send_command("J5100", wait_response=False); time.sleep(0.1)
            self.send_command(f"J40{self.current_volume:02X}", wait_response=False); time.sleep(0.1)
            self.send_command(f"J40{self.current_volume:02X}", wait_response=False); time.sleep(0.1)
            self.send_command(f"J41{self.current_squelch:02X}", wait_response=False)
            self.send_command(f"J45{1 if self.dsp_agc else 0:02X}", wait_response=False)
            self.send_command(f"J46{1 if self.dsp_nb else 0:02X}", wait_response=False)
            self.send_command(f"J47{1 if self.dsp_attenuator else 0:02X}", wait_response=False)
            self.send_command("J5000", wait_response=False); time.sleep(0.1)

            gd = self.send_command_sync("GD?", wait_response=True, timeout=1.5)
            if gd:
                try: self.has_dsp = bool(int(gd[2:4], 16) & 0x01)
                except ValueError: self.has_dsp = False
            else: self.has_dsp = False

            if self.has_dsp: self._log("DSP-модуль обнаружен.")
            else:
                self._log("DSP-модуль не найден (GD00). ATT/AGC/NB — аналоговые функции.")
                self.switch_afc.configure(state="disabled"); self.switch_vsc.configure(state="disabled")

            self.sync_frequency(force=True)
            self._start_watchdog()
            if self._active_meter is not None:
                self._active_meter.set_value(self.raw_smeter)
            self.apply_theme()
            self.port_cb.configure(state="disabled")
            self.lbl_status.configure(text="● СЕТЬ ВКЛ")
            self._log("Соединение установлено. Watchdog запущен.")
        except Exception as e:
            self.is_connected = False
            if self.ser:
                try:
                    with self.com_lock: self.ser.close()
                except Exception: pass
            messagebox.showerror("Ошибка", f"Не удалось подключиться:\n{e}")

    def disconnect_radio(self):
        was_connected = self.is_connected
        self.is_scanning = False
        self.stop_event.set()
        self.is_connected = False
        self._stop_watchdog()
        if self.ser and self.ser.is_open:
            try:
                with self.com_lock:
                    if self.ser and self.ser.is_open:
                        self.ser.write(b"H100\r\n")
                        self.ser.flush()
                        self.ser.close()
            except Exception as e:
                self._log(f"Ошибка закрытия COM-порта: {e}")
        self.apply_theme()
        self.port_cb.configure(state="readonly")
        self.lbl_status.configure(text="● СЕТЬ ВЫКЛ")
        if self._active_meter is not None:
            self._active_meter.set_value(0)
        if was_connected: self._log("Соединение разорвано.")

    def _start_watchdog(self):
        self._stop_watchdog()
        def watchdog_tick():
            if not self.is_connected or self._closing:
                return
            self.send_command("I0?", wait_response=False)
            self._watchdog_timer = self.after(5000, watchdog_tick)
        self._watchdog_timer = self.after(5000, watchdog_tick)

    def _stop_watchdog(self):
        if self._watchdog_timer:
            try:
                self.after_cancel(self._watchdog_timer)
            except Exception:
                pass
        self._watchdog_timer = None

    def _serial_reader(self):
        token_re = re.compile(r"(GD|G0|H1|I[0-4])\s*([0-9A-Fa-f]{2})")
        while self.is_connected and self.ser and self.ser.is_open:
            try:
                with self.com_lock:
                    if not self.ser or not self.ser.is_open: break
                    waiting = self.ser.in_waiting
                    chunk = self.ser.read(waiting if waiting else 1)
                if not chunk: continue
                if self.debug_raw_log: self._log(f"RX RAW: {chunk!r}")
                
                clean = bytes(b for b in chunk if 32 <= b < 127 or b in (10, 13))
                self.rx_dropped_bytes += len(chunk) - len(clean)
                if not clean: continue
                
                self.rx_buffer += clean.decode("ascii")
                self.rx_buffer = self.rx_buffer.replace("\r", "").replace("\n", "")
                
                matches = list(token_re.finditer(self.rx_buffer))
                if matches:
                    for match in matches:
                        token = (match.group(1) + match.group(2)).upper()
                        with self.rx_condition:
                            self.rx_tokens.append(token)
                            if len(self.rx_tokens) > 100: del self.rx_tokens[:-100]
                            self.rx_condition.notify_all()
                        self._handle_rx_token(token)
                    self.rx_buffer = self.rx_buffer[matches[-1].end():]
                
                if len(self.rx_buffer) > 32:
                    self.rx_buffer = self.rx_buffer[-8:]
            except (serial.SerialException, OSError) as e:
                if self.is_connected: self._log(f"Ошибка чтения COM-порта: {e}")
                break
            except Exception as e:
                if self.is_connected: self._log(f"Ошибка обработчика RX: {e}")
                time.sleep(0.05)

    def _handle_rx_token(self, token):
        prefix = token[:2]
        try: value = int(token[2:4], 16)
        except ValueError: return
        if prefix == "I1":
            self.raw_smeter = value
            self.smeter_value = min(value / 255.0, 1.0)
            with self.smeter_condition:
                self.smeter_seq += 1
                self.smeter_condition.notify_all()
        elif prefix == "I0":
            self.is_busy = bool(value & 0x01)
        elif prefix == "I2":
            self.center_meter = value

    def _update_gui_indicators(self):
        if self._closing:
            return
        try:
            if self._active_meter is not None:
                self._active_meter.set_value(self.raw_smeter if self.is_connected else 0)
            self.after(100, self._update_gui_indicators)
        except (tk.TclError, AttributeError):
            pass


    def _take_token(self, prefix, timeout=0.8):
        deadline = time.monotonic() + timeout
        with self.rx_condition:
            while True:
                for index, token in enumerate(self.rx_tokens):
                    if token.startswith(prefix): return self.rx_tokens.pop(index)
                remaining = deadline - time.monotonic()
                if remaining <= 0: return ""
                self.rx_condition.wait(remaining)

    def send_command_sync(self, cmd, wait_response=True, timeout=0.8):
        prefix = cmd[:2].upper()
        if wait_response:
            with self.rx_condition: self.rx_tokens = [token for token in self.rx_tokens if not token.startswith(prefix)]
        with self.com_lock:
            if not self.ser or not self.ser.is_open: return ""
            try:
                self.ser.write((cmd + "\r\n").encode("ascii"))
                self.ser.flush()
                self._log(f"TX: {cmd}")
            except (serial.SerialException, OSError, serial.SerialTimeoutException) as e:
                self._log(f"Ошибка связи Serial ({cmd}): {e}")
                return ""
        if not wait_response: return ""
        response = self._take_token(prefix, timeout=timeout)
        if response: self._log(f"RX: {response!r}")
        else: self._log(f"Тайм-аут ответа на {cmd}")
        return response

    def send_command(self, cmd, wait_response=False):
        return self.send_command_sync(cmd, wait_response=wait_response)

    def _slider_command(self, key, val, prefix, label=None, offset=0):
        value = int(round(float(val)))
        value = max(0, min(255, value))
        if label is not None: label.configure(text=str(value - offset))
        st = self._slider_state.setdefault(key, {"last": 0.0, "pending": None, "timer": None})
        st["pending"] = value
        wait = self.slider_interval - (time.monotonic() - st["last"])
        if wait <= 0: self._flush_slider(key, prefix)
        elif st["timer"] is None:
            try: st["timer"] = self.after(int(wait * 1000) + 5, lambda k=key, p=prefix: self._flush_slider(k, p))
            except tk.TclError: pass
        return value

    def _flush_slider(self, key, prefix):
        st = self._slider_state.get(key)
        if not st: return
        if st["timer"] is not None:
            try: self.after_cancel(st["timer"])
            except Exception: pass
        st["timer"] = None
        value = st["pending"]
        if value is None: return
        st["pending"] = None
        st["last"] = time.monotonic()
        self.send_command(f"{prefix}{value:02X}")

    def set_volume(self, val): self.current_volume = self._slider_command("vol", val, "J40")
    def set_squelch(self, val): self.current_squelch = self._slider_command("sql", val, "J41")

    def _toggle_att(self):
        if not self._ui_ready: return
        self.dsp_attenuator = bool(self.switch_att.get())
        self.send_command(f"J47{1 if self.dsp_attenuator else 0:02X}")
        self.apply_theme()

    def _toggle_agc(self):
        if not self._ui_ready: return
        self.dsp_agc = bool(self.switch_agc.get())
        self.send_command(f"J45{1 if self.dsp_agc else 0:02X}")
        self.apply_theme()

    def _toggle_nb(self):
        if not self._ui_ready: return
        self.dsp_nb = bool(self.switch_nb.get())
        self.send_command(f"J46{1 if self.dsp_nb else 0:02X}")
        self.apply_theme()

    def _toggle_afc(self):
        if not self._ui_ready: return
        self.dsp_afc = bool(self.switch_afc.get())
        self.send_command(f"J50{1 if self.dsp_afc else 0:02X}")
        self.apply_theme()

    def _toggle_vsc(self):
        if not self._ui_ready: return
        self.dsp_vsc = bool(self.switch_vsc.get())
        self.send_command(f"J50{1 if self.dsp_vsc else 0:02X}")
        self.apply_theme()

    def apply_settings(self):
        if self._applying_settings:
            return
        self._applying_settings = True
        try:
            raw = self.entry_freq.get().strip().replace(",", ".")
            try:
                value = float(raw)
            except ValueError:
                messagebox.showerror("Частота", "Введите частоту в МГц, например 99.60000.")
                return
            if not math.isfinite(value) or not 0.5 <= value <= 1300.0:
                messagebox.showerror("Частота", "Допустимый диапазон: 0.50000–1300.00000 МГц.")
                return
            self.current_freq_mhz = round(value, 6)
            self._update_freq_widgets()
            if self.is_connected:
                self.sync_frequency(force=True)
        finally:
            self._applying_settings = False

    def sync_frequency(self, force=False):
        if not self.is_connected: return
        if threading.current_thread() is not threading.main_thread():
            with self.tune_lock:
                now = time.monotonic()
                if not force and now - self.last_tune_time < self.tune_interval: return
                self.last_tune_time = now
            self._send_tune()
            return
        self._tune_pending = True
        wait = self.tune_interval - (time.monotonic() - self.last_tune_time)
        if force or wait <= 0: self._tune_flush()
        elif self._tune_timer is None:
            try: self._tune_timer = self.after(int(wait * 1000) + 5, self._tune_flush)
            except tk.TclError: pass

    def _tune_flush(self):
        if self._tune_timer is not None:
            try: self.after_cancel(self._tune_timer)
            except Exception: pass
            self._tune_timer = None
        if not self._tune_pending: return
        self._tune_pending = False
        self.last_tune_time = time.monotonic()
        self._send_tune()

    def _send_tune(self):
        freq_hz = int(round(self.current_freq_mhz * 1_000_000))
        mhz_part = freq_hz // 1_000_000
        hz_part = freq_hz % 1_000_000
        mode_code = MODE_CODES.get(self.current_mode, 6)
        filter_code = FILTER_CODES.get(self.current_filter, 4)
        cmd = f"K0{mhz_part:04d}{hz_part:06d}{mode_code:02d}{filter_code:02d}00"
        self.send_command_sync(cmd, wait_response=False)
        self._update_freq_widgets()

    def toggle_scan(self):
        if not self.is_connected: return
        if self.is_scanning:
            self.is_scanning = False
            self.stop_event.set()
            self.ui_queue.put(("scan_info", "Поиск остановлен"))
            self.btn_save_freq.configure(state="disabled")
            self.btn_skip.configure(state="disabled")
            self.btn_scan.configure(text="▶  СТАРТ ПОИСКА", fg_color=self.theme["btn_bg"], text_color="#000000")
        else:
            try:
                self.scan_start_mhz = float(self.entry_scan_start.get())
                self.scan_end_mhz = float(self.entry_scan_end.get())
                self.scan_step_khz = float(self.step_cb.get())
                self.scan_threshold = float(self.slider_threshold.get())
                
                if self.scan_step_khz <= 0: raise ValueError("Шаг сканирования должен быть > 0")
                if self.scan_end_mhz <= self.scan_start_mhz: raise ValueError("Конец диапазона должен быть выше начала")
                    
                self.current_freq_mhz = self.scan_start_mhz
                self.is_scanning = True
                self.stop_event.clear()
                self.ui_queue.put(("scan_info", "Идет поиск..."))
                self.btn_scan.configure(text="■  СТОП ПОИСКА", fg_color=self.theme["danger"], text_color="#ffffff")
                if self.scan_thread is None or not self.scan_thread.is_alive():
                    self.scan_thread = threading.Thread(target=self._scan_worker, daemon=True)
                    self.scan_thread.start()
            except ValueError as e:
                messagebox.showerror("Ошибка", str(e))

    def _scan_worker(self):
        max_attempts = int((self.scan_end_mhz - self.scan_start_mhz) * 1000 / self.scan_step_khz) + 2
        while self.is_scanning and self.is_connected and not self.stop_event.is_set():
            try:
                nf = round(self.current_freq_mhz + self.scan_step_khz / 1000.0, 6)
                if nf > self.scan_end_mhz: nf = self.scan_start_mhz
                
                attempts = 0
                while any(abs(nf - skip) < 0.001 for skip in self.skipped_freqs):
                    nf = round(nf + self.scan_step_khz / 1000.0, 6)
                    if nf > self.scan_end_mhz: nf = self.scan_start_mhz
                    attempts += 1
                    if attempts >= max_attempts:
                        self.ui_queue.put(("scan_info", "Весь диапазон частот пропущен"))
                        self.is_scanning = False
                        return
                        
                self.current_freq_mhz = nf
                self.ui_queue.put(("frequency", nf))
                self.sync_frequency()
                
                if self.stop_event.wait(self.scan_speed_ms / 1000.0): break
                
                raw = self.send_command_sync("I1?", wait_response=True, timeout=0.7)
                scan_value = self._parse_hex_response(raw, "I1")
                if scan_value is not None:
                    self.raw_smeter = scan_value
                    self.smeter_value = min(scan_value / 255.0, 1.0)
                    
                if self.smeter_value > self.scan_threshold:
                    freq = self.current_freq_mhz
                    is_nearby = any(abs(item["freq"] - freq) < 0.3 for item in self.found_freqs)
                    if not is_nearby:
                        self.ui_queue.put(("found", freq, self.raw_smeter))
                        self.ui_queue.put(("scan_info", f"Найдено: {freq:.5f} МГц (пауза)"))
                        if self.stop_event.wait(self.scan_hold_time): break
                        if self.is_scanning:
                            self.ui_queue.put(("scan_info", "Идет поиск..."))
            except Exception:
                break

    @staticmethod
    def _parse_hex_response(response, command):
        if not response: return None
        idx = response.find(command)
        if idx < 0 or len(response) < idx + len(command) + 2: return None
        try: return int(response[idx + len(command):idx + len(command) + 2], 16)
        except ValueError: return None

    def _log(self, msg):
        print(f"[LOG {time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def on_closing(self):
        self._closing = True
        self.stop_event.set()
        self.is_scanning = False
        self.disconnect_radio()
        try: self.destroy()
        except Exception: pass
        sys.exit(0)


if __name__ == "__main__":
    app = PCR1000Pro()
    app.mainloop()