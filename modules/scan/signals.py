#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/scan/signals.py — Сканирование сигналов.

Собирает информацию о радиосигналах вокруг:
  • Bluetooth-устройства (через termux-bt-status / hciconfig, если доступны);
  • статус мобильных/радиомодулей устройства.
Для Sub-GHz / RFID требуется внешнее железо (например, Flipper или CC1101) —
модуль оставлен как точка расширения.
"""

import shutil
import subprocess

try:
    from core.ui import C
except ImportError:
    from core.ui import C

from core.termuxapi import api_bin


def run(cmd):
    """Выполнить команду, вернуть вывод или None.

    Бинарники Termux:API ищутся через core.termuxapi (PATH + каталоги
    Termux) — чтобы не было ложного «Termux:API недоступен».
    """
    exe = api_bin(cmd[0]) or shutil.which(cmd[0])
    if exe is None:
        return None
    try:
        return subprocess.check_output([exe] + list(cmd[1:]),
                                       stderr=subprocess.DEVNULL,
                                       text=True, timeout=10)
    except Exception:
        return None


def scan_bluetooth():
    """Показывает состояние и известные BT-устройства Termux API."""
    print(f"{C.YELLOW}  ⟳ Сканирую Bluetooth-сигналы…{C.RESET}\n")

    status = run(["termux-bt-status"])
    if status:
        name = ""
        mac = ""
        devs = []
        for line in status.splitlines():
            if line.startswith("Name:"):
                name = line.split(":", 1)[1].strip()
            elif line.startswith("MAC Address:"):
                mac = line.split(":", 1)[1].strip()
            elif line.startswith("Device Name:") or line.startswith("Device MAC:"):
                devs.append(line.strip())
        print(f"{C.CYAN}  Адаптер:{C.RESET} {name or 'нет имени'}  [{mac or 'MAC скрыт'}]")
        if devs:
            print(f"{C.GREEN}  Обнаруженные устройства:{C.RESET}")
            for d in devs:
                print(f"    • {d}")
        else:
            print(f"{C.DIM}  Список устройств пуст — включите поиск "
                  f"(cmd bluetooth_devices) и разрешение на геолокацию.{C.RESET}")
        return True

    hci = run(["hciconfig", "-a"])
    if hci:
        print(hci)
        return True

    print(f"{C.RED}  ✖ Bluetooth-сканирование недоступно.{C.RESET}")
    print(f"{C.DIM}    Установите Termux:API: pkg install termux-api{C.RESET}")
    print(f"{C.DIM}    и приложение Termux:API, затем выдайте разрешения Android.{C.RESET}")
    return False


def scan_radio_state():
    """Общая информация о радиомодулях (для справки)."""
    print(f"\n{C.CYAN}  Доступные радиомодули телефона:{C.RESET}")
    notes = [
        ("Wi-Fi",     "доступен через модуль «Сканирование Wi-Fi»"),
        ("Bluetooth", "доступен выше (termux-api)"),
        ("Sub-GHz / RFID / NFC", "требуют внешнего железа (e.g. Flipper Zero, HackRF)"),
    ]
    for k, v in notes:
        print(f"    • {k:<22} — {v}")


def scan_signals():
    """Точка входа пункта меню «Сканирование сигналов»."""
    scan_bluetooth()
    scan_radio_state()
