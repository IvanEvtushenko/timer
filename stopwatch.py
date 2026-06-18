#!/usr/bin/env python3
"""Секундомер для учёта времени за ноутбуком.

Большие цифры, одна кнопка Старт/Пауза. Каждый непрерывный запуск таймера
(от старта/продолжения до паузы или закрытия окна) пишется отдельной строкой
в CSV-лог. Закрытие окна = стоп.

Цифры выводятся по фиксированным ячейкам (каждый разряд — своя ячейка
постоянной ширины), поэтому таймер не «дёргается» при смене цифр даже на
шрифтах с разной шириной знаков.

Запуск:  python3 stopwatch.py
Горячая клавиша:  Пробел — старт/пауза.
"""

import csv
import time
import tkinter as tk
import tkinter.font as tkfont
from datetime import datetime
from pathlib import Path

# --- Настройки ----------------------------------------------------------------
LOG_FILE = Path(__file__).resolve().parent / "time_log.csv"
# session_start — время первого старта сессии (без учёта пауз): одинаково для
# всех сегментов одной сессии, удобно для группировки.
FIELDS = ["session_start", "start", "end", "duration_sec", "duration_hms", "task"]

# Шрифт цифр таймера (подбери в font_preview.py и впиши сюда).
# Вес «250» в Tkinter числом не задаётся — он берётся из имени семейства,
# поэтому тонкое начертание указываем прямо в названии (…ExtraLight / …Light).
CLOCK_FONT = "Poppins ExtraLight"
CLOCK_SIZE = 184

# --- Палитра (часы — единственный акцент, остальное приглушено) ----------------
BG = "#14161c"          # фон окна
BG_HOVER = "#1e212b"    # подсветка кнопки при наведении
CLOCK_ON = "#f4f6fb"    # часы во время отсчёта — яркие
CLOCK_DIM = "#aeb6c7"   # часы на паузе / в покое — приглушённые, но читаемые
MUTED = "#6b7385"       # вторичный текст
MUTED_SOFT = "#4b5263"  # совсем тихий текст (плейсхолдер, подписи)
LINE = "#262a34"        # тонкая линия под полем задачи

PLACEHOLDER = "try_"


def hms(seconds: float) -> str:
    """Секунды -> 'HH:MM:SS'."""
    s = int(seconds)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


class Stopwatch:
    def __init__(self, root: tk.Tk):
        self.root = root
        # root.title("try_")
        root.configure(bg=BG)

        # Состояние таймера
        self.running = False            # идёт ли отсчёт прямо сейчас
        self.session_active = False     # начата ли сессия (есть незакрытый старт)
        self.accumulated = 0.0          # сумма завершённых сегментов текущей сессии
        self.seg_start_mono = 0.0       # monotonic-метка начала текущего сегмента
        self.seg_start_wall = None      # реальное время начала сегмента (для лога)
        self.session_start_wall = None  # время первого старта текущей сессии
        self._task_is_placeholder = True

        self._ensure_log_format()
        self._build_ui()
        self._fit_and_center()
        self._tick()

        root.bind("<space>", self._space)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

    # --- Интерфейс ------------------------------------------------------------
    def _build_ui(self):
        wrap = tk.Frame(self.root, bg=BG)
        wrap.pack(expand=True, fill="both", padx=40, pady=24)

        self.clock_font = tkfont.Font(family=CLOCK_FONT, size=CLOCK_SIZE)
        self._build_clock(wrap)

        # # Статичная надпись-вордмарк под часами
        # tk.Label(wrap, text="try_", fg=MUTED, bg=BG,
        #          font=("DejaVu Sans Mono", 13)).pack(pady=(2, 18))

        # Кнопка — без заливки, в цвет фона
        self.start_btn = self._btn(wrap, "Старт", self.toggle)
        self.start_btn.pack()

        # Поле задачи — под кнопкой, приглушённое, с тонкой линией снизу
        task_wrap = tk.Frame(wrap, bg=BG)
        task_wrap.pack(pady=(20, 0))
        self.task_var = tk.StringVar(value=PLACEHOLDER)
        self.task_entry = tk.Entry(
            task_wrap, textvariable=self.task_var, justify="center",
            font=("DejaVu Sans", 13), bg=BG, fg=MUTED_SOFT,
            insertbackground=MUTED, relief="flat", bd=0,
            highlightthickness=0, width=30)
        self.task_entry.pack(ipady=4)
        tk.Frame(task_wrap, bg=LINE, height=1).pack(fill="x")
        self.task_entry.bind("<FocusIn>", self._task_focus_in)
        self.task_entry.bind("<FocusOut>", self._task_focus_out)
        self.task_entry.bind("<Return>", self._task_done)
        self.task_entry.bind("<Escape>", self._task_done)

    def _build_clock(self, parent):
        """Часы из фиксированных ячеек: смена цифры не сдвигает соседние."""
        self.clock_frame = tk.Frame(parent, bg=BG)
        self.clock_frame.pack(pady=(4, 0))

        digit_w = max(self.clock_font.measure(d) for d in "0123456789") + 4
        colon_w = self.clock_font.measure(":") + 2
        cell_h = self.clock_font.metrics("linespace")

        self.cells = []  # по одной ячейке на символ "00:00:00"
        for char in "00:00:00":
            w = colon_w if char == ":" else digit_w
            cell = tk.Frame(self.clock_frame, width=w, height=cell_h, bg=BG)
            cell.pack_propagate(False)
            cell.pack(side="left")
            lbl = tk.Label(cell, text=char, fg=CLOCK_DIM, bg=BG, font=self.clock_font)
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            self.cells.append(lbl)

    def _set_clock_text(self, text):
        for lbl, ch in zip(self.cells, text):
            if lbl.cget("text") != ch:
                lbl.config(text=ch)

    def _set_clock_color(self, color):
        for lbl in self.cells:
            lbl.config(fg=color)

    def _btn(self, parent, text, cmd):
        b = tk.Button(
            parent, text=text, command=cmd, font=("DejaVu Sans", 13),
            bg=BG, fg=MUTED, activebackground=BG_HOVER, activeforeground=CLOCK_ON,
            relief="flat", bd=0, highlightthickness=0, padx=18, pady=8,
            cursor="hand2")
        b.bind("<Enter>", lambda _: b.config(bg=BG_HOVER, fg=CLOCK_ON))
        b.bind("<Leave>", lambda _: b.config(bg=BG, fg=MUTED))
        return b

    def _fit_and_center(self):
        """Подогнать окно под содержимое (таймер крупный) и поставить по центру."""
        self.root.update_idletasks()
        w, h = self.root.winfo_reqwidth(), self.root.winfo_reqheight()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x, y = (sw - w) // 2, (sh - h) // 3
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(w, h)

    # --- Поле задачи (плейсхолдер) --------------------------------------------
    def _task_focus_in(self, _):
        if self._task_is_placeholder:
            self.task_entry.delete(0, "end")
            self.task_entry.config(fg=MUTED)
            self._task_is_placeholder = False

    def _task_focus_out(self, _):
        if not self.task_entry.get().strip():
            self.task_entry.delete(0, "end")
            self.task_entry.insert(0, PLACEHOLDER)
            self.task_entry.config(fg=MUTED_SOFT)
            self._task_is_placeholder = True

    def _task_done(self, _):
        # Enter/Esc: снять фокус с поля — каретка пропадает,
        # пробел снова управляет таймером (а не печатается).
        self.root.focus_set()
        return "break"

    def _task_text(self):
        if self._task_is_placeholder:
            return ""
        return self.task_entry.get().strip()

    # --- Логика таймера -------------------------------------------------------
    def _space(self, _):
        if self.root.focus_get() is self.task_entry:
            return       # поле задачи в фокусе — печатаем пробел, таймер не трогаем
        self.toggle()
        return "break"   # пробел не «нажимает» сфокусированную кнопку

    def toggle(self):
        """Старт / Продолжить  <->  Пауза."""
        if self.running:
            self._end_segment()           # пауза: закрываем и логируем сегмент
            self.running = False
            self._set_clock_color(CLOCK_DIM)
            self.start_btn.config(text="Продолжить")
        else:
            if not self.session_active:
                self.session_active = True
                self.accumulated = 0.0
                self.session_start_wall = datetime.now()
            self.seg_start_mono = time.monotonic()
            self.seg_start_wall = datetime.now()
            self.running = True
            self._set_clock_color(CLOCK_ON)
            self.start_btn.config(text="Пауза")

    def _end_segment(self):
        """Закрыть текущий рабочий интервал и записать его в лог."""
        dur = time.monotonic() - self.seg_start_mono
        self.accumulated += dur
        if dur >= 1:  # не засоряем лог случайными нажатиями < 1 c
            self._log_segment(self.seg_start_wall, datetime.now(), dur)

    def _log_segment(self, start_dt, end_dt, dur):
        new_file = not LOG_FILE.exists()
        with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(FIELDS)
            w.writerow([
                self.session_start_wall.strftime("%Y-%m-%d %H:%M:%S"),
                start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                int(dur),
                hms(dur),
                self._task_text() or "—",
            ])

    @staticmethod
    def _ensure_log_format():
        """Привести старый лог (без session_start) к новому формату.

        Старые строки получают session_start = собственному start (каждая
        становится отдельной сессией). Идемпотентно, без потери данных.
        """
        if not LOG_FILE.exists():
            return
        with open(LOG_FILE, newline="", encoding="utf-8") as f:
            rows = list(csv.reader(f))
        if not rows or rows[0] == FIELDS:
            return
        migrated = [FIELDS] + [[r[0]] + r for r in rows[1:] if r]
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerows(migrated)

    # --- Обновление экрана ----------------------------------------------------
    def _tick(self):
        if self.running:
            live = self.accumulated + (time.monotonic() - self.seg_start_mono)
        else:
            live = self.accumulated
        self._set_clock_text(hms(live))
        self.root.after(200, self._tick)

    def on_close(self):
        if self.running:        # стоп при закрытии: дописываем текущий сегмент
            self._end_segment()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Stopwatch(root)
    root.mainloop()
