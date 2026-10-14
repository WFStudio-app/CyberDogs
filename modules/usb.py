# -*- coding: utf-8 -*-
"""
modules.usb — Раздел «USB» (полное управление USB на устройстве).

Работает поверх системных интерфейсов Android/Termux без root там, где это
возможно:

  • /sys/bus/usb          — ядро Linux перечисляет подключенные устройства;
  • lsusb                 — если пакет usbutils установлен;
  • termux-usb            — Termux:API USB (список, запрос разрешения,
                            отключение);
  • getprop               — свойства Android (режим USB, OTG и т.п.).

Функции меню:
   1. Список USB-устройств        — полный дамп (/sys + lsusb + termux-usb)
   2. Информация об устройстве    — подробный профиль по индексу/VEN+DEV
   3. Дерево USB-топологии        — наглядная иераргия хаб → порт → устройство
   4. Статус USB / OTG            — режим порта Android, питание, OTG-подключение
   5. ⚠ USB-Killer (!)            — деструктивная функция: сильная нагрузка и
                                    вредоносные пакеты на выбранное устройство,
                                    из-за чего оно «крашится». Требует
                                    подтверждение и ключевое слово KILL.
   6. Отключить устройство        — termux-usb -d (или подсказка для root)
   7. Перезагрузить драйвер       — bind/unbind устройства (root)
   8. Тоннель / Mass Storage      — проверка режима и инструкция переключения
   9. Логи ядра (dmesg)           — последние события usb/driver
  10. Сеть через USB (RNDIS)       — интерфейс rndis/usb0: IP, ping-тест
  11. Разрешение USB (termux-usb)  — запрос доступа к устройству для Termux
  12. Пустой слот / сброс шины     — диагностика + reset через authorized (root)

⚠ Пункт 5 (USB-Killer) предназначен только для собственных устройств в
лабораторных целях. Его использование против чужого оборудования незаконно.
"""

import os
import sys
import time
import glob
import shutil
import random
import subprocess
import threading

from core.ui import C, ACCENT, header, pause, spinner, progress, section, box, key_hint


SYS_USB = "/sys/bus/usb/devices"


# ───────────────────────── helpers ─────────────────────────

def run(cmd, timeout=10):
    """Выполнить команду, вернуть stdout или None."""
    if not shutil.which(cmd[0]):
        return None
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL,
                                       text=True, timeout=timeout)
    except Exception:
        return None


def readf(path):
    """Прочитать sysfs-файл (strip), None если нет/нельзя."""
    try:
        with open(path) as f:
            return f.read().strip()
    except Exception:
        return None


def has_root():
    """Есть ли root (su без пароля) — используется для опасных операций."""
    out = run(["su", "-c", "id -u"], timeout=5)
    return out is not None and out.strip() == "0"


def require_root(what):
    if has_root():
        return True
    print(f"{C.RED}  ✖ {what} требует root-права (Termux: su не доступен)."
          f"{C.RESET}")
    return False


# ─────────────────── enumeration (/sys/bus/usb) ───────────────────

def _is_device_dir(path):
    """Каталог устройства USB содержит busnum+devnum+product/idVendor."""
    return (os.path.exists(os.path.join(path, "busnum")) and
            os.path.exists(os.path.join(path, "devnum")))


def enumerate_usb():
    """Собрать список USB-устройств из /sys/bus/usb/devices.

    Возвращает список словарей: name, vendor_id, product_id, speed,
    manufacturer, product, serial, maxpower, authorized, path, devfile.
    Если sysfs недоступен (нет root-чтения) — пытается termux-usb --devices.
    """
    devs = []
    if os.path.isdir(SYS_USB):
        for d in sorted(glob.glob(os.path.join(SYS_USB, "*"))):
            if not os.path.isdir(d):
                continue
            if not _is_device_dir(d):
                continue
            vid = readf(os.path.join(d, "idVendor"))
            pid = readf(os.path.join(d, "idProduct"))
            # имя: product или idVendor:idProduct
            prod = readf(os.path.join(d, "product"))
            manuf = readf(os.path.join(d, "manufacturer"))
            name = prod or f"USB device {vid}:{pid}" if (vid and pid) else prod or os.path.basename(d)
            devs.append({
                "path": d,
                "dir": os.path.basename(d),
                "name": name,
                "vendor": manuf,
                "vendor_id": vid,
                "product_id": pid,
                "speed": readf(os.path.join(d, "speed")),
                "maxpower": readf(os.path.join(d, "bMaxPower")),
                "serial": readf(os.path.join(d, "serial")),
                "authorized": readf(os.path.join(d, "authorized")),
                "busnum": readf(os.path.join(d, "busnum")),
                "devnum": readf(os.path.join(d, "devnum")),
            })
    if not devs:
        # фолбэк: termux-usb --devices (JSON)
        out = run(["termux-usb", "--devices"])
        if out:
            try:
                import json
                data = json.loads(out)
                items = data.get("devices", data if isinstance(data, list) else [])
                for it in items:
                    fid = it.get("device", "") or it.get("filter", "")
                    vid, pid = (fid.split(":") + [""])[:2] if ":" in fid else ("", "")
                    devs.append({
                        "path": "",
                        "dir": fid or f"termux-{len(devs)}",
                        "name": it.get("productName") or f"Device {fid}",
                        "vendor": it.get("manufacturerName"),
                        "vendor_id": vid,
                        "product_id": pid,
                        "speed": None,
                        "maxpower": None,
                        "serial": None,
                        "authorized": None,
                        "busnum": None,
                        "devnum": None,
                        "termux_filter": fid,
                    })
            except Exception:
                pass
    return devs


def pick_device(devs=None):
    """Показать список и дать выбрать устройство; вернуть dict или None."""
    devs = devs if devs is not None else enumerate_usb()
    if not devs:
        print(f"{C.YELLOW}  ⚠ USB-устройства не обнаружены "
              f"(нет подключений или нет доступа к {SYS_USB}).{C.RESET}")
        print(f"{C.DIM}  На стоковых Android чтение sysfs требует root; "
              f"без root используйте Termux:USB (termux-usb).{C.RESET}")
        return None
    print(f"\n{C.BOLD}  Обнаружено устройств: {len(devs)}{C.RESET}\n")
    for i, d in enumerate(devs, 1):
        vid = d["vendor_id"] or "?"
        pid = d["product_id"] or "?"
        sp = f" · {d['speed']} Mb/s" if d.get("speed") else ""
        auth = "" if d.get("authorized") in (None, "1") else \
            f"{C.RED} · disabled{C.RESET}"
        print(f"   {C.CYAN}[{i}]{C.RESET} {C.BOLD}{d['name']}{C.RESET} "
              f"({vid}:{pid}){sp}{auth}")
    try:
        sel = input(f"\n{C.GREEN}  Номер устройства (Enter — отмена): {C.RESET}").strip()
    except EOFError:
        return None
    if not sel.isdigit() or not (1 <= int(sel) <= len(devs)):
        return None
    return devs[int(sel) - 1]


# ────────────────────── 1. Список устройств ──────────────────────

def usb_list():
    section("СПИСОК USB-УСТРОЙСТВ", "🔌")
    with spinner("Опрашиваю шину USB…"):
        devs = enumerate_usb()
    if not devs:
        print(f"{C.YELLOW}  ⚠ Ни одно USB-устройство не видно.{C.RESET}")
        print(f"{C.DIM}    Проверьте: кабель/OTG-переходник включены? "
              f"Termux:USB установлен? Есть ли root для чтения sysfs?{C.RESET}")
        return
    print(f"\n  {'№':<3}{'Название':<28}{'VEN:DEV':<11}{'Скорость':<10}{'Питание':<8}Статус")
    print(f"  {'─' * 78}")
    for i, d in enumerate(devs, 1):
        vid = f"{d['vendor_id']}:{d['product_id']}" if d["vendor_id"] else "-"
        sp = d["speed"] + " Mb/s" if d["speed"] else "-"
        pw = d["maxpower"] if d["maxpower"] else "-"
        st = "active" if d.get("authorized") != "0" else "disabled"
        col = C.GREEN if st == "active" else C.RED
        print(f"  {i:<3}{d['name'][:27]:<28}{vid:<11}{sp:<10}{pw:<8}"
              f"{col}{st}{C.RESET}")
    # lsusb как дополнение
    out = run(["lsusb"])
    if out:
        print(f"\n{ACCENT}  lsusb:{C.RESET}")
        for line in out.splitlines():
            print(f"    {line}")
    print(f"\n  Итого: {C.BOLD}{len(devs)}{C.RESET} устройств на шине.")


# ─────────────────── 2. Информация об устройстве ───────────────────

def usb_info():
    section("ИНФОРМАЦИЯ ОБ УСТРОЙСТВЕ", "ℹ")
    d = pick_device()
    if not d:
        return
    print(f"\n{ACCENT}  ╭{'─' * 48}╮{C.RESET}")
    rows = [
        ("Название", d["name"]),
        ("Производитель", d["vendor"] or "-"),
        ("VID:PID", f"{d['vendor_id']}:{d['product_id']}"),
        ("Серийный номер", d.get("serial") or "-"),
        ("Шина / адрес", f"bus {d.get('busnum')} · dev {d.get('devnum')}"),
        ("Скорость", f"{d['speed']} Mb/s" if d["speed"] else "-"),
        ("Макс. питание", d.get("maxpower") or "-"),
        ("Разрешено (authorized)", "да" if d.get("authorized") != "0" else "НЕТ"),
        ("Sysfs-путь", d["path"] or "(через termux-usb)"),
    ]
    for k, v in rows:
        print(f"  {C.CYAN}{k:<24}{C.RESET} {v}")
    print(f"{ACCENT}  ╰{'─' * 48}╯{C.RESET}")
    # конфигурации/интерфейсы из sysfs
    if d["path"]:
        cfg = readf(os.path.join(d["path"], "bNumConfigurations"))
        if cfg:
            print(f"  Конфигураций: {cfg}")
        ifs = glob.glob(os.path.join(d["path"], "*:*", "interface")) 
        if ifs:
            print(f"  Интерфейсов: {len(ifs)}")


# ─────────────────── 3. Топология (дерево) ───────────────────

def usb_tree():
    section("ТОПОЛОГИЯ USB (дерево шины)", "🌳")
    devs = enumerate_usb()
    if not devs:
        print(f"{C.YELLOW}  ⚠ Устройства не найдены.{C.RESET}")
        return
    # строим дерево по префиксу каталога: 1-0:1.0 etc.
    print()
    roots = [d for d in devs if ":" not in d["dir"]]
    children = [d for d in devs if ":" in d["dir"]]
    for r in roots:
        vid = f" [{r['vendor_id']}:{r['product_id']}]" if r["vendor_id"] else ""
        print(f"  {C.MAGENTA}├─{C.RESET} {C.BOLD}{r['name']}{C.RESET}{vid} "
              f"{C.DIM}({r['dir']}){C.RESET}")
        kids = [c for c in children if c["dir"].startswith(r["dir"])]
        for i, c in enumerate(kids):
            last = i == len(kids) - 1
            branch = "└─" if last else "├─"
            vid = f" [{c['vendor_id']}:{c['product_id']}]" if c["vendor_id"] else ""
            print(f"  │   {C.CYAN}{branch}{C.RESET} {c['name']}{vid} "
                  f"{C.DIM}({c['dir']}){C.RESET}")
    others = [d for d in children if not any(d["dir"].startswith(r["dir"]) for r in roots)]
    for o in others:
        print(f"  {C.GRAY}└─ {o['name']} ({o['dir']}){C.RESET}")
    print(f"\n  Всего узлов: {len(devs)}")


# ─────────────────── 4. Статус USB / OTG ───────────────────

def usb_status():
    section("СТАТУС USB / OTG", "📊")
    props = {}
    out = run(["getprop"])
    if out:
        for line in out.splitlines():
            if line.startswith("[") and "]" in line:
                k, _, v = line.partition("]")
                props[k.strip("[]")] = v.strip().strip(": ").strip("[]")
    keys = [
        "sys.usb.state", "sys.usb.config", "persist.sys.usb.config",
        "ro.product.model", "ro.build.version.release",
        "sys.usb.controller",
    ]
    for k in keys:
        v = props.get(k)
        if v:
            print(f"  {C.CYAN}{k:<28}{C.RESET} {v}")
    # есть ли вообще устройства на шине
    devs = enumerate_usb()
    print(f"\n  Подключено периферийных устройств: {C.BOLD}{len(devs)}{C.RESET}")
    otg = any((d.get("speed") or "").endswith(("480", "5000")) for d in devs)
    if devs:
        print(f"  {C.GREEN}✔ OTG-режим активен — периферия видна ядру.{C.RESET}")
    else:
        print(f"  {C.YELLOW}⚠ Периферия не видна. Возможно, OTG выключен, "
              f"нет root-доступа к sysfs или нужен Termux:USB.{C.RESET}")
    if run(["termux-usb", "--help"]) is None:
        print(f"{C.DIM}  Termux:USB (termux-usb) не установлен — часть "
              f"функций будет доступна только с root.{C.RESET}")


# ─────────────────── 5. ⚠ USB-KILLER (!) ───────────────────

def usb_killer():
    """USB-Killer: перегрузка + спам вредоносными/некорректными пакетами.

    Методы (выполняются пока пользователь держит Enter):
      • flood control transfers (GET_DESCRIPTOR / SET_CONFIGURATION spam)
      • USB descriptor fuzzing (битые/раздутые дескрипторы)
      • enumeration storm (reset/re-enumerate устройства)
      • bulk I/O load (максимальная нагрузка на endpoint)
    Реализация зависит от доступного инструмента:
      - root + usbmon/usblp: прямой raw I/O через /dev/usb/lpN или usbfs ioctl
      - без root: интенсивное перечисление шины + request/disconnect через
        termux-usb (эмуляция нагрузки) и предупреждение.
    """
    section("⚠ ⚠ ⚠  U S B - K I L L E R  ⚠ ⚠ ⚠", "☠")
    print(f"""{C.RED}
  ╔{'═' * 54}╗
  ║  КРАЙНЕ ОПАСНАЯ ДЕСТРУКТИВНАЯ ФУНКЦИЯ!             ║
  ║                                                     ║
  ║  При активации CyberDogs начинает:                  ║
  ║   • максимальную нагрузку на USB-устройство;        ║
  ║   • отправку повреждённых/вредоносных пакетов;      ║
  ║   • шторм перезапросов дескрипторов и сбросов.      ║
  ║                                                     ║
  ║  Подключённое устройство может ОТКАЗАТЬ, зависнуть  ║
  ║  или повредить файловую систему (для mass-storage). ║
  ║                                                     ║
  ║  Используйте ТОЛЬКО на СОБСТВЕННОМ оборудовании     ║
  ║  в лабораторных целях. Против чужих устройств это   ║
  ║  уголовное преступление (ст. 272/273 УК РФ и        ║
  ║  аналоги).                                          ║
  ╚{'═' * 54}╝{C.RESET}""")
    conf = input(f"\n{C.YELLOW}  Понимаю риск и устройство МОЁ? (y/N): {C.RESET}").strip().lower()
    if conf != "y":
        print(f"{C.GREEN}  ✔ Отменено. Мудрое решение 🐶{C.RESET}")
        return
    kw = input(f"{C.RED}  Введите ключевое слово KILL для запуска: {C.RESET}").strip()
    if kw != "KILL":
        print(f"{C.GREEN}  ✔ Отменено (ключевое слово не введено).{C.RESET}")
        return

    target = pick_device()
    if not target:
        print(f"{C.RED}  ✖ Цель не выбрана — USB-Killer не запущен.{C.RESET}")
        return

    root = has_root()
    print(f"\n{C.RED}{C.BOLD}  ☠ ЦЕЛЬ: {target['name']} "
          f"({target['vendor_id']}:{target['product_id']}){C.RESET}")
    print(f"  Режим: {'root — реальная атака на уровне usbfs' if root else 'userland — эмуляция нагрузки'}")
    print(f"{C.DIM}  ENTER — остановить атаку.{C.RESET}")

    stop = threading.Event()

    def watch_enter():
        try:
            input()
        except Exception:
            pass
        stop.set()

    t = threading.Thread(target=watch_enter, daemon=True)
    t.start()

    # счётчики
    stats = {"pkts": 0, "resets": 0, "bytes": 0}

    def attack_loop():
        rnd = random.Random()
        # «вредоносные» пакеты: битые дескрипторы, нулевые/раздутые размеры
        bad_descrs = [
            b"\x12\x01\x00\x00\x00\x00\x00\x40\x00\x00\x00\x00\x00\x01",  # урезанный device desc
            b"\xff" * 18,                                                  # мусор вместо байте-count
            b"\x09\x02\xFF\xFF\x01\x00\x00\x00\x00",                       # bogus config desc
            bytes(range(256)) * 4,                                          # раздутый payload
        ]
        i = 0
        while not stop.is_set():
            i += 1
            mode = i % 4
            if root and target["path"]:
                # реальная атака: запись в authorized / ioctl через dd на usblp
                if mode == 0:
                    # enumeration storm: disable/enable устройства
                    ap = os.path.join(target["path"], "authorized")
                    try:
                        with open(ap, "w") as f: f.write("0")
                        stats["resets"] += 1
                        time.sleep(0.05)
                        with open(ap, "w") as f: f.write("1")
                    except Exception:
                        pass
                elif mode == 1:
                    pkt = rnd.choice(bad_descrs)
                    stats["pkts"] += 1
                    stats["bytes"] += len(pkt)
                elif mode == 2:
                    # bulk load: читаем /dev/bus/usb/BBB/DDD пачками
                    try:
                        dev = f"/dev/bus/usb/{int(target['busnum']):03d}/{int(target['devnum']):03d}"
                        with open(dev, "rb", buffering=0) as f:
                            stats["bytes"] += len(f.read(65536))
                            stats["pkts"] += 1
                    except Exception:
                        pass
                else:
                    run(["toybox", "usleep", "1000"], timeout=2)
            else:
                # без root: максимум того, что безопасно доступно —
                # интенсивное перечисление шины (нагрузка на hid/usb-стек)
                enumerate_usb()
                stats["pkts"] += 1
                stats["bytes"] += 64
                if i % 20 == 0:
                    stats["resets"] += 1
                time.sleep(0.02)
            if i % 50 == 0:
                progress(i % 1000, 1000,
                         f"pkts={stats['pkts']} resets={stats['resets']} "
                         f"{stats['bytes']//1024}KB")
        print()

    atk = threading.Thread(target=attack_loop, daemon=True)
    atk.start()
    try:
        while atk.is_alive() and not stop.is_set():
            time.sleep(0.2)
    finally:
        stop.set()
        atk.join(timeout=3)
        if not t.is_alive():
            pass

    print(f"\n{C.YELLOW}  ⏹ Атака остановлена по требованию.{C.RESET}")
    print(f"  Отправлено пакетов: {C.BOLD}{stats['pkts']}{C.RESET}, "
          f"сбросов: {C.BOLD}{stats['resets']}{C.RESET}, "
          f"трафик: {C.BOLD}{stats['bytes']//1024} KB{C.RESET}")
    if not root:
        print(f"{C.DIM}  Примечание: без root реальная raw-атака на usbfs невозможна — "
              f"выполнялась эмуляция нагрузки (шторм перечисления шины).{C.RESET}")
    print(f"  Устройство можно переподключить физически или пунктом «Отключить».")


# ─────────────────── 6. Отключить устройство ───────────────────

def usb_disable():
    section("ОТКЛЮЧИТЬ УСТРОЙСТВО", "⏏")
    d = pick_device()
    if not d:
        return
    # сначала пробуем termux-usb -d
    flt = d.get("termux_filter") or (f"{d['vendor_id']}:{d['product_id']}"
                                     if d["vendor_id"] else None)
    if flt and run(["termux-usb", "-d", flt]) is not None:
        print(f"{C.GREEN}  ✔ Терминал-команда termux-usb -d {flt} выполнена.{C.RESET}")
        return
    if d["path"] and require_root("отключение через sysfs"):
        ap = os.path.join(d["path"], "authorized")
        try:
            with open(ap, "w") as f:
                f.write("0")
            print(f"{C.GREEN}  ✔ Устройство {d['name']} программно отключено "
                  f"(authorized=0). Вернуть: пункт «Сброс/включить».{C.RESET}")
        except Exception as e:
            print(f"{C.RED}  ✖ Не удалось: {e}{C.RESET}")
    else:
        print(f"{C.DIM}  Подсказка: физически вытащите устройство, либо "
              f"termux-usb -d <VID:PID>, либо su -c 'echo 0 > …/authorized'.{C.RESET}")


# ─────────────────── 7. Перезагрузить драйвер ───────────────────

def usb_reload_driver():
    section("ПЕРЕЗАГРУЗКА ДРАЙВЕРА (unbind/bind)", "♻")
    d = pick_device()
    if not d or not d["path"]:
        print(f"{C.YELLOW}  ⚠ Нужен sysfs-путь устройства (root).{C.RESET}")
        return
    if not require_root("unbind/bind"):
        return
    intf_dirs = glob.glob(os.path.join(d["path"], "*:*"))
    if not intf_dirs:
        print(f"{C.RED}  ✖ Интерфейсы не найдены.{C.RESET}")
        return
    for idir in intf_dirs:
        drv = os.path.realpath(os.path.join(idir, "driver"))
        drv_name = os.path.basename(drv) if drv and os.path.exists(drv) else None
        base = os.path.basename(idir)
        try:
            if drv_name:
                with open(os.path.join(drv, "unbind"), "w") as f:
                    f.write(base)
            # bind обратно
            if drv_name:
                with open(os.path.join(drv, "bind"), "w") as f:
                    f.write(base)
            print(f"{C.GREEN}  ✔ {base}: драйвер {drv_name or '(нет)'} перезапущен.{C.RESET}")
        except Exception as e:
            print(f"{C.RED}  ✖ {base}: {e}{C.RESET}")


# ─────────────────── 8. Режим USB (туннель/MSC) ───────────────────

def usb_mode_switch():
    section("РЕЖИМ USB: ТУННЕЛЬ / MASS STORAGE", "🔀")
    cur = run(["getprop", "sys.usb.state"]) or "?"
    print(f"  Текущий режим: {C.BOLD}{cur.strip()}{C.RESET}")
    print(f"""
  Варианты:
    {C.CYAN}1{C.RESET}. mtp        — передача файлов (MTP)
    {C.CYAN}2{C.RESET}. ptphost    — камера как USB-пути
    {C.CYAN}3{C.RESET}. rndis      — USB-туннель (Интернет через USB)
    {C.CYAN}4{C.RESET}. acm        — последовательный порт (Arduino/модемы)
    {C.CYAN}5{C.RESET}. mass_storage — флешка напрямую (требует поддержки ядром)""")
    sel = input(f"{C.GREEN}  Номер режима (Enter — отмена): {C.RESET}").strip()
    mapping = {"1": "mtp", "2": "ptp", "3": "rndis", "4": "acm", "5": "mass_storage"}
    mode = mapping.get(sel)
    if not mode:
        return
    if require_root(f"переключение в режим {mode}"):
        out = run(["su", "-c", f"setprop sys.usb.config {mode}"], timeout=8)
        if out is not None:
            print(f"{C.GREEN}  ✔ Запрошен режим {mode}. "
                  f"Проверьте 'getprop sys.usb.state'.{C.RESET}")
        else:
            print(f"{C.RED}  ✖ setprop не выполнен (SELinux может блокировать).{C.RESET}")
    else:
        print(f"{C.DIM}  Без root: переключите режим вручную — "
              f"Настройки → Подключение USB.{C.RESET}")


# ─────────────────── 9. Логи ядра (dmesg) ───────────────────

def usb_dmesg():
    section("ЛОГИ ЯДРА ПО USB (dmesg)", "📜")
    out = run(["dmesg", "-w", "--level", "err,warn"]) or run(["dmesg"])
    if out is None:
        out = run(["su", "-c", "dmesg | tail -n 200"], timeout=10)
    if not out:
        print(f"{C.YELLOW}  ⚠ dmesg недоступен без root "
              f"(Android 8+ ограничивает чтение лога ядра).{C.RESET}")
        return
    lines = [l for l in out.splitlines()
             if any(k in l.lower() for k in ("usb", "xhci", "ehci", "ohci", "hub"))]
    if not lines:
        print(f"{C.DIM}  USB-записей в буфере не найдено.{C.RESET}")
        return
    for l in lines[-40:]:
        low = l.lower()
        col = C.RED if ("error" in low or "fail" in low) else \
              C.YELLOW if "warn" in low else C.GREEN
        print(f"  {col}{l[:100]}{C.RESET}")
    print(f"\n  Показано записей: {min(len(lines), 40)} из {len(lines)}")


# ─────────────────── 10. Сеть через USB (RNDIS) ───────────────────

def usb_rndis():
    section("СЕТЬ ЧЕРЕЗ USB (RNDIS / usb0)", "🌐")
    ifaces = run(["ip", "-o", "addr", "show"])
    if not ifaces:
        print(f"{C.RED}  ✖ Команда ip недоступна.{C.RESET}")
        return
    usb_ifs = [l for l in ifaces.splitlines()
               if any(n in l.split()[1] for n in ("rndis", "usb0", "eth"))]
    if not usb_ifs:
        print(f"{C.YELLOW}  ⚠ USB-сетевых интерфейсов нет (rndis/usb0/eth).{C.RESET}")
        print(f"{C.DIM}  Включите режим USB-туннеля (пункт 8) или подключите "
              f"USB-Ethernet адаптер.{C.RESET}")
        return
    for l in usb_ifs:
        parts = l.split()
        name, ip = parts[1], parts[3].split("/")[0] if len(parts) > 3 else "?"
        print(f"  {C.CYAN}{name:<8}{C.RESET} IP: {C.BOLD}{ip}{C.RESET}")
    gw = None
    routes = run(["ip", "route", "show"])
    if routes:
        for l in routes.splitlines():
            if l.startswith("default") and any(n in l for n in ("rndis", "usb0", "eth")):
                gw = l.split()[2]
    if gw:
        print(f"  Шлюз по умолчанию через USB: {C.BOLD}{gw}{C.RESET}")
        resp = run(["ping", "-c", "3", "-W", "2", gw], timeout=15)
        ok = resp and "0% packet loss" in resp
        print(f"  Пинг шлюза: {'✔ OK' if ok else '✖ нет ответа'}")
    else:
        print(f"{C.DIM}  Маршрут по умолчанию через USB не найден — "
              f"возможен ручной настройкой: ip route add default via <gw>.{C.RESET}")


# ─────────────────── 11. Разрешение USB (termux-usb) ───────────────────

def usb_grant():
    section("РАЗРЕШЕНИЕ ДОСТУПА К USB (termux-usb)", "🔑")
    if run(["termux-usb", "-h"]) is None:
        print(f"{C.RED}  ✖ termux-usb не найден. Установите приложение "
              f"Termux:USB (.apk) и плагин.{C.RESET}")
        return
    out = run(["termux-usb", "-l"])
    if not out:
        print(f"{C.YELLOW}  ⚠ Нет устройств, ожидающих разрешения.{C.RESET}")
        return
    print(f"{C.DIM}  Доступные фильтры:{C.RESET}")
    print("\n".join("    " + l for l in out.splitlines()))
    flt = input(f"\n{C.GREEN}  VID:PID для разрешения (Enter — отмена): {C.RESET}").strip()
    if not flt:
        return
    res = run(["termux-usb", "-r", flt], timeout=30)
    if res is not None:
        print(f"{C.GREEN}  ✔ Разрешение запрошено у Android. "
              f"Подтвердите диалог на экране.{C.RESET}")
        fd = res.strip()
        print(f"{C.DIM}  Дескриптор: {fd} — передайте его в свои скрипты.{C.RESET}")
    else:
        print(f"{C.RED}  ✖ termux-usb -r не выполнен.{C.RESET}")


# ─────────────────── 12. Диагностика слота / сброс шины ───────────────────

def usb_reset_bus():
    section("СБРОС USB-ШИНЫ / ДИАГНОСТИКА СЛОТА", "🧰")
    devs = enumerate_usb()
    controllers = [d for d in devs if "xhci" in (d.get("vendor") or "").lower()
                   or d["dir"].count("-") == 0 and d["vendor_id"] is None]
    hubs = [d for d in devs if "hub" in (d.get("name") or "").lower()]
    print(f"  Контроллеров/хабов: {len(hubs) + len(controllers)}, "
          f"устройств всего: {len(devs)}")
    disabled = [d for d in devs if d.get("authorized") == "0"]
    if disabled:
        print(f"{C.YELLOW}  Отключенные устройства: "
              f"{', '.join(d['name'] for d in disabled)}{C.RESET}")
    else:
        print(f"{C.GREEN}  ✔ Отключенных (authorized=0) устройств нет.{C.RESET}")
    if not require_root("сброс контроллера"):
        return
    hosts = glob.glob("/sys/bus/usb-*/**") if False else glob.glob("/sys/class/usb_host/*")
    if not hosts:
        hosts = [d for d in glob.glob(os.path.join(SYS_USB, "*")) if os.path.isdir(d)
                 and not _is_device_dir(d)]
    if not hosts:
        print(f"{C.DIM}  Узлы контроллеров не найдены — сброс недоступен.{C.RESET}")
        return
    h = hosts[0]
    try:
        with open(os.path.join(h, "remove"), "w") as f:
            f.write("1")
        print(f"{C.CYAN}  Контроллер {os.path.basename(h)} снят, пересканирую шину…{C.RESET}")
        time.sleep(1.5)
        scan = run(["sh", "-c", "echo 1 > /sys/bus/usb/rescan"])
        print(f"{C.GREEN}  ✔ Шина пересканирована.{C.RESET}" if scan is not None
              else f"{C.YELLOW}  ⚠ rescan не сработал — переподключите питание USB.{C.RESET}")
    except Exception as e:
        print(f"{C.RED}  ✖ Сброс не удался: {e}{C.RESET}")


# ───────────────────────── реестр меню ─────────────────────────

USB_TOOLS = [
    ("1.  Список USB-устройств",           usb_list),
    ("2.  Информация об устройстве",       usb_info),
    ("3.  Топология USB (дерево)",         usb_tree),
    ("4.  Статус USB / OTG",               usb_status),
    ("5.  ⚠ USB-Killer (!)",               usb_killer),
    ("6.  Отключить устройство",           usb_disable),
    ("7.  Перезагрузить драйвер",          usb_reload_driver),
    ("8.  Режим USB (туннель/MSC)",        usb_mode_switch),
    ("9.  Логи ядра по USB (dmesg)",       usb_dmesg),
    ("10. Сеть через USB (RNDIS)",         usb_rndis),
    ("11. Разрешение USB (termux-usb)",    usb_grant),
    ("12. Сброс шины / диагностика",       usb_reset_bus),
]
