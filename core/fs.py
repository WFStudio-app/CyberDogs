# -*- coding: utf-8 -*-
"""CyberOS file system helpers."""
import os


def list_dir(path):
    """Return (dirs, files) for path."""
    try:
        entries = sorted(os.listdir(path))
    except PermissionError:
        return [], []
    dirs, files = [], []
    for name in entries:
        full = os.path.join(path, name)
        if os.path.isdir(full):
            dirs.append(name + "/")
        else:
            files.append(name)
    return dirs, files


def human_size(n):
    for unit in ("B", "K", "M", "G", "T"):
        if n < 1024 or unit == "T":
            return "%d%s" % (n, unit) if unit == "B" else "%.1f%s" % (n, unit)
        n /= 1024.0
    return str(n)


def read_file(path, limit=4096):
    try:
        with open(path, "r", errors="replace") as f:
            data = f.read(limit)
        if len(data) == limit:
            data += "\n...[truncated]"
        return data
    except Exception as e:
        return "[ошибка чтения: %s]" % e
