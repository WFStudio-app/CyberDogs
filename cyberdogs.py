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

from core.ui import header, clear, pause, menu_loop
from modules.scan import networks, signals, wifi


APP_NAME = "CyberDogs"
VERSION = "0.1.0"


# ───────────────────────── Сканирование ─────────────────────────

def scan_networks():
    """Сканирование сетей вокруг (ARP / подсеть)."""
    clear()
    header("Сканирование сетей вокруг")
    networks.scan_local_networks()
    pause()


def scan_signals():
    """Сканирование радиосигналов (Bluetooth / RF)."""
    clear()
    header("Сканирование сигналов")
    signals.scan_signals()
    pause()


def scan_wifi():
    """Сканирование Wi-Fi вокруг."""
    clear()
    header("Сканирование Wi-Fi вокруг")
    wifi.scan_wifi_networks()
    pause()


def scanning_menu():
    """Внутреннее меню раздела «Сканирование»."""
    items = [
        ("1. Сканирование сетей вокруг", scan_networks),
        ("2. Сканирование сигналов",     scan_signals),
        ("3. Сканирование Wi-Fi вокруг", scan_wifi),
        ("← Назад", None),
    ]
    menu_loop("СКАНИРОВАНИЕ", items)


# ───────────────────────── Главное меню ─────────────────────────

def main_menu():
    items = [
        ("1. Сканирование", scanning_menu),
        ("0. Выход", None),
    ]
    menu_loop(f"{APP_NAME} v{VERSION}", items, banner=True)


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print("\n\n  До встречи! 🐶")
        sys.exit(0)
