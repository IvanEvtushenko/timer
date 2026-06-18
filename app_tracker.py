#!/usr/bin/env python3
"""ОПЦИОНАЛЬНО и ЭКСПЕРИМЕНТАЛЬНО: учёт экранного времени по приложениям.

Раз в несколько секунд опрашивает активное окно и копит время по приложениям.
Раз в минуту дописывает накопленное в app_usage.csv.

ВАЖНО про твою систему (GNOME + Wayland):
  На Wayland активное окно по соображениям безопасности обычным программам
  недоступно. Чтобы это работало, поставь GNOME-расширение «Window Calls»:
      https://extensions.gnome.org/extension/4724/window-calls/
  Оно отдаёт активное окно через D-Bus (gdbus), и этот скрипт его использует.

  На X11 (или для XWayland-окон) есть запасной путь через xdotool, если он
  установлен:  sudo apt install xdotool

Запуск:  python3 app_tracker.py     (останов — Ctrl+C)
"""

import csv
import json
import shutil
import subprocess
import time
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent / "app_usage.csv"
POLL_SEC = 3          # как часто опрашивать активное окно
FLUSH_SEC = 60        # как часто сбрасывать накопленное на диск


def active_via_gnome():
    """Активное окно через расширение Window Calls (GNOME/Wayland)."""
    try:
        out = subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.gnome.Shell",
             "--object-path", "/org/gnome/Shell/Extensions/Windows",
             "--method", "org.gnome.Shell.Extensions.Windows.List"],
            capture_output=True, text=True, timeout=4)
        if out.returncode != 0:
            return None
        # gdbus возвращает ('[...json...]',) — вытаскиваем JSON
        raw = out.stdout.strip()
        start, end = raw.find("'"), raw.rfind("'")
        data = json.loads(raw[start + 1:end])
        for w in data:
            if w.get("focus"):
                return w.get("wm_class") or w.get("class") or "unknown"
    except (subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return None
    return None


def active_via_xdotool():
    """Запасной путь для X11/XWayland."""
    if not shutil.which("xdotool"):
        return None
    try:
        wid = subprocess.run(["xdotool", "getactivewindow"],
                             capture_output=True, text=True, timeout=4).stdout.strip()
        if not wid:
            return None
        name = subprocess.run(
            ["xdotool", "getwindowclassname", wid],
            capture_output=True, text=True, timeout=4).stdout.strip()
        return name or "unknown"
    except subprocess.SubprocessError:
        return None


def get_active_app():
    return active_via_gnome() or active_via_xdotool()


def flush(usage):
    if not usage:
        return
    new_file = not LOG_FILE.exists()
    today = date.today().isoformat()
    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["date", "app", "seconds"])
        for app, sec in usage.items():
            w.writerow([today, app, int(sec)])
    usage.clear()


def main():
    print("Проверяю доступ к активному окну...")
    probe = get_active_app()
    if probe is None:
        print("✗ Активное окно недоступно.")
        print("  На GNOME/Wayland поставь расширение Window Calls (см. шапку файла)")
        print("  или установи xdotool для X11. Скрипт остановлен.")
        return
    print(f"✓ Работает. Активное приложение сейчас: {probe}")
    print(f"  Пишу в {LOG_FILE}. Останов — Ctrl+C.")

    usage = defaultdict(float)
    last_flush = time.monotonic()
    try:
        while True:
            app = get_active_app()
            if app:
                usage[app] += POLL_SEC
            if time.monotonic() - last_flush >= FLUSH_SEC:
                flush(usage)
                last_flush = time.monotonic()
            time.sleep(POLL_SEC)
    except KeyboardInterrupt:
        flush(usage)
        print("\nОстановлено, данные сохранены.")


if __name__ == "__main__":
    main()
