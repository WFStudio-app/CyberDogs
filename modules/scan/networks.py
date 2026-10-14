#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/scan/networks.py — Сканирование сетей вокруг.

Определяет локальные сети устройства (Termux) и делает быстрый
ARP/ping-обход подсети, чтобы найти активные хосты.
Без внешних зависимостей: только стандартная библиотека + ping.
"""

import socket
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor

try:
    from core.ui import C
except ImportError:  # запуск модуля напрямую
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

    # Дополнительно — через `ip addr` (есть в Termux: package install net-tools / iproute2)
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


def scan_local_networks(max_hosts=254, workers=40):
    """Поиск активных хостов в локальных /24-подсетях устройства."""
    ips = get_local_interfaces()
    if not ips:
        print(f"{C.RED}  ✖ Не удалось определить локальные IP-адреса.{C.RESET}")
        print(f"{C.DIM}    Проверьте Wi-Fi/мобильные данные и права Termux.{C.RESET}")
        return []

    print(f"{C.CYAN}  Локальные адреса:{C.RESET}")
    for ip in ips:
        print(f"    • {ip}  ({subnet_of(ip)})")

    found = []
    lock = threading.Lock()

    for ip in ips:
        base = ip.rsplit(".", 1)[0]
        targets = [f"{base}.{i}" for i in range(1, max_hosts + 1) if i != int(ip.rsplit('.', 1)[1])]

        print(f"\n{C.YELLOW}  ⟳ Сканирую подсеть {base}.0/24 …{C.RESET}\n")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = pool.map(ping_host, targets)
            for tgt, alive in zip(targets, results):
                if alive:
                    name = ""
                    try:
                        name = socket.gethostbyaddr(tgt)[0]
                    except Exception:
                        pass
                    line = f"    ✔ {tgt:<16} {name}"
                    print(f"{C.GREEN}{line}{C.RESET}")
                    with lock:
                        found.append((tgt, name))

    if not found:
        print(f"{C.DIM}  Активных хостов не найдено "
              f"(возможно, сеть блокирует ICMP / нужен root).{C.RESET}")
    else:
        print(f"\n{C.BOLD}  Итого найдено хостов: {len(found)}{C.RESET}")

    return found
