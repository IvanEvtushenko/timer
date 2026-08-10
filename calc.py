#!/usr/bin/env python3
"""Калькулятор темпа: факт против плана по времени из time_log.csv.

Вводится:
  1. дата, с которой считаем;
  2. дата, по которую считаем (необязательно, по умолчанию — бесконечность);
  3. желаемый темп в часах в неделю.
Снизу рисуется график накопленных часов: факт против плановой прямой.

Запуск:  python3 calc.py
Оформление — то же, что у секундомера (stopwatch.py).
"""

import csv
import math
import tkinter as tk
import tkinter.font as tkfont
from datetime import date, datetime, timedelta
from pathlib import Path

# --- Настройки ----------------------------------------------------------------
LOG_FILE = Path(__file__).resolve().parent / "time_log.csv"
ACCENT_FONT = "Poppins ExtraLight"   # тот же тонкий шрифт, что у таймера
DEFAULT_PACE = 49.0                  # ч/нед по умолчанию (= 7 ч/день)

# --- Палитра (как в таймере) --------------------------------------------------
BG = "#14161c"
FG = "#f4f6fb"          # яркий акцент
INPUT = "#aeb6c7"       # текст в полях — приглушён, но читаем
MUTED = "#6b7385"       # вторичный текст / плановая линия
FAINT = "#4b5263"       # совсем тихие подписи
LINE = "#262a34"        # оси, сетка, подчёркивания
AHEAD = "#5aa576"       # опережение плана
BEHIND = "#c96a5e"      # отставание от плана

DATE_FORMATS = ("%Y-%m-%d", "%Y.%m.%d", "%d.%m.%Y")
OPEN_TOKENS = {"", "∞", "inf", "+inf", "-", "—"}


def parse_date(text):
    text = text.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def nice_step(vmax, target=5):
    """Приятный шаг сетки, чтобы делений было ~target."""
    if vmax <= 0:
        return 1.0
    raw = vmax / target
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            return m * mag
    return 10 * mag


def fmt_h(h):
    return f"{h:.1f}".rstrip("0").rstrip(".") + " ч"


class PaceCalc:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("калькулятор темпа")
        root.configure(bg=BG)

        self._plot = None           # посчитанные данные для отрисовки
        self._build_ui()
        self._fit_and_center(720, 700)
        self._recompute()
        self._auto()                # периодически подтягивать свежий лог

        root.bind("<Configure>", lambda e: e.widget is root and self._draw())

    # --- Интерфейс ------------------------------------------------------------
    def _build_ui(self):
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(expand=True, fill="both", padx=40, pady=(26, 30))

        daily, earliest = self._load_daily()
        start_default = earliest.isoformat() if earliest else date.today().isoformat()

        form = tk.Frame(wrap, bg=BG)
        form.pack(anchor="center")
        self.e_start = self._field(form, 0, "считать с", start_default)
        self.e_end = self._field(form, 1, "по", "∞")
        self.e_pace = self._field(form, 2, "темп, ч/нед", f"{DEFAULT_PACE:g}")

        # Крупный акцент — отклонение от плана
        self.accent_font = tkfont.Font(family=ACCENT_FONT, size=58)
        self.delta_label = tk.Label(wrap, text="", fg=FG, bg=BG, font=self.accent_font)
        self.delta_label.pack(pady=(18, 0))
        self.status_label = tk.Label(wrap, text="", fg=MUTED, bg=BG,
                                     font=("DejaVu Sans", 11), justify="center")
        self.status_label.pack(pady=(2, 14))

        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, height=260)
        self.canvas.pack(expand=True, fill="both")

    def _field(self, parent, row, caption, value):
        tk.Label(parent, text=caption, fg=MUTED, bg=BG, font=("DejaVu Sans", 12),
                 width=12, anchor="e").grid(row=row, column=0, padx=(0, 14), pady=6)
        cell = tk.Frame(parent, bg=BG)
        cell.grid(row=row, column=1, sticky="w", pady=6)
        entry = tk.Entry(cell, justify="left", font=("DejaVu Sans", 13), bg=BG,
                         fg=INPUT, insertbackground=INPUT, relief="flat", bd=0,
                         highlightthickness=0, width=18)
        entry.insert(0, value)
        entry.pack(ipady=3)
        tk.Frame(cell, bg=LINE, height=1).pack(fill="x")
        entry.bind("<Return>", self._on_edit)
        entry.bind("<FocusOut>", self._on_edit)
        entry.bind("<Escape>", lambda e: (self.root.focus_set(), "break")[1])
        return entry

    def _fit_and_center(self, w, h):
        self.root.update_idletasks()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 3
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(560, 560)

    def _on_edit(self, _):
        self._recompute()
        return "break"

    def _auto(self):
        self._recompute()
        self.root.after(60000, self._auto)   # раз в минуту подхватываем новый лог

    # --- Данные ---------------------------------------------------------------
    @staticmethod
    def _load_daily():
        """dict{date: секунды за день} и самая ранняя дата (или None)."""
        daily, earliest = {}, None
        if not LOG_FILE.exists():
            return daily, None
        with open(LOG_FILE, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    d = datetime.strptime(row["start"], "%Y-%m-%d %H:%M:%S").date()
                    daily[d] = daily.get(d, 0) + int(row["duration_sec"])
                except (ValueError, KeyError):
                    continue
                if earliest is None or d < earliest:
                    earliest = d
        return daily, earliest

    def _recompute(self):
        start = parse_date(self.e_start.get())
        end_raw = self.e_end.get().strip().lower()
        end = None if end_raw in OPEN_TOKENS else parse_date(self.e_end.get())
        try:
            pace = float(self.e_pace.get().strip().replace(",", "."))
        except ValueError:
            pace = None

        if start is None or pace is None or (self.e_end.get().strip().lower() not in OPEN_TOKENS and end is None):
            self._plot = None
            self.delta_label.config(text="—", fg=MUTED)
            self.status_label.config(text="проверь формат: дата ГГГГ-ММ-ДД, темп — число",
                                     fg=BEHIND)
            self._draw()
            return

        daily, _ = self._load_daily()
        today = date.today()
        actual_end = today if end is None else min(end, today)
        x_max = max(start, end if end is not None else today)

        # Накопленный факт по дням
        cum, actual_pts = 0.0, [(start, 0.0)]
        d = start
        while d <= actual_end:
            cum += daily.get(d, 0) / 3600
            actual_pts.append((d, cum))
            d += timedelta(days=1)
        actual_h = cum

        # План (прямая с наклоном pace ч/нед)
        weeks_now = max(0.0, (actual_end - start).days / 7)
        plan_now = pace * weeks_now
        plan_end = pace * (max(0, (x_max - start).days) / 7)
        delta = actual_h - plan_now
        my_pace = actual_h / weeks_now if weeks_now > 0 else 0.0

        self._plot = dict(start=start, x_max=x_max, today=today,
                          actual_pts=actual_pts, plan_end=plan_end,
                          y_max=max(actual_h, plan_end, 1.0))

        self.delta_label.config(text=f"{delta:+.1f} ч", fg=AHEAD if delta >= 0 else BEHIND)
        word = "впереди плана" if delta >= 0 else "позади плана"
        self.status_label.config(
            text=f"факт {fmt_h(actual_h)}  ·  план {fmt_h(plan_now)}  ·  {abs(delta):.1f} ч {word}\n"
                 f"твой темп {my_pace:.1f} ч/нед   (цель {pace:g})", fg=MUTED)
        self._draw()

    # --- Отрисовка графика ----------------------------------------------------
    def _draw(self):
        c = self.canvas
        c.delete("all")
        W, H = c.winfo_width(), c.winfo_height()
        if W <= 1 or H <= 1:
            return
        if not self._plot:
            return

        p = self._plot
        start, x_max, y_max = p["start"], p["x_max"], p["y_max"]
        left, right, top, bottom = 52, W - 30, 20, H - 26
        span = max(1, (x_max - start).days)

        def sx(dt):
            return left + (right - left) * ((dt - start).days / span)

        def sy(h):
            return bottom - (bottom - top) * (h / y_max)

        # Сетка по часам + подписи оси Y
        step = nice_step(y_max)
        v = 0.0
        while v <= y_max + 1e-9:
            yy = sy(v)
            c.create_line(left, yy, right, yy, fill=LINE)
            c.create_text(left - 8, yy, text=f"{v:g}", fill=FAINT, anchor="e",
                          font=("DejaVu Sans", 9))
            v += step

        # Подписи оси X (несколько дат)
        for i in range(5):
            dt = start + timedelta(days=round(span * i / 4))
            xx = sx(dt)
            c.create_text(xx, bottom + 12, text=dt.strftime("%d.%m"), fill=FAINT,
                          anchor="n", font=("DejaVu Sans", 9))

        # Вертикаль «сегодня», если справа есть будущее
        if p["today"] < x_max:
            tx = sx(p["today"])
            c.create_line(tx, top, tx, bottom, fill=MUTED, dash=(2, 4))
            c.create_text(tx, top - 2, text="сегодня", fill=FAINT, anchor="s",
                          font=("DejaVu Sans", 8))

        # Плановая прямая (пунктир)
        c.create_line(sx(start), sy(0), sx(x_max), sy(p["plan_end"]),
                      fill=MUTED, dash=(5, 4), width=1)

        # Факт (сплошная, яркая)
        pts = [coord for (dt, h) in p["actual_pts"] for coord in (sx(dt), sy(h))]
        if len(pts) >= 4:
            c.create_line(*pts, fill=FG, width=2)
        lx, ly = pts[-2], pts[-1]
        c.create_oval(lx - 3, ly - 3, lx + 3, ly + 3, fill=FG, outline=BG)

        # Легенда
        c.create_line(left, top + 4, left + 22, top + 4, fill=FG, width=2)
        c.create_text(left + 28, top + 4, text="факт", fill=MUTED, anchor="w",
                      font=("DejaVu Sans", 9))
        c.create_line(left + 74, top + 4, left + 96, top + 4, fill=MUTED, dash=(5, 4))
        c.create_text(left + 102, top + 4, text="план", fill=MUTED, anchor="w",
                      font=("DejaVu Sans", 9))


if __name__ == "__main__":
    root = tk.Tk()
    PaceCalc(root)
    root.mainloop()
