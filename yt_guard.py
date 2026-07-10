#!/usr/bin/env python3
"""Блокировщик youtube.com, пока за сегодня на таймере нет 7 часов.

Раз в запуск считает суммарное время за сегодня из time_log.csv и:
  - если меньше цели — добавляет в /etc/hosts блок youtube-доменов -> 0.0.0.0;
  - если цель достигнута — убирает блок.

Запускать от root периодически (см. yt-guard.service / yt-guard.timer).
Правит только свой размеченный блок в /etc/hosts, остальное не трогает.

Использование:
    sudo python3 yt_guard.py            # пересчитать и обновить блок
    sudo python3 yt_guard.py --unblock  # снять блок (для отключения фичи)
"""

import csv
import json
import os
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

# --- Настройки ----------------------------------------------------------------
LOG_FILE = Path(__file__).resolve().parent / "time_log.csv"
GOAL_SECONDS = 7 * 3600          # цель на день
HOSTS = Path("/etc/hosts")
DOMAINS = [
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be", "youtube-nocookie.com",
]
BEGIN = "# >>> yt_guard (managed — не редактировать вручную) >>>"
END = "# <<< yt_guard <<<"

# Chrome-политика: режет youtube в браузере ДО прокси (работает, даже когда
# Chrome ходит через SOCKS/Xray и резолвит домены на стороне прокси).
CHROME_POLICY_FILE = Path("/etc/opt/chrome/policies/managed/yt_guard.json")
URL_BLOCKLIST = ["youtube.com", "youtu.be"]   # хост и все его поддомены


def today_seconds() -> int:
    """Суммарная длительность интервалов за сегодня (по полю start)."""
    if not LOG_FILE.exists():
        return 0
    today, total = date.today(), 0
    with open(LOG_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                d = datetime.strptime(row["start"], "%Y-%m-%d %H:%M:%S").date()
                if d == today:
                    total += int(row["duration_sec"])
            except (ValueError, KeyError):
                continue
    return total


def strip_block(text: str) -> str:
    """Убрать управляемый блок yt_guard из содержимого hosts (если он есть)."""
    out, skip = [], False
    for ln in text.splitlines():
        if ln.strip() == BEGIN:
            skip = True
            continue
        if ln.strip() == END:
            skip = False
            continue
        if not skip:
            out.append(ln)
    return "\n".join(out).rstrip("\n") + "\n"


def build_block() -> str:
    return "\n".join([BEGIN] + [f"0.0.0.0 {d}" for d in DOMAINS] + [END]) + "\n"


def write_hosts(new_text: str) -> None:
    """Атомарная перезапись /etc/hosts."""
    fd, tmp = tempfile.mkstemp(dir=str(HOSTS.parent), prefix=".hosts.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, HOSTS)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def apply_hosts(need_block: bool) -> bool:
    """Барьер для приложений, ходящих напрямую (не через прокси). Вернёт True,
    если /etc/hosts изменился."""
    current = HOSTS.read_text(encoding="utf-8")
    base = strip_block(current)
    new = base + build_block() if need_block else base
    if new == current:
        return False
    write_hosts(new)
    os.system("resolvectl flush-caches >/dev/null 2>&1")
    return True


def apply_chrome_policy(need_block: bool) -> bool:
    """Барьер для Chrome (режет URL в браузере до прокси/Xray). Вернёт True,
    если файл политики изменился."""
    if need_block:
        CHROME_POLICY_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps({"URLBlocklist": URL_BLOCKLIST},
                          ensure_ascii=False, indent=2) + "\n"
        if CHROME_POLICY_FILE.exists() and CHROME_POLICY_FILE.read_text(encoding="utf-8") == data:
            return False
        fd, tmp = tempfile.mkstemp(dir=str(CHROME_POLICY_FILE.parent), prefix=".yt_guard.")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(data)
            os.chmod(tmp, 0o644)
            os.replace(tmp, CHROME_POLICY_FILE)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return True
    else:
        if CHROME_POLICY_FILE.exists():
            CHROME_POLICY_FILE.unlink()
            return True
        return False


def main() -> None:
    if os.geteuid() != 0:
        sys.exit("Нужны права root (правятся /etc/hosts и политика Chrome). Запусти через sudo.")

    unblock = "--unblock" in sys.argv
    secs = today_seconds()
    h, m = secs // 3600, secs % 3600 // 60
    need_block = (not unblock) and (secs < GOAL_SECONDS)

    changed = []
    if apply_hosts(need_block):
        changed.append("/etc/hosts")
    if apply_chrome_policy(need_block):
        changed.append("chrome-policy")

    state = "БЛОК включён" if need_block else ("разблок (--unblock)" if unblock
                                               else "разблок (цель достигнута)")
    tail = ("изменено: " + ", ".join(changed)) if changed else "без изменений"
    print(f"{state} · сегодня {h}:{m:02d} / 7:00 · {tail}")


if __name__ == "__main__":
    main()
