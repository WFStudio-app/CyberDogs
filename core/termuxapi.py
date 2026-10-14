#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/termuxapi.py — надёжное определение Termux:API.

Проблема, которую решает этот модуль: бинарники Termux:API
(termux-wifi-scaninfo, termux-battery-status и т.д.) лежат в
/data/data/com.termux/files/usr/bin, но при запуске CyberDogs НЕ из
обычной оболочки Termux (например: `python3 cyberdogs.py` через
`termux-open`, sh -c, cron/boot) эта директория может отсутствовать
в PATH. Из-за этого shutil.which() возвращает None и программа
ошибочно пишет «Termux:API недоступен», хотя API включён и работает.

Решение: ищем бинарники и в PATH, и по известным путям Termux;
сам результат кешируем.
"""

import os
import shutil

# Стандартное расположение бинарников Termux (префикс установки)
TERMUX_BIN_CANDIDATES = [
    "/data/data/com.termux/files/usr/bin",
    "/data/user/0/com.termux/files/usr/bin",   # work-профили / вторые копии
]


def _extra_dirs():
    """Каталоги с бинарниками Termux: добавляем их в PATH процесса."""
    dirs = []
    for d in TERMUX_BIN_CANDIDATES:
        if os.path.isdir(d):
            dirs.append(d)
    prefix = os.environ.get("PREFIX", "")
    if prefix:
        p = os.path.join(prefix, "bin")
        if os.path.isdir(p) and p not in dirs:
            dirs.append(p)
    return dirs


def ensure_path():
    """Гарантирует, что каталоги Termux есть в PATH текущего процесса."""
    env_path = os.environ.get("PATH", "")
    parts = env_path.split(os.pathsep) if env_path else []
    add = [d for d in _extra_dirs() if d not in parts]
    if add:
        os.environ["PATH"] = os.pathsep.join(add + parts)


def api_bin(name):
    """Полный путь к бинарнику Termux:API `name` или None.

    Ищет сначала в PATH, затем напрямую в каталогах Termux.
    """
    ensure_path()
    found = shutil.which(name)
    if found:
        return found
    for d in _extra_dirs():
        cand = os.path.join(d, name)
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return None


def api_available(probe="termux-wifi-scaninfo"):
    """Есть ли Termux:API (по умолчанию проверяется Wi-Fi-команда)."""
    return api_bin(probe) is not None


def api_version():
    """Версия приложения Termux:API (из пакета dpkg), если найдена."""
    status = api_bin("termux-api-version")
    if status:
        import subprocess
        try:
            out = subprocess.run([status], capture_output=True, text=True,
                                 timeout=5).stdout.strip()
            if out:
                return out
        except Exception:
            pass
    try:
        import glob
        for f in glob.glob("/data/data/com.termux/files/usr/var/lib/dpkg/"
                           "info/termux-api*"):
            if f.endswith(".md5sums"):
                continue
            with open(f, encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    if line.startswith("Version:"):
                        return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""
