#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.ui — интерфейс CyberDogs в стиле Flipper Zero:
баннер, меню, очистка экрана, паузы.
"""

import os
import sys
import time
import shutil
import platform


# ─────────── Цвета (ANSI) ───────────

class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    DIM     = "\033[2m"
    ITALIC  = "\033[3m"
    UNDER   = "\033[4m"
    BLINK   = "\033[5m"
    RED     = "\033[91m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    BLUE    = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN    = "\033[96m"
    WHITE   = "\033[97m"
    GRAY    = "\033[90m"
    # фоны
    BG_DARK = "\033[48;5;236m"

    @staticmethod
    def disable_if_not_tty():
        if not sys.stdout.isatty():
            for attr in ("RESET", "BOLD", "DIM", "ITALIC", "UNDER", "BLINK",
                         "RED", "GREEN", "YELLOW", "BLUE", "MAGENTA",
                         "CYAN", "WHITE", "GRAY", "BG_DARK"):
                setattr(C, attr, "")


C.disable_if_not_tty()


ACCENT = C.MAGENTA          # фирменный цвет акцентов CyberDogs

# Версия приложения: ставится cyberdogs.py при импорте (единый источник — там).
APP_VERSION = "dev"


def set_version(v):
    """cyberdogs.py вызывает ui.set_version(VERSION) — версия не дублируется."""
    global APP_VERSION
    APP_VERSION = v


BANNER = r"""
{c}   ____      _                      ____
{c}  / ___|   _| |__   ___ _ __ ___     |  _ \  ___   __ _   ___
{c} | |  | | | | '_ \ / _ \ '__/ __|____| | | |/ _ \ / _` | / __|
{c} | |__| |_| | |_) |  __/ |  \__ \_____| |_| | (_) | (_| | \__ \
{c}  \____\__,_|_.__/ \___|_|  |___/     |____/ \___/ \__, | |___/
{c}                                                   |___/
{m}       ▄▄· ▄▄·  ·▄▄▄▄  ▄▄▄  ▄▄▄▄· ▄▄▄  ·▄▄▄▄· ▄▄▄·  ▐▄▄·
{m}      ·██ ▐█▌  ██· ██ ▀▄ █·███  ▀▄ █·██ ▐█▌· ▐█▌▪  ██·
{m}      ██▌ ▐█▌  ██ ▀█   ▀▄▀  ▀▀ ██ ▀▄▀  ▐█▀▀▄ ██·▄▄ ▀▀█·
{m}      ▐▌ ▐█▌  ▐█▪██  ▐█▌.▐█▌.▐█▌.▐█▌.██ ▐█▌.▐█████.▐█▌
{m}      ▀  ▀▀▀   ▀▀▀▀  ▀▀▀ ▀▀▀ ▀▀▀ ▀▀▀ ▀▀▀▀▀·▀▀▀▀ .▀▀▀
{r}            Termux Hacking Tool  ·  v{v}{s}
""".strip("\n")


def termux_version():
    """Версия Termux (для статус-бара), если доступна."""
    try:
        return os.environ.get("TERMUX_VERSION", "")
    except Exception:
        return ""


def _visible_len(s):
    """Длина строки без ANSI-кодов."""
    import re
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


def box(title="", width=52, color=None):
    """Красивая рамка-бокс с заголовком (улучшенный визуал)."""
    color = color or ACCENT
    top = f"╭─{' ' + title + ' ' if title else ''}".ljust(0)
    line_in = color + "─" * (width - 2) + C.RESET
    print(f"{color}╭{'─' * (width - 2)}╮{C.RESET}")
    if title:
        pad = width - 4 - _visible_len(title)
        left = pad // 2
        print(f"{color}│{C.RESET}" + " " * left +
              f"{C.BOLD}{C.WHITE}{title}{C.RESET}" +
              " " * (pad - left) + f"{color}│{C.RESET}")
        print(f"{color}├{'─' * (width - 2)}┤{C.RESET}")
    return width


def status_bar():
    """Строка статуса под баннером: устройство · время · Termux."""
    host = platform.system() or "?"
    py = platform.python_version()
    now = time.strftime("%H:%M:%S")
    tmx = termux_version()
    parts = [f"OS: {host}", f"Py: {py}"]
    if tmx:
        parts.append(f"Termux: {tmx}")
    parts.append(f" {now}")
    txt = f"  {' · '.join(parts)}  "
    print(f"{C.BG_DARK}{C.GRAY}{txt}{C.RESET}")


def clear():
    """Очистка терминала."""
    os.system("clear" if os.name != "nt" else "cls")


def header(title=""):
    """Печать баннера или заголовка раздела."""
    if title:
        line = "═" * 50
        print(f"{ACCENT}{line}{C.RESET}")
        print(f"{C.BOLD}{C.GREEN}  > {title}{C.RESET}")
        print(f"{ACCENT}{line}{C.RESET}")
    else:
        print(BANNER.format(c=C.CYAN, m=ACCENT, r=C.YELLOW,
                            v=APP_VERSION, s=C.RESET))
        status_bar()


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

        # Список пунктов — с иконками-боксами
        for name, cb in items:
            color = C.DIM if cb is None else C.YELLOW
            print(f"  {color}{name}{C.RESET}")

        print(f"{C.DIM}  ─{'─' * 40}")
        print(f"{C.DIM}  » Подсказка: ввод 01 — быстрый возврат в главное меню{C.RESET}")
        print()
        try:
            choice = input(f"{C.GREEN}  cyberdogs/{title.split()[0].lower()}> {C.RESET}").strip()
        except EOFError:
            break

        # Пустой ввод — ничего не делаем
        if not choice:
            continue

        # Ввод "01" — быстрый возврат в главное меню
        # (в самом главном меню не перехватываем, иначе нечем было бы выходить)
        if choice == "01" and not banner:
            return

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
            print(f"{C.RED}  [x] Неверный пункт меню.{C.RESET}")
            pause()


# ─────────── новые утилиты визуала / полезные функции ───────────

def spinner(text="Работаю…", delay=0.08):
    """Анимированный спиннер в стиле Flipper Zero (▰▱). Возвращает класс."""
    frames = ["▰▱▱▱", "▰▰▱▱", "▰▰▰▱", "▰▰▰▰", "▱▰▰▰", "▱▱▰▰", "▱▱▱▰"]

    class _Spin:
        def __enter__(self):
            self._stop = False
            import threading

            def _loop():
                i = 0
                while not self._stop:
                    sys.stdout.write(
                        f"\r{ACCENT}  {frames[i % len(frames)]}{C.RESET} {text}   ")
                    sys.stdout.flush()
                    time.sleep(delay)
                    i += 1
                sys.stdout.write("\r" + " " * (len(text) + 20) + "\r")
                sys.stdout.flush()

            self.t = threading.Thread(target=_loop, daemon=True)
            self.t.start()
            return self

        def __exit__(self, *exc):
            self._stop = True
            self.t.join(timeout=1)
            return False

    return _Spin()


def progress(i, total, label="", width=26):
    """Однострочный прогресс-бар: [██████░░░░] 42% · метка."""
    pct = int(i * 100 / total) if total else 0
    filled = int(width * i / total) if total else 0
    bar = "█" * filled + "░" * (width - filled)
    sys.stdout.write(f"\r  {ACCENT}[{bar}]{C.RESET} {pct:>3}% {label[:28]:<28}")
    sys.stdout.flush()
    if i >= total:
        print()


def key_hint():
    """Печатать подсказку про «01» в начале разделов."""
    print(f"{C.DIM}  01 — главное меню · 0 — назад/выход{C.RESET}")


def section(title, icon=">"):
    """Красивый подзаголовок внутри экрана."""
    print(f"\n{ACCENT}  {icon} {C.BOLD}{title}{C.RESET}")
    print(f"{C.DIM}  {'·' * 40}{C.RESET}")


def check_termux():
    """Предупреждение, если запускаемся не в Termux (не блокирует работу)."""
    prefix = os.environ.get("PREFIX", "")
    if "com.termux" not in prefix and platform.system() != "Android":
        print(f"{C.YELLOW}  [!] Запуск вне Termux — некоторые функции могут не работать.{C.RESET}")
