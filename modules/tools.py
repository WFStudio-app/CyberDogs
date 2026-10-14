# -*- coding: utf-8 -*-
"""
modules.tools — Полезные инструменты CyberDogs (раздел «Инструменты»).

10 функций в одном месте:
   1. ping-хост            — проверка доступности с красивым выводом;
   2. порт-сканер          — быстрый скан TCP-портов (со стандартным списком);
   3. whois/IP-инфо        — публичный IP, геолокация через ip-api.com (Termux:API не нужен);
   4. DNS-утилита          — A/AAAA/MX/TXT записи домена;
   5. MAC-вендор           — определить производителя устройства по MAC/OUI;
   6. генератор паролей    — криптостойкие пароли любой длины/набора;
   7. hash-калькулятор     — MD5/SHA1/SHA256/SHA512 строки или файла;
   8. base64/URL/Hex       — кодирование/декодирование;
   9. Telnet-клиент        — ручная проверка баннеров сервисов;
  10. информация об устройстве — сводка Termux/Android (батарея, память, дисплей,
      сеть, сенсоры — где доступно через Termux:API).

Все команды безопасны и работают без root.
"""

import os
import sys
import json
import shutil
import socket
import string
import secrets
import hashlib
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote, unquote

try:
    from core.ui import C, header, pause, spinner, progress, section, box
except ImportError:
    from core.ui import C, header, pause, spinner, progress, section, box

from core.termuxapi import api_bin


def run(cmd, timeout=15):
    """Выполнить команду, вернуть stdout или None.

    Сначала бинарь ищется через core.termuxapi (PATH + каталоги Termux),
    затем обычным shutil.which — чтобы Termux:API не считался ложно
    «недоступным».
    """
    exe = api_bin(cmd[0]) or shutil.which(cmd[0])
    if exe is None:
        return None
    try:
        return subprocess.check_output([exe] + list(cmd[1:]),
                                       stderr=subprocess.DEVNULL,
                                       text=True, timeout=timeout)
    except Exception:
        return None


def _http_get_json(url, timeout=8):
    """GET запрос без внешних зависимостей (urllib)."""
    try:
        from urllib.request import urlopen, Request
        req = Request(url, headers={"User-Agent": "CyberDogs"})
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "ignore"))
    except Exception:
        return None


# ─────────────────── 1. Ping-хост ───────────────────

def tool_ping():
    """Проверить доступность хоста (ping -c 4) с красивым итогом."""
    section("PING-хост", "📡")
    host = input(f"{C.GREEN}  Хост / IP (Enter — отмена): {C.RESET}").strip()
    if not host:
        return
    print(f"{C.CYAN}  ⟳ Пингую {host}…{C.RESET}\n")
    out = run(["ping", "-c", "4", "-W", "2", host], timeout=20)
    if out is None:
        print(f"{C.RED}  ✖ Команда ping недоступна.{C.RESET}")
        return
    for line in out.splitlines():
        low = line.lower()
        if "bytes from" in low or "icmp_seq" in low:
            print(f"{C.GREEN}    {line}{C.RESET}")
        elif "packet loss" in low or "round-trip" in low or "rtt" in low:
            print(f"{C.BOLD}    {line}{C.RESET}")
        else:
            print(f"    {line}")


# ─────────────────── 2. Порт-сканер ───────────────────

COMMON_PORTS = [21, 22, 23, 25, 53, 80, 110, 135, 139, 143, 443, 445,
               993, 995, 1723, 3306, 3389, 5432, 5900, 8080, 8443]

PORT_NAMES = {21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
              80: "HTTP", 110: "POP3", 135: "MSRPC", 139: "NetBIOS",
              143: "IMAP", 443: "HTTPS", 445: "SMB", 993: "IMAPS",
              995: "POP3S", 1723: "PPTP", 3306: "MySQL", 3389: "RDP",
              5432: "PostgreSQL", 5900: "VNC", 8080: "HTTP-alt",
              8443: "HTTPS-alt"}


def _scan_port(host, port):
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return port, True
    except OSError:
        return port, False


def tool_ports():
    """Быстрый скан TCP-портов хоста (стандартный список + свой диапазон)."""
    section("Порт-сканер", "🔌")
    host = input(f"{C.GREEN}  Целевой хост / IP: {C.RESET}").strip()
    if not host:
        return
    custom = input(f"{C.DIM}  Свои порты через запятую (Enter — типичные 21): {C.RESET}").strip()
    if custom:
        ports = []
        for p in custom.split(","):
            p = p.strip()
            if p.isdigit() and 1 <= int(p) <= 65535:
                ports.append(int(p))
    else:
        ports = COMMON_PORTS

    open_ports = []
    total = len(ports)
    try:
        with ThreadPoolExecutor(max_workers=20) as pool:
            futs = {pool.submit(_scan_port, host, p): p for p in ports}
            done = 0
            for fut in as_completed(futs):
                port, alive = fut.result()
                done += 1
                progress(done, total, f"порт {port} {'ОТКРЫТ' if alive else 'закрыт'}")
                if alive:
                    open_ports.append(port)
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}  ⛔ Сканирование остановлено.{C.RESET}")

    print()
    if open_ports:
        print(f"{C.GREEN}{C.BOLD}  ✔ Открытые порты на {host}: {len(open_ports)}{C.RESET}")
        for p in sorted(open_ports):
            print(f"    • {p:<6} {PORT_NAMES.get(p, '?')}")
    else:
        print(f"{C.DIM}  Открытых портов не найдено.{C.RESET}")


# ─────────────────── 3. Кто я / IP-инфо ───────────────────

def tool_myip():
    """Публичный IP + геолокация (бесплатный API ip-api.com)."""
    section("Мой IP и геолокация", "🌍")
    with spinner("Запрашиваю данные…"):
        data = _http_get_json("http://ip-api.com/json/?lang=ru-RU&fields="
                              "status,country,regionName,city,isp,org,query,lat,lon")
    if not data or data.get("status") != "success":
        print(f"{C.RED}  ✖ Нет соединения или API недоступен.{C.RESET}")
        return
    rows = [
        ("IP-адрес   ", data.get("query", "?")),
        ("Страна     ", f"{data.get('country', '?')} "
                        f"({data.get('regionName', '')})"),
        ("Город      ", data.get("city", "?")),
        ("Провайдер  ", data.get("isp", "?")),
        ("Организация", data.get("org", "?")),
        ("Координаты ", f"{data.get('lat', '?')}, {data.get('lon', '?')}"),
    ]
    box("Результат", width=46)
    for k, v in rows:
        print(f"    {C.CYAN}{k}{C.RESET} : {v}")
    print(f"{C.MAGENTA}╰{'─' * 45}╯{C.RESET}")


# ─────────────────── 4. DNS-утилита ───────────────────

def tool_dns():
    """A / AAAA / MX / TXT записи домена."""
    section("DNS-запрос", "🧬")
    dom = input(f"{C.GREEN}  Домен (ru.wikipedia.org): {C.RESET}").strip()
    if not dom:
        return
    types = [("A (IPv4)", socket.AF_INET), ("AAAA (IPv6)", socket.AF_INET6)]
    for label, fam in types:
        try:
            infos = socket.getaddrinfo(dom, None, fam)
            ips = sorted({i[4][0] for i in infos})
            print(f"    {C.CYAN}{label:<10}{C.RESET} : {', '.join(ips) or '—'}")
        except socket.gaierror:
            print(f"    {C.CYAN}{label:<10}{C.RESET} : нет записи")
    # MX / TXT — через dig, если установлен
    for rtype in ("MX", "TXT"):
        out = run(["dig", "+short", rtype, dom], timeout=8)
        if out and out.strip():
            print(f"    {C.CYAN}{rtype:<10}{C.RESET} :")
            for line in out.strip().splitlines():
                print(f"      · {line[:70]}")
        elif out is None:
            print(f"    {C.DIM}{rtype:<10} : dig не установлен (pkg install dnsutils){C.RESET}")
        else:
            print(f"    {C.CYAN}{rtype:<10}{C.RESET} : нет записи")


# ─────────────────── 5. MAC-вендор ───────────────────

def tool_mac_vendor():
    """Производитель устройства по MAC (OUI, база wifi.vendor_from_mac)."""
    section("MAC → производитель", "🏷")
    mac = input(f"{C.GREEN}  MAC-адрес (AA:BB:CC:DD:EE:FF): {C.RESET}").strip()
    if not mac:
        return
    try:
        from modules.scan.wifi import vendor_from_mac
    except ImportError:
        vendor_from_mac = lambda m: "?"
    vend = vendor_from_mac(mac)
    if vend == "?":
        print(f"{C.YELLOW}  ⚠ Производителя нет в мини-базе OUI проекта."
              f"\n    Полный поиск: https://macvendors.io/{mac.replace(':', '-')}{C.RESET}")
    else:
        print(f"{C.GREEN}  ✔ {mac} → {C.BOLD}{vend}{C.RESET}")


# ─────────────────── 6. Генератор паролей ───────────────────

def tool_password_gen():
    """Криптостойкая генерация паролей (secrets)."""
    section("Генератор паролей", "🔑")
    raw = input(f"{C.GREEN}  Длина [16]: {C.RESET}").strip()
    length = int(raw) if raw.isdigit() and 4 <= int(raw) <= 128 else 16
    flags = {}
    for key, prompt in (("d", "Цифры (y/n) [y]"), ("u", "Заглавные (y/n) [y]"),
                        ("l", "Строчные (y/n) [y]"), ("s", "Спецсимволы (y/n) [y]")):
        a = input(f"  {prompt}: {C.RESET}").strip().lower()
        flags[key] = a != "n"
    alphabet = ""
    if flags["d"]:
        alphabet += string.digits
    if flags["u"]:
        alphabet += string.ascii_uppercase
    if flags["l"]:
        alphabet += string.ascii_lowercase
    if flags["s"]:
        alphabet += "!@#$%^&*()-_=+[]{};:,.<>?/~"
    if not alphabet:
        print(f"{C.RED}  ✖ Пустой набор символов.{C.RESET}")
        return
    cnt_raw = input(f"{C.GREEN}  Сколько паролей [5]: {C.RESET}").strip()
    count = int(cnt_raw) if cnt_raw.isdigit() and 1 <= int(cnt_raw) <= 50 else 5
    print()
    for _ in range(count):
        pwd = "".join(secrets.choice(alphabet) for _ in range(length))
        print(f"    {C.GREEN}🔒 {pwd}{C.RESET}")


# ─────────────────── 7. Hash-калькулятор ───────────────────

def tool_hashes():
    """MD5 / SHA1 / SHA256 / SHA512 строки или файла."""
    section("Hash-калькулятор", "#️⃣")
    what = input(f"{C.GREEN}  [1] Строка  [2] Файл: {C.RESET}").strip()
    data = b""
    name = ""
    if what == "1":
        s = input(f"{C.GREEN}  Введите строку: {C.RESET}")
        data = s.encode("utf-8")
        name = "<строка>"
    elif what == "2":
        path = input(f"{C.GREEN}  Путь к файлу: {C.RESET}").strip()
        if not os.path.isfile(path):
            print(f"{C.RED}  ✖ Файл не найден.{C.RESET}")
            return
        with open(path, "rb") as f:
            data = f.read()
        name = os.path.basename(path)
    else:
        return
    print(f"\n  {C.BOLD}Данные:{C.RESET} {name} · {len(data):,} байт".replace(",", " "))
    for algo in ("md5", "sha1", "sha256", "sha512"):
        h = hashlib.new(algo, data).hexdigest()
        print(f"    {C.CYAN}{algo:<8}{C.RESET} {h}")


# ─────────────────── 8. Base64 / URL / Hex ───────────────────

def tool_codecs():
    """Кодирование и декодирование base64 / url / hex."""
    section("Base64 · URL · Hex", "🧾")
    txt = input(f"{C.GREEN}  Текст: {C.RESET}").rstrip("\n")
    if not txt:
        return
    mode = input(f"{C.DIM}  [1] Закодировать  [2] Раскодировать: {C.RESET}").strip()
    b = txt.encode("utf-8")
    if mode == "1":
        import base64 as _b64
        print(f"    {C.CYAN}base64{C.RESET} : {_b64.b64encode(b).decode()}")
        print(f"    {C.CYAN}url    {C.RESET} : {quote(txt)}")
        print(f"    {C.CYAN}hex    {C.RESET} : {b.hex()}")
    else:
        import base64 as _b64
        def _try(fn, label):
            try:
                print(f"    {C.GREEN}{label:<7}: {fn()}{C.RESET}")
            except Exception:
                print(f"    {C.DIM}{label:<7}: не декодируется{C.RESET}")
        _try(lambda: _b64.b64decode(b).decode("utf-8", "ignore"), "base64")
        _try(lambda: unquote(txt), "url")
        _try(lambda: bytes.fromhex(txt).decode("utf-8", "ignore"), "hex")


# ─────────────────── 9. Telnet-клиент ───────────────────

def tool_telnet():
    """Ручная проверка баннера сервиса (Telnet-клиент на сокетах)."""
    section("Telnet-клиент", "📞")
    host = input(f"{C.GREEN}  Хост: {C.RESET}").strip()
    if not host:
        return
    port_raw = input(f"{C.GREEN}  Порт [23]: {C.RESET}").strip()
    port = int(port_raw) if port_raw.isdigit() else 23
    try:
        s = socket.create_connection((host, port), timeout=5)
    except OSError:
        print(f"{C.RED}  ✖ Не удалось подключиться к {host}:{port}.{C.RESET}")
        return
    print(f"{C.GREEN}  ✔ Подключено. Ctrl+] или пустая строка — отбой.{C.RESET}\n")
    stop = threading.Event()

    def _reader():
        while not stop.is_set():
            try:
                data = s.recv(1024)
            except OSError:
                break
            if not data:
                break
            sys.stdout.write(data.decode("utf-8", "ignore"))
            sys.stdout.flush()

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    try:
        while not stop.is_set():
            line = input()
            if not line:
                break
            s.sendall(line.encode("utf-8") + b"\r\n")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        stop.set()
        try:
            s.close()
        except Exception:
            pass
    print(f"{C.DIM}  Соединение закрыто.{C.RESET}")


# ─────────────────── 10. Об устройстве ───────────────────

def _termux_json(cmd):
    out = run(cmd)
    try:
        return json.loads(out) if out else None
    except Exception:
        return None


def tool_device_info():
    """Сводка об Android-устройстве через Termux:API (где доступно)."""
    section("Об устройстве", "📱")
    rows = []

    batt = _termux_json(["termux-battery-status"])
    if batt:
        pct = batt.get("percentage", "?")
        plug = batt.get("plug_status", "?")
        temp = batt.get("temperature", "?")
        rows.append(("Батарея", f"{pct}% · {plug} · {temp}°C"))

    disp = _termux_json(["termux-display-information"])
    if disp:
        rows.append(("Дисплей", f"{disp.get('width', '?')}×"
                                f"{disp.get('height', '?')} px · dpi "
                                f"{disp.get('density_dpi', '?')}"))

    mem = run(["free", "-m"])
    if mem:
        for line in mem.splitlines():
            if line.startswith("Mem:"):
                p = line.split()
                rows.append(("Память", f"{p[2]} / {p[1]} МБ занято"))

    tele = _termux_json(["termux-telephony-cellinfo"])
    if tele:
        cell = tele[0] if isinstance(tele, list) and tele else tele
        if isinstance(cell, dict):
            rows.append(("Сотовая сеть",
                         f"{cell.get('network_type', '?')} · "
                         f"MCC {cell.get('mcc', '?')}"))

    wifi = _termux_json(["termux-wifi-connectioninfo"])
    if wifi:
        rows.append(("Wi-Fi", f"{wifi.get('ssid', '?')} · "
                              f"{wifi.get('level', '?')} dBm"))

    sensor = run(["termux-sensor", "-s"])
    if sensor:
        names = [s.strip() for s in sensor.splitlines() if s.strip()][:6]
        rows.append(("Сенсоры", ", ".join(names) or "—"))

    cpu = os.cpu_count()
    rows.append(("CPU ядер", str(cpu)))
    rows.append(("Termux", os.environ.get("TERMUX_VERSION",
                                          "не в Termux")))

    if not rows:
        print(f"{C.DIM}  Данные недоступны — установите Termux:API.{C.RESET}")
        return
    box("Сводка", width=46)
    for k, v in rows:
        print(f"    {C.CYAN}{k:<12}{C.RESET} {v}")
    print(f"{C.MAGENTA}╰{'─' * 45}╯{C.RESET}")


# ─────────────────── реестр инструментов ───────────────────

TOOLS = [
    ("1.  Ping-хост (доступность)",            tool_ping),
    ("2.  Порт-сканер (TCP)",                  tool_ports),
    ("3.  Мой IP и геолокация",                tool_myip),
    ("4.  DNS-запрос (A/AAAA/MX/TXT)",         tool_dns),
    ("5.  MAC → производитель (OUI)",          tool_mac_vendor),
    ("6.  Генератор паролей",                  tool_password_gen),
    ("7.  Hash-калькулятор (MD5/SHA)",         tool_hashes),
    ("8.  Base64 / URL / Hex кодеки",          tool_codecs),
    ("9.  Telnet-клиент (ручной)",             tool_telnet),
    ("10. Об устройстве (Termux:API)",         tool_device_info),
]
