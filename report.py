#!/usr/bin/env python3
"""Отчёт по логу секундомера (time_log.csv).

Запуск:
    python3 report.py            # сводка за сегодня, неделю и по задачам
    python3 report.py --days 30  # разбивка по дням за последние 30 дней
"""

import argparse
import csv
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

LOG_FILE = Path(__file__).resolve().parent / "time_log.csv"


def human(seconds: int) -> str:
    h, m = seconds // 3600, (seconds % 3600) // 60
    if h:
        return f"{h} ч {m:02d} м"
    if m:
        return f"{m} м"
    return f"{seconds} с"


def load():
    rows = []
    if not LOG_FILE.exists():
        return rows
    with open(LOG_FILE, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                r["_date"] = datetime.strptime(r["start"], "%Y-%m-%d %H:%M:%S").date()
                r["_sec"] = int(r["duration_sec"])
                rows.append(r)
            except (ValueError, KeyError):
                continue
    return rows


def bar(seconds: int, scale: int) -> str:
    n = round(seconds / scale * 30) if scale else 0
    return "█" * n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=0,
                    help="показать разбивку по дням за N последних дней")
    args = ap.parse_args()

    rows = load()
    if not rows:
        print(f"Лог пуст или не найден: {LOG_FILE}")
        return

    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    today_sec = sum(r["_sec"] for r in rows if r["_date"] == today)
    week_sec = sum(r["_sec"] for r in rows if r["_date"] >= week_start)
    total_sec = sum(r["_sec"] for r in rows)

    print("=" * 44)
    print(f"  Сегодня:    {human(today_sec)}")
    print(f"  За неделю:  {human(week_sec)}")
    print(f"  Всего:      {human(total_sec)}  ({len(rows)} интервалов)")
    print("=" * 44)

    if args.days:
        per_day = defaultdict(int)
        for r in rows:
            if r["_date"] >= today - timedelta(days=args.days - 1):
                per_day[r["_date"]] += r["_sec"]
        if per_day:
            scale = max(per_day.values())
            print(f"\nПо дням (последние {args.days}):")
            for d in sorted(per_day):
                print(f"  {d:%a %d.%m}  {human(per_day[d]):>10}  {bar(per_day[d], scale)}")

    # Разбивка по задачам за текущую неделю
    per_task = defaultdict(int)
    for r in rows:
        if r["_date"] >= week_start:
            per_task[r.get("task", "—")] += r["_sec"]
    if per_task:
        scale = max(per_task.values())
        print("\nПо задачам (за неделю):")
        for task, sec in sorted(per_task.items(), key=lambda x: -x[1]):
            print(f"  {human(sec):>10}  {bar(sec, scale)} {task}")


if __name__ == "__main__":
    main()
