#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules.settings — раздел «Настройки» CyberDogs/CyberOS.

Конфиг хранится в ~/.cyberos/config.json. Пункт 9 главного меню.
Без смайликов — только символы и ANSI-цвет.
"""

import os
import json
import time

from core.ui import header, clear, pause, menu_loop, C, ACCENT

CFG_DIR = os.path.join(os.path.expanduser("~"), ".cyberos")
CFG_PATH = os.path.join(CFG_DIR, "config.json")

DEFAULTS = {
    "accent_color": "magenta",   # фирменный цвет акцентов
    "clock_24h": True,           # формат времени (влияет на статус-бар/шелл)
    "show_status_bar": True,     # показывать строку статуса под баннером
    "crack_delay_ms": 100,       # задержка между паролями при подборе, мс
    "sound": False,              # звуковые сигналы (termux-toast / bell)
    "vibrate": False,            # вибрация (termux-vibrate)
    "theme": "dark",             # тема вывода (dark | mono)
}

ACCENT_MAP = {
    "magenta": "\033[95m",
    "cyan": "\033[96m",
    "green": "\033[92m",
    "yellow": "\033[93m",
    "red": "\033[91m",
    "blue": "\033[94m",
}


def load():
    try:
        with open(CFG_PATH, encoding="utf-8") as f:
            cfg = dict(DEFAULTS)
            cfg.update(json.load(f))
            return cfg
    except Exception:
        return dict(DEFAULTS)


def save(cfg):
    os.makedirs(CFG_DIR, exist_ok=True)
    with open(CFG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def apply():
    """Применить конфиг к UI (акцентный цвет, формат часов, статус-бар).

    Вызывать при старте и после изменения настроек.
    """
    cfg = load()
    import core.ui as ui
    col = ACCENT_MAP.get(cfg.get("accent_color", "magenta"))
    if col:
        ui.ACCENT = col
    ui.set_display_flags(clock_24h=cfg.get("clock_24h", True),
                         show_status_bar=cfg.get("show_status_bar", True))
    return cfg


def _kv(k, v, hint=""):
    print(f"  {C.CYAN}{k:<18}{C.RESET} = {C.BOLD}{C.WHITE}{v}{C.RESET}"
          + (f"  {C.DIM}{hint}{C.RESET}" if hint else ""))


def set_accent():
    clear()
    header("НАСТРОЙКИ · Акцентный цвет")
    cfg = load()
    names = list(ACCENT_MAP.keys())
    for i, n in enumerate(names, 1):
        sample = f"\033[9{'0' if False else ''}{names.index(n) + 5}m"
        print(f"  {ACCENT_MAP[n]}{i}. {n:<8}{C.RESET}"
              + ("   <- текущий" if cfg["accent_color"] == n else ""))
    try:
        ch = input(f"\n{C.GREEN}  выбор (1-{len(names)}) или ENTER — отмена: {C.RESET}").strip()
    except EOFError:
        return
    if ch.isdigit() and 1 <= int(ch) <= len(names):
        cfg["accent_color"] = names[int(ch) - 1]
        save(cfg)
        apply()
        print(f"  {C.GREEN}[+]{C.RESET} акцент: {cfg['accent_color']}")
        pause()


def toggle(key, label):
    cfg = load()
    cfg[key] = not cfg[key]
    save(cfg)
    state = "ВКЛ" if cfg[key] else "выкл"
    color = C.GREEN if cfg[key] else C.DIM
    print(f"  {C.YELLOW}[>]{C.RESET} {label}: {color}{state}{C.RESET}")
    pause()


def set_crack_speed():
    clear()
    header("НАСТРОЙКИ · Скорость подбора")
    cfg = load()
    _kv("задержка, мс", cfg["crack_delay_ms"],
        "100 = ~10 паролей/сек")
    try:
        v = input(f"{C.GREEN}  новое значение (мс), ENTER — отмена: {C.RESET}").strip()
    except EOFError:
        return
    if v.isdigit() and 10 <= int(v) <= 5000:
        cfg["crack_delay_ms"] = int(v)
        save(cfg)
        print(f"  {C.GREEN}[+]{C.RESET} сохранено: {v} мс")
    elif v:
        print(f"  {C.RED}[x]{C.RESET} диапазон 10..5000 мс")
    pause()


def show_info():
    clear()
    header("НАСТРОЙКИ · О системе")
    cfg = load()
    line = "─" * 46
    print(f"  {ACCENT}{line}{C.RESET}")
    _kv("система", "CyberOS / CyberDogs")
    _kv("конфиг", CFG_PATH)
    _kv("дата", time.strftime("%Y-%m-%d %H:%M:%S %Z").strip())
    _kv("домашний каталог", os.path.expanduser("~"))
    truck_dir = os.path.join(CFG_DIR, "truck")
    pkgs = len([f for f in os.listdir(truck_dir)]) if os.path.isdir(truck_dir) else 0
    _kv("пакеты trk", pkgs)
    print(f"  {C.DIM}  полный список: trk list (терминал){C.RESET}")
    print(f"  {ACCENT}{line}{C.RESET}")
    pause()


def reset_cfg():
    cfg = dict(DEFAULTS)
    save(cfg)
    apply()
    print(f"  {C.GREEN}[+]{C.RESET} настройки сброшены к значениям по умолчанию")
    pause()


def settings_menu():
    """Пункт 9 главного меню — Настройки."""
    items = [
        ("1. Акцентный цвет интерфейса",  set_accent),
        ("2. Дисплей: 24-часовой формат", lambda: toggle("clock_24h", "24-часовой формат")),
        ("3. Дисплей: строка статуса",    lambda: toggle("show_status_bar", "строка статуса")),
        ("4. Дисплей: тема dark/mono",    lambda: toggle("theme_mono", "монохромная тема")),
        ("5. Подбор: скорость перебора",  set_crack_speed),
        ("6. Звуковые сигналы",           lambda: toggle("sound", "звук")),
        ("7. Вибрация (Termux)",          lambda: toggle("vibrate", "вибрация")),
        ("8. О системе и конфиге",        show_info),
        ("9. Сброс настроек",             reset_cfg),
        ("01. ← Главное меню",            None),
        ("0.  ← Назад",                   None),
    ]
    menu_loop("НАСТРОЙКИ", items)
