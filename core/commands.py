# -*- coding: utf-8 -*-
"""CyberOS shell command handlers."""
import os
import time

from core import fs


def cmd_ls(sh, args):
    path = args[0] if args else sh.cwd
    if not os.path.isdir(path):
        sh.ui.error("ls: %s: не каталог" % path)
        return
    dirs, files = fs.list_dir(path)
    for d in dirs:
        sh.out(sh.ui.CYAN + "  " + d + sh.ui.RESET)
    for f in files:
        full = os.path.join(path, f)
        try:
            size = fs.human_size(os.path.getsize(full))
        except OSError:
            size = "?"
        sh.out("  %8s  %s" % (size, f))
    if not dirs and not files:
        sh.out("  (пусто)")


def cmd_cd(sh, args):
    if not args:
        sh.cwd = "/"
        return
    target = args[0]
    if not os.path.isabs(target):
        target = os.path.normpath(os.path.join(sh.cwd, target))
    if os.path.isdir(target):
        sh.cwd = target
    else:
        sh.ui.error("cd: %s: нет такого каталога" % target)


def cmd_cat(sh, args):
    if not args:
        sh.ui.error("использование: cat <файл>")
        return
    for name in args:
        p = name if os.path.isabs(name) else os.path.join(sh.cwd, name)
        if os.path.isfile(p):
            sh.out(fs.read_file(p))
        else:
            sh.ui.error("cat: %s: файл не найден" % name)


def cmd_pwd(sh, args):
    sh.out(sh.cwd)


def cmd_touch(sh, args):
    if not args:
        sh.ui.error("использование: touch <файл>")
        return
    p = args[0] if os.path.isabs(args[0]) else os.path.join(sh.cwd, args[0])
    try:
        open(p, "a").close()
        sh.ui.ok("создан: %s" % p)
    except OSError as e:
        sh.ui.error(str(e))


def cmd_mkdir(sh, args):
    if not args:
        sh.ui.error("использование: mkdir <каталог>")
        return
    p = args[0] if os.path.isabs(args[0]) else os.path.join(sh.cwd, args[0])
    try:
        os.makedirs(p)
        sh.ui.ok("каталог создан: %s" % p)
    except OSError as e:
        sh.ui.error(str(e))


def cmd_rm(sh, args):
    if not args:
        sh.ui.error("использование: rm <файл>")
        return
    p = args[0] if os.path.isabs(args[0]) else os.path.join(sh.cwd, args[0])
    if os.path.isfile(p):
        os.remove(p)
        sh.ui.ok("удалён: %s" % p)
    else:
        sh.ui.error("rm: %s: файл не найден" % args[0])


def cmd_echo(sh, args):
    sh.out(" ".join(args))


def cmd_head(sh, args):
    if not args:
        sh.ui.error("использование: head <файл> [строк]")
        return
    n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 10
    p = args[0] if os.path.isabs(args[0]) else os.path.join(sh.cwd, args[0])
    if not os.path.isfile(p):
        sh.ui.error("head: файл не найден")
        return
    with open(p, "r", errors="replace") as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            sh.out(line.rstrip("\n"))


def cmd_df(sh, args):
    try:
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        used = total - free
        pct = int(100 * used / total) if total else 0
        bar = sh.ui.progress_bar(pct, width=24)
        sh.out("Диск   Размер  Занято  Свободно  Использование")
        sh.out("/      %8s %8s %9s  %s %d%%" % (
            fs.human_size(total), fs.human_size(used),
            fs.human_size(free), bar, pct))
    except Exception as e:
        sh.ui.error(str(e))


def cmd_uptime(sh, args):
    secs = int(time.time() - sh.boot_time)
    h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
    sh.out("аптайм: %dh %dm %ds" % (h, m, s))


def cmd_uname(sh, args):
    sh.out("CyberOS %s (%s %s)" % (sh.version, os.uname().sysname,
                                   os.uname().machine))


def cmd_clear(sh, args):
    sh.ui.clear()


def cmd_trk(sh, args):
    """Пакетный менеджер Truck: trk install/remove/list/search/info/update..."""
    from core import truck
    sh.syslog("trk " + " ".join(args) if args else "trk (usage)")
    truck.run(list(args))
