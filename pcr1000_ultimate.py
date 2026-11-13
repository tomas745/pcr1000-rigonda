import sys
import threading
import time
import json
import os
import csv
import math
import re
import queue
import random
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import serial
import serial.tools.list_ports

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "pcr1000_profiles.json"

# ============================================================================
# ПАЛИТРЫ ТЕМ
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
DEFAULT_FILTER_FOR_MODE = {"WFM": "230k", "NFM": "15k", "AM": "6k",
                           "LSB": "2.8k", "USB": "2.8k", "CW": "2.8k"}

SMETER_CALIBRATION = [
    (0x00, 0), (0x30, 3), (0x50, 5), (0x70, 7),
    (0x90, 9), (0xB0, 20), (0xD0, 40), (0xF0, 60),
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
# ГАЗОРАЗРЯДНЫЕ ЧАСЫ ИН-14
# ============================================================================
class NixieClockIN14(tk.Canvas):
    def __init__(self, master, theme, width=246, height=40, **kwargs):
        super().__init__(master, width=width, height=height, highlightthickness=0,
                         bg=theme["panel"], **kwargs)
        self.theme = theme
        self.show_utc = False
        self._after_id = None
        self.bind("<Button-1>", self._toggle_tz)
        self._tick()

    def update_theme(self, new_theme):
        self.theme = new_theme
        self.configure(bg=self.theme["panel"])
        self.draw()

    def _toggle_tz(self, event=None):
        self.show_utc = not self.show_utc
        self.draw()

    def _tick(self):
        if not self.winfo_exists(): return
        self.draw()
        self._after_id = self.after(200, self._tick)

    def destroy(self):
        if self._after_id:
            try: self.after_cancel(self._after_id)
            except Exception: pass
            self._after_id = None
        super().destroy()

    def _draw_inverted_two(self, cx, cy, color, width):
        pts = [cx + 5, cy - 8, cx - 5, cy - 8, cx + 5, cy + 1,
               cx + 5, cy + 5, cx + 2, cy + 8, cx - 2, cy + 8, cx - 5, cy + 5]
        self.create_line(pts, fill=color, width=width,
                         capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True)

    def _draw_tube(self, x, y, w, h, digit_char, is_night):
        t = self.theme
        cx = x + w // 2
        cy = y + h // 2 + 2
        self.create_rectangle(x, y + 3, x + w, y + h, fill="#120E0A", outline=t["brass_shadow"], width=1)
        glass_fill = "#0D0907" if is_night else "#211914"
        self.create_arc(x + 2, y + 1, x + w - 2, y + 12, start=0, extent=180,
                        fill=glass_fill, outline="#5E4D3B", width=1)
        self.create_rectangle(x + 2, y + 6, x + w - 2, y + h - 3,
                              fill=glass_fill, outline="#5E4D3B", width=1)
        self.create_rectangle(cx - 2, y, cx + 2, y + 3, fill="#6E5A44", outline="")
        self.create_oval(x + 4, y + 7, x + w - 4, y + h - 5, fill="#3D1200", outline="")
        self.create_oval(x + 6, y + 9, x + w - 6, y + h - 7, fill="#7A2200", outline="")
        self.create_text(cx, cy, text="8", fill="#2A1C16", font=("Consolas", 17, "bold"))
        if digit_char == "5":
            self._draw_inverted_two(cx, cy, "#D83A00", 4)
            self._draw_inverted_two(cx, cy, "#FF6D00", 2)
            self._draw_inverted_two(cx, cy, "#FFD180", 1)
        else:
            self.create_text(cx + 1, cy + 1, text=digit_char, fill="#D83A00", font=("Consolas", 17, "bold"))
            self.create_text(cx, cy, text=digit_char, fill="#FF6D00", font=("Consolas", 17, "bold"))
            self.create_text(cx, cy, text=digit_char, fill="#FFD180", font=("Consolas", 15, "bold"))
        for gx in range(x + 5, x + w - 4, 4):
            self.create_line(gx, y + 6, gx, y + h - 4, fill="#1E1610", width=1, stipple="gray50")
        self.create_line(x + 4, y + 7, x + 4, y + h - 6, fill="#FFFFFF", width=1, stipple="gray50")
        self.create_rectangle(x + 1, y + h - 4, x + w - 1, y + h, fill="#2B1D12", outline=t["brass_shadow"])

    def draw(self):
        self.delete("all")
        is_night = (self.theme is THEMES["night"])
        now = time.gmtime() if self.show_utc else time.localtime()
        time_str = f"{now.tm_hour:02d}{now.tm_min:02d}{now.tm_sec:02d}"
        dot_on = (time.time() % 1.0) < 0.55
        positions = [4, 33, 73, 102, 142, 171]
        for idx, x0 in enumerate(positions):
            self._draw_tube(x0, 3, 26, 34, time_str[idx], is_night)
        for dot_x in (66, 135):
            for dot_y in (14, 26):
                self.create_oval(dot_x - 3, dot_y - 3, dot_x + 3, dot_y + 3,
                                 fill="#180D08", outline="#4A3828")
                if dot_on:
                    self.create_oval(dot_x - 3, dot_y - 3, dot_x + 3, dot_y + 3, fill="#FF5500", outline="")
                    self.create_oval(dot_x - 1, dot_y - 1, dot_x + 1, dot_y + 1, fill="#FFE082", outline="")
        tz_label = "UTC" if self.show_utc else "LOC"
        tz_col = "#FF8F00" if self.show_utc else self.theme["muted"]
        self.create_text(221, 20, text=tz_label, fill=tz_col, font=("Consolas", 8, "bold"))


# ============================================================================
# ЛАМПА 6Е5С (h=200)
# ============================================================================
class MagicEyeMeter(tk.Canvas):
    def __init__(self, master, theme, width=260, height=200, **kwargs):
        super().__init__(master, width=width, height=height, highlightthickness=0,
                         bg=theme["panel"], **kwargs)
        self.theme = theme
        self.target_value = 0.0
        self.smooth_value = 0.0
        self.is_powered = False
        self.heater_level = 0.0
        self.phosphor_level = 0.0
        self._anim_after_id = None
        self.bind("<Configure>", lambda e: self.draw())
        self._animate()

    def update_theme(self, new_theme):
        self.theme = new_theme
        self.configure(bg=self.theme["panel"])
        self.draw()

    def set_power(self, state):
        self.is_powered = bool(state)
        if not self.is_powered: self.target_value = 0.0

    def set_value(self, value):
        self.target_value = float(max(0, min(255, value)))

    @staticmethod
    def _lerp_color(hex1, hex2, t):
        t = max(0.0, min(1.0, t))
        c1 = tuple(int(hex1[i:i+2], 16) for i in (1, 3, 5))
        c2 = tuple(int(hex2[i:i+2], 16) for i in (1, 3, 5))
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _animate(self):
        needs_redraw = False
        if self.is_powered:
            if self.heater_level < 1.0:
                self.heater_level = min(1.0, self.heater_level + 0.035); needs_redraw = True
            if self.heater_level > 0.35 and self.phosphor_level < 1.0:
                self.phosphor_level = min(1.0, self.phosphor_level + 0.045); needs_redraw = True
        else:
            if self.phosphor_level > 0.0:
                self.phosphor_level = max(0.0, self.phosphor_level - 0.06); needs_redraw = True
            if self.heater_level > 0.0:
                self.heater_level = max(0.0, self.heater_level - 0.025); needs_redraw = True
        diff = self.target_value - self.smooth_value
        if abs(diff) > 0.1:
            speed = 0.22 if diff > 0 else 0.10
            self.smooth_value += diff * speed
            needs_redraw = True
        if needs_redraw or self.is_powered:
            self.draw()
        self._anim_after_id = self.after(33, self._animate)

    def draw(self):
        self.delete("all")
        w = self.winfo_width() or 260
        h = self.winfo_height() or 200
        if w < 50 or h < 50: return
        t = self.theme
        cx, cy = w // 2, h // 2 - 6
        r = min(w, h) // 2 - 28
        if r < 30: r = 30
        self.create_oval(cx - r - 16, cy - r - 16, cx + r + 16, cy + r + 16,
                         fill="#14100D", outline=t["brass_shadow"], width=4)
        self.create_oval(cx - r - 11, cy - r - 11, cx + r + 11, cy + r + 11,
                         fill="#090A08", outline=t["brass"], width=2)
        dark_glass = "#070C07" if self.theme is THEMES["night"] else "#182218"
        self.create_oval(cx - r, cy - r, cx + r, cy + r, fill=dark_glass, outline="")
        if self.phosphor_level > 0.01:
            p = self.phosphor_level
            edge_col = self._lerp_color(dark_glass, "#0B4D18", p)
            mid_col = self._lerp_color(dark_glass, "#18C943", p)
            core_col = self._lerp_color(dark_glass, "#80FF9E", p)
            steps = 12
            for i in range(steps):
                frac = i / (steps - 1)
                curr_r = r * (1.0 - frac * 0.65)
                if frac < 0.6: col = self._lerp_color(edge_col, mid_col, frac / 0.6)
                else: col = self._lerp_color(mid_col, core_col, (frac - 0.6) / 0.4)
                self.create_oval(cx - curr_r, cy - curr_r, cx + curr_r, cy + curr_r, fill=col, outline="")
            norm = max(0.0, min(1.0, self.smooth_value / 235.0))
            shadow_angle = 96.0 * max(0.0, 1.0 - (norm ** 0.85))
            if shadow_angle > 1.0:
                soft_col = self._lerp_color(dark_glass, mid_col, 0.35)
                self.create_arc(cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1,
                                start=270 - (shadow_angle + 6) / 2, extent=shadow_angle + 6,
                                fill=soft_col, outline="", style=tk.PIESLICE)
                self.create_arc(cx - r - 1, cy - r - 1, cx + r + 1, cy + r + 1,
                                start=270 - shadow_angle / 2, extent=shadow_angle,
                                fill=dark_glass, outline="", style=tk.PIESLICE)
            elif norm > 0.92:
                overlap = (norm - 0.92) * 140.0
                overlap_col = self._lerp_color(core_col, "#D8FFE0", p)
                self.create_arc(cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2,
                                start=270 - overlap / 2, extent=overlap,
                                fill=overlap_col, outline="", style=tk.PIESLICE)
        inner_r = max(12, r // 3)
        if self.heater_level > 0.05:
            glow_r = inner_r + 3
            heater_col = self._lerp_color("#1A0800", "#FF6A00", self.heater_level)
            self.create_oval(cx - glow_r, cy - glow_r, cx + glow_r, cy + glow_r,
                             fill="", outline=heater_col, width=3)
            self.create_arc(cx - inner_r - 2, cy - inner_r - 2,
                            cx + inner_r + 2, cy + inner_r + 2,
                            start=215, extent=110, outline="#FFB347", width=2, style=tk.ARC)
        self.create_oval(cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r,
                         fill="#1C1815", outline="#4A4238", width=2)
        self.create_oval(cx - inner_r + 4, cy - inner_r + 4,
                         cx + inner_r - 4, cy + inner_r - 4,
                         fill="#110E0C", outline="#2E2924", width=1)
        self.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill="#5C5245", outline="")
        self.create_arc(cx - r + 6, cy - r + 6, cx + r - 6, cy + r - 6,
                        start=110, extent=55, outline="#FFFFFF", width=2, style=tk.ARC)
        self.create_arc(cx - r + 11, cy - r + 11, cx + r - 11, cy + r - 11,
                        start=122, extent=30, outline="#C8E6C9", width=1, style=tk.ARC)
        cal = calibrate_smeter(self.smooth_value) if self.is_powered else 0
        if cal >= 60: s_level = "S9+60"
        elif cal >= 40: s_level = "S9+40"
        elif cal >= 20: s_level = "S9+20"
        elif cal >= 9: s_level = "S9"
        elif cal > 0.5: s_level = f"S{int(round(cal))}"
        else: s_level = "S0"
        text_bg = "#0A140B" if self.theme is THEMES["night"] else "#E0E8D0"
        self.create_rectangle(cx - 48, h - 26, cx + 48, h - 6, fill=text_bg, outline=t["brass_shadow"])
        self.create_text(cx, h - 16, text=f"{s_level} ({int(self.smooth_value)})",
                         fill=t["text"], font=("Consolas", 10, "bold"))


# ============================================================================
# S-МЕТР (h=200)
# ============================================================================
class ClassicSMeter(tk.Canvas):
    def __init__(self, master, theme, width=260, height=200, **kwargs):
        super().__init__(master, width=width, height=height, highlightthickness=0,
                         bg=theme["panel"], **kwargs)
        self.theme = theme
        self.target_value = 0.0
        self.current_pos = 0.0
        self.velocity = 0.0
        self.is_powered = False
        self.backlight_level = 0.0
        self.bind("<Configure>", lambda e: self.draw_face())
        self._animate()

    def update_theme(self, new_theme):
        self.theme = new_theme
        self.configure(bg=self.theme["panel"])
        self.draw_face()

    def set_power(self, state):
        self.is_powered = bool(state)
        if not self.is_powered: self.target_value = 0.0

    def set_value(self, value):
        self.target_value = float(max(0, min(255, int(value))))

    @staticmethod
    def _lerp_color(hex1, hex2, t):
        t = max(0.0, min(1.0, t))
        c1 = tuple(int(hex1[i:i+2], 16) for i in (1, 3, 5))
        c2 = tuple(int(hex2[i:i+2], 16) for i in (1, 3, 5))
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _animate(self):
        needs_redraw = False
        if self.is_powered and self.backlight_level < 1.0:
            self.backlight_level = min(1.0, self.backlight_level + 0.05); needs_redraw = True
        elif not self.is_powered and self.backlight_level > 0.0:
            self.backlight_level = max(0.0, self.backlight_level - 0.07); needs_redraw = True
        force = (self.target_value - self.current_pos) * 0.14
        self.velocity = (self.velocity + force) * 0.68
        if abs(self.velocity) > 0.05 or abs(self.target_value - self.current_pos) > 0.1:
            self.current_pos += self.velocity
            self.current_pos = max(-3.0, min(260.0, self.current_pos))
            needs_redraw = True
        if needs_redraw:
            self.draw_face()
        self.after(30, self._animate)

    def draw_face(self):
        self.delete("all")
        w = self.winfo_width() or 260
        h = self.winfo_height() or 200
        if w < 100 or h < 100: return
        t = self.theme
        cx = w // 2
        cy = h - 22
        r = max(45, min(w // 2 - 18, h - 36))
        self.create_oval(cx - r - 12, cy - r - 12, cx + r + 12, cy + r + 12,
                         fill=t["wood_dark"], outline=t["brass_shadow"], width=4)
        off_bg = "#D6CEB8" if self.theme is THEMES["night"] else "#EFE7D1"
        on_bg = "#FFE8A3" if self.theme is THEMES["night"] else "#FFF7DC"
        face_bg = self._lerp_color(off_bg, on_bg, self.backlight_level)
        self.create_oval(cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6,
                         fill=face_bg, outline=t["brass"], width=2)
        if self.backlight_level > 0.05:
            glow_col = self._lerp_color(face_bg, "#FFBA42", self.backlight_level * 0.35)
            self.create_oval(cx - r * 0.75, cy - r - 4, cx + r * 0.75, cy - r * 0.1, fill=glow_col, outline="")
        self.create_rectangle(0, cy + 2, w, h + 10, fill=t["panel"], outline="")
        self.create_line(cx - r - 8, cy, cx + r + 8, cy, fill=t["brass_shadow"], width=3)
        labels = ["0", "1", "3", "5", "7", "9", "+20", "+40", "+60"]
        total_ticks = (len(labels) - 1) * 2
        for i in range(total_ticks + 1):
            angle_deg = 180 - i * (180.0 / total_ticks)
            angle_rad = math.radians(angle_deg)
            cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
            is_major = (i % 2 == 0)
            tick_len = 12 if is_major else 6
            tick_w = 2 if is_major else 1
            tick_col = "#B71C1C" if i >= 20 else "#3E2723"
            self.create_line(cx + (r - 10) * cos_a, cy - (r - 10) * sin_a,
                             cx + (r - 10 - tick_len) * cos_a, cy - (r - 10 - tick_len) * sin_a,
                             fill=tick_col, width=tick_w)
            if is_major:
                lbl = labels[i // 2]
                self.create_text(cx + (r - 32) * cos_a, cy - (r - 32) * sin_a,
                                 text=lbl, fill=tick_col, font=("Arial", 9, "bold"))
        self.create_text(cx, cy - r * 0.42, text="S-UNITS   dB",
                         fill="#5D4037", font=("Georgia", 8, "bold"))
        red_points = []
        for i in range(41):
            db = 20.0 + i
            angle_rad = math.radians(180.0 - (db / 60.0) * 180.0)
            red_points.extend([cx + (r - 15) * math.cos(angle_rad),
                               cy - (r - 15) * math.sin(angle_rad)])
        if len(red_points) >= 4:
            self.create_line(red_points, fill="#C62828", width=5, capstyle=tk.ROUND, smooth=True)
        calibrated = calibrate_smeter(max(0.0, self.current_pos))
        angle_rad = math.radians(180 - (calibrated / 60.0) * 180)
        cos_a, sin_a = math.cos(angle_rad), math.sin(angle_rad)
        x_tip = cx + (r - 14) * cos_a
        y_tip = cy - (r - 14) * sin_a
        x_tail = cx - (r // 5) * cos_a
        y_tail = cy + (r // 5) * sin_a
        self.create_line(x_tail + 2, y_tail + 3, x_tip + 2, y_tip + 3,
                         fill="#8D8472", width=2, capstyle=tk.ROUND)
        self.create_line(x_tail, y_tail, x_tip, y_tip,
                         fill=t["needle"], width=2, capstyle=tk.ROUND)
        self.create_oval(cx - 7, cy - 7, cx + 7, cy + 7,
                         fill="#2B160A", outline=t["brass"], width=2)
        self.create_oval(cx - 2, cy - 2, cx + 2, cy + 2,
                         fill=t["brass"], outline="")
        self.create_arc(cx - r + 10, cy - r + 10, cx + r - 10, cy + r - 10,
                        start=135, extent=42, outline="#FFFFFF", width=2, style=tk.ARC)


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
    def __init__(self, master, theme, command, width=96, height=96, **kwargs):
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
# ШКАЛА С ГОРОДАМИ (h=215)
# ============================================================================
class PhotoRealDialDashboard(tk.Canvas):
    def __init__(self, master, theme, on_freq_select=None, **kwargs):
        super().__init__(master, height=215, highlightthickness=0, bg=theme["glass_bg"], **kwargs)
        self.theme = theme
        self.current_freq = 99.6
        self.on_freq_select = on_freq_select
        self.is_powered = False
        self.backlight = 0.0
        self.bind("<Configure>", self.draw)
        self.bind("<Button-1>", self._on_click_or_drag)
        self.bind("<B1-Motion>", self._on_click_or_drag)
        self._animate_backlight()

    def update_theme(self, new_theme):
        self.theme = new_theme
        self.configure(bg=self.theme["glass_bg"])
        self.draw()

    def set_power(self, state): self.is_powered = bool(state)
    def set_frequency(self, freq):
        self.current_freq = freq
        self.draw()

    def _animate_backlight(self):
        target = 1.0 if self.is_powered else 0.0
        if abs(self.backlight - target) > 0.01:
            self.backlight += (target - self.backlight) * 0.08
            self.draw()
        self.after(35, self._animate_backlight)

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

    def _on_click_or_drag(self, event):
        w = self.winfo_width() or 1000
        x_left, x_right = 100, w - 100
        if x_right <= x_left: return
        pos = max(0.0, min(1.0, (event.x - x_left) / (x_right - x_left)))
        fmin, fmax, logarithmic = self._band_for(self.current_freq)
        if logarithmic:
            new_freq = math.exp(math.log(fmin) + pos * (math.log(fmax) - math.log(fmin)))
        else:
            new_freq = fmin + pos * (fmax - fmin)
        self.current_freq = round(new_freq, 4)
        self.draw()
        if self.on_freq_select: self.on_freq_select(self.current_freq)

    @staticmethod
    def _lerp_color(hex1, hex2, t):
        t = max(0.0, min(1.0, t))
        c1 = tuple(int(hex1[i:i+2], 16) for i in (1, 3, 5))
        c2 = tuple(int(hex2[i:i+2], 16) for i in (1, 3, 5))
        r = int(c1[0] + (c2[0] - c1[0]) * t)
        g = int(c1[1] + (c2[1] - c1[1]) * t)
        b = int(c1[2] + (c2[2] - c1[2]) * t)
        return f"#{r:02x}{g:02x}{b:02x}"

    def draw(self, event=None):
        self.delete("all")
        w = self.winfo_width() or 1000
        h = self.winfo_height() or 215
        if w < 100 or h < 100: return
        t = self.theme
        is_night = (self.theme is THEMES["night"])
        if is_night:
            glass_base = "#120F0A"; lamp_warm = "#5C3A12"; lamp_hot = "#9E641E"; center_tint = "#291B0B"
            logo_dim, logo_lit = "#8C733A", "#F2C96B"
            line_dim, line_lit = "#2E4D31", "#55A65B"
            text_dim, text_lit = "#7A6A4B", "#F5E2B8"
            tick_dim, tick_lit = "#8C733A", "#FFE082"
            active_band_col = "#FFD54F"
        else:
            glass_base = "#E6DBC0"; lamp_warm = "#F5E3B3"; lamp_hot = "#FFF2C9"; center_tint = "#EFE5CA"
            logo_dim, logo_lit = "#6E5323", "#4A320C"
            line_dim, line_lit = "#5C7A62", "#264D31"
            text_dim, text_lit = "#5E523F", "#1E2B20"
            tick_dim, tick_lit = "#5C4928", "#2B1E08"
            active_band_col = "#B71C1C"
        self.create_rectangle(0, 0, w, h, fill=glass_base, outline="")
        lvl = getattr(self, "backlight", 1.0 if getattr(self, "is_powered", True) else 0.0)
        if lvl > 0.02:
            steps = 18
            max_rx = w * 0.34
            max_ry = h * 0.72
            for lamp_x in (32, w - 32):
                for i in range(steps):
                    frac = i / (steps - 1)
                    rx = max_rx * (1.0 - frac * 0.75)
                    ry = max_ry * (1.0 - frac * 0.65)
                    if frac < 0.7: col = self._lerp_color(glass_base, lamp_warm, (frac / 0.7) * lvl)
                    else: col = self._lerp_color(lamp_warm, lamp_hot, ((frac - 0.7) / 0.3) * lvl)
                    self.create_oval(lamp_x - rx, h // 2 - ry, lamp_x + rx, h // 2 + ry, fill=col, outline="")
            center_glow = self._lerp_color(glass_base, center_tint, lvl)
            self.create_oval(w * 0.2, 20, w * 0.8, h - 20, fill=center_glow, outline="")
        self.create_line(10, 10, w - 10, 10, fill="#8C6D2E" if is_night else "#FFFDF5", width=1)
        self.create_line(10, h - 10, w - 10, h - 10, fill="#3D2E12" if is_night else "#9E8B66", width=2)
        self.create_rectangle(1, 1, w - 1, h - 1, outline=t["brass"], width=3)
        for (x, y) in [(9, 9), (w - 9, 9), (9, h - 9), (w - 9, h - 9)]:
            self.create_oval(x - 3, y - 3, x + 3, y + 3, fill=t["brass_shadow"], outline=t["brass"])
        font_size = 24 if w > 800 else 16
        logo_col = self._lerp_color(logo_dim, logo_lit, lvl)
        self.create_text(w // 2, int(h * 0.13), text="Ригонда", fill=logo_col,
                         font=("Georgia", font_size, "bold", "italic"))
        active_band = self.get_active_band(self.current_freq)
        bands_y = {"КВI": int(h * 0.29), "КВII": int(h * 0.40), "ДВ": int(h * 0.52), "СВ": int(h * 0.63), "УКВ": int(h * 0.79)}
        for b_name, y in bands_y.items():
            is_active = (b_name == active_band)
            b_col = active_band_col if (is_active and lvl > 0.2) else self._lerp_color(line_dim, line_lit, lvl)
            self.create_line(80, y, w - 80, y, fill=b_col, width=2 if is_active else 1)
            self.create_text(45, y, text=b_name, fill=b_col, font=("Arial", 10, "bold"))
            self.create_text(w - 45, y, text=b_name, fill=b_col, font=("Arial", 10, "bold"))
        city_col = self._lerp_color(text_dim, text_lit, lvl)
        if w >= 700:
            fs = max(7, min(9, w // 120))
            cities_kv = ["МОСКВА", "МИНСК", "КИЕВ", "ТАШКЕНТ", "БАЛТИКА", "ПЕКИН", "ЛОНДОН", "ПАРИЖ"]
            cities_mw = ["БЕРЛИН", "ОДЕССА", "РИГА", "ВАРШАВА", "ПРАГА", "МАДРИД", "РИМ", "ЖЕНЕВА"]
            y_kv = bands_y["КВI"] + 12
            y_mw = bands_y["ДВ"] + 12
            for i, city in enumerate(cities_kv):
                x = 140 + i * ((w - 280) // (len(cities_kv) - 1))
                self.create_text(x, y_kv, text=city, fill=city_col,
                                 font=("Arial", fs, "bold" if not is_night else "normal"))
                self.create_line(x, bands_y["КВI"], x, bands_y["КВI"] + 4, fill=city_col)
            for i, city in enumerate(cities_mw):
                x = 120 + i * ((w - 240) // (len(cities_mw) - 1))
                self.create_text(x, y_mw, text=city, fill=city_col,
                                 font=("Arial", fs, "bold" if not is_night else "normal"))
                self.create_line(x, bands_y["ДВ"], x, bands_y["ДВ"] + 4, fill=city_col)
        y = bands_y.get(active_band, int(h * 0.40))
        fmin, fmax, logarithmic = self._band_for(self.current_freq)
        x_left, x_right = 100, w - 100
        tick_col = self._lerp_color(tick_dim, tick_lit, lvl)
        if logarithmic:
            for i in range(9):
                fraction = i / 8
                freq_tick = math.exp(math.log(fmin) + fraction * (math.log(fmax) - math.log(fmin)))
                x = x_left + fraction * (x_right - x_left)
                self.create_line(x, y, x, y - 7, fill=tick_col, width=1)
                if i % 2 == 0:
                    self.create_text(x, y - 14, text=f"{freq_tick:.2f}", fill=city_col, font=("Consolas", 8, "bold"))
        else:
            for i in range(11):
                fraction = i / 10
                freq_tick = fmin + fraction * (fmax - fmin)
                x = x_left + fraction * (x_right - x_left)
                self.create_line(x, y, x, y - 7, fill=tick_col, width=1)
                if i % 2 == 0:
                    self.create_text(x, y - 14, text=f"{freq_tick:.1f}", fill=city_col, font=("Consolas", 8, "bold"))
        position = (math.log(self.current_freq) - math.log(fmin)) / (math.log(fmax) - math.log(fmin)) if logarithmic else (self.current_freq - fmin) / (fmax - fmin)
        position = max(0.0, min(1.0, position))
        x = x_left + position * (x_right - x_left)
        if lvl > 0.2:
            halo_col = "#4A2508" if is_night else "#D9B36C"
            self.create_rectangle(x - 5, y - 24, x + 5, y + 10, fill=halo_col, outline="")
        self.create_line(x, y - 22, x, y + 8, fill="#240504", width=5)
        self.create_line(x, y - 22, x, y + 8, fill="#E53935", width=3)
        self.create_line(x, y - 23, x, y - 19, fill="#FFCC80", width=2)


# ============================================================================
# ГЛАВНОЕ ПРИЛОЖЕНИЕ
# ============================================================================
class PCR1000Pro(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Радиола Ригонда-Моно & IC-PCR1000")
        self.geometry("1360x900")
        self.minsize(1050, 720)

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

        self._i1_poll_timer = None
        self._expecting_smeter = False
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
                elif kind == "connected":
                    self._on_connected_ui()
                elif kind == "disconnected":
                    self._on_disconnected_ui()
                elif kind == "error":
                    messagebox.showerror("Ошибка", event[1])
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self.after(40, self.process_ui_queue)

    def on_vfo_wheel(self, event):
        focused = self.focus_get()
        if focused and focused.winfo_class() in ('Entry', 'Text', 'TEntry', 'CTkEntry', 'CTkComboBox'):
            return
        if event.delta > 0 or event.num == 4: self._step_freq(1)
        elif event.delta < 0 or event.num == 5: self._step_freq(-1)

    def _on_space_key(self, event=None):
        focused = self.focus_get()
        if focused and focused.winfo_class() in ("Entry", "Text", "TEntry", "CTkEntry"):
            return
        self.toggle_scan()
        return "break"

    def _set_mode_from_key(self, mode): self._on_mode_key_press(mode)
    def stop_scan(self):
        if self.is_scanning: self.toggle_scan()

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
            if isinstance(widget, (ctk.CTkFrame, ctk.CTkScrollableFrame, ctk.CTk)):
                try:
                    if widget.cget("fg_color") != "transparent":
                        widget.configure(fg_color=t["panel"])
                except Exception:
                    pass
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
        if hasattr(self, "nixie_clock"): self.nixie_clock.update_theme(t)
        for key in self.mode_keys.values(): key.update_theme(t)
        self.update_mode_buttons(self.current_mode)

    def _switch_meter_type(self, choice):
        if choice == "Лампа 6Е5С":
            self.classic_meter.grid_remove()
            self.magic_eye.grid(row=1, column=0, pady=(2, 4), padx=4, sticky="nsew")
            self._active_meter = self.magic_eye
        else:
            self.magic_eye.grid_remove()
            self.classic_meter.grid(row=1, column=0, pady=(2, 4), padx=4, sticky="nsew")
            self._active_meter = self.classic_meter
        if self._active_meter: self._active_meter.set_value(self.raw_smeter)

    def toggle_side_panel(self, panel, button, title, row, column):
        if panel.winfo_viewable():
            panel.grid_remove()
            button.configure(text=f"{title}  +")
        else:
            panel.grid(row=row, column=column, padx=2, pady=2, sticky="nsew")
            button.configure(text=f"{title}  −")

    def _on_dial_scale_drag(self, freq):
        if self.is_scanning: return
        self.current_freq_mhz = freq
        self._update_freq_widgets()
        if self.is_connected: self.sync_frequency()

    def _build_ui(self):
        t = self.theme
        self.top_wood = PhotoRealWoodPanel(self, theme=t, height=20)
        self.top_wood.pack(fill="x", side="top")

        self.top_frame = ctk.CTkFrame(self, height=40, fg_color=t["panel"], corner_radius=0)
        self.top_frame.pack(fill="x")

        self.lbl_title = ctk.CTkLabel(self.top_frame, text="📻 РИГОНДА-МОНО (PCR1000)",
                                      font=("Arial", 16, "bold"), text_color=t["brass"])
        self.lbl_title.pack(side="left", padx=(12, 8))

        self.port_cb = ctk.CTkComboBox(self.top_frame, values=[], width=120, height=28,
                                       fg_color=t["entry_bg"], border_color=t["border"],
                                       text_color=t["text"], button_color=t["border"], button_hover_color=t["brass_shadow"])
        self.port_cb.pack(side="left", padx=4)

        self.btn_refresh = ctk.CTkButton(self.top_frame, text="⟳", width=30, height=28,
                                         fg_color=t["panel"], hover_color=t["border"], text_color=t["text"],
                                         border_color=t["border"], border_width=1, command=self.refresh_ports)
        self.btn_refresh.pack(side="left", padx=4)

        self.btn_connect = ctk.CTkButton(self.top_frame, text="ВКЛ РАДИО", width=110, height=28,
                                         fg_color=t["brass"], hover_color="#9E7F30", text_color="#000000",
                                         font=("Arial", 10, "bold"), command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=8)

        self.btn_theme = ctk.CTkButton(self.top_frame, text="☀/☾", width=36, height=28,
                                       fg_color=t["panel"], hover_color=t["border"], text_color=t["text"],
                                       border_color=t["border"], border_width=1, command=self.toggle_theme)
        self.btn_theme.pack(side="left", padx=4)
        add_tooltip(self.btn_theme, "Переключить дневную/ночную тему")

        self.nixie_clock = NixieClockIN14(self.top_frame, theme=t)
        self.nixie_clock.pack(side="left", padx=(14, 4), pady=2)
        add_tooltip(self.nixie_clock, "Газоразрядные часы ИН-14 (клик: Местное / UTC время)")

        self.lbl_status = ctk.CTkLabel(self.top_frame, text="● СЕТЬ ВЫКЛ", font=("Arial", 10, "bold"), text_color=t["danger"])
        self.lbl_status.pack(side="right", padx=12)

        center_frame = ctk.CTkFrame(self, fg_color="transparent")
        center_frame.pack(fill="x", expand=False, padx=12, pady=2)
        center_frame.grid_columnconfigure(0, weight=0, minsize=190)
        center_frame.grid_columnconfigure(1, weight=1)
        center_frame.grid_columnconfigure(2, weight=0, minsize=170)
        center_frame.grid_rowconfigure(0, weight=0)

        indicator_frame = ctk.CTkFrame(center_frame, fg_color=t["panel"], corner_radius=8, border_width=2, border_color=t["brass"])
        indicator_frame.grid(row=0, column=0, padx=(0, 6), pady=2, sticky="n")
        indicator_frame.grid_columnconfigure(0, weight=1)
        indicator_frame.grid_rowconfigure(0, weight=0)
        indicator_frame.grid_rowconfigure(1, weight=0)

        self.meter_toggle = ctk.CTkSegmentedButton(indicator_frame, values=["Лампа 6Е5С", "Стрелка"],
                                                   command=self._switch_meter_type, fg_color=t["panel"],
                                                   selected_color=t["accent"], text_color=t["text"], font=("Arial", 9, "bold"))
        self.meter_toggle.grid(row=0, column=0, pady=(6, 3), padx=6, sticky="ew")
        self.meter_toggle.set("Лампа 6Е5С")

        self.magic_eye = MagicEyeMeter(indicator_frame, theme=t, width=260, height=200)
        self.classic_meter = ClassicSMeter(indicator_frame, theme=t, width=260, height=200)
        self._switch_meter_type("Лампа 6Е5С")

        self.dial_scale = PhotoRealDialDashboard(center_frame, theme=t, on_freq_select=self._on_dial_scale_drag)
        self.dial_scale.grid(row=0, column=1, sticky="nsew", pady=2)

        right_vfo = ctk.CTkFrame(center_frame, fg_color=t["panel"], corner_radius=4, border_width=1, border_color=t["brass"])
        right_vfo.grid(row=0, column=2, padx=(6, 0), pady=2, sticky="n")

        vfo_text = ctk.CTkFrame(right_vfo, fg_color=t["entry_bg"], corner_radius=2, border_width=1, border_color=t["brass"])
        vfo_text.pack(padx=6, pady=(6, 3), fill="x")

        self.lbl_vfo = ctk.CTkLabel(vfo_text, text="99.60000", font=("Consolas", 26, "bold"), text_color=t["glass_green"])
        self.lbl_vfo.pack(pady=(3, 0))

        self.lbl_vfo_info = ctk.CTkLabel(vfo_text, text="УКВ  |  Шаг: 1 кГц", font=("Arial", 8, "bold"), text_color=t["muted"])
        self.lbl_vfo_info.pack(pady=(0, 3))

        self.entry_freq = ctk.CTkEntry(
            vfo_text, width=130, height=26, justify="center",
            font=("Consolas", 12), placeholder_text="Частота, МГц"
        )
        self.entry_freq.insert(0, "99.60000")
        self.entry_freq.pack(pady=(2, 3))
        self.entry_freq.bind("<Return>", lambda event: self.apply_settings())
        self.btn_apply_freq = ctk.CTkButton(
            vfo_text, text="УСТАНОВИТЬ", width=110, height=24,
            command=self.apply_settings, fg_color=t["btn_bg"],
            hover_color=t["btn_hover"], text_color="#000000",
            font=("Arial", 9, "bold")
        )
        self.btn_apply_freq.pack(pady=(0, 4))

        step_row = ctk.CTkFrame(right_vfo, fg_color="transparent")
        step_row.pack(pady=3)

        self.btn_step_down = ctk.CTkButton(step_row, text="−", width=28, height=28, fg_color=t["btn_bg"],
                                           hover_color=t["btn_hover"], text_color="#000000", border_color=t["brass"],
                                           border_width=1, font=("Arial", 14, "bold"), command=lambda: self._step_freq(-1))
        self.btn_step_down.pack(side="left", padx=2)

        self.step_vfo_cb = ctk.CTkComboBox(step_row, values=list(VFO_STEPS.keys()), width=72, height=24, font=("Arial", 9),
                                           fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"],
                                           button_color=t["border"], button_hover_color=t["brass_shadow"],
                                           command=self._on_step_change)
        self.step_vfo_cb.set("1 кГц")
        self.step_vfo_cb.pack(side="left", padx=2)

        self.btn_step_up = ctk.CTkButton(step_row, text="+", width=28, height=28, fg_color=t["btn_bg"],
                                         hover_color=t["btn_hover"], text_color="#000000", border_color=t["brass"],
                                         border_width=1, font=("Arial", 14, "bold"), command=lambda: self._step_freq(1))
        self.btn_step_up.pack(side="left", padx=2)

        self.vfo_dial = RigondaVFO_Dial(right_vfo, theme=t, command=self._on_dial_move, width=96, height=96)
        self.vfo_dial.pack(pady=(2, 4))

        p2k_deck = ctk.CTkFrame(self, fg_color=t["panel"], height=44, corner_radius=0, border_width=1, border_color=t["border"])
        p2k_deck.pack(fill="x", padx=12, pady=2)
        p2k_inner = tk.Frame(p2k_deck, bg=t["panel"])
        p2k_inner.pack(expand=True, pady=4)

        modes = ["LSB", "USB", "AM", "CW", "NFM", "WFM"]
        for i, mode in enumerate(modes):
            key = PhotoRealP2KButton(p2k_inner, theme=t, text=mode, command=self._on_mode_key_press)
            key.grid(row=0, column=i, padx=3)
            self.mode_keys[mode] = key
        self.update_mode_buttons("WFM")

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=12, pady=2)
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(0, weight=0)
        main.grid_rowconfigure(1, weight=1)

        self.btn_adv_panel = ctk.CTkButton(main, text="НАСТРОЙКИ  −", height=24, fg_color=t["panel"],
                                           text_color=t["text"], border_color=t["brass"], border_width=1,
                                           font=("Arial", 10, "bold"),
                                           command=lambda: self.toggle_side_panel(self.left_frame, self.btn_adv_panel, "НАСТРОЙКИ", 1, 0))
        self.btn_adv_panel.grid(row=0, column=0, sticky="ew", padx=(0, 2))

        self.btn_scan_panel = ctk.CTkButton(main, text="СКАНЕР  −", height=24, fg_color=t["panel"],
                                            text_color=t["text"], border_color=t["brass"], border_width=1,
                                            font=("Arial", 10, "bold"),
                                            command=lambda: self.toggle_side_panel(self.right_frame, self.btn_scan_panel, "СКАНЕР", 1, 1))
        self.btn_scan_panel.grid(row=0, column=1, sticky="ew", padx=(2, 0))

        self.left_frame = ctk.CTkScrollableFrame(main, corner_radius=6, border_width=1,
                                                 fg_color=t["panel"], border_color=t["border"])
        self.left_frame.grid(row=1, column=0, padx=(0, 2), pady=2, sticky="nsew")

        def add_left_label(parent, text):
            lbl = ctk.CTkLabel(parent, text=text.upper(), font=("Arial", 8, "bold"), text_color=t["brass"])
            lbl.pack(anchor="w", padx=4, pady=(4, 1))

        # Строка 1: Громкость НЧ и Шумоподавитель рядом в 2 колонки
        row_audio = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        row_audio.pack(fill="x", padx=4, pady=(2, 1))
        row_audio.grid_columnconfigure(0, weight=1)
        row_audio.grid_columnconfigure(1, weight=1)

        col_vol = ctk.CTkFrame(row_audio, fg_color="transparent")
        col_vol.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        add_left_label(col_vol, "Громкость НЧ")
        self.slider_vol = ctk.CTkSlider(col_vol, from_=0, to=255, height=12, width=170,
                                        fg_color=t["entry_bg"], progress_color=t["brass"],
                                        button_color=t["brass"], button_hover_color=t["accent"],
                                        command=self.set_volume)
        self.slider_vol.set(self.current_volume)
        self.slider_vol.pack(pady=1, anchor="w")

        col_sql = ctk.CTkFrame(row_audio, fg_color="transparent")
        col_sql.grid(row=0, column=1, sticky="ew", padx=(2, 0))
        add_left_label(col_sql, "Шумоподавитель")
        self.slider_sql = ctk.CTkSlider(col_sql, from_=0, to=255, height=12, width=170,
                                        fg_color=t["entry_bg"], progress_color=t["brass"],
                                        button_color=t["brass"], button_hover_color=t["accent"],
                                        command=self.set_squelch)
        self.slider_sql.set(self.current_squelch)
        self.slider_sql.pack(pady=1, anchor="w")

        # Строка 2: Фильтр ПЧ и Сдвиг ПЧ в 2 колонки
        row_if = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        row_if.pack(fill="x", padx=4, pady=(3, 1))
        row_if.grid_columnconfigure(0, weight=1)
        row_if.grid_columnconfigure(1, weight=1)

        col_filter = ctk.CTkFrame(row_if, fg_color="transparent")
        col_filter.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        add_left_label(col_filter, "Фильтр ПЧ")
        self.filter_cb = ctk.CTkComboBox(col_filter, values=list(FILTER_CODES.keys()), width=100, height=26,
                                         font=("Arial", 9), fg_color=t["entry_bg"], border_color=t["border"],
                                         text_color=t["text"], button_color=t["border"], button_hover_color=t["brass_shadow"],
                                         command=self._on_filter_change)
        self.filter_cb.set(self.current_filter)
        self.filter_cb.pack(pady=1, anchor="w")

        col_if = ctk.CTkFrame(row_if, fg_color="transparent")
        col_if.grid(row=0, column=1, sticky="ew", padx=(2, 0))
        add_left_label(col_if, "Сдвиг ПЧ (IF)")
        row_if_inner = ctk.CTkFrame(col_if, fg_color="transparent")
        row_if_inner.pack(fill="x")
        self.slider_if_shift = ctk.CTkSlider(row_if_inner, from_=0, to=255, width=110, height=10,
                                             fg_color=t["entry_bg"], progress_color=t["brass"],
                                             button_color=t["btn_bg"], command=self.set_if_shift)
        self.slider_if_shift.set(self.if_shift_value)
        self.slider_if_shift.pack(side="left")
        self.lbl_if_shift = ctk.CTkLabel(row_if_inner, text="0", font=("Consolas", 9), text_color=t["text"], width=30)
        self.lbl_if_shift.pack(side="left")
        self.btn_reset_if = ctk.CTkButton(row_if_inner, text="⟲", width=24, height=20,
                                          fg_color=t["panel"], hover_color=t["border"], text_color=t["text"],
                                          border_width=1, border_color=t["border"],
                                          command=lambda: self._set_if_shift(128))
        self.btn_reset_if.pack(side="left", padx=(2, 0))

        # Строка 3: Center Meter
        add_left_label(self.left_frame, "Точная настройка")
        self.center_meter_cv = tk.Canvas(self.left_frame, height=18, width=340, bg=t["entry_bg"], highlightthickness=0)
        self.center_meter_cv.pack(pady=(1, 3), padx=4, anchor="w")
        self._draw_center_meter()

        # Строка 4: Доп. переключатели
        add_left_label(self.left_frame, "Доп. функции")
        row_dsp = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        row_dsp.pack(fill="x", padx=4, pady=(1, 4))

        self.switch_att = ctk.CTkSwitch(row_dsp, text="АТТ", font=("Arial", 8), fg_color=t["border"], progress_color=t["on"], text_color=t["text"], command=self._toggle_att)
        self.switch_att.pack(side="left", padx=(0, 4))
        self.switch_agc = ctk.CTkSwitch(row_dsp, text="АРУ", font=("Arial", 8), fg_color=t["border"], progress_color=t["on"], text_color=t["text"], command=self._toggle_agc)
        self.switch_agc.pack(side="left", padx=(0, 4)); self.switch_agc.select()
        self.switch_nb = ctk.CTkSwitch(row_dsp, text="ПОШ", font=("Arial", 8), fg_color=t["border"], progress_color=t["on"], text_color=t["text"], command=self._toggle_nb)
        self.switch_nb.pack(side="left", padx=(0, 4))
        self.switch_afc = ctk.CTkSwitch(row_dsp, text="АПЧ", font=("Arial", 8), fg_color=t["border"], progress_color=t["on"], text_color=t["text"], command=self._toggle_afc)
        self.switch_afc.pack(side="left", padx=(0, 4))
        self.switch_vsc = ctk.CTkSwitch(row_dsp, text="ГОР", font=("Arial", 8), fg_color=t["border"], progress_color=t["on"], text_color=t["text"], command=self._toggle_vsc)
        self.switch_vsc.pack(side="left")

        self.right_frame = ctk.CTkScrollableFrame(main, corner_radius=6, border_width=1,
                                                  fg_color=t["panel"], border_color=t["border"])
        self.right_frame.grid(row=1, column=1, padx=(2, 0), pady=2, sticky="nsew")

        def add_right_label(text):
            lbl = ctk.CTkLabel(self.right_frame, text=text.upper(), font=("Arial", 8, "bold"), text_color=t["brass"])
            lbl.pack(anchor="w", padx=4, pady=(4, 1))

        add_right_label("Автоматический поиск")
        row_band = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        row_band.pack(pady=1, padx=4, fill="x")

        self.band_cb = ctk.CTkComboBox(row_band, values=["Custom"] + list(self.profiles.keys()), width=150, height=28,
                                       fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"],
                                       button_color=t["border"], button_hover_color=t["brass_shadow"], command=self._on_band_change)
        self.band_cb.set("FM Radio")
        self.band_cb.pack(side="left", padx=(0, 4))

        self.btn_add_profile = ctk.CTkButton(row_band, text="+", width=28, height=28, fg_color=t["panel"], hover_color=t["border"],
                                             text_color=t["text"], border_width=1, border_color=t["border"], font=("Arial", 12), command=self._save_custom_profile)
        self.btn_add_profile.pack(side="left")

        row_range = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        row_range.pack(pady=1, padx=4, fill="x")
        self.entry_scan_start = ctk.CTkEntry(row_range, placeholder_text="Старт", width=70, height=28, justify="center", fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"])
        self.entry_scan_start.insert(0, "87.5")
        self.entry_scan_start.pack(side="left", padx=(0, 4))
        self.entry_scan_end = ctk.CTkEntry(row_range, placeholder_text="Стоп", width=70, height=28, justify="center", fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"])
        self.entry_scan_end.insert(0, "108.0")
        self.entry_scan_end.pack(side="left", padx=(0, 4))
        self.step_cb = ctk.CTkComboBox(row_range, values=["5", "10", "12.5", "25", "50", "100"], width=60, height=28, fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"], button_color=t["border"], button_hover_color=t["brass_shadow"])
        self.step_cb.set("100")
        self.step_cb.pack(side="left")

        add_right_label("Порог срабатывания")
        self.slider_threshold = ctk.CTkSlider(self.right_frame, from_=0.05, to=0.9, height=12, width=260, fg_color=t["entry_bg"], progress_color=t["brass"], button_color=t["brass"], button_hover_color=t["accent"])
        self.slider_threshold.set(0.3)
        self.slider_threshold.pack(pady=1, padx=4, anchor="w")

        self.btn_scan = ctk.CTkButton(self.right_frame, text="▶  СТАРТ ПОИСКА", height=32, fg_color=t["btn_bg"], hover_color=t["btn_hover"], text_color="#000000", font=("Arial", 11, "bold"), command=self.toggle_scan)
        self.btn_scan.pack(fill="x", padx=4, pady=(8, 2))

        self.progress_scan = ctk.CTkProgressBar(self.right_frame, width=260, height=5, fg_color=t["entry_bg"], progress_color=t["success"])
        self.progress_scan.set(0)
        self.progress_scan.pack(padx=4, pady=(0, 2), anchor="w")

        self.lbl_scan_info = ctk.CTkLabel(self.right_frame, text="Приемник готов", font=("Arial", 9), text_color=t["text"])
        self.lbl_scan_info.pack(pady=(0, 2))

        self.btn_meter_refresh = ctk.CTkButton(
            self.right_frame, text="🔄 Обновить S-метр", height=24,
            fg_color=t["panel"], hover_color=t["border"],
            text_color=t["text"], border_width=1, border_color=t["border"],
            font=("Arial", 9), command=self._manual_meter_refresh
        )
        self.btn_meter_refresh.pack(fill="x", padx=4, pady=(0, 4))

        self.action_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.action_frame.pack(fill="x", padx=4, pady=(0, 2))
        self.btn_save_freq = ctk.CTkButton(self.action_frame, text="💾 Сохранить", height=26, state="disabled", fg_color=t["panel"], hover_color=t["border"], text_color=t["text"], border_width=1, border_color=t["border"], font=("Arial", 9), command=self.save_current_freq)
        self.btn_save_freq.pack(side="left", fill="x", expand=True, padx=(0, 2))
        self.btn_skip = ctk.CTkButton(self.action_frame, text="⏭ Пропустить", height=26, state="disabled", fg_color=t["panel"], hover_color=t["border"], text_color=t["text"], border_width=1, border_color=t["border"], font=("Arial", 9), command=self.skip_current_freq)
        self.btn_skip.pack(side="left", fill="x", expand=True, padx=(2, 0))

        add_right_label("Зафиксированные станции")
        self.found_list = ctk.CTkTextbox(self.right_frame, height=75, font=("Consolas", 9), fg_color=t["entry_bg"], border_color=t["border"], border_width=1, text_color=t["text"])
        self.found_list.pack(fill="both", expand=True, padx=4, pady=(1, 2))
        self.found_list.configure(state="disabled")

        self.btn_export = ctk.CTkButton(self.right_frame, text="📊 Экспорт в CSV", height=26, fg_color="transparent", hover_color=t["border"], text_color=t["text"], border_width=1, border_color=t["border"], font=("Arial", 9), command=self.export_csv)
        self.btn_export.pack(fill="x", padx=4, pady=(0, 4))

        self.bottom_wood = PhotoRealWoodPanel(self, theme=t, height=12)
        self.bottom_wood.pack(fill="x", side="bottom")

    def _draw_center_meter(self):
        cv = getattr(self, "center_meter_cv", None)
        if cv is None: return
        try:
            t = self.theme
            cv.delete("all")
            w = int(cv.cget("width")); h = int(cv.cget("height"))
            cv.configure(bg=t["entry_bg"])
            cv.create_line(4, h // 2, w - 4, h // 2, fill=t["border"], width=1)
            cv.create_line(w // 2, 2, w // 2, h - 2, fill=t["brass_shadow"], width=1)
            frac = max(0.0, min(1.0, self.center_meter / 255.0))
            x = int(4 + frac * (w - 8))
            cv.create_oval(x - 3, h // 2 - 3, x + 3, h // 2 + 3, fill=t["needle"], outline="")
        except Exception:
            pass

    def _on_filter_change(self, val):
        self.current_filter = val
        if self.is_connected:
            self._send_tune()

    def set_if_shift(self, val):
        self.if_shift_value = self._slider_command("if_shift", val, "J43")
        self.lbl_if_shift.configure(text=str(int(self.if_shift_value) - 128))

    def _set_if_shift(self, value):
        self.if_shift_value = int(value)
        self.slider_if_shift.set(value)
        self.lbl_if_shift.configure(text=str(int(value) - 128))
        self.send_command(f"J43{int(value):02X}")

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
        self.current_filter = DEFAULT_FILTER_FOR_MODE.get(mode, "230k")
        if hasattr(self, "filter_cb"):
            self.filter_cb.set(self.current_filter)
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
                "mode": self.current_mode, "filter": self.current_filter
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
        if self.is_connected:
            self.disconnect_radio()
        else:
            threading.Thread(target=self.connect_radio, daemon=True).start()

    def _flush_serial_input(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.reset_input_buffer()
        except Exception:
            pass
        self.rx_buffer = ""

    def _on_connected_ui(self):
        self.port_cb.configure(state="disabled")
        self.btn_connect.configure(text="ВЫКЛ РАДИО",
                                   fg_color=self.theme["danger"],
                                   hover_color="#9E1B1B",
                                   text_color="#ffffff")
        self.lbl_status.configure(text="● СЕТЬ ВКЛ", text_color=self.theme["success"])
        self.magic_eye.set_power(True)
        self.classic_meter.set_power(True)
        self.dial_scale.set_power(True)

    def _on_disconnected_ui(self):
        self.apply_theme()
        self.port_cb.configure(state="readonly")
        self.btn_connect.configure(text="ВКЛ РАДИО",
                                   fg_color=self.theme["brass"],
                                   hover_color="#9E7F30",
                                   text_color="#000000")
        self.lbl_status.configure(text="● СЕТЬ ВЫКЛ", text_color=self.theme["danger"])
        self.magic_eye.set_power(False)
        self.classic_meter.set_power(False)
        self.dial_scale.set_power(False)
        if self._active_meter is not None:
            self._active_meter.set_value(0)

    def connect_radio(self):
        port = self.port_cb.get()
        if not port: return
        try:
            self.ser = serial.Serial(port, 9600, timeout=0.1, write_timeout=1.0, dsrdtr=False, xonxoff=False)
            self.ser.rts = True
            self.ser.reset_input_buffer()
            self.is_connected = True
            self.stop_event.clear()
            self.rx_buffer = ""
            self.rx_dropped_bytes = 0
            with self.rx_condition: self.rx_tokens.clear()

            self.reader_thread = threading.Thread(target=self._serial_reader, daemon=True)
            self.reader_thread.start()

            self._log("Инициализация аудиотракта...")
            self.send_command("H101", wait_response=False); time.sleep(0.6)
            self.send_command("G301", wait_response=False); time.sleep(0.3)

            gd = self.send_command_sync("GD?", wait_response=True, timeout=2.5)
            if gd:
                try: self.has_dsp = bool(int(gd[2:4], 16) & 0x01)
                except ValueError: self.has_dsp = False
            else: self.has_dsp = False

            if self.has_dsp:
                self._log("DSP-модуль обнаружен.")
            else:
                self._log("DSP-модуль не найден (GD00). ATT/AGC/NB — аналоговые функции.")

            commands = (
                f"J40{self.current_volume:02X}",
                f"J41{self.current_squelch:02X}",
                f"J45{1 if self.dsp_agc else 0:02X}",
                f"J46{1 if self.dsp_nb else 0:02X}",
                f"J47{1 if self.dsp_attenuator else 0:02X}",
                "J5000",
                f"J43{self.if_shift_value:02X}",
                f"J51{1 if self.dsp_afc else 0:02X}",
            )
            for cmd in commands:
                self.send_command(cmd, wait_response=False)
                time.sleep(0.08)

            self.sync_frequency(force=True)
            self._start_watchdog()
            self._start_i1_poll()

            self.ui_queue.put(("connected",))
            self._log("Соединение установлено. Watchdog запущен.")
        except Exception as e:
            self.is_connected = False
            if self.ser:
                try:
                    with self.com_lock: self.ser.close()
                except Exception: pass
            self.ui_queue.put(("error", f"Не удалось подключиться:\n{e}"))

    def disconnect_radio(self):
        was_connected = self.is_connected
        self.is_scanning = False
        self.stop_event.set()
        self.is_connected = False
        self._stop_watchdog()
        self._stop_i1_poll()
        if self.ser and self.ser.is_open:
            try:
                with self.com_lock:
                    if self.ser and self.ser.is_open:
                        self.ser.write(b"H100\r\n")
                        self.ser.flush()
                        self.ser.close()
            except Exception as e:
                self._log(f"Ошибка закрытия COM-порта: {e}")
        self.ui_queue.put(("disconnected",))
        if was_connected: self._log("Соединение разорвано.")

    def _start_watchdog(self):
        self._stop_watchdog()
        def watchdog_tick():
            if not self.is_connected or self._closing: return
            self.send_command("I0?", wait_response=False)
            self._watchdog_timer = self.after(15000, watchdog_tick)
        self._watchdog_timer = self.after(15000, watchdog_tick)

    def _stop_watchdog(self):
        if self._watchdog_timer:
            try: self.after_cancel(self._watchdog_timer)
            except Exception: pass
        self._watchdog_timer = None

    def _start_i1_poll(self):
        self._stop_i1_poll()
        def poll_tick():
            if not self.is_connected or self._closing: return
            if not self.is_scanning:
                self._expecting_smeter = True
                self.send_command("I1?", wait_response=False)
            self._i1_poll_timer = self.after(1200, poll_tick)
        self._i1_poll_timer = self.after(1200, poll_tick)

    def _stop_i1_poll(self):
        if self._i1_poll_timer:
            try: self.after_cancel(self._i1_poll_timer)
            except Exception: pass
        self._i1_poll_timer = None

    def _manual_meter_refresh(self):
        if self.is_connected and not self._closing:
            self._expecting_smeter = True
            self.send_command("I1?", wait_response=False)

    def _serial_reader(self):
        token_re = re.compile(r"(GD|G0|G2|H1|I[0-4])\s*([0-9A-Fa-f]{2})")
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

        if prefix == "I0":
            self.is_busy = bool(value & 0x04)
        elif prefix == "I1":
            with self.smeter_condition:
                self.raw_smeter = value
                self.smeter_value = min(value / 255.0, 1.0)
                self.smeter_seq += 1
                self.smeter_condition.notify_all()
        elif prefix == "I2":
            self.center_meter = value
            self._draw_center_meter()
        elif prefix == "G0":
            pass
        elif prefix == "G2":
            pass
        elif prefix == "H1":
            if value == 1: self._log("H1: POWER ON")

    def _update_gui_indicators(self):
        if self._closing: return
        try:
            if self.is_connected and self._active_meter:
                noisy_raw = max(0, min(255, int(self.raw_smeter + random.uniform(-1.0, 1.0))))
                self._active_meter.set_value(noisy_raw)
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
            with self.rx_condition: self.rx_tokens = [t for t in self.rx_tokens if not t.startswith(prefix)]
        self._log(f"TX: {cmd}")
        with self.com_lock:
            if not self.ser or not self.ser.is_open: return ""
            try:
                self.ser.write((cmd + "\r\n").encode("ascii"))
                self.ser.flush()
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
        self.send_command(f"J51{1 if self.dsp_afc else 0:02X}")

    def _toggle_vsc(self):
        if not self._ui_ready: return
        self.dsp_vsc = bool(self.switch_vsc.get())
        self.send_command(f"J50{1 if self.dsp_vsc else 0:02X}")

    def apply_settings(self):
        if self._applying_settings: return
        self._applying_settings = True
        try:
            raw = self.entry_freq.get().strip().replace(",", ".")
            try: value = float(raw)
            except ValueError:
                messagebox.showerror("Частота", "Введите частоту в МГц, например 99.60000.")
                return
            if not math.isfinite(value) or not 0.5 <= value <= 1300.0:
                messagebox.showerror("Частота", "Допустимый диапазон: 0.50000–1300.00000 МГц.")
                return
            self.current_freq_mhz = round(value, 6)
            self._update_freq_widgets()
            if self.is_connected: self.sync_frequency(force=True)
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
        if not self.is_scanning:
            self.after(400, self._post_tune_meter_refresh)

    def _post_tune_meter_refresh(self):
        if self.is_connected and not self._closing and not self.is_scanning:
            self._expecting_smeter = True
            self.send_command("I1?", wait_response=False)

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
                with self.smeter_condition:
                    seq_before = self.smeter_seq
                self.sync_frequency()
                with self.smeter_condition:
                    self.smeter_condition.wait_for(lambda: self.smeter_seq > seq_before, timeout=0.35)

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
        self._stop_i1_poll()
        self._stop_watchdog()
        self.disconnect_radio()
        if hasattr(self, "nixie_clock"):
            self.nixie_clock.destroy()
        try: self.destroy()
        except Exception: pass
        sys.exit(0)


if __name__ == "__main__":
    app = PCR1000Pro()
    app.mainloop()