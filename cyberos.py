# -*- coding: utf-8 -*-
"""
CyberOS — терминальная операционная система на базе CyberDogs.

Загрузка ядра, boot-последовательность, шелл с командами,
виртуальные консоли (tty), многозадачность, файловая система,
сеть и приложения (пентест-модули CyberDogs встроены как утилиты ОС).
"""

import os
import sys
import time
import json
import getpass
import platform

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import core.ui as ui
from core.ui import C, ACCENT, clear, header, pause, menu_loop

from core import fs
from core import commands as cmds
from modules.scan import networks, signals, wifi
from modules.attack import wifi_crack, hosts_crack
from modules import tools, usb

APP_NAME = "CyberDogs"
KERNEL = "CyberOS Kernel 1.1.0-cyber"
VERSION = "1.1.0"
ui.set_version(VERSION)

HOME = os.path.expanduser("~")
OS_ROOT = os.path.join(HOME, ".cyberos")
PROC_DIR = os.path.join(OS_ROOT, "proc")
LOG_FILE = os.path.join(OS_ROOT, "system.log")
USERS_FILE = os.path.join(OS_ROOT, "users.json")


def _visible_len(s):
    import re
    return len(re.sub(r"\033\[[0-9;]*m", "", s))


class Shell(object):
    """Оболочка CyberOS: состояние, команды, процессы."""

    def __init__(self):
        self.boot_time = time.time()
        self.cwd = BASE_DIR
        self.user = getpass.getuser()
        self.tty = 1
        self.processes = []      # [{'pid','name','cmd','start'}]
        self.next_pid = 100
        self.history = []
        self.version = VERSION
        self.ui = UIRenderer()
        self.users = self._load_users()
        if not self.users:
            self.users = {self.user: {"pass": "", "shell": "/bin/sh"}}
        self.running = True

    # ── вывод ────────────────────────────────────────────────
    def out(self, text=""):
        print(text)

    def println(self, *a):
        print(*a)

    def prompt(self):
        t = int(time.time() - self.boot_time)
        up = "%dh%02dm" % (t // 3600, (t % 3600) // 60)
        path = self.cwd.replace(HOME, "~")
        return ("%s%s@cyber:%s%s tty%d %s$%s [%s] " % (
            C.BOLD + C.GREEN, self.user, C.RESET, C.DIM,
            self.tty, C.CYAN + path, C.RESET, up)).strip()

    # ── пользователи ─────────────────────────────────────────
    def _load_users(self):
        try:
            with open(USERS_FILE) as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_users(self):
        try:
            os.makedirs(OS_ROOT, exist_ok=True)
            with open(USERS_FILE, "w") as f:
                json.dump(self.users, f)
        except Exception:
            pass

    # ── реестр команд ────────────────────────────────────────
    def build_registry(self):
        # обёртки для хендлеров из core/commands.py: они принимают (sh, args)
        def _c(fn):
            return lambda args: fn(self, args)
        r = {
            "ls": _c(cmds.cmd_ls), "dir": _c(cmds.cmd_ls),
            "cd": _c(cmds.cmd_cd), "pwd": _c(cmds.cmd_pwd),
            "cat": _c(cmds.cmd_cat), "head": _c(cmds.cmd_head),
            "touch": _c(cmds.cmd_touch), "mkdir": _c(cmds.cmd_mkdir),
            "rm": _c(cmds.cmd_rm), "echo": _c(cmds.cmd_echo),
            "df": _c(cmds.cmd_df), "uptime": _c(cmds.cmd_uptime),
            "uname": _c(cmds.cmd_uname), "clear": _c(cmds.cmd_clear), "cls": _c(cmds.cmd_clear),
            "help": self.cmd_help, "whoami": self.cmd_whoami,
            "date": self.cmd_date, "ps": self.cmd_ps,
            "kill": self.cmd_kill, "neofetch": self.cmd_neofetch,
            "tree": self.cmd_tree, "grep": self.cmd_grep,
            "wc": self.cmd_wc, "env": self.cmd_env,
            "history": self.cmd_history, "man": self.cmd_man,
            "su": self.cmd_su, "exit": self.cmd_exit, "logout": self.cmd_exit,
            "reboot": self.cmd_reboot, "shutdown": self.cmd_shutdown,
            "log": self.cmd_log, "write": self.cmd_write,
            "run": self.cmd_run, "apps": self.cmd_apps,
            "net": self.cmd_net, "scanwifi": self.app_scanwifi,
            "crack": self.app_crack, "usbinfo": self.app_usbinfo,
            "ping": self.app_ping, "ifconfig": self.app_ifconfig,
            "tools": self.app_tools_menu, "menu": self.app_cyberdogs_menu,
            "tty": self.cmd_tty, "goto": self.cmd_goto, "alias": self.cmd_alias,
            # пакетный менеджер Truck и настройки ОС
            "trk": _c(cmds.cmd_trk), "truck": _c(cmds.cmd_trk),
            "settings": self.cmd_settings,
        }
        return r

    def cmd_settings(self, args):
        """Открыть раздел «Настройки» прямо из терминала."""
        from modules.settings import settings_menu
        self.syslog("open settings from shell")
        settings_menu()

    # ── встроенные команды шелла ──────────────────────────────
    def cmd_help(self, args):
        reg = sorted(self.build_registry().keys())
        line = ""
        for c in reg:
            line += c + "  "
            if len(line) > 70:
                self.out(C.DIM + "  " + line + C.RESET)
                line = ""
        if line:
            self.out(C.DIM + "  " + line + C.RESET)
        self.out("")
        self.out(C.YELLOW + "  Синтаксис: <команда> [аргументы]" + C.RESET)
        self.out(C.DIM + "  man <команда> — справка, apps — приложения CyberOS" + C.RESET)

    def cmd_whoami(self, args):
        self.out("%s (tty%d)" % (self.user, self.tty))

    def cmd_date(self, args):
        self.out(time.strftime("%a %d %b %Y %H:%M:%S"))

    def cmd_ps(self, args):
        self.out("  PID   TTY  STARTED          COMMAND")
        now = time.time()
        self.out("    1     -  %s  cyber-kernel" %
                 time.strftime("%H:%M:%S", time.localtime(self.boot_time)))
        for p in self.processes:
            el = int(now - p["start"])
            self.out("  %4d   tty%d %s  %s (%ds)" % (
                p["pid"], p["tty"],
                time.strftime("%H:%M:%S", time.localtime(p["start"])),
                p["cmd"][:30], el))

    def cmd_kill(self, args):
        if not args or not args[0].isdigit():
            self.ui.error("использование: kill <pid>")
            return
        pid = int(args[0])
        before = len(self.processes)
        self.processes = [p for p in self.processes if p["pid"] != pid]
        if len(self.processes) == before:
            self.ui.error("kill: процесс %d не найден" % pid)
        else:
            self.ui.ok("процесс %d завершён" % pid)

    def cmd_tree(self, args):
        root = args[0] if args else self.cwd
        if not os.path.isdir(root):
            self.ui.error("tree: нет такого каталога")
            return
        self._tree_rec(root, "", 0)

    def _tree_rec(self, path, prefix, depth):
        if depth > 3:
            return
        dirs, files = fs.list_dir(path)
        entries = dirs + files
        for i, name in enumerate(entries[:20]):
            last = i == len(entries) - 1 or i == 19
            connector = "└── " if last else "├── "
            is_dir = name.endswith("/")
            color = C.CYAN if is_dir else ""
            reset = C.RESET if color else ""
            self.out(prefix + connector + color + name + reset)
            if is_dir:
                self._tree_rec(os.path.join(path, name.rstrip("/")),
                               prefix + ("    " if last else "│   "), depth + 1)

    def cmd_grep(self, args):
        if len(args) < 2:
            self.ui.error("использование: grep <шаблон> <файл>")
            return
        pat, fname = args[0], args[1]
        p = fname if os.path.isabs(fname) else os.path.join(self.cwd, fname)
        if not os.path.isfile(p):
            self.ui.error("grep: файл не найден")
            return
        found = False
        with open(p, "r", errors="replace") as f:
            for n, line in enumerate(f, 1):
                if pat.lower() in line.lower():
                    found = True
                    self.out("%s%d:%s %s" % (C.RED, n, C.RESET, line.rstrip()))
        if not found:
            self.out(C.DIM + "  совпадений нет" + C.RESET)

    def cmd_wc(self, args):
        if not args:
            self.ui.error("использование: wc <файл>")
            return
        p = args[0] if os.path.isabs(args[0]) else os.path.join(self.cwd, args[0])
        if not os.path.isfile(p):
            self.ui.error("wc: файл не найден")
            return
        with open(p, "r", errors="replace") as f:
            data = f.read()
        lines = data.count("\n")
        words = len(data.split())
        self.out("  %d строк  %d слов  %d байт" % (lines, words, len(data.encode())))

    def cmd_env(self, args):
        for k in sorted(os.environ):
            v = os.environ[k]
            if len(v) > 50:
                v = v[:47] + "..."
            self.out("  %s=%s" % (k, v))

    def cmd_history(self, args):
        for i, h in enumerate(self.history[-30:], 1):
            self.out("  %3d  %s" % (i, h))

    def cmd_man(self, args):
        if not args:
            self.ui.error("использование: man <команда>")
            return
        pages = {
            "ls": "ls [путь] — листинг каталога",
            "cd": "cd [путь] — смена каталога",
            "cat": "cat <файл> — вывод файла",
            "ps": "ps — список процессов CyberOS",
            "kill": "kill <pid> — завершить процесс",
            "apps": "apps — приложения пентест-набора",
            "run": "run <№ приложения> — запуск приложения в фоне (ps/kill)",
            "neofetch": "neofetch — сведения о системе",
            "su": "su <user> — смена пользователя",
            "menu": "menu — классическое меню CyberDogs",
        }
        self.out(C.CYAN + "  CYBEROS MAN PAGE\n" + C.RESET)
        self.out("  " + pages.get(args[0], "справки нет для '%s'" % args[0]))

    def cmd_su(self, args):
        if not args:
            self.ui.error("использование: su <user>")
            return
        user = args[0]
        if user not in self.users:
            self.ui.error("su: пользователь '%s' не существует" % user)
            return
        stored = self.users[user].get("pass", "")
        if stored:
            pw = getpass.getpass("  пароль %s: " % user)
            if pw != stored:
                self.ui.error("su: неверный пароль")
                return
        self.user = user
        self.ui.ok("сессия: %s" % user)

    def cmd_exit(self, args):
        self.running = False

    def cmd_reboot(self, args):
        if sys.stdin.isatty():
            ans = input(C.YELLOW + "  Перезагрузить систему? [y/N]: " + C.RESET)
            if ans.lower() != "y":
                return
        self.out(C.YELLOW + "  Перезагрузка CyberOS..." + C.RESET)
        time.sleep(1)
        boot_sequence()
        self.cwd = BASE_DIR
        self.tty = 1
        self.processes = []

    def cmd_shutdown(self, args):
        if sys.stdin.isatty():
            ans = input(C.RED + "  Выключить CyberOS? [y/N]: " + C.RESET)
            if ans.lower() != "y":
                return
        self.out(C.RED + "  Выключение системы... poweroff" + C.RESET)
        time.sleep(1)
        self.running = False

    def cmd_log(self, args):
        if not os.path.isfile(LOG_FILE):
            self.out(C.DIM + "  журнал пуст" + C.RESET)
            return
        with open(LOG_FILE) as f:
            lines = f.readlines()
        for l in lines[-15:]:
            self.out("  " + l.rstrip())

    def cmd_write(self, args):
        if len(args) < 2:
            self.ui.error("использование: write <файл> <текст>")
            return
        fname = args[0]
        text = " ".join(args[1:])
        p = fname if os.path.isabs(fname) else os.path.join(self.cwd, fname)
        try:
            with open(p, "a") as f:
                f.write(text + "\n")
            self.ui.ok("записано в %s" % fname)
        except OSError as e:
            self.ui.error(str(e))

    def cmd_run(self, args):
        if not args or not args[0].isdigit():
            self.ui.error("использование: run <№ из apps>")
            return
        idx = int(args[0])
        apps = list(APPS)
        if not (1 <= idx <= len(apps)):
            self.ui.error("run: приложение %d не найдено" % idx)
            return
        name, fn, desc = apps[idx - 1]
        self.next_pid += 1
        proc = {"pid": self.next_pid, "name": name, "cmd": name,
                "start": time.time(), "tty": self.tty}
        self.processes.append(proc)
        self.syslog("spawn pid=%d app=%s" % (proc["pid"], name))
        self.out(C.GREEN + "  запущено: %s (pid %d)" % (name, proc["pid"]) + C.RESET)
        try:
            fn()
        finally:
            self.processes = [p for p in self.processes if p["pid"] != proc["pid"]]

    def cmd_apps(self, args):
        self.out(C.BOLD + "  Приложения CyberOS:" + C.RESET)
        for i, (name, fn, desc) in enumerate(APPS, 1):
            self.out("  %s%2d.%s %-12s %s" % (C.YELLOW, i, C.RESET, name,
                                              C.DIM + desc + C.RESET))
        self.out(C.DIM + "  запуск: run <№> · ps · kill <pid>" + C.RESET)

    def cmd_net(self, args):
        sub = args[0].lower() if args else "info"
        if sub == "scan":
            self.app_scanwifi([])
        elif sub == "ports":
            tools.tool_ports()
        elif sub == "info":
            self.app_ifconfig([])
        else:
            self.ui.error("net: usage net info|scan|ports")

    def cmd_tty(self, args):
        if args and args[0].isdigit():
            self.tty = int(args[0])
            self.ui.ok("переключено на tty%d" % self.tty)
        else:
            self.out("активная консоль: tty%d (tty1..tty6)" % self.tty)

    def cmd_goto(self, args):
        spots = {"home": HOME, "/": "/", "root": "/",
                 "os": OS_ROOT, "logs": OS_ROOT}
        key = (args[0] if args else "").lower()
        if key in spots:
            self.cwd = spots[key]
        else:
            self.ui.error("известные точки: home, os, logs")

    def cmd_alias(self, args):
        if not hasattr(self, "aliases"):
            self.aliases = {}
        if not args:
            for k, v in sorted(self.aliases.items()):
                self.out("  %s='%s'" % (k, v))
            return
        joined = " ".join(args)
        if "=" in joined:
            name, val = joined.split("=", 1)
            val = val.strip().strip("'").strip('"')
            name = name.strip()
            self.aliases[name] = val
            self.ui.ok("alias %s='%s'" % (name, val))
        else:
            self.ui.error("использование: alias имя='команда'")

    # ── приложения/обёртки ───────────────────────────────────
    def _run_app(self, name):
        fn = _lookup_app(name)
        if not fn:
            self.ui.error("приложение '%s' не найдено (apps)" % name)
            return
        clear()
        header("CYBEROS APP :: " + name.upper())
        try:
            fn()
        except KeyboardInterrupt:
            self.out(C.DIM + "  прервано" + C.RESET)
        pause()

    def app_scanwifi(self, args):
        self._run_app("scanwifi")

    def app_crack(self, args):
        self._run_app("wificrack")

    def app_usbinfo(self, args):
        self._run_app("usbtools")

    def app_tools_menu(self, args):
        self._run_app("toolkit")

    def app_cyberdogs_menu(self, args):
        from cyberdogs import main_menu
        main_menu()

    def app_ping(self, args):
        if args:
            host = args[0]
            code = os.system("ping -c 4 " + host)
            if code != 0:
                self.ui.error("ping недоступен в этой системе")
        else:
            self._run_app("toolkit")

    def app_ifconfig(self, args):
        cmd = "ip addr" if os.system("which ip >/dev/null 2>&1") == 0 else "ifconfig"
        os.system(cmd)

    def cmd_neofetch(self, args):
        t = int(time.time() - self.boot_time)
        up = "%dh%02dm" % (t // 3600, (t % 3600) // 60)
        logo = [
            "   ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄",
            "   █ CYBEROS █",
            "   ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀",
        ]
        info = [
            ("user", self.user),
            ("host", platform.system() + " " + platform.release()),
            ("kernel", KERNEL),
            ("shell", "cyber-sh 1.0"),
            ("uptime", up),
            ("python", platform.python_version()),
            ("tty", "tty%d" % self.tty),
            ("procs", str(len(self.processes) + 1)),
        ]
        rows = max(len(logo), len(info))
        for i in range(rows):
            left = logo[i] if i < len(logo) else ""
            right = ("%s%s%s: %s" % (C.BOLD + C.CYAN, info[i][0],
                                     C.RESET, info[i][1])) if i < len(info) else ""
            print("%-20s %s" % (C.MAGENTA + left + C.RESET, right))

    # ── syslog ───────────────────────────────────────────────
    def syslog(self, msg):
        try:
            os.makedirs(OS_ROOT, exist_ok=True)
            with open(LOG_FILE, "a") as f:
                f.write("%s %s %s\n" % (time.strftime("%H:%M:%S"),
                                       self.user, msg))
        except Exception:
            pass

    # ── выполнение строки ────────────────────────────────────
    def execute_line(self, line):
        parts = line.split()
        if not parts:
            return
        cmd, args = parts[0].lower(), parts[1:]
        self.history.append(line)
        aliases = getattr(self, "aliases", {})
        if cmd in aliases:
            line = aliases[cmd] + " " + " ".join(args)
            parts = line.split()
            cmd, args = parts[0].lower(), parts[1:]
        reg = self.build_registry()
        fn = reg.get(cmd)
        if fn:
            try:
                fn(args)
            except KeyboardInterrupt:
                self.out(C.DIM + "  прервано" + C.RESET)
        else:
            self.out("%scyber: %s: команда не найдена%s  (help)" %
                     (C.RED, cmd, C.RESET))

    # ── REPL ─────────────────────────────────────────────────
    def repl(self):
        while self.running:
            try:
                line = input(self.prompt())
            except EOFError:
                break
            except KeyboardInterrupt:
                self.out("")
                continue
            line = line.strip()
            if not line:
                continue
            self.execute_line(line)
        self.out(C.DIM + "  сеанс завершён." + C.RESET)


class UIRenderer(object):
    """Методы вывода для core/commands.py (обёртки над ui)."""

    def __init__(self):
        self.CYAN = C.CYAN
        self.RESET = C.RESET
        self.MAGENTA = C.MAGENTA

    def error(self, msg):
        print(C.RED + "  [x] " + msg + C.RESET)

    def ok(self, msg):
        print(C.GREEN + "  [ok] " + msg + C.RESET)

    def progress_bar(self, pct, width=24):
        filled = int(width * pct / 100)
        return "█" * filled + "░" * (width - filled)

    def clear(self):
        clear()


# ─────────────────── приложения (CyberDogs модули) ───────────────────

def app_scan_wifi_interactive():
    wifi.scan_wifi_networks_interactive()


def app_crack_wifi():
    wifi_crack.main()


APPS = [
    ("scanwifi", lambda: wifi.scan_wifi_networks_interactive(),
     "скан Wi-Fi через Termux:API"),
    ("netdiscover", lambda: networks.scan_local_networks_interactive(),
     "ARP-скан подсети"),
    ("bluetooth", lambda: (signals.scan_signals(), pause()),
     "скан Bluetooth/радиосигналов"),
    ("wificrack", app_crack_wifi, "подбор пароля WPA (демо/боевой)"),
    ("sshcrack", lambda: hosts_crack.main(service="ssh"),
     "брутфорс SSH"),
    ("ftpcrack", lambda: hosts_crack.main(service="ftp"),
     "брутфорс FTP"),
    ("usbtools", lambda: menu_loop("USB", list(usb.USB_TOOLS) +
                                   [("0. Назад", None)]),
     "управление USB (12 функций)"),
    ("toolkit", lambda: menu_loop("ИНСТРУМЕНТЫ", list(tools.TOOLS) +
                                  [("0. Назад", None)]),
     "сетевые утилиты (10 шт.)"),
]


def _lookup_app(name):
    for n, fn, d in APPS:
        if n == name:
            return fn
    return None


# тонкие обёртки для прямого вызова из шелла
def _app_direct(self_name):
    def wrapper(args):
        fn = _lookup_app(self_name)
        if fn:
            clear()
            header("CYBEROS APP :: " + self_name.upper())
            fn()
            pause()
        else:
            shell.ui.error("приложение не найдено")
    return wrapper


# ─────────────────── boot ───────────────────

BOOT_LINES = [
    ("BIOS POST ... OK", 0.05),
    ("Loading CyberOS kernel 1.0.0-cyber ...", 0.12),
    ("Mounting /rootfs .................... done", 0.08),
    ("Starting syslogd ..................... ok", 0.06),
    ("Initializing Termux:API bridge .......", 0.10),
    ("Scanning USB subsystem ................. ok", 0.08),
    ("Bringing up wlan0 ...................... ok", 0.10),
    ("Loading pentest modules [scan/attack/usb/tools]", 0.12),
    ("Starting window-compositor (TTY mode) .. ok", 0.06),
    ("All services started. Welcome.", 0.05),
]


def boot_sequence():
    clear()
    logo = (
        C.CYAN + "   ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄\n"
        "   █  CYBEROS  v" + VERSION + "  ·  Termux Terminal OS  █\n"
        "   ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀\n" + C.RESET
    )
    print(logo)
    for txt, delay in BOOT_LINES:
        print(C.GREEN + "  [ OK ] " + C.RESET + C.DIM + txt + C.RESET)
        time.sleep(delay)
    print()
    time.sleep(0.3)


class _EOFExit(Exception):
    pass


def login_prompt(shell):
    clear()
    print(C.BOLD + C.CYAN + "  CyberOS 1.0.0-cyber  tty%d" % shell.tty + C.RESET)
    print(C.DIM + "  Unauthorized access is prohibited." + C.RESET)
    print()
    try:
        user = input(C.GREEN + "  login: " + C.RESET).strip() or shell.user
    except EOFError:
        raise _EOFExit()
    if user in shell.users:
        stored = shell.users[user].get("pass", "")
        if stored:
            pw = (getpass.getpass("  password: ") if sys.stdin.isatty()
                  else input("  password: "))
            if pw != stored:
                shell.ui.error("неверный пароль")
                return False
        shell.user = user
        shell.syslog("login user=%s tty=%d" % (user, shell.tty))
        print(C.GREEN + "  Last login: %s" %
              time.strftime("%a %d %b %H:%M") + C.RESET)
        time.sleep(0.6)
        return True
    shell.ui.error("нет такого пользователя: %s" % user)
    time.sleep(0.8)
    return False


def first_boot_setup(shell):
    """При первом запуске — создание root-пароля."""
    clear()
    print(C.BOLD + "  Первый запуск CyberOS" + C.RESET)
    print(C.DIM + "  Создайте учётную запись администратора." + C.RESET)
    print()
    name = input("  Имя пользователя [" + shell.user + "]: ").strip()
    if name:
        shell.user = name
    if sys.stdin.isatty():
        pw = getpass.getpass("  Пароль (Enter = без пароля): ")
        pw2 = getpass.getpass("  Повторите пароль: ")
    else:
        pw = input("  Пароль (Enter = без пароля): ")
        pw2 = input("  Повторите пароль: ")
    if pw and pw != pw2:
        print(C.RED + "  Пароли не совпадают — пароль не задан." + C.RESET)
        pw = ""
    shell.users[shell.user] = {"pass": pw, "shell": "/bin/sh"}
    shell._save_users()
    os.makedirs(PROC_DIR, exist_ok=True)
    shell.syslog("first-boot setup user=%s" % shell.user)
    print(C.GREEN + "  Готово. Добро пожаловать в CyberOS." + C.RESET)
    time.sleep(1)


# ─────────────────── main ───────────────────

shell = None


def main_menu_fallback():
    """Старое меню CyberDogs доступно как 'menu'."""
    from cyberdogs import main_menu
    main_menu()


def main():
    global shell
    if "--classic" in sys.argv:
        from cyberdogs import main_menu
        main_menu()
        return

    shell = Shell()
    if not os.path.isfile(USERS_FILE):
        first_boot_setup(shell)
    boot_sequence()
    try:
        while not login_prompt(shell):
            pass
    except _EOFExit:
        print("\n  (stdin закрыт — выход)")
        return
    shell.syslog("shell ready")
    print()
    print(C.BOLD + C.MAGENTA + "  Добро пожаловать в CyberOS." + C.RESET +
          C.DIM + " help · apps · neofetch · menu" + C.RESET)
    shell.repl()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  Отключено.")
        sys.exit(0)
