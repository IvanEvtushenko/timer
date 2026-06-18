#!/usr/bin/env python3
"""Окно-референс шрифтов для цифр таймера.

Показывает один и тот же образец времени в выбранных шрифтах (тонкие начертания,
близкие к запрошенному весу ~250). Понравившийся вариант впиши в CLOCK_FONT
в stopwatch.py.

Запуск:  python3 font_preview.py
"""

import tkinter as tk
import tkinter.font as tkfont

BG = "#14161c"
CLOCK = "#f4f6fb"
MUTED = "#6b7385"
MISS = "#5a3b3b"

SAMPLE = "01:23:45"   # разные цифры — видно ширину знаков
SIZE = 150            # крупно (в 2 раза больше прежнего превью)

# (имя_для_рендера, базовое_семейство_для_проверки, подпись)
# Вес «250» в шрифтах не существует — берём ближайшее тонкое начертание.
FONTS = [
    ("Poppins ExtraLight",     "Poppins",          "1.  Poppins · ExtraLight (200 — ближайший к 250)"),
    ("Open Sans Light",        "Open Sans",        "2.  Open Sans · Light (300 — самый тонкий доступный)"),
    ("Zen Maru Gothic Light",  "Zen Maru Gothic",  "3.  Zen Maru Gothic · Light (300 — самый тонкий доступный)"),
]


def main():
    root = tk.Tk()
    root.title("Шрифты таймера — выбери номер")
    root.configure(bg=BG)

    available = set(tkfont.families())

    tk.Label(root, text="Образец времени · тонкое начертание (~250)",
             fg=MUTED, bg=BG, font=("DejaVu Sans", 13)).pack(pady=(20, 6))

    for render_fam, base, note in FONTS:
        row = tk.Frame(root, bg=BG)
        row.pack(fill="x", padx=50, pady=(14, 0))

        present = base in available
        tk.Label(row, text=SAMPLE, fg=CLOCK if present else MISS, bg=BG,
                 font=(render_fam, SIZE)).pack(anchor="center")
        label = note + ("" if present else "   (нет в системе)")
        tk.Label(row, text=label, fg=MUTED, bg=BG,
                 font=("DejaVu Sans", 12)).pack(anchor="center")
        if (render_fam, base, note) != FONTS[-1]:
            tk.Frame(root, bg="#232733", height=1).pack(fill="x", padx=40, pady=(14, 0))

    tk.Label(root, text="Понравился номер N → впиши его семейство в CLOCK_FONT в stopwatch.py",
             fg=MUTED, bg=BG, font=("DejaVu Sans", 11)).pack(pady=(22, 20))

    root.update_idletasks()
    w, h = root.winfo_reqwidth(), root.winfo_reqheight()
    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{max(0, (sh - h) // 2)}")

    root.mainloop()


if __name__ == "__main__":
    main()
