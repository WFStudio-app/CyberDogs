#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.ui — интерфейс CyberDogs в стиле Flipper Zero:
баннер, меню, очистка экрана, паузы.
"""

import os
import sys
import platform


# ─────────── Цвета (ANSI) ───────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"

    @staticmethod
    def disable_if_not_tty():
        if not sys.stdout.isatty():
            for attr in ("RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW",
                         "BLUE", "MAGENTA", "CYAN", "WHITE"):
                setattr(C, attr, "")


C.disable_if_not_tty()


BANNER = r"""
{c}   ____      _                      ____
{c}  / ___|   _| |__   ___ _ __ ___     |  _ \  ___   __ _   ___
{c} | |  | | | | '_ \ / _ \ '__/ __|____| | | |/ _ \ / _` | / __|
{c} | |__| |_| | |_) |  __/ |  \__ \_____| |_| | (_) | (_| | \__ \
{c}  \____\__,_|_.__/ \___|_|  |___/     |____/ \___/ \__, | |___/
{c}                                                   |___/
{r}          🐶  Termux Hacking Tool  ·  v{v}{s}
""".strip("\n")


def clear():
    """Очистка терминала."""
    os.system("clear" if os.name != "nt" else "cls")


def header(title=""):
    """Печать баннера или заголовка раздела."""
    if title:
        line = "─" * 46
        print(f"{C.CYAN}{line}{C.RESET}")
        print(f"{C.BOLD}{C.GREEN}  ▶ {title}{C.RESET}")
        print(f"{C.CYAN}{line}{C.RESET}")
    else:
        print(BANNER.format(c=C.CYAN, r=C.YELLOW, v="0.2.0", s=C.RESET))


def pause(text="Нажмите ENTER для продолжения…"):
    """Пауза до нажатия Enter."""
    try:
        input(f"\n{C.DIM}  {text}{C.RESET}")
    except EOFError:
        pass


def menu_loop(title, items, banner=False):
    """
    Универсальный цикл меню.

    items: список кортежей (название, callback).
           callback=None → выход из меню («Назад» / «Выход»).
    """
    while True:
        clear()
        if banner:
            header()
        else:
            header(title)

        # Список пунктов
        for name, cb in items:
            color = C.DIM if cb is None else C.YELLOW
            print(f"  {color}{name}{C.RESET}")

        print()
        try:
            choice = input(f"{C.GREEN}  cyberdogs/{title.split()[0].lower()}> {C.RESET}").strip()
        except EOFError:
            break

        # Пустой ввод — ничего не делаем
        if not choice:
            continue

        found = False
        for name, cb in items:
            # Сравниваем по номеру пункта (первый символ строки)
            num = name.split(".")[0].strip()
            if choice == num or choice.lower() == name.lower():
                found = True
                if cb is None:
                    return  # «Назад» / «Выход»
                cb()
                break

        if not found:
            print(f"{C.RED}  ✖ Неверный пункт меню.{C.RESET}")
            pause()


def check_termux():
    """Предупреждение, если запускаемся не в Termux (не блокирует работу)."""
    prefix = os.environ.get("PREFIX", "")
    if "com.termux" not in prefix and platform.system() != "Android":
        print(f"{C.YELLOW}  ⚠ Запуск вне Termux — некоторые функции могут не работать.{C.RESET}")
