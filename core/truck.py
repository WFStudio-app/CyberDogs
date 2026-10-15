#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.truck — пакетный менеджер Truck (команда: trk) для CyberOS.

Хранит установленные пакеты в ~/.cyberos/truck/ (по одному файлу на пакет),
реестр доступных пакетов — в ~/.cyberos/truck_registry.json.

Команды:
    trk install <pkg> [pkg2 ...]   установка пакета из реестра
    trk remove <pkg>               удаление установленного пакета
    trk list                       список установленных пакетов
    trk search <запрос>            поиск по реестру
    trk info <pkg>                 информация о пакете
    trk update                     обновление списка пакетов (реестра)
    trk upgrade                    переустановка устаревших пакетов
    trk clean                      очистка кэша загрузки
    trk history                    журнал операций менеджера
"""

import os
import sys
import json
import time
import hashlib

HOME = os.path.expanduser("~")
TRK_DIR = os.path.join(HOME, ".cyberos", "truck")
REG_PATH = os.path.join(HOME, ".cyberos", "truck_registry.json")
HIST_PATH = os.path.join(HOME, ".cyberos", "truck_history.log")
CACHE_DIR = os.path.join(TRK_DIR, ".cache")


class T:
    """ANSI-цвета (без смайликов — только символы и цвет)."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    GRAY = "\033[90m"
    MAGENTA = "\033[95m"

    @staticmethod
    def disable():
        if not sys.stdout.isatty():
            for a in ("RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW",
                      "CYAN", "GRAY", "MAGENTA"):
                setattr(T, a, "")


T.disable()

# ─────────── базовый реестр пакетов Truck ───────────

DEFAULT_REGISTRY = {
    "netmap":      {"version": "1.4.2", "size_kb": 214,
                    "desc": "Картография подсети: быстрые ping/ARP обходы"},
    "portpeek":    {"version": "0.9.7", "size_kb": 96,
                    "desc": "Лёгкий TCP/UDP сканер портов с баннерами"},
    "hashcat-lite": {"version": "2.1.0", "size_kb": 388,
                     "desc": "Оффлайн перебор хешей (MD5/SHA family)"},
    "wordsmith":   {"version": "1.0.3", "size_kb": 44,
                    "desc": "Генератор словарей и масок для брутфорса"},
    "wifimap":     {"version": "0.5.1", "size_kb": 61,
                    "desc": "Драйверный Wi-Fi снапшот + экспорт в JSON"},
    "bluesniff":   {"version": "0.3.9", "size_kb": 78,
                    "desc": "Разведка Bluetooth/BLE окружения"},
    "usbwatch":    {"version": "1.2.0", "size_kb": 35,
                    "desc": "Мониторинг событий подключения USB (uevent)"},
    "pktcraft":    {"version": "0.8.4", "size_kb": 512,
                    "desc": "Конструктор и отправитель сырых пакетов"},
    "revhex":      {"version": "3.0.1", "size_kb": 173,
                    "desc": "Hex-реверс инженер: дампы, строки, энтропия"},
    "cryptool":    {"version": "1.6.5", "size_kb": 122,
                    "desc": "Кодеки, шифры, отпечатки, padding oracle tools"},
    "logtail":     {"version": "0.4.0", "size_kb": 18,
                    "desc": "Хвост логов ядра/системы с подсветкой"},
    "dnsrecon-lite": {"version": "1.1.1", "size_kb": 87,
                      "desc": "DNS разведка домена: записи, зоны, subdomain"},
}


def _ensure_dirs():
    os.makedirs(TRK_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)


def load_registry():
    """Реестр доступных пакетов (создаётся из встроенного при первом запуске)."""
    _ensure_dirs()
    if not os.path.exists(REG_PATH):
        with open(REG_PATH, "w", encoding="utf-8") as f:
            json.dump({"updated": time.strftime("%Y-%m-%d %H:%M"),
                       "packages": DEFAULT_REGISTRY}, f, ensure_ascii=False, indent=2)
    try:
        with open(REG_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"updated": "?", "packages": dict(DEFAULT_REGISTRY)}


def installed_list():
    """Установленные пакеты: имя -> метаданные."""
    _ensure_dirs()
    out = {}
    for fn in sorted(os.listdir(TRK_DIR)):
        p = os.path.join(TRK_DIR, fn)
        if fn.endswith(".json") and os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                out[d.get("name", fn[:-5])] = d
            except Exception:
                continue
    return out


def _history(op, text):
    try:
        with open(HIST_PATH, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {op:<8} {text}\n")
    except Exception:
        pass


def _bar(pct, width=24):
    filled = int(width * pct / 100)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


def _say(msg):
    print(f"  {msg}")


def _err(msg):
    print(f"  {T.RED}[x]{T.RESET} {msg}")


def _ok(msg):
    print(f"  {T.GREEN}[+]{T.RESET} {msg}")


# ─────────── команды ───────────

def cmd_install(args):
    reg = load_registry()["packages"]
    if not args:
        _err("использование: trk install <pkg> [pkg2 ...]")
        return
    for name in args:
        pkg = reg.get(name)
        if not pkg:
            _err(f"пакет '{name}' не найден в реестре (trk search {name})")
            continue
        if name in installed_list():
            _say(f"{T.YELLOW}[!]{T.RESET} пакет '{name}' уже установлен "
                 f"(v{pkg['version']})")
            continue
        _say(f"{T.CYAN}--> {T.BOLD}Загрузка {name}-{pkg['version']}{T.RESET}")
        # имитация загрузки с прогрессом
        steps = 20
        for i in range(1, steps + 1):
            pct = int(i * 100 / steps)
            sys.stdout.write(f"\r  {_bar(pct)} {pct:>3}%  "
                             f"{pkg['size_kb']} KB  {name}.trk")
            sys.stdout.flush()
            time.sleep(0.05)
        print()
        meta = {"name": name, "version": pkg["version"],
                "size_kb": pkg["size_kb"], "desc": pkg["desc"],
                "installed": time.strftime("%Y-%m-%d %H:%M:%S"),
                "checksum": hashlib.sha256(
                    f"{name}{pkg['version']}".encode()).hexdigest()[:16]}
        with open(os.path.join(TRK_DIR, f"{name}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        _history("install", name)
        _ok(f"установлен {T.BOLD}{name}{T.RESET} v{pkg['version']} "
            f"({pkg['size_kb']} KB)")


def cmd_remove(args):
    inst = installed_list()
    if not args:
        _err("использование: trk remove <pkg>")
        return
    for name in args:
        if name not in inst:
            _err(f"пакет '{name}' не установлен")
            continue
        os.remove(os.path.join(TRK_DIR, f"{name}.json"))
        _history("remove", name)
        _ok(f"удалён пакет {name}")


def cmd_list(_args):
    inst = installed_list()
    if not inst:
        _say(f"{T.DIM}нет установленных пакетов — trk install <pkg>{T.RESET}")
        return
    _say(f"{T.BOLD}Установленные пакеты ({len(inst)}):{T.RESET}")
    for name, d in inst.items():
        _say(f"  {T.GREEN}*{T.RESET} {name:<16} v{d.get('version','?'):<8} "
             f"{T.GRAY}{d.get('size_kb', '?')} KB · {d.get('desc', '')[:44]}{T.RESET}")


def cmd_search(args):
    reg = load_registry()["packages"]
    if not args:
        _err("использование: trk search <запрос>")
        return
    q = " ".join(args).lower()
    hits = [(n, p) for n, p in reg.items()
            if q in n.lower() or q in p["desc"].lower()]
    if not hits:
        _say(f"{T.DIM}ничего не найдено по запросу '{q}'{T.RESET}")
        return
    _say(f"{T.BOLD}Найдено в реестре ({len(hits)}):{T.RESET}")
    for n, p in hits:
        mark = T.GREEN + "[i]" if n in installed_list() else T.CYAN + "[ ]"
        _say(f"  {mark}{T.RESET} {n:<16} v{p['version']:<8} {T.GRAY}{p['desc'][:46]}{T.RESET}")


def cmd_info(args):
    reg = load_registry()["packages"]
    if not args or args[0] not in reg:
        _err("пакет не найден в реестре")
        return
    name = args[0]
    p = reg[name]
    inst = installed_list().get(name)
    _say(f"{T.BOLD}{T.MAGENTA}┌─ пакет: {name}{T.RESET}")
    _say(f"  версия : {p['version']}")
    _say(f"  размер : {p['size_kb']} KB")
    _say(f"  описание: {p['desc']}")
    if inst:
        _say(f"  статус : {T.GREEN}установлен{T.RESET} "
             f"({inst['installed']}, sha256:{inst['checksum']})")
    else:
        _say(f"  статус : {T.DIM}не установлен{T.RESET}")
    _say(f"{T.MAGENTA}└{'─' * 30}{T.RESET}")


def cmd_update(_args):
    reg = load_registry()
    _say(f"{T.CYAN}--> Обновление индекса пакетов...{T.RESET}")
    time.sleep(0.4)
    _say(f"{_bar(100)} 100%  индекс загружен")
    _history("update", f"registry {reg['updated']}")
    _ok(f"индекс актуален: {len(reg['packages'])} пакетов "
        f"(обновлён {reg['updated']})")


def cmd_upgrade(_args):
    reg = load_registry()["packages"]
    inst = installed_list()
    outdated = [(n, d["version"], reg[n]["version"])
                for n, d in inst.items()
                if n in reg and reg[n]["version"] != d["version"]]
    if not outdated:
        _say(f"{T.DIM}все пакеты обновлены — ничего не найдено{T.RESET}")
        return
    for n, cur, new in outdated:
        _say(f"{T.CYAN}--> {n}: {cur} -> {new}{T.RESET}")
        d = dict(inst[n]); d["version"] = new
        d["installed"] = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(TRK_DIR, f"{n}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)
        _history("upgrade", n)
        _ok(f"обновлён {n} до v{new}")


def cmd_clean(_args):
    removed = 0
    if os.path.isdir(CACHE_DIR):
        for fn in os.listdir(CACHE_DIR):
            try:
                os.remove(os.path.join(CACHE_DIR, fn))
                removed += 1
            except OSError:
                pass
    _history("clean", f"{removed} files")
    _ok(f"кэш очищен ({removed} файлов)")


def cmd_history(_args):
    if not os.path.exists(HIST_PATH):
        _say(f"{T.DIM}журнал пуст{T.RESET}")
        return
    _say(f"{T.BOLD}Журнал операций Truck:{T.RESET}")
    with open(HIST_PATH, encoding="utf-8") as f:
        for line in f.read().splitlines()[-20:]:
            _say(f"  {T.GRAY}{line}{T.RESET}")


COMMANDS = {
    "install": cmd_install,
    "remove":  cmd_remove,
    "uninstall": cmd_remove,
    "list":    cmd_list,
    "ls":      cmd_list,
    "search":  cmd_search,
    "info":    cmd_info,
    "show":    cmd_info,
    "update":  cmd_update,
    "upgrade": cmd_upgrade,
    "clean":   cmd_clean,
    "history": cmd_history,
}


def banner():
    _say(f"{T.MAGENTA}{T.BOLD}Truck{T.RESET}{T.CYAN} package manager{T.RESET} "
         f"{T.GRAY}v1.0 · CyberOS{C0()}")
    _say(f"{T.DIM}  команды: install remove list search info update upgrade "
         f"clean history{T.RESET}")


def C0():
    return T.RESET


def usage():
    banner()
    _say("")
    _say(f"  {T.YELLOW}trk <команда> [аргументы]{T.RESET}")
    _say("  примеры:")
    _say(f"    {T.CYAN}trk install portpeek{T.RESET}     установить пакет")
    _say(f"    {T.CYAN}trk list{T.RESET}                  установленные пакеты")
    _say(f"    {T.CYAN}trk search wifi{T.RESET}           поиск по реестру")


def run(argv):
    """Точка входа: argv — список аргументов после 'trk'."""
    if not argv:
        banner()
        usage()
        return
    cmd, args = argv[0].lower(), argv[1:]
    if cmd in ("-h", "--help", "help"):
        usage()
        return
    fn = COMMANDS.get(cmd)
    if not fn:
        _err(f"неизвестная команда: '{cmd}' (trk help)")
        return
    fn(args)


# ─────────── меню trk для пункта «Терминал» главного меню ───────────

def truck_menu():
    """Интерактивная оболочка Truck (из главного меню → Терминал)."""
    from core.ui import header, clear, pause
    while True:
        clear()
        header("TERMINAL · TRUCK PKG MANAGER")
        banner()
        _say("")
        _say(f"  {T.CYAN}1.{T.RESET} install <pkg>    "
             f"{T.CYAN}2.{T.RESET} remove <pkg>    "
             f"{T.CYAN}3.{T.RESET} list")
        _say(f"  {T.CYAN}4.{T.RESET} search <q>      "
             f"{T.CYAN}5.{T.RESET} info <pkg>      "
             f"{T.CYAN}6.{T.RESET} update")
        _say(f"  {T.CYAN}7.{T.RESET} upgrade         "
             f"{T.CYAN}8.{T.RESET} clean           "
             f"{T.CYAN}9.{T.RESET} history")
        _say(f"  {T.DIM}01. ← назад в главное меню · 0. выход из терминала{T.RESET}")
        try:
            line = input(f"\n{t_colored_prompt()}").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not line:
            continue
        if line == "01":
            return
        if line in ("0", "exit", "quit", "q"):
            return
        parts = line.split()
        quick = {"1": "install", "2": "remove", "3": "list", "4": "search",
                 "5": "info", "6": "update", "7": "upgrade", "8": "clean",
                 "9": "history"}
        if parts[0] in quick and len(parts) == 1:
            parts = [quick[parts[0]]]
        elif parts[0] in quick and len(parts) > 1:
            parts = [quick[parts[0]]] + parts[1:]
        run(parts)
        pause("ENTER — продолжить работу в терминале…")


def t_colored_prompt():
    return (f"{T.GREEN}trk{T.RESET}{T.GRAY}@{T.RESET}"
            f"{T.CYAN}cyberos{T.RESET} {T.MAGENTA}~${T.RESET} ")
