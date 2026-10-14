#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules/scan/wifi.py — Сканирование Wi-Fi вокруг (v0.3.0).

Живой список всех Wi-Fi сетей/роутеров, которые видит устройство:
  * скан повторяется циклически, новые сети добавляются в таблицу;
  * в строке — SSID, BSSID (MAC роутера), сигнал (dBm + шкала),
    защита, канал/частота, производитель роутера (по OUI MAC-адреса);
  * ОСТАНОВКА по нажатию ENTER в любой момент;
  * после остановки — итоги и автовозврат в главное меню через 5 секунд.

Источник данных — ТОЛЬКО Termux:API:
  * termux-wifi-scan        — запускает активный скан через Android;
  * termux-wifi-scaninfo    — возвращает результаты скана (JSON);
  * termux-wifi-connectioninfo — данные текущего подключения (запасной вывод).
pywifi / nmcli / iw не используются.
"""

import json
import subprocess
import threading
import time

try:
    from core.ui import C
except ImportError:
    from core.ui import C

from core.termuxapi import api_bin


# ─────────────── утилиты ───────────────

def run(cmd, timeout=25):
    """Выполнить команду, вернуть stdout или None.

    Бинарники ищутся через core.termuxapi (PATH + каталоги Termux),
    поэтому Termux:API определяется корректно даже при запуске
    CyberDogs вне обычной оболочки Termux.
    """
    exe = api_bin(cmd[0])
    if exe is None:
        return None
    try:
        return subprocess.check_output([exe] + list(cmd[1:]),
                                       stderr=subprocess.DEVNULL,
                                       text=True, timeout=timeout)
    except Exception:
        return None


def signal_bar(q):
    """Шкала уровня сигнала (dBm → ████)."""
    try:
        q = int(q)
    except Exception:
        return "?  "
    if q >= -50:
        return "████"
    if q >= -60:
        return "███ "
    if q >= -70:
        return "██  "
    if q >= -80:
        return "█   "
    return "▏   "


def sig_num(s):
    try:
        return int(s)
    except Exception:
        return -999


def freq_to_channel(f):
    """Частота (MHz) → номер канала."""
    try:
        f = int(float(f))
    except Exception:
        return str(f)
    if f == 2484:
        return "14"
    if 2412 <= f <= 2472:
        return str((f - 2407) // 5)
    if 5160 <= f <= 5885:
        return str((f - 5000) // 5)
    if 5955 <= f <= 7115:          # Wi-Fi 6E
        return str((f - 5950) // 5)
    return f"{f} MHz"


def vendor_from_mac(bssid):
    """Производитель роутера по первым 3 байтам MAC (OUI). Мини-база."""
    if not bssid:
        return "?"
    oui = bssid.upper().replace(":", "-")[:8]
    vendors = {
        "00-1D-7A": "Ubiquiti", "04-18-D6": "Ubiquiti", "24-A4-3C": "Ubiquiti",
        "F8-CF-15": "TP-Link",  "EC-08-6B": "TP-Link",  "64-66-B3": "TP-Link",
        "50-C7-BF": "TP-Link",  "14-CC-20": "TP-Link",  "B0-4E-26": "ASUS",
        "2C-F0-5D": "MicroTik", "48-8F-5A": "MicroTik", "CC-20-6E": "Apple",
        "3C-22-FB": "Apple",    "AC-A2-23": "Cisco",    "00-1C-10": "Cisco",
        "F0-79-59": "Razer",    "9C-8E-CD": "Huawei",   "00-E0-FC": "Huawei",
        "C4-71-54": "TP-Link",  "40-3F-3C": "Netgear",  "A0-40-25": "Netgear",
        "00-24-D3": "Intel",    "00-15-00": "Intel",    "DC-A6-33": "Raspberry",
        "B8-27-EB": "Raspberry","00-0C-43": "RouterBoard/MicroTik",
    }
    return vendors.get(oui, "?")


def sec_label(cap):
    """Привести capability-строку к короткому виду."""
    cap = (cap or "").upper()
    if not cap or cap in ("OPEN", "[ESS]"):
        return "OPEN"
    if "WPA3" in cap:
        return "WPA3"
    if "WPA2" in cap or "RSN" in cap:
        return "WPA2"
    if "WPA" in cap:
        return "WPA"
    if "WEP" in cap or "WEP" in cap:
        return "WEP"
    return cap[:10]


# ─────────────── источники данных ───────────────

def termux_available():
    """Termux:API доступен? (ищем бинарники через core.termuxapi —
    PATH + каталоги Termux, чтобы не было ложного «недоступен»)."""
    return api_bin("termux-wifi-scaninfo") is not None


def parse_termux(out):
    """Разобрать JSON-вывод `termux-wifi-scaninfo` → список сетей."""
    try:
        data = json.loads(out)
    except Exception:
        return []
    if isinstance(data, dict):      # иногда приходит один объект
        data = [data]
    if not isinstance(data, list):
        return []
    nets = []
    for n in data:
        if not isinstance(n, dict):
            continue
        bssid = n.get("bssid") or n.get("BSSID") or "?"
        level = n.get("level", n.get("RSSI", "?"))
        nets.append({
            "ssid":   n.get("ssid") or n.get("SSID") or "<скрытая>",
            "bssid":  bssid,
            "signal": level,
            "sec":    sec_label(n.get("capabilities",
                                      n.get("security_type", ""))),
            "ch":     freq_to_channel(n.get("frequency",
                                            n.get("center_freq0", "?"))),
        })
    return nets


def trigger_termux_scan(stop_event):
    """Запустить активный Wi-Fi-скан средствами Android через Termux:API."""
    exe = api_bin("termux-wifi-scan")
    if exe is None:
        return False
    try:
        subprocess.run([exe], stderr=subprocess.DEVNULL,
                       stdin=subprocess.DEVNULL, text=True, timeout=10)
    except Exception:
        return False
    stop_event.wait(3)          # даём адаптеру время завершить скан
    return not stop_event.is_set()


def one_shot_scan(stop_event):
    """Один проход скана через Termux:API → список сетей или None."""
    if stop_event.is_set():
        return None
    if not termux_available():
        return None             # Termux:API отсутствует — активного метода нет

    # сначала инициируем свежий скан через Android (если команда доступна)
    triggered = trigger_termux_scan(stop_event)
    if stop_event.is_set():
        return None

    out = run(["termux-wifi-scaninfo"], timeout=15)
    if out is None:
        return None
    nets = parse_termux(out)
    if nets:
        return nets
    # если триггер недоступен и кэша нет — активных методов больше нет
    # (pywifi / nmcli / iw сознательно убраны в пользу Termux:API)
    if not triggered:
        return None
    return []


# ─────────────── отрисовка таблицы ───────────────

HEADER = (f"  {'SSID':<20}{'BSSID':<18}{'СИГНАЛ':>7} {'ШКАЛА':<6}"
          f"{'ЗАЩИТА':<8}{'КАН':>4}  {'РОУТЕР':<12}")


def print_table(all_nets, updated=False):
    print(f"\r{C.CYAN}{C.BOLD}{HEADER}{C.RESET}")
    print(f"  {'─' * 82}")
    for bssid, n in sorted(all_nets.items(),
                           key=lambda kv: sig_num(kv[1]["signal"]), reverse=True):
        mark = f"{C.GREEN}●{C.RESET}" if updated and n.get("new_flag") else " "
        vend = n.get("vendor", "?")
        print(f" {mark} {n['ssid'][:19]:<20}{str(n['bssid'])[:17]:<18}"
              f"{str(n['signal']):>6}dB {signal_bar(n['signal']):<6}"
              f"{str(n['sec'])[:7]:<8}{str(n['ch']):>4}  {vend[:12]:<12}")


# ─────────────── рабочий поток и точка входа ───────────────

def _worker(stop_event, state):
    all_nets = state.setdefault("nets", {})
    passes = state.setdefault("passes", 0)

    # Первый проход — определяем метод
    first = one_shot_scan(stop_event)
    if first is None:
        state["no_active_method"] = True
        return all_nets

    for n in first:
        n["vendor"] = vendor_from_mac(n["bssid"])
        all_nets[n["bssid"]] = n
    passes += 1
    print_table(all_nets, updated=True)

    while not stop_event.is_set():
        # ждём до следующего прохода, но проснёмся сразу по ENTER
        if stop_event.wait(4):
            break
        nets = one_shot_scan(stop_event)
        if nets is None:
            break
        new_found = False
        for n in nets:
            if n["bssid"] not in all_nets:
                n["vendor"] = vendor_from_mac(n["bssid"])
                n["new_flag"] = True
                all_nets[n["bssid"]] = n
                new_found = True
            else:
                all_nets[n["bssid"]].update(
                    {"signal": n["signal"], "ssid": n["ssid"] or
                     all_nets[n["bssid"]]["ssid"]})
                all_nets[n["bssid"]]["new_flag"] = False
        passes += 1
        if new_found:
            print(f"\n{C.GREEN}  ＋ Найдены новые сети:{C.RESET}")
        print_table(all_nets, updated=True)
        print(f"{C.DIM}  Проходов скана: {passes} · всего сетей: {len(all_nets)}{C.RESET}")

    return all_nets


def _summary(state, result, stopped_by_user):
    nets = state.get("nets", {})
    if state.get("no_active_method"):
        print(f"{C.RED}  ✖ Termux:API недоступен — сканирование невозможно.{C.RESET}")
        print(f"{C.DIM}    Все данные о Wi-Fi сетях берутся только через Termux:API.{C.RESET}")
        print(f"{C.DIM}    Установка: pkg install termux-api +"
              f" приложение Termux:API из F-Droid.{C.RESET}\n")
        _show_current_connection()
        return
    if not nets:
        print(f"{C.DIM}  Сети не обнаружены.{C.RESET}")
        return
    print(f"\n{C.BOLD}  ИТОГ: найдено Wi-Fi сетей / роутеров — {len(nets)}{C.RESET}")
    print_table(nets)


def _show_current_connection():
    out = run(["termux-wifi-connectioninfo"])
    if out:
        try:
            info = json.loads(out)
            print(f"{C.CYAN}  Текущее Wi-Fi подключение:{C.RESET}")
            print(f"    SSID      : {info.get('ssid', '?')}")
            print(f"    BSSID     : {info.get('bssid', '?')} "
                  f"({vendor_from_mac(info.get('bssid', ''))})")
            print(f"    Уровень   : {info.get('level', '?')} dBm")
            print(f"    Частота   : {info.get('frequency', '?')} MHz "
                  f"(канал {freq_to_channel(info.get('frequency', 0))})")
            return
        except Exception:
            pass
    print(f"{C.DIM}    Информация о текущем подключении недоступна.{C.RESET}")


def scan_wifi_networks_interactive():
    """Точка входа пункта меню «Сканирование Wi-Fi вокруг» (v0.3.0)."""
    from core.stopwatch import run_with_stop
    run_with_stop(_worker, title="Сканирование Wi-Fi", summary_fn=_summary)


# Совместимость со старым вызовом
def scan_wifi_networks():
    ev = threading.Event()
    _worker(ev, {})
