#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/scan/wifi.py — Сканирование Wi-Fi вокруг.

Порядок попыток (от лучшего к запасному):
  1. nmcli      — если доступен;
  2. termux-api — `termux-wifi-scaninfo` (нужен Termux:API + разрешения);
  3. iw dev … scan / iwlist … scan — при root;
  4. запасной вариант — информация о текущем подключении
     (`termux-wifi-connectioninfo` / `ip route` + DNS).
"""

import json
import shutil
import socket
import subprocess

try:
    from core.ui import C
except ImportError:
    from core.ui import C


def run(cmd):
    """Выполнить команду, вернуть stdout или None."""
    if not shutil.which(cmd[0]):
        return None
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                       text=True, timeout=25)
    except Exception:
        return None


def signal_bar(q):
    """Красивая шкала уровня сигнала (dBm → ▂▄▆█)."""
    try:
        q = int(q)
    except Exception:
        return "  ?"
    if q >= -50:
        return "████"
    if q >= -60:
        return "███ "
    if q >= -70:
        return "██  "
    if q >= -80:
        return "█   "
    return "▏   "


def scan_nmcli():
    out = run(["nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,SECURITY,CHANNEL",
               "dev", "wifi", "list", "--rescan", "yes"])
    if not out:
        return False
    nets = []
    for line in out.splitlines()[1:]:
        parts = line.split("\\:")
        if len(parts) >= 5 and parts[0]:
            nets.append({"ssid": parts[0], "bssid": parts[1],
                         "signal": parts[2], "sec": parts[3], "ch": parts[4]})
    _print_table(nets)
    return True


def scan_termux_api():
    out = run(["termux-wifi-scaninfo"])
    if not out:
        return False
    try:
        data = json.loads(out)
    except Exception:
        data = []
    if not isinstance(data, list) or not data:
        return False
    nets = []
    for n in data:
        nets.append({
            "ssid":   n.get("ssid") or "<скрытая>",
            "bssid":  n.get("bssid", "?"),
            "signal": n.get("level", "?"),
            "sec":    n.get("capabilities", "open"),
            "ch":     n.get("frequency", "?"),
        })
    _print_table(nets)
    return True


def scan_iw():
    # iw dev wlan0 scan требует root, но попробуем
    dev = run(["iw", "dev"])
    if not dev:
        return False
    iface = None
    lines = dev.splitlines()
    for i, l in enumerate(lines):
        if "Interface" in l and i + 1 < len(lines):
            iface = lines[i + 1].strip()
            break
    if not iface:
        return False
    run(["iw", "dev", iface, "scan", "flush"])
    run(["iw", "dev", iface, "scan"])
    return False  # разбор iw оставлен на доработку (нужен root)


def fallback_current_connection():
    """Если активное сканирование недоступно — показываем текущую сеть."""
    out = run(["termux-wifi-connectioninfo"])
    if out:
        try:
            info = json.loads(out)
            print(f"{C.CYAN}  Текущее Wi-Fi подключение:{C.RESET}")
            print(f"    SSID     : {info.get('ssid', '?')}")
            print(f"    BSSID    : {info.get('bssid', '?')}")
            print(f"    Уровень  : {info.get('level', '?')} dBm")
            print(f"    Частота  : {info.get('frequency', '?')} MHz")
            print(f"    Шифрование: {info.get('hidden_ssid', '')}")
            return True
        except Exception:
            pass

    # совсем запасной вариант — через маршрут по умолчанию
    gw = None
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                fields = line.strip().split()
                if fields[1] == "00000000":
                    h = fields[2]
                    gw = ".".join(str(int(h[i:i + 2], 16)) for i in (6, 4, 2, 0))
                    break
    except Exception:
        pass
    hostname = socket.gethostname()
    print(f"{C.CYAN}  Косвенная информация:{C.RESET}")
    print(f"    Хост: {hostname}")
    if gw:
        print(f"    Шлюз (роутер): {gw}")
    return bool(gw)


def _print_table(nets):
    if not nets:
        print(f"{C.DIM}  Сети не обнаружены.{C.RESET}")
        return
    print(f"  {C.BOLD}{'SSID':<24}{'BSSID':<20}{'СИГНАЛ':>8}  {'ЗАЩИТА':<12}{'КАНАЛ':>6}{C.RESET}")
    print(f"  {'─' * 74}")
    for n in sorted(nets, key=lambda x: _sig_num(x["signal"]), reverse=True):
        sig = n["signal"]
        bar = signal_bar(sig)
        print(f"  {n['ssid'][:23]:<24}{str(n['bssid'])[:19]:<20}"
              f"{str(sig):>6} {bar}  {str(n['sec'])[:11]:<12}{str(n['ch']):>6}")
    print(f"\n{C.BOLD}  Всего сетей: {len(nets)}{C.RESET}")


def _sig_num(s):
    try:
        return int(s)
    except Exception:
        return -999


def scan_wifi_networks():
    """Точка входа пункта меню «Сканирование Wi-Fi вокруг»."""
    print(f"{C.YELLOW}  ⟳ Сканирую эфир Wi-Fi…{C.RESET}\n")

    if scan_nmcli():
        return
    if scan_termux_api():
        return
    if scan_iw():
        return

    print(f"{C.RED}  ✖ Активное сканирование Wi-Fi из Termux без root недоступно.{C.RESET}")
    print(f"{C.DIM}    Android ограничивает Wi-Fi-скан для приложений.{C.RESET}")
    print(f"{C.DIM}    Варианты: 1) установить Termux:API и выдать права,"
          f" 2) root + iw/nmcli.{C.RESET}\n")
    fallback_current_connection()
