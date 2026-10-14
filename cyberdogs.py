#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CyberDogs — мультиинструментальный пентест-комбайн для Termux
в стиле Flipper Zero.

Главный запуск: ./cyberdogs.py  (или python3 cyberdogs.py)
"""

import sys
import os

# Добавляем корень проекта в sys.path, чтобы модули
# работали и при запуске из любой директории.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.ui import header, clear, pause, menu_loop, box, key_hint, C, ACCENT
import core.ui as ui
from modules.scan import networks, signals, wifi
from modules.attack import wifi_crack, hosts_crack
from modules import tools, usb


APP_NAME = "CyberDogs"
VERSION = "0.5.0"

# единый источник версии для баннера (core.ui)
ui.set_version(VERSION)


# ───────────────────────── Сканирование ─────────────────────────

def scan_networks():
    """Сканирование сетей вокруг (ARP / подсеть), остановка по ENTER."""
    clear()
    header("Сканирование сетей вокруг")
    networks.scan_local_networks_interactive()   # ⏹ ENTER — стоп, ↩ меню через 5 сек


def scan_signals():
    """Сканирование радиосигналов (Bluetooth / RF)."""
    clear()
    header("Сканирование сигналов")
    signals.scan_signals()
    pause()


def scan_wifi():
    """Сканирование Wi-Fi вокруг — живой список сетей, остановка по ENTER."""
    clear()
    header("Сканирование Wi-Fi вокруг")
    wifi.scan_wifi_networks_interactive()        # ⏹ ENTER — стоп, ↩ меню через 5 сек


def scanning_menu():
    """Внутреннее меню раздела «Сканирование»."""
    items = [
        ("1. Сканирование сетей вокруг", scan_networks),
        ("2. Сканирование сигналов",     scan_signals),
        ("3. Сканирование Wi-Fi вокруг", scan_wifi),
        ("01. ← Главное меню",           None),
        ("0.  ← Назад",                  None),
    ]
    menu_loop("СКАНИРОВАНИЕ", items)


# ───────────────────────── Подбор / Взлом ─────────────────────────

def crack_wifi():
    """Подбор пароля от Wi-Fi (шаг 0.5 сек, словари pn_*.txt)."""
    clear()
    wifi_crack.main()


def crack_host():
    """Подбор пароля от хоста (SSH)."""
    clear()
    hosts_crack.main(service="ssh")


def crack_devices():
    """Подбор пароля от других устройств (FTP/Telnet-сервисы роутеров, камер и т.п.)."""
    clear()
    hosts_crack.main(service="ftp")


def attack_menu():
    """Внутреннее меню раздела «Подбор / Взлом»."""
    items = [
        ("1. Подбор пароля от Wifi",         crack_wifi),
        ("2. Подбор пароля от Хоста",        crack_host),
        ("3. Подбор пароля от других устройств", crack_devices),
        ("01. ← Главное меню",               None),
        ("0.  ← Назад",                       None),
    ]
    menu_loop("ПОДБОР / ВЗЛОМ", items)


# ───────────────────────── Инструменты (10 функций) ─────────────────────────

def tools_menu():
    """Раздел «Инструменты» — 10 полезных сетевых/утилитарных функций."""
    items = list(tools.TOOLS) + [
        ("01. ← Главное меню", None),
        ("0.  ← Назад",        None),
    ]
    menu_loop("ИНСТРУМЕНТЫ", items)


# ───────────────────────── USB ─────────────────────────

def usb_menu():
    """Раздел «USB» — полное управление USB на устройстве (12 функций)."""
    items = list(usb.USB_TOOLS) + [
        ("01. ← Главное меню", None),
        ("0.  ← Назад",        None),
    ]
    menu_loop("USB", items)


# ───────────────────────── Игры (пока пусто) ─────────────────────────

def games_menu():
    """Раздел «Игры» — заготовка, содержимое появится позже."""
    clear()
    header("ИГРЫ")
    print(f"{ACCENT}  ╭{'─' * 48}╮{C.RESET}")
    print(f"  🎮  {C.BOLD}Раздел в разработке…{C.RESET}")
    print(f"      Скоро здесь появятся мини-игры для терминала:")
    print(f"      крестики-нолики · змейка · угадай число и другие.")
    print(f"{C.DIM}      Пока тут пусто — загляните позже!{C.RESET}")
    print(f"{ACCENT}  ╰{'─' * 48}╯{C.RESET}")
    key_hint()
    pause("Нажмите ENTER чтобы вернуться в главное меню…")


# ───────────────────────── Главное меню ─────────────────────────

def main_menu():
    items = [
        ("1. Сканирование",   scanning_menu),
        ("2. Подбор / Взлом", attack_menu),
        ("3. USB",            usb_menu),
        ("4. Инструменты",    tools_menu),
        ("5. Игры",           games_menu),
        ("0. Выход", None),
    ]
    menu_loop(f"{APP_NAME} v{VERSION}", items, banner=True)


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n  До встречи! 🐶")
        sys.exit(0)
