#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/scan/networks.py — Сканирование сетей вокруг.

Определяет локальные сети устройства (Termux) и делает быстрый
ARP/ping-обход подсети, чтобы найти активные хосты.

v0.3.0: сканирование можно ОСТАНОВИТЬ по ENTER в любой момент
(core.stopwatch), после остановки — итоги и автовозврат в меню через 5 сек.
"""

import socket
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from core.ui import C
except ImportError:
    from core.ui import C


def get_local_interfaces():
    """Возвращает IP-адреса активных интерфейсов устройства."""
    ips = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass

    # Дополнительно — через `ip addr` (Termux: iproute2)
    try:
        out = subprocess.check_output(["ip", "-o", "-4", "addr", "show"],
                                      stderr=subprocess.DEVNULL, text=True)
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and "/" in parts[3]:
                ip = parts[3].split("/")[0]
                if not ip.startswith("127."):
                    ips.add(ip)
    except Exception:
        pass

    return sorted(ips)


def subnet_of(ip):
    """Возвращает префикс /24 для IPv4-адреса."""
    return ".".join(ip.split(".")[:3]) + ".0/24"


def ping_host(ip):
    """Быстрый ping; возвращает True, если хост отвечает."""
    try:
        r = subprocess.run(
            ["ping", "-c", "1", "-W", "1", ip],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=3,
        )
        return r.returncode == 0
    except Exception:
        return False


def resolve_name(ip):
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return ""


def _worker(stop_event, state):
    """Рабочий поток сканирования (периодически проверяет stop_event)."""
    found = state.setdefault("found", [])
    scanned = state.setdefault("scanned", 0)

    ips = get_local_interfaces()
    if not ips:
        print(f"{C.RED}  ✖ Не удалось определить локальные IP-адреса.{C.RESET}")
        print(f"{C.DIM}    Проверьте Wi-Fi/мобильные данные и права Termux.{C.RESET}")
        return found

    print(f"{C.CYAN}  Локальные адреса:{C.RESET}")
    for ip in ips:
        print(f"    • {ip}  ({subnet_of(ip)})")

    lock = threading.Lock()

    for ip in ips:
        if stop_event.is_set():
            break
        base = ip.rsplit(".", 1)[0]
        targets = [f"{base}.{i}" for i in range(1, 255)
                   if i != int(ip.rsplit(".", 1)[1])]

        print(f"\n{C.YELLOW}  ⟳ Сканирую подсеть {base}.0/24 …{C.RESET}\n")

        with ThreadPoolExecutor(max_workers=40) as pool:
            futures = {pool.submit(ping_host, t): t for t in targets}
            for fut in as_completed(futures):
                if stop_event.is_set():
                    for f in futures:
                        f.cancel()
                    break
                tgt = futures[fut]
                with lock:
                    state["scanned"] += 1
                try:
                    alive = fut.result()
                except Exception:
                    alive = False
                if alive:
                    name = resolve_name(tgt)
                    print(f"{C.GREEN}    ✔ {tgt:<16} {name}{C.RESET}")
                    with lock:
                        found.append((tgt, name))

        if not stop_event.is_set():
            print(f"{C.DIM}    Просканировано адресов: {state['scanned']}{C.RESET}")

    return found


def _summary(state, result, stopped_by_user):
    found = state.get("found", [])
    scanned = state.get("scanned", 0)
    if not found:
        print(f"{C.DIM}  Активных хостов не найдено "
              f"(просканировано адресов: {scanned}; "
              f"возможно, сеть блокирует ICMP / нужен root).{C.RESET}")
    else:
        print(f"\n{C.BOLD}  ИТОГ:{C.RESET} найдено активных хостов — {len(found)} "
              f"(просканировано адресов: {scanned})")
        for tgt, name in found:
            print(f"    • {tgt:<16} {name}")


def scan_local_networks_interactive():
    """Точка входа пункта меню: сканирование с остановкой по ENTER."""
    from core.stopwatch import run_with_stop
    run_with_stop(_worker, title="Сканирование сетей", summary_fn=_summary)


# Совместимость со старым прямым вызовом
def scan_local_networks():
    return _worker(threading.Event(), {})
