import sys
import threading
import time
import json
import os
import csv
import math
import re
import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
import serial
import serial.tools.list_ports

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

CONFIG_FILE = "pcr1000_profiles.json"

THEMES = {
    "Dark": {
        "bg": "#0d0e12", "panel": "#161820", "text": "#ffffff",
        "muted": "#6f738a", "accent": "#00f0ff", "accent_hover": "#00c0cc",
        "danger": "#ff4444", "success": "#00ff88", "entry_bg": "#1e2230",
        "border": "#2a2e3d", "btn_bg": "#1e2230", "btn_hover": "#2a2e3d",
        "on": "#00ff88", "off": "#444444",
        "meter_body": "#1a1e2a", "meter_face": "#f4f0e0", "meter_needle": "#c0392b",
        "knob_outer": "#2a2e3d", "knob_mid": "#3a3f50", "knob_inner": "#1e2230",
        "knob_ridge": "#4a4f60", "knob_indicator": "#00f0ff"
    },
    "Light": {
        "bg": "#f4f5f8", "panel": "#ffffff", "text": "#1a1a1a",
        "muted": "#888888", "accent": "#0066ff", "accent_hover": "#0055cc",
        "danger": "#e53935", "success": "#43a047", "entry_bg": "#f4f5f8",
        "border": "#e0e0e0", "btn_bg": "#e0e0e0", "btn_hover": "#d0d0d0",
        "on": "#2e7d32", "off": "#999999",
        "meter_body": "#2c3e50", "meter_face": "#fdf6e3", "meter_needle": "#c0392b",
        "knob_outer": "#d0d0d0", "knob_mid": "#b0b0b0", "knob_inner": "#e0e0e0",
        "knob_ridge": "#909090", "knob_indicator": "#0066ff"
    }
}

MODE_CODES = {"LSB": 0, "USB": 1, "AM": 2, "CW": 3, "NFM": 5, "WFM": 6}
FILTER_CODES = {"2.8k": 0, "6k": 1, "15k": 2, "50k": 3, "230k": 4}

VFO_STEPS = {
    "10 Гц": 0.00001, "50 Гц": 0.00005, "100 Гц": 0.0001, "500 Гц": 0.0005,
    "1 кГц": 0.001, "10 кГц": 0.01, "25 кГц": 0.025, "100 кГц": 0.1, "1 МГц": 1.0
}

CTCSS_TONES = {
    "OFF": 0, "67.0": 1, "69.3": 2, "71.9": 3, "74.4": 4, "77.0": 5, "79.7": 6, "82.5": 7, "85.4": 8, "88.5": 9, "91.5": 10,
    "94.8": 11, "97.4": 12, "100.0": 13, "103.5": 14, "107.2": 15, "110.9": 16, "114.8": 17, "118.8": 18, "123.0": 19, "127.3": 20,
    "131.8": 21, "136.5": 22, "141.3": 23, "146.2": 24, "151.4": 25, "156.7": 26, "159.8": 27, "162.2": 28, "165.5": 29, "167.9": 30,
    "171.3": 31, "173.8": 32, "177.3": 33, "179.9": 34, "183.5": 35, "186.2": 36, "189.9": 37, "192.8": 38, "196.6": 39, "199.5": 40,
    "203.5": 41, "206.5": 42, "210.7": 43, "218.1": 44, "225.7": 45, "229.1": 46, "233.6": 47, "241.8": 48, "250.3": 49, "254.1": 50
}

DEFAULT_PROFILES = {
    "FM Radio": {"start": 87.5, "end": 108.0, "step": 100, "threshold": 0.3, "mode": "WFM", "filter": "230k"},
    "Air Band": {"start": 118.0, "end": 136.0, "step": 25, "threshold": 0.2, "mode": "AM", "filter": "6k"},
    "Amateur 2m": {"start": 144.0, "end": 148.0, "step": 12.5, "threshold": 0.15, "mode": "NFM", "filter": "15k"},
    "PMR/LPD": {"start": 433.0, "end": 434.8, "step": 12.5, "threshold": 0.15, "mode": "NFM", "filter": "15k"},
}


# ============================================================================
# РЕАЛИСТИЧНАЯ КРУТИЛКА VFO
# ============================================================================
class VFO_Dial(tk.Canvas):
    """Реалистичная ручка настройки в стиле Icom/Kenwood."""
    
    def __init__(self, master, command, width=140, height=140, **kwargs):
        self.bg_color = kwargs.pop("bg", "#0d0e12")
        super().__init__(master, width=width, height=height, highlightthickness=0, bg=self.bg_color, **kwargs)
        self.command = command
        self.width = width
        self.height = height
        self.angle = 0
        self.last_y = 0
        self.dragging = False
        self.accumulated_steps = 0
        
        self.bind("<ButtonPress-1>", self.on_press)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.draw()

    def draw(self):
        self.delete("all")
        t = THEMES.get("Dark" if self.bg_color == "#0d0e12" else "Light", THEMES["Dark"])
        
        cx, cy = self.width // 2, self.height // 2
        r = min(self.width, self.height) // 2 - 8
        
        # Тень
        shadow_offset = 3
        self.create_oval(cx - r + shadow_offset, cy - r + shadow_offset,
                         cx + r + shadow_offset, cy + r + shadow_offset,
                         fill="#000000", outline="", stipple="gray25")
        
        # Рифлёный внешний обод (72 насечки)
        num_ridges = 72
        for i in range(num_ridges):
            angle_rad = math.radians(i * 360 / num_ridges - 90)
            x1 = cx + (r - 2) * math.cos(angle_rad)
            y1 = cy + (r - 2) * math.sin(angle_rad)
            x2 = cx + (r - 7) * math.cos(angle_rad)
            y2 = cy + (r - 7) * math.sin(angle_rad)
            color = t["knob_ridge"] if i % 2 == 0 else t["knob_outer"]
            self.create_line(x1, y1, x2, y2, fill=color, width=2)
        
        # Основной корпус
        self.create_oval(cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5,
                         fill=t["knob_outer"], outline="#1a1e2a", width=1)
        self.create_oval(cx - r + 10, cy - r + 10, cx + r - 10, cy + r - 10,
                         fill=t["knob_mid"], outline="")
        self.create_oval(cx - r + 18, cy - r + 18, cx + r - 18, cy + r - 18,
                         fill=t["knob_inner"], outline="")
        
        # Блик сверху
        self.create_arc(cx - r + 18, cy - r + 18, cx + r - 18, cy + r - 18,
                        start=200, extent=140,
                        fill="#ffffff", outline="", stipple="gray12")
        
        # Неподвижная индикаторная точка сверху (12 часов)
        top_x, top_y = cx, cy - r + 12
        self.create_oval(top_x - 3, top_y - 3, top_x + 3, top_y + 3,
                         fill=t["knob_indicator"], outline="")
        
        # Вращающаяся риска
        angle_rad = math.radians(self.angle - 90)
        x1 = cx + 15 * math.cos(angle_rad)
        y1 = cy + 15 * math.sin(angle_rad)
        x2 = cx + (r - 20) * math.cos(angle_rad)
        y2 = cy + (r - 20) * math.sin(angle_rad)
        self.create_line(x1, y1, x2, y2, fill=t["knob_indicator"], width=3, capstyle="round")
        self.create_oval(x2 - 4, y2 - 4, x2 + 4, y2 + 4,
                         fill=t["knob_indicator"], outline="#ffffff", width=1)
        
        # Центральный колпачок с "винтом"
        self.create_oval(cx - 18, cy - 18, cx + 18, cy + 18,
                         fill=t["knob_outer"], outline="#1a1e2a", width=1)
        self.create_oval(cx - 12, cy - 12, cx + 12, cy + 12,
                         fill=t["knob_mid"], outline="")
        self.create_line(cx - 6, cy, cx + 6, cy, fill="#1a1e2a", width=2)
        self.create_line(cx, cy - 6, cx, cy + 6, fill="#1a1e2a", width=2)
        self.create_oval(cx - 8, cy - 8, cx + 2, cy + 2,
                         fill="#ffffff", outline="", stipple="gray25")

    def on_press(self, event):
        self.dragging = True
        self.last_y = event.y

    def on_drag(self, event):
        if not self.dragging:
            return
        dy = event.y - self.last_y
        self.last_y = event.y
        step = -dy * 0.6
        self.angle = (self.angle + step) % 360
        self.draw()
        self.accumulated_steps += step
        if abs(self.accumulated_steps) >= 2:
            self.command(int(self.accumulated_steps))
            self.accumulated_steps = 0

    def on_release(self, event):
        self.dragging = False
        if abs(self.accumulated_steps) > 0:
            self.command(int(self.accumulated_steps))
            self.accumulated_steps = 0


# ============================================================================
# АНАЛОГОВЫЙ S-МЕТР
# ============================================================================
class AnalogSMeter(tk.Canvas):
    """Классический аналоговый стрелочный S-метр."""
    
    SCALE_POINTS = [
        (0x00, "0"), (0x19, "1"), (0x30, "3"), (0x44, "5"),
        (0x5A, "7"), (0x70, "9"), (0x90, "+20"), (0xB0, "+40"),
        (0xD0, "+60"), (0xF0, "")
    ]
    
    def __init__(self, master, width=320, height=180, theme=None, **kwargs):
        self.bg_color = kwargs.pop("bg", "#0d0e12")
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bg=self.bg_color, **kwargs)
        self.width = width
        self.height = height
        self.value = 0
        self.smooth_value = 0.0
        self.theme = theme or THEMES["Dark"]
        
        self.cx = self.width // 2
        self.cy = self.height - 25
        self.radius = min(self.width // 2 - 20, self.height - 50)
        
        self.angle_min = -75
        self.angle_max = 75
        
        self.draw()
    
    def _value_to_angle(self, value):
        value = max(0, min(255, value))
        fraction = value / 255.0
        fraction = fraction ** 0.75
        return self.angle_min + fraction * (self.angle_max - self.angle_min)
    
    def _polar_to_cart(self, angle_deg, radius):
        angle_rad = math.radians(angle_deg - 90)
        x = self.cx + radius * math.cos(angle_rad)
        y = self.cy + radius * math.sin(angle_rad)
        return x, y
    
    def set_theme(self, theme):
        self.theme = theme
        self.bg_color = theme["meter_body"]
        self.configure(bg=self.bg_color)
        self.draw()
    
    def set_value(self, value):
        self.value = max(0, min(255, value))
        self.smooth_value += (self.value - self.smooth_value) * 0.35
        self.draw()
    
    def draw(self):
        self.delete("all")
        t = self.theme
        
        # Корпус
        self.create_oval(self.cx - self.radius - 15, self.cy - self.radius - 15,
                         self.cx + self.radius + 15, self.cy + self.radius + 15,
                         fill=t.get("meter_body", "#1a1e2a"), outline=t["border"], width=2)
        
        # Шкала
        self.create_arc(self.cx - self.radius, self.cy - self.radius,
                        self.cx + self.radius, self.cy + self.radius,
                        start=0, extent=180,
                        fill=t.get("meter_face", "#f4f0e0"), outline="")
        
        # Деления и подписи
        for val, label in self.SCALE_POINTS:
            angle = self._value_to_angle(val)
            x1, y1 = self._polar_to_cart(angle, self.radius - 5)
            x2, y2 = self._polar_to_cart(angle, self.radius - 25)
            self.create_line(x1, y1, x2, y2, fill="#1a1a1a", width=2)
            
            if label:
                xl, yl = self._polar_to_cart(angle, self.radius - 40)
                self.create_text(xl, yl, text=label, fill="#1a1a1a",
                                 font=("Inter", 10, "bold"))
        
        # Мелкие деления
        for i in range(len(self.SCALE_POINTS) - 1):
            v1 = self.SCALE_POINTS[i][0]
            v2 = self.SCALE_POINTS[i + 1][0]
            for k in range(1, 4):
                val = v1 + (v2 - v1) * k / 4
                angle = self._value_to_angle(val)
                x1, y1 = self._polar_to_cart(angle, self.radius - 5)
                x2, y2 = self._polar_to_cart(angle, self.radius - 15)
                self.create_line(x1, y1, x2, y2, fill="#1a1a1a", width=1)
        
        # Красная зона — тонкая дуга
        angle_red_start = self._value_to_angle(0x90)
        angle_red_end = self._value_to_angle(0xF0)
        red_width = 8
        self.create_arc(
            self.cx - self.radius + red_width, self.cy - self.radius + red_width,
            self.cx + self.radius - red_width, self.cy + self.radius - red_width,
            start=angle_red_start, extent=angle_red_end - angle_red_start,
            style=tk.ARC, outline="#c0392b", width=6
        )
        
        # Надпись "S"
        self.create_text(self.cx, self.cy - self.radius + 55, text="S",
                         fill="#1a1a1a", font=("Inter", 16, "bold"))
        
        # Цифровое значение — в правом нижнем углу (вне траектории стрелки)
        digit_x = self.cx + self.radius * 0.55
        digit_y = self.cy + 15
        self.create_rectangle(digit_x - 22, digit_y - 12, digit_x + 22, digit_y + 12,
                              fill=t.get("meter_body", "#1a1e2a"), outline=t["border"], width=1)
        self.create_text(digit_x, digit_y, text=str(int(self.smooth_value)),
                         fill=t["accent"], font=("Consolas", 13, "bold"))
        
        # Стрелка (укороченная)
        angle = self._value_to_angle(self.smooth_value)
        x_tip, y_tip = self._polar_to_cart(angle, self.radius - 12)
        x_base, y_base = self._polar_to_cart(angle, self.radius - 25)
        
        self.create_line(x_base + 1, y_base + 1, x_tip + 1, y_tip + 1,
                         fill="#000000", width=3, capstyle="round")
        self.create_line(x_base, y_base, x_tip, y_tip,
                         fill=t.get("meter_needle", "#c0392b"), width=3, capstyle="round")
        
        # Центр
        self.create_oval(self.cx - 10, self.cy - 10, self.cx + 10, self.cy + 10,
                         fill="#2a2e3d", outline=t.get("meter_needle", "#c0392b"), width=2)
        self.create_oval(self.cx - 4, self.cy - 4, self.cx + 4, self.cy + 4,
                         fill=t.get("meter_needle", "#c0392b"), outline="")


# ============================================================================
# ОСНОВНОЙ КЛАСС
# ============================================================================
class PCR1000Pro(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("IC-PCR1000 Pro")
        self.geometry("1300x950")
        self.minsize(1200, 850)

        self.is_dark = True
        self.theme = THEMES["Dark"]
        self.configure(fg_color=self.theme["bg"])

        self._ui_ready = False
        self._closing = False
        self._applying_settings = False

        self.ser = None
        self.is_connected = False
        self.scan_thread = None

        self.current_freq_mhz = 99.6
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

        self.profiles = self._load_profiles()
        self._build_ui()
        self._ui_ready = True
        self._apply_theme()
        self.refresh_ports()
        self._update_gui_indicators()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _load_profiles(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data:
                    return data
            except Exception:
                pass
        return DEFAULT_PROFILES.copy()

    def _save_profiles(self):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.profiles, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _toggle_theme(self):
        self.is_dark = not self.is_dark
        self.theme = THEMES["Dark"] if self.is_dark else THEMES["Light"]
        ctk.set_appearance_mode("Dark" if self.is_dark else "Light")
        self._apply_theme()

    def _apply_theme(self):
        if not self._ui_ready:
            return
        t = self.theme
        self.configure(fg_color=t["bg"])
        
        self.top_frame.configure(fg_color="transparent")
        self.lbl_title.configure(text_color=t["text"])
        self.port_cb.configure(fg_color=t["panel"], border_color=t["border"], text_color=t["text"],
                               button_color=t["border"], button_hover_color=t["muted"])
        self.btn_refresh.configure(fg_color=t["panel"], hover_color=t["btn_hover"], text_color=t["text"], border_color=t["border"])
        self.btn_connect.configure(fg_color=t["danger"] if self.is_connected else t["accent"],
                                   hover_color="#cc0000" if self.is_connected else t["accent_hover"],
                                   text_color="#ffffff",
                                   text="Disconnect" if self.is_connected else "Подключить",
                                   border_color=t["danger"] if self.is_connected else t["accent"])
        self.btn_theme.configure(fg_color=t["panel"], hover_color=t["btn_hover"], text_color=t["text"], border_color=t["border"])
        self.btn_diag.configure(fg_color=t["panel"], hover_color=t["btn_hover"], text_color=t["text"], border_color=t["border"])
        self.switch_log.configure(fg_color=t["border"], text_color=t["muted"],
                                  progress_color=t["on"] if self.log_meter else t["off"])
        self.lbl_status.configure(text_color=t["success"] if self.is_connected else t["danger"])

        self.vfo_frame.configure(fg_color=t["panel"], border_color=t["border"])
        self.lbl_vfo.configure(text_color=t["accent"])
        self.lbl_mhz.configure(text_color=t["muted"])
        self.btn_step_down.configure(fg_color=t["btn_bg"], hover_color=t["btn_hover"], text_color=t["text"], border_color=t["border"])
        self.btn_step_up.configure(fg_color=t["btn_bg"], hover_color=t["btn_hover"], text_color=t["text"], border_color=t["border"])
        self.step_vfo_cb.configure(fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"],
                                   button_color=t["border"], button_hover_color=t["muted"])
        self.vfo_dial.configure(bg=t["panel"])
        self.vfo_dial.draw()

        self.meter_frame.configure(fg_color=t["panel"], border_color=t["border"])
        self.smeter_canvas.set_theme(t)

        self.left_frame.configure(fg_color=t["panel"], border_color=t["border"])
        for lbl in self.left_labels:
            lbl.configure(text_color=t["muted"])

        self.entry_freq.configure(fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"])
        self.btn_apply.configure(fg_color=t["accent"], hover_color=t["accent_hover"],
                                 text_color="#000000" if self.is_dark else "#ffffff")

        self.mode_cb.configure(fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"],
                               button_color=t["border"], button_hover_color=t["muted"])
        self.filter_cb.configure(fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"],
                                 button_color=t["border"], button_hover_color=t["muted"])

        self.slider_vol.configure(progress_color=t["accent"], button_color=t["accent"], button_hover_color="white", fg_color=t["entry_bg"])
        self.slider_sql.configure(progress_color=t["accent"], button_color=t["accent"], button_hover_color="white", fg_color=t["entry_bg"])

        self.lbl_busy.configure(text_color=t["success"] if self.is_busy else t["off"])
        self.progress_center.configure(progress_color=t["accent"], fg_color=t["entry_bg"])
        self.lbl_center_val.configure(text_color=t["accent"])

        self.switch_att.configure(fg_color=t["border"], progress_color=t["on"] if self.dsp_attenuator else t["off"])
        self.switch_agc.configure(fg_color=t["border"], progress_color=t["on"] if self.dsp_agc else t["off"])
        self.switch_nb.configure(fg_color=t["border"], progress_color=t["on"] if self.dsp_nb else t["off"])
        self.switch_afc.configure(fg_color=t["border"], progress_color=t["on"] if self.dsp_afc else t["off"])
        self.switch_vsc.configure(fg_color=t["border"], progress_color=t["on"] if self.dsp_vsc else t["off"])

        self.slider_if_shift.configure(progress_color=t["accent"], button_color=t["accent"], button_hover_color="white", fg_color=t["entry_bg"])
        self.slider_bfo.configure(progress_color=t["accent"], button_color=t["accent"], button_hover_color="white", fg_color=t["entry_bg"])
        self.lbl_if_shift.configure(text_color=t["accent"])
        self.lbl_bfo.configure(text_color=t["accent"])
        self.btn_reset_if.configure(fg_color=t["btn_bg"], hover_color=t["btn_hover"], text_color=t["text"], border_color=t["border"])
        self.btn_reset_bfo.configure(fg_color=t["btn_bg"], hover_color=t["btn_hover"], text_color=t["text"], border_color=t["border"])

        self.ctcss_cb.configure(fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"],
                                button_color=t["border"], button_hover_color=t["muted"])

        self.right_frame.configure(fg_color=t["panel"], border_color=t["border"])
        for lbl in self.right_labels:
            lbl.configure(text_color=t["muted"])

        self.band_cb.configure(fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"],
                               button_color=t["border"], button_hover_color=t["muted"])
        self.btn_add_profile.configure(fg_color=t["btn_bg"], hover_color=t["btn_hover"], text_color=t["text"], border_color=t["border"])

        self.entry_scan_start.configure(fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"])
        self.entry_scan_end.configure(fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"])
        self.step_cb.configure(fg_color=t["entry_bg"], border_color=t["border"], text_color=t["text"],
                               button_color=t["border"], button_hover_color=t["muted"])

        self.slider_threshold.configure(progress_color=t["accent"], button_color=t["accent"], button_hover_color="white", fg_color=t["entry_bg"])
        self.btn_export.configure(fg_color="transparent", hover_color=t["btn_hover"], border_color=t["border"], text_color=t["text"])
        self.progress_scan.configure(progress_color=t["success"], fg_color=t["entry_bg"])
        self.lbl_scan_info.configure(text_color=t["accent"])
        self.btn_save_freq.configure(fg_color=t["btn_bg"], hover_color=t["btn_hover"], text_color=t["text"], border_color=t["border"])
        self.btn_skip.configure(fg_color=t["btn_bg"], hover_color=t["btn_hover"], text_color=t["text"], border_color=t["border"])

        if self.is_scanning:
            self.btn_scan.configure(fg_color=t["danger"], hover_color="#cc0000", text="■  СТОП СКАНЕРА", text_color="#ffffff")
        else:
            self.btn_scan.configure(fg_color=t["accent"], hover_color=t["accent_hover"], text="▶  СТАРТ СКАНЕРА",
                                    text_color="#000000" if self.is_dark else "#ffffff")

        self.found_list.configure(fg_color=t["panel"], border_color=t["border"], text_color=t["text"])

    def _build_ui(self):
        t = self.theme
        
        self.top_frame = ctk.CTkFrame(self, height=50, fg_color="transparent")
        self.top_frame.pack(fill="x", padx=20, pady=(15, 10))

        self.lbl_title = ctk.CTkLabel(self.top_frame, text="📻 IC-PCR1000 Pro", font=("Inter", 20, "bold"))
        self.lbl_title.pack(side="left", padx=(0, 20))

        self.port_cb = ctk.CTkComboBox(self.top_frame, values=[], width=140, height=36, corner_radius=8, border_width=1)
        self.port_cb.pack(side="left", padx=5)

        self.btn_refresh = ctk.CTkButton(self.top_frame, text="⟳", width=36, height=36, corner_radius=8,
                                         border_width=1, command=self.refresh_ports, font=("Inter", 14))
        self.btn_refresh.pack(side="left", padx=5)

        self.btn_connect = ctk.CTkButton(self.top_frame, text="Подключить", width=130, height=36, corner_radius=8,
                                         font=("Inter", 13, "bold"), command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=10)

        self.btn_theme = ctk.CTkButton(self.top_frame, text="🌓", width=36, height=36, corner_radius=8,
                                       border_width=1, command=self._toggle_theme, font=("Inter", 14))
        self.btn_theme.pack(side="left", padx=5)

        self.btn_diag = ctk.CTkButton(self.top_frame, text="🩺 Тест", width=80, height=36, corner_radius=8,
                                      border_width=1, font=("Inter", 11), command=self.run_diagnostics)
        self.btn_diag.pack(side="left", padx=5)

        self.switch_log = ctk.CTkSwitch(self.top_frame, text="LOG S", width=80, font=("Inter", 10),
                                        command=self._toggle_meter_log)
        self.switch_log.pack(side="left", padx=10)

        self.lbl_status = ctk.CTkLabel(self.top_frame, text="● ОТКЛЮЧЕНО", font=("Inter", 12, "bold"))
        self.lbl_status.pack(side="right", padx=10)

        center_frame = ctk.CTkFrame(self, fg_color="transparent")
        center_frame.pack(fill="x", padx=20, pady=5)
        center_frame.grid_columnconfigure(0, weight=1)
        center_frame.grid_columnconfigure(1, weight=1)

        self.vfo_frame = ctk.CTkFrame(center_frame, corner_radius=12, border_width=1)
        self.vfo_frame.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="nsew")

        vfo_inner = ctk.CTkFrame(self.vfo_frame, fg_color="transparent")
        vfo_inner.pack(pady=15)

        self.btn_step_down = ctk.CTkButton(vfo_inner, text="▼", width=45, height=55, font=("Inter", 18),
                                           corner_radius=10, border_width=1, command=lambda: self._step_freq(-1))
        self.btn_step_down.pack(side="left", padx=(0, 15))

        vfo_text_frame = ctk.CTkFrame(vfo_inner, fg_color="transparent")
        vfo_text_frame.pack(side="left")

        self.lbl_vfo = ctk.CTkLabel(vfo_text_frame, text="99.60000", font=("Consolas", 44, "bold"))
        self.lbl_vfo.pack()

        self.lbl_mhz = ctk.CTkLabel(vfo_text_frame, text="MHz", font=("Inter", 11, "bold"))
        self.lbl_mhz.pack()

        self.step_vfo_cb = ctk.CTkComboBox(vfo_text_frame, values=list(VFO_STEPS.keys()), width=100, height=24,
                                           font=("Inter", 10), corner_radius=6, border_width=1)
        self.step_vfo_cb.set("100 Гц")
        self.step_vfo_cb.pack(pady=(5, 0))

        self.btn_step_up = ctk.CTkButton(vfo_inner, text="▲", width=45, height=55, font=("Inter", 18),
                                         corner_radius=10, border_width=1, command=lambda: self._step_freq(1))
        self.btn_step_up.pack(side="left", padx=(15, 20))

        self.vfo_dial = VFO_Dial(vfo_inner, self._on_dial_move, width=140, height=140, bg=t["panel"])
        self.vfo_dial.pack(side="left", padx=10)

        self.meter_frame = ctk.CTkFrame(center_frame, corner_radius=12, border_width=1)
        self.meter_frame.grid(row=0, column=1, padx=(5, 0), pady=5, sticky="nsew")

        self.smeter_canvas = AnalogSMeter(self.meter_frame, width=340, height=190, theme=t)
        self.smeter_canvas.pack(pady=10)

        meter_info = ctk.CTkFrame(self.meter_frame, fg_color="transparent")
        meter_info.pack(fill="x", padx=15, pady=(0, 10))
        
        lbl_b = ctk.CTkLabel(meter_info, text="BUSY", font=("Inter", 9, "bold"))
        lbl_b.pack(side="left")
        self.lbl_busy = ctk.CTkLabel(meter_info, text="● OFF", font=("Consolas", 10, "bold"))
        self.lbl_busy.pack(side="left", padx=(5, 20))
        
        lbl_c = ctk.CTkLabel(meter_info, text="CENTER", font=("Inter", 9, "bold"))
        lbl_c.pack(side="left")
        self.lbl_center_val = ctk.CTkLabel(meter_info, text="80", font=("Consolas", 10, "bold"))
        self.lbl_center_val.pack(side="left", padx=(5, 0))
        
        self.progress_center = ctk.CTkProgressBar(self.meter_frame, width=310, height=8, corner_radius=4)
        self.progress_center.set(0.5)
        self.progress_center.pack(pady=(0, 10))

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=20, pady=5)
        main.grid_columnconfigure(0, weight=1, uniform="col")
        main.grid_columnconfigure(1, weight=1, uniform="col")

        self.left_frame = ctk.CTkFrame(main, corner_radius=12)
        self.left_frame.grid(row=0, column=0, padx=(0, 5), pady=5, sticky="nsew")

        self.left_labels = []

        def add_left_label(text):
            lbl = ctk.CTkLabel(self.left_frame, text=text.upper(), font=("Inter", 9, "bold"))
            lbl.pack(anchor="w", padx=15, pady=(10, 2))
            self.left_labels.append(lbl)

        add_left_label("Частота")
        row_freq = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        row_freq.pack(pady=2, padx=15, fill="x")
        self.entry_freq = ctk.CTkEntry(row_freq, width=160, height=34, justify="center", font=("Consolas", 14),
                                       corner_radius=8, border_width=1)
        self.entry_freq.insert(0, "99.600")
        self.entry_freq.pack(side="left", padx=(0, 8))
        self.entry_freq.bind("<Return>", lambda e: self.apply_settings())
        self.btn_apply = ctk.CTkButton(row_freq, text="ENTER", width=70, height=34, corner_radius=8,
                                       font=("Inter", 12, "bold"), command=self.apply_settings)
        self.btn_apply.pack(side="left")

        add_left_label("Режим / Фильтр")
        row_mode = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        row_mode.pack(pady=2, padx=15, fill="x")
        self.mode_cb = ctk.CTkComboBox(row_mode, values=["LSB", "USB", "AM", "CW", "NFM", "WFM"], width=120, height=34,
                                       corner_radius=8, border_width=1)
        self.mode_cb.set("WFM")
        self.mode_cb.pack(side="left", padx=(0, 8))
        self.mode_cb.configure(command=lambda v: self.apply_settings())
        self.filter_cb = ctk.CTkComboBox(row_mode, values=["2.8k", "6k", "15k", "50k", "230k"], width=120, height=34,
                                         corner_radius=8, border_width=1)
        self.filter_cb.set("230k")
        self.filter_cb.pack(side="left")
        self.filter_cb.configure(command=lambda v: self.apply_settings())

        add_left_label("Громкость (AF)")
        self.slider_vol = ctk.CTkSlider(self.left_frame, from_=0, to=255, width=280, height=14,
                                        corner_radius=7, command=self.set_volume)
        self.slider_vol.set(self.current_volume)
        self.slider_vol.pack(pady=2, padx=15, anchor="w")

        add_left_label("Шумоподавитель (SQL)")
        self.slider_sql = ctk.CTkSlider(self.left_frame, from_=0, to=255, width=280, height=14,
                                        corner_radius=7, command=self.set_squelch)
        self.slider_sql.set(self.current_squelch)
        self.slider_sql.pack(pady=2, padx=15, anchor="w")

        row_shift = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        row_shift.pack(fill="x", padx=15, pady=(10, 5))
        ctk.CTkLabel(row_shift, text="IF SHIFT", font=("Inter", 9, "bold"), text_color=t["muted"]).pack(side="left")
        self.slider_if_shift = ctk.CTkSlider(row_shift, from_=0, to=255, width=180, height=10,
                                             corner_radius=5, command=self.set_if_shift)
        self.slider_if_shift.set(128)
        self.slider_if_shift.pack(side="left", padx=5)
        self.lbl_if_shift = ctk.CTkLabel(row_shift, text="0", font=("Consolas", 10, "bold"), width=40)
        self.lbl_if_shift.pack(side="left")
        self.btn_reset_if = ctk.CTkButton(row_shift, text="⟲", width=28, height=22, corner_radius=6, border_width=1,
                                          font=("Inter", 12), command=lambda: self._set_if_shift(128))
        self.btn_reset_if.pack(side="left", padx=(6, 0))

        row_bfo = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        row_bfo.pack(fill="x", padx=15, pady=(0, 10))
        ctk.CTkLabel(row_bfo, text="BFO SHIFT", font=("Inter", 9, "bold"), text_color=t["muted"]).pack(side="left")
        self.slider_bfo = ctk.CTkSlider(row_bfo, from_=0, to=255, width=180, height=10,
                                        corner_radius=5, command=self.set_bfo)
        self.slider_bfo.set(128)
        self.slider_bfo.pack(side="left", padx=5)
        self.lbl_bfo = ctk.CTkLabel(row_bfo, text="0", font=("Consolas", 10, "bold"), width=40)
        self.lbl_bfo.pack(side="left")
        self.btn_reset_bfo = ctk.CTkButton(row_bfo, text="⟲", width=28, height=22, corner_radius=6, border_width=1,
                                           font=("Inter", 12), command=lambda: self._set_bfo(128))
        self.btn_reset_bfo.pack(side="left", padx=(6, 0))

        add_left_label("Тракт")
        row_dsp = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        row_dsp.pack(fill="x", padx=15, pady=(0, 10))
        self.switch_att = ctk.CTkSwitch(row_dsp, text="ATT", font=("Inter", 9), command=self._toggle_att)
        self.switch_att.pack(side="left", padx=(0, 8))
        self.switch_agc = ctk.CTkSwitch(row_dsp, text="AGC", font=("Inter", 9), command=self._toggle_agc)
        self.switch_agc.pack(side="left", padx=(0, 8))
        self.switch_agc.select()
        self.switch_nb = ctk.CTkSwitch(row_dsp, text="NB", font=("Inter", 9), command=self._toggle_nb)
        self.switch_nb.pack(side="left", padx=(0, 8))
        self.switch_afc = ctk.CTkSwitch(row_dsp, text="AFC", font=("Inter", 9), command=self._toggle_afc)
        self.switch_afc.pack(side="left", padx=(0, 8))
        self.switch_vsc = ctk.CTkSwitch(row_dsp, text="VSC", font=("Inter", 9), command=self._toggle_vsc)
        self.switch_vsc.pack(side="left")

        row_ctcss = ctk.CTkFrame(self.left_frame, fg_color="transparent")
        row_ctcss.pack(fill="x", padx=15, pady=(0, 15))
        ctk.CTkLabel(row_ctcss, text="CTCSS", font=("Inter", 9, "bold"), text_color=t["muted"]).pack(side="left")
        self.ctcss_cb = ctk.CTkComboBox(row_ctcss, values=list(CTCSS_TONES.keys()), width=100, height=28,
                                        font=("Inter", 10), corner_radius=6, border_width=1, command=self.set_ctcss)
        self.ctcss_cb.set("OFF")
        self.ctcss_cb.pack(side="left", padx=10)

        self.right_frame = ctk.CTkFrame(main, corner_radius=12)
        self.right_frame.grid(row=0, column=1, padx=(5, 0), pady=5, sticky="nsew")

        self.right_labels = []

        def add_right_label(text):
            lbl = ctk.CTkLabel(self.right_frame, text=text.upper(), font=("Inter", 9, "bold"))
            lbl.pack(anchor="w", padx=15, pady=(10, 2))
            self.right_labels.append(lbl)

        add_right_label("Сканер")
        row_band = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        row_band.pack(pady=2, padx=15, fill="x")
        self.band_cb = ctk.CTkComboBox(row_band, values=["Custom", "FM Radio", "Air Band", "Amateur 2m", "PMR/LPD"],
                                       width=180, height=34, corner_radius=8, border_width=1, command=self._on_band_change)
        self.band_cb.set("FM Radio")
        self.band_cb.pack(side="left", padx=(0, 8))
        self.btn_add_profile = ctk.CTkButton(row_band, text="+", width=36, height=36, corner_radius=8, border_width=1,
                                             font=("Inter", 16), command=self._save_custom_profile)
        self.btn_add_profile.pack(side="left")

        row_range = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        row_range.pack(pady=2, padx=15, fill="x")
        self.entry_scan_start = ctk.CTkEntry(row_range, placeholder_text="Старт", width=90, height=34,
                                             justify="center", corner_radius=8, border_width=1)
        self.entry_scan_start.insert(0, "87.5")
        self.entry_scan_start.pack(side="left", padx=(0, 8))
        self.entry_scan_end = ctk.CTkEntry(row_range, placeholder_text="Стоп", width=90, height=34,
                                           justify="center", corner_radius=8, border_width=1)
        self.entry_scan_end.insert(0, "108.0")
        self.entry_scan_end.pack(side="left", padx=(0, 8))
        self.step_cb = ctk.CTkComboBox(row_range, values=["5", "10", "12.5", "25", "50", "100"], width=80, height=34,
                                       corner_radius=8, border_width=1)
        self.step_cb.set("100")
        self.step_cb.pack(side="left")

        add_right_label("Порог (S)")
        self.slider_threshold = ctk.CTkSlider(self.right_frame, from_=0.05, to=0.9, width=280, height=14, corner_radius=7)
        self.slider_threshold.set(0.3)
        self.slider_threshold.pack(pady=2, padx=15, anchor="w")

        self.btn_scan = ctk.CTkButton(self.right_frame, text="▶  СТАРТ СКАНЕРА", height=44, corner_radius=10,
                                      font=("Inter", 14, "bold"), command=self.toggle_scan)
        self.btn_scan.pack(fill="x", padx=15, pady=(15, 5))

        self.progress_scan = ctk.CTkProgressBar(self.right_frame, width=280, height=8, corner_radius=4)
        self.progress_scan.set(0)
        self.progress_scan.pack(padx=15, pady=(0, 5), anchor="w")

        self.lbl_scan_info = ctk.CTkLabel(self.right_frame, text="Готов к работе", font=("Inter", 11))
        self.lbl_scan_info.pack(pady=(0, 10))

        self.action_frame = ctk.CTkFrame(self.right_frame, fg_color="transparent")
        self.action_frame.pack(fill="x", padx=15)
        self.btn_save_freq = ctk.CTkButton(self.action_frame, text="💾 В память", height=34, corner_radius=8,
                                           border_width=1, state="disabled", font=("Inter", 11), command=self.save_current_freq)
        self.btn_save_freq.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.btn_skip = ctk.CTkButton(self.action_frame, text="⏭ Пропустить", height=34, corner_radius=8,
                                      border_width=1, state="disabled", font=("Inter", 11), command=self.skip_current_freq)
        self.btn_skip.pack(side="left", fill="x", expand=True, padx=(4, 0))

        add_right_label("Найденные станции")
        self.found_list = ctk.CTkTextbox(self.right_frame, height=120, font=("Consolas", 11), corner_radius=8, border_width=1)
        self.found_list.pack(fill="both", expand=True, padx=15, pady=(2, 10))
        self.found_list.configure(state="disabled")

        self.btn_export = ctk.CTkButton(self.right_frame, text="📊 Экспорт в CSV", height=34, corner_radius=8, border_width=1,
                                        fg_color="transparent", font=("Inter", 11), command=self.export_csv)
        self.btn_export.pack(fill="x", padx=15, pady=(0, 15))

    def _update_freq_widgets(self):
        self.entry_freq.delete(0, "end")
        self.entry_freq.insert(0, f"{self.current_freq_mhz:.5f}")
        self.lbl_vfo.configure(text=f"{self.current_freq_mhz:.5f}")

    def _on_dial_move(self, step):
        if self.is_scanning:
            return
        self.current_freq_mhz = round(self.current_freq_mhz + step * 0.001, 6)
        self.current_freq_mhz = max(0.5, min(1300.0, self.current_freq_mhz))
        self._update_freq_widgets()
        if self.is_connected:
            self.sync_frequency()

    def _step_freq(self, direction):
        if self.is_scanning:
            return
        step = VFO_STEPS.get(self.step_vfo_cb.get(), 0.0001)
        self.current_freq_mhz = round(self.current_freq_mhz + direction * step, 6)
        self.current_freq_mhz = max(0.5, min(1300.0, self.current_freq_mhz))
        self._update_freq_widgets()
        if self.is_connected:
            self.sync_frequency()

    def _on_band_change(self, band):
        if band == "Custom":
            return
        p = self.profiles.get(band)
        if not p:
            return
        self.entry_scan_start.delete(0, "end")
        self.entry_scan_start.insert(0, str(p["start"]))
        self.entry_scan_end.delete(0, "end")
        self.entry_scan_end.insert(0, str(p["end"]))
        self.mode_cb.set(p["mode"])
        self.filter_cb.set(p["filter"])
        self.slider_threshold.set(p["threshold"])
        self.step_cb.set(str(p.get("step", 100)))

    def _save_custom_profile(self):
        name = ctk.CTkInputDialog(text="Введите имя профиля:", title="Новый профиль").get_input()
        if not name:
            return
        try:
            self.profiles[name] = {
                "start": float(self.entry_scan_start.get()),
                "end": float(self.entry_scan_end.get()),
                "step": float(self.step_cb.get()),
                "threshold": float(self.slider_threshold.get()),
                "mode": self.mode_cb.get(),
                "filter": self.filter_cb.get()
            }
            self._save_profiles()
            self.band_cb.configure(values=list(self.profiles.keys()))
            self.band_cb.set(name)
            self._log(f"Профиль '{name}' сохранен.")
        except ValueError:
            messagebox.showerror("Ошибка", "Проверьте введенные данные.")

    def save_current_freq(self):
        freq = self.current_freq_mhz
        if freq not in [f["freq"] for f in self.found_freqs]:
            self.found_freqs.append({"freq": freq, "smeter": self.raw_smeter})
            self._update_found_list()
            self._log(f"В память добавлена {freq:.5f} МГц.")
            self.btn_save_freq.configure(state="disabled")

    def skip_current_freq(self):
        freq = self.current_freq_mhz
        if freq not in self.skipped_freqs:
            self.skipped_freqs.append(freq)
            self._log(f"{freq:.5f} МГц добавлена в исключения.")
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
            self._log(f"Данные сохранены в {fname}")
            messagebox.showinfo("Успех", f"Файл: {fname}")
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _log(self, msg):
        print(f"[LOG {time.strftime('%H:%M:%S')}] {msg}", flush=True)

    def _toggle_meter_log(self):
        self.log_meter = bool(self.switch_log.get())
        self._log(f"Периодический лог S-meter: {'ВКЛ' if self.log_meter else 'ВЫКЛ'}")
        self._apply_theme()

    def refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb.configure(values=ports)
        if ports:
            self.port_cb.set(ports[0])

    def toggle_connection(self):
        if self.is_connected:
            self.disconnect_radio()
        else:
            self.connect_radio()

    def _flush_serial_input(self):
        try:
            if self.ser and self.ser.is_open:
                self.ser.reset_input_buffer()
        except Exception:
            pass
        self.rx_buffer = ""

    def connect_radio(self):
        port = self.port_cb.get()
        if not port:
            return
        try:
            self.ser = serial.Serial(port, 9600, timeout=0.1, write_timeout=1.0, dsrdtr=False, xonxoff=False)
            self.ser.rts = True
            self.is_connected = True
            self.stop_event.clear()
            self.rx_buffer = ""
            self.rx_dropped_bytes = 0
            with self.rx_condition:
                self.rx_tokens.clear()

            self.reader_thread = threading.Thread(target=self._serial_reader, daemon=True)
            self.reader_thread.start()

            self._log("Инициализация аудиотракта...")
            self.send_command("H101", wait_response=False)
            time.sleep(0.3)
            self.send_command("H1?", wait_response=False)
            time.sleep(0.3)
            self.send_command("G301", wait_response=False)
            time.sleep(0.2)
            self.send_command("G103", wait_response=False)
            time.sleep(0.2)
            
            self.send_command("J4380", wait_response=False)
            self.send_command("J4A80", wait_response=False)
            time.sleep(0.1)
            
            self.send_command("J4100", wait_response=False)
            self.send_command("J5100", wait_response=False)
            time.sleep(0.1)
            
            self.send_command(f"J40{self.current_volume:02X}", wait_response=False)
            time.sleep(0.1)
            self.send_command(f"J40{self.current_volume:02X}", wait_response=False)
            time.sleep(0.1)
            
            self.send_command(f"J41{self.current_squelch:02X}", wait_response=False)
            self.send_command(f"J45{1 if self.dsp_agc else 0:02X}", wait_response=False)
            self.send_command(f"J46{1 if self.dsp_nb else 0:02X}", wait_response=False)
            self.send_command(f"J47{1 if self.dsp_attenuator else 0:02X}", wait_response=False)
            self.send_command("J5000", wait_response=False)
            time.sleep(0.1)

            gd = self.send_command_sync("GD?", wait_response=True, timeout=1.5)
            if gd:
                try:
                    self.has_dsp = bool(int(gd[2:4], 16) & 0x01)
                except ValueError:
                    self.has_dsp = False
            else:
                self.has_dsp = False

            if self.has_dsp:
                self._log("DSP-модуль обнаружен.")
            else:
                self._log("DSP-модуль не найден (GD00). ATT/AGC/NB — аналоговые функции.")
                self._disable_dsp_controls()

            self.sync_frequency(force=True)
            self._start_watchdog()

            self._apply_theme()
            self.port_cb.configure(state="disabled")
            self.lbl_status.configure(text="● ПОДКЛЮЧЕНО")
            self._log("Соединение установлено. Watchdog запущен.")

        except Exception as e:
            self.is_connected = False
            if self.ser:
                try:
                    with self.com_lock:
                        self.ser.close()
                except Exception:
                    pass
            messagebox.showerror("Ошибка", f"Не удалось подключиться:\n{e}")

    def _disable_dsp_controls(self):
        for sw in [self.switch_afc, self.switch_vsc]:
            sw.configure(state="disabled")

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
        self._apply_theme()
        self.port_cb.configure(state="readonly")
        self.lbl_status.configure(text="● ОТКЛЮЧЕНО")
        self.smeter_canvas.set_value(0)
        self.lbl_busy.configure(text="● OFF")
        if was_connected:
            self._log("Соединение разорвано.")

    def _start_watchdog(self):
        def watchdog_tick():
            if not self.is_connected or self._closing:
                return
            try:
                self.send_command("I0?", wait_response=False)
            except Exception:
                pass
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
                    if not self.ser or not self.ser.is_open:
                        break
                    waiting = self.ser.in_waiting
                    chunk = self.ser.read(waiting if waiting else 1)

                if not chunk:
                    continue

                if self.debug_raw_log:
                    self._log(f"RX RAW: {chunk!r}")

                clean = bytes(b for b in chunk if 32 <= b < 127 or b in (10, 13))
                self.rx_dropped_bytes += len(chunk) - len(clean)
                if not clean:
                    continue

                self.rx_buffer += clean.decode("ascii")
                self.rx_buffer = self.rx_buffer.replace("\r", "").replace("\n", "")

                matches = list(token_re.finditer(self.rx_buffer))
                if matches:
                    for match in matches:
                        token = (match.group(1) + match.group(2)).upper()
                        with self.rx_condition:
                            self.rx_tokens.append(token)
                            if len(self.rx_tokens) > 100:
                                del self.rx_tokens[:-100]
                            self.rx_condition.notify_all()
                        self._handle_rx_token(token)
                    self.rx_buffer = self.rx_buffer[matches[-1].end():]

                if len(self.rx_buffer) > 32:
                    self.rx_buffer = self.rx_buffer[-8:]

            except (serial.SerialException, OSError) as e:
                if self.is_connected:
                    self._log(f"Ошибка чтения COM-порта: {e}")
                break
            except Exception as e:
                if self.is_connected:
                    self._log(f"Ошибка обработчика RX: {e}")
                time.sleep(0.05)

    def _handle_rx_token(self, token):
        prefix = token[:2]
        try:
            value = int(token[2:4], 16)
        except ValueError:
            return
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
            if self.is_connected:
                self.smeter_canvas.set_value(self.raw_smeter)
                
                self.lbl_busy.configure(
                    text="● BUSY" if self.is_busy else "● OFF",
                    text_color=self.theme["success"] if self.is_busy else self.theme["off"]
                )
                
                deviation = (self.center_meter - 128) / 128.0
                self.progress_center.set(max(0.0, min(1.0, (deviation + 1) / 2)))
                self.lbl_center_val.configure(text=f"{self.center_meter:02X}")

                if self.log_meter:
                    now = time.monotonic()
                    if now - self._last_meter_log >= 1.0:
                        self._last_meter_log = now
                        self._log(f"METER S={self.raw_smeter:3d}(0x{self.raw_smeter:02X}) "
                                  f"BUSY={int(self.is_busy)} CTR=0x{self.center_meter:02X} "
                                  f"F={self.current_freq_mhz:.5f} {self.current_mode}/{self.current_filter} "
                                  f"IF={self.if_shift_value - 128:+d} BFO={self.bfo_value - 128:+d} "
                                  f"drop={self.rx_dropped_bytes}")
            self.after(100, self._update_gui_indicators)
        except tk.TclError:
            pass

    def _take_token(self, prefix, timeout=0.8):
        deadline = time.monotonic() + timeout
        with self.rx_condition:
            while True:
                for index, token in enumerate(self.rx_tokens):
                    if token.startswith(prefix):
                        return self.rx_tokens.pop(index)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return ""
                self.rx_condition.wait(remaining)

    def send_command_sync(self, cmd, wait_response=True, timeout=0.8):
        prefix = cmd[:2].upper()
        if wait_response:
            with self.rx_condition:
                self.rx_tokens = [token for token in self.rx_tokens if not token.startswith(prefix)]
        with self.com_lock:
            if not self.ser or not self.ser.is_open:
                return ""
            try:
                self.ser.write((cmd + "\r\n").encode("ascii"))
                self.ser.flush()
                self._log(f"TX: {cmd}")
            except (serial.SerialException, OSError, serial.SerialTimeoutException) as e:
                self._log(f"Ошибка связи Serial ({cmd}): {e}")
                return ""
        if not wait_response:
            return ""
        response = self._take_token(prefix, timeout=timeout)
        if response:
            self._log(f"RX: {response!r}")
        else:
            self._log(f"Тайм-аут ответа на {cmd}")
        return response

    def send_command(self, cmd, wait_response=False):
        return self.send_command_sync(cmd, wait_response=wait_response)

    def _slider_command(self, key, val, prefix, label=None, offset=0):
        value = int(round(float(val)))
        value = max(0, min(255, value))
        if label is not None:
            label.configure(text=str(value - offset))
        st = self._slider_state.setdefault(key, {"last": 0.0, "pending": None, "timer": None})
        st["pending"] = value
        wait = self.slider_interval - (time.monotonic() - st["last"])
        if wait <= 0:
            self._flush_slider(key, prefix)
        elif st["timer"] is None:
            try:
                st["timer"] = self.after(int(wait * 1000) + 5,
                                         lambda k=key, p=prefix: self._flush_slider(k, p))
            except tk.TclError:
                pass
        return value

    def _flush_slider(self, key, prefix):
        st = self._slider_state.get(key)
        if not st:
            return
        if st["timer"] is not None:
            try:
                self.after_cancel(st["timer"])
            except Exception:
                pass
            st["timer"] = None
        value = st["pending"]
        if value is None:
            return
        st["pending"] = None
        st["last"] = time.monotonic()
        self.send_command(f"{prefix}{value:02X}")

    def set_volume(self, val):
        self.current_volume = self._slider_command("vol", val, "J40")

    def set_squelch(self, val):
        self.current_squelch = self._slider_command("sql", val, "J41")

    def set_if_shift(self, val):
        self.if_shift_value = self._slider_command("if", val, "J43", self.lbl_if_shift, 128)

    def set_bfo(self, val):
        self.bfo_value = self._slider_command("bfo", val, "J4A", self.lbl_bfo, 128)

    def _set_if_shift(self, value):
        self.if_shift_value = int(value)
        self.slider_if_shift.set(value)
        self.lbl_if_shift.configure(text=str(int(value) - 128))
        self.send_command(f"J43{int(value):02X}")

    def _set_bfo(self, value):
        self.bfo_value = int(value)
        self.slider_bfo.set(value)
        self.lbl_bfo.configure(text=str(int(value) - 128))
        self.send_command(f"J4A{int(value):02X}")

    def _reset_shifts(self):
        self._set_if_shift(128)
        self._set_bfo(128)

    def _toggle_att(self):
        if not self._ui_ready:
            return
        self.dsp_attenuator = bool(self.switch_att.get())
        self.send_command(f"J47{1 if self.dsp_attenuator else 0:02X}")
        self._apply_theme()

    def _toggle_agc(self):
        if not self._ui_ready:
            return
        self.dsp_agc = bool(self.switch_agc.get())
        self.send_command(f"J45{1 if self.dsp_agc else 0:02X}")
        self._apply_theme()

    def _toggle_nb(self):
        if not self._ui_ready:
            return
        self.dsp_nb = bool(self.switch_nb.get())
        self.send_command(f"J46{1 if self.dsp_nb else 0:02X}")
        self._apply_theme()

    def _toggle_afc(self):
        if not self._ui_ready:
            return
        self.dsp_afc = bool(self.switch_afc.get())
        self.send_command(f"J50{1 if self.dsp_afc else 0:02X}")
        self._apply_theme()

    def _toggle_vsc(self):
        if not self._ui_ready:
            return
        self.dsp_vsc = bool(self.switch_vsc.get())
        self.send_command(f"J50{1 if self.dsp_vsc else 0:02X}")
        self._apply_theme()

    def set_ctcss(self, tone_name):
        code = CTCSS_TONES.get(tone_name, 0)
        self.ctcss_code = code
        self.send_command(f"J51{code:02X}")
        self._log(f"CTCSS: {tone_name}")

    def _after_mode_change(self, old_mode, old_filter, new_mode, new_filter):
        self._log(f"Смена режима {old_mode}/{old_filter} → {new_mode}/{new_filter}: восстановление аудиотракта")
        
        if self.if_shift_value != 128 or self.bfo_value != 128:
            self._log("IF/BFO -> центр")
            self._reset_shifts()
        
        if new_mode in ("LSB", "USB", "CW"):
            if self.ctcss_code != 0:
                self._log("CTCSS -> OFF для SSB/CW")
                self.ctcss_code = 0
                self.ctcss_cb.set("OFF")
                self.send_command("J5100", wait_response=False)
            if self.dsp_vsc:
                self._log("VSC -> OFF для SSB/CW")
                self.dsp_vsc = False
                self.switch_vsc.deselect()
                self.send_command("J5000", wait_response=False)
        
        self._log("Смена режима (K)")
        self.sync_frequency(force=True)
        self.send_command(f"J40{self.current_volume:02X}", wait_response=False)
        self.send_command(f"J41{self.current_squelch:02X}", wait_response=False)
        self.send_command(f"J45{1 if self.dsp_agc else 0:02X}", wait_response=False)
        self.send_command(f"J46{1 if self.dsp_nb else 0:02X}", wait_response=False)
        self.send_command(f"J47{1 if self.dsp_attenuator else 0:02X}", wait_response=False)
        self.send_command("J5000", wait_response=False)
        self.sync_frequency(force=True)

    def apply_settings(self):
        if self._applying_settings:
            return
        self._applying_settings = True
        try:
            old_mode, old_filter = self.current_mode, self.current_filter
            try:
                self.current_freq_mhz = round(float(self.entry_freq.get().strip().replace(",", ".")), 6)
            except ValueError:
                return
            self.current_freq_mhz = max(0.5, min(1300.0, self.current_freq_mhz))
            self.current_mode = self.mode_cb.get()

            # ИСПРАВЛЕНИЕ: не принудительно сбрасывать фильтр — пользователь выбирает сам
            self.current_filter = self.filter_cb.get()

            self.lbl_vfo.configure(text=f"{self.current_freq_mhz:.5f}")

            changed = (self.current_mode != old_mode) or (self.current_filter != old_filter)
            if self.is_connected:
                self.sync_frequency(force=True)
                if changed:
                    self._after_mode_change(old_mode, old_filter, self.current_mode, self.current_filter)
        finally:
            self._applying_settings = False

    def sync_frequency(self, force=False):
        if not self.is_connected:
            return
        if threading.current_thread() is not threading.main_thread():
            with self.tune_lock:
                now = time.monotonic()
                if not force and now - self.last_tune_time < self.tune_interval:
                    return
                self.last_tune_time = now
            self._send_tune()
            return

        self._tune_pending = True
        wait = self.tune_interval - (time.monotonic() - self.last_tune_time)
        if force or wait <= 0:
            self._tune_flush()
        elif self._tune_timer is None:
            try:
                self._tune_timer = self.after(int(wait * 1000) + 5, self._tune_flush)
            except tk.TclError:
                pass

    def _tune_flush(self):
        if self._tune_timer is not None:
            try:
                self.after_cancel(self._tune_timer)
            except Exception:
                pass
            self._tune_timer = None
        if not self._tune_pending:
            return
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
        try:
            self.lbl_vfo.configure(text=f"{freq_hz / 1_000_000:.5f}")
        except tk.TclError:
            pass

    def run_diagnostics(self):
        if not self.is_connected:
            messagebox.showinfo("Диагностика", "Сначала подключитесь к приёмнику.")
            return
        if self.diag_running:
            return
        self.diag_running = True
        self.btn_diag.configure(state="disabled")
        self.switch_log.select()
        self.log_meter = True
        self._log("=== ДИАГНОСТИКА: СТАРТ ===")

        def done():
            self._log("=== ДИАГНОСТИКА: КОНЕЦ ===")
            self.diag_running = False
            if not self._closing:
                self.btn_diag.configure(state="normal")

        self.after(5000, done)

    def toggle_scan(self):
        if not self.is_connected:
            return
        if self.is_scanning:
            self.is_scanning = False
            self.stop_event.set()
            self.btn_save_freq.configure(state="disabled")
            self.btn_skip.configure(state="disabled")
            self.lbl_scan_info.configure(text="Остановлено")
            self._log("Сканер остановлен.")
            self._apply_theme()
        else:
            try:
                self.scan_start_mhz = float(self.entry_scan_start.get())
                self.scan_end_mhz = float(self.entry_scan_end.get())
                self.scan_step_khz = float(self.step_cb.get())
                self.scan_threshold = float(self.slider_threshold.get())
                self.current_freq_mhz = self.scan_start_mhz
                self.is_scanning = True
                self.stop_event.clear()
                self.lbl_scan_info.configure(text="Поиск...")
                self._log(f"Сканирование {self.scan_start_mhz} - {self.scan_end_mhz} МГц")
                self._apply_theme()
                if self.scan_thread is None or not self.scan_thread.is_alive():
                    self.scan_thread = threading.Thread(target=self._scan_worker, daemon=True)
                    self.scan_thread.start()
            except ValueError:
                messagebox.showerror("Ошибка", "Проверьте параметры сканирования.")

    @staticmethod
    def _parse_hex_response(response, command):
        if not response:
            return None
        idx = response.find(command)
        if idx < 0 or len(response) < idx + len(command) + 2:
            return None
        try:
            return int(response[idx + len(command):idx + len(command) + 2], 16)
        except ValueError:
            return None

    def _scan_worker(self):
        while self.is_scanning and self.is_connected and not self.stop_event.is_set():
            try:
                nf = round(self.current_freq_mhz + self.scan_step_khz / 1000.0, 6)
                if nf > self.scan_end_mhz:
                    nf = self.scan_start_mhz
                while any(abs(nf - skip) < 0.001 for skip in self.skipped_freqs):
                    nf = round(nf + self.scan_step_khz / 1000.0, 6)
                    if nf > self.scan_end_mhz:
                        nf = self.scan_start_mhz

                self.current_freq_mhz = nf
                self.after(0, self._update_freq_widgets)
                self.sync_frequency()

                time.sleep(self.scan_speed_ms / 1000.0)

                raw = self.send_command_sync("I1?", wait_response=True, timeout=0.7)
                scan_value = self._parse_hex_response(raw, "I1")
                if scan_value is not None:
                    self.raw_smeter = scan_value
                    self.smeter_value = min(scan_value / 255.0, 1.0)

                if self.smeter_value > self.scan_threshold:
                    freq = self.current_freq_mhz
                    is_nearby = False
                    for item in self.found_freqs:
                        if abs(item["freq"] - freq) < 0.3:
                            is_nearby = True
                            break
                    if not is_nearby:
                        self.found_freqs.append({"freq": freq, "smeter": self.raw_smeter})
                        self.after(0, self._update_found_list)
                        self.after(0, lambda f=freq, s=self.raw_smeter:
                                   self._log(f"Новая станция: {f:.5f} МГц (S={s})"))
                        self.after(0, lambda f=freq:
                                   self.lbl_scan_info.configure(text=f"Найдено: {f:.5f} МГц (пауза)"))
                        time.sleep(self.scan_hold_time)
                        if self.is_scanning:
                            self.after(0, lambda: self.lbl_scan_info.configure(text="Поиск..."))
            except Exception:
                break

    def on_closing(self):
        self._closing = True
        self.stop_event.set()
        self.is_scanning = False
        self.disconnect_radio()
        try:
            self.destroy()
        except Exception:
            pass
        sys.exit(0)


if __name__ == "__main__":
    app = PCR1000Pro()
    app.mainloop()