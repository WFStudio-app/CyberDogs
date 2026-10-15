#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
modules.updates — раздел «Обновления» CyberOS / CyberDogs.

Проверяет наличие новых коммитов в GitHub-репозитории и автоматически
обновляет локальную копию (git pull, при необходимости — клонирование).

Способы проверки (по порядку):
  1. git ls-remote origin        — если это git-репозиторий;
  2. GitHub API                  — если задан токен (GITHUB_TOKEN,
     ~/.cyberos/token или переменные окружения Termux-сборки);
  3. HTML-страница репозитория   — извлечение commit-sha регуляркой.

Без смайликов — только символы и ANSI-цвет.
"""

import os
import re
import sys
import json
import shutil
import subprocess
import urllib.request

from core.ui import header, clear, pause, C, ACCENT

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_URL = "https://github.com/WFStudio-app/CyberDogs"
API_REPO = "WFStudio-app/CyberDogs"
TOKEN_FILE = os.path.join(os.path.expanduser("~"), ".cyberos", "token")


def _run(cmd, cwd=None, timeout=30):
    """Выполнить команду, вернуть (rc, stdout+stderr)."""
    try:
        p = subprocess.run(cmd, cwd=cwd, timeout=timeout,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p.returncode, p.stdout.decode("utf-8", "replace").strip()
    except Exception as e:
        return -1, str(e)


def _is_git_repo():
    rc, out = _run(["git", "rev-parse", "--is-inside-work-tree"], cwd=BASE_DIR)
    return rc == 0 and out.strip() == "true"


def _local_sha():
    rc, out = _run(["git", "rev-parse", "HEAD"], cwd=BASE_DIR)
    return out if rc == 0 else ""


def _branch():
    rc, out = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=BASE_DIR)
    return out if rc == 0 and out else "main"


def load_token():
    """Токен GitHub: env GITHUB_TOKEN / файл ~/.cyberos/token / env-файл Termux."""
    t = os.environ.get("GITHUB_TOKEN", "").strip()
    if t:
        return t
    try:
        with open(TOKEN_FILE, encoding="utf-8") as f:
            t = f.read().strip()
            if t:
                return t
    except Exception:
        pass
    for ef in (os.path.expanduser("~/.termux/termux.properties"),
               "/data/data/com.termux/files/usr/etc/termux.env"):
        try:
            with open(ef, encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip().upper() in ("GITHUB_TOKEN", "GH_TOKEN"):
                            return v.strip().strip('"').strip("'")
        except Exception:
            continue
    return ""


def _api_get(url, token=""):
    req = urllib.request.Request(url, headers={
        "User-Agent": "CyberOS-updater",
        "Accept": "application/vnd.github+json",
    })
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def remote_sha():
    """Актуальный HEAD-коммит в репозитории. Возвращает (sha, способ)."""
    # 1) git ls-remote
    if shutil.which("git"):
        rc, out = _run(["git", "ls-remote", REPO_URL, _branch()], timeout=25)
        if rc == 0 and out:
            sha = out.split()[0]
            if re.match(r"^[0-9a-f]{40}$", sha):
                return sha, "git ls-remote"
    # 2) GitHub API (с токеном или анонимно)
    token = load_token()
    try:
        data = _api_get(f"https://api.github.com/repos/{API_REPO}/commits/HEAD",
                        token)
        sha = data.get("sha", "")
        if re.match(r"^[0-9a-f]{40}$", sha):
            return sha, "GitHub API" + (" (token)" if token else "")
    except Exception:
        pass
    # 3) HTML-страница репозитория
    try:
        req = urllib.request.Request(REPO_URL + "/commit",
                                     headers={"User-Agent": "CyberOS-updater"})
        with urllib.request.urlopen(req, timeout=20) as r:
            html = r.read().decode("utf-8", "replace")
        m = re.search(r'"oid"\s*:\s*"([0-9a-f]{40})"', html) or \
            re.search(r'/commit/([0-9a-f]{40})', html)
        if m:
            return m.group(1), "HTML scrape"
    except Exception:
        pass
    return "", ""


def _short(sha):
    return sha[:7] if sha else "?"


def check_updates():
    """Печатает результат проверки. Возвращает True, если есть обновление."""
    print(f"\n{C.DIM}  проверка репозитория: {REPO_URL}{C.RESET}")
    print(f"{C.DIM}  ветка: {_branch()}{C.RESET}\n")

    if not _is_git_repo():
        print(f"  {C.YELLOW}[!]{C.RESET} каталог не является git-копией — "
              f"обновление через git недоступно.")
        print(f"  {C.DIM}  вариант: удалите папку и склонируйте заново "
              f"(кнопка 3 ниже){C.RESET}")
        return False

    local = _local_sha()
    print(f"  локальная версия : {ACCENT}{_short(local)}{C.RESET}")
    print(f"  {C.DIM}  опрашиваю GitHub…{C.RESET}")
    remote, how = remote_sha()
    if not remote:
        print(f"  {C.RED}[x]{C.RESET} не удалось получить удалённую версию "
              f"(нет сети или доступ к GitHub заблокирован)")
        return False
    print(f"  удалённая версия : {ACCENT}{_short(remote)}{C.RESET}"
          f"  {C.DIM}(источник: {how}){C.RESET}")

    if local == remote:
        print(f"\n  {C.GREEN}[ok]{C.RESET} установлена последняя версия — "
              f"обновлений нет.")
        return False

    print(f"\n  {C.YELLOW}[>]{C.RESET} найдено обновление: "
          f"{_short(local)} -> {_short(remote)}")
    # что изменится (если git покажет)
    rc, out = _run(["git", "log", "--oneline", f"HEAD..origin/{_branch()}"],
                   cwd=BASE_DIR)
    if rc == 0 and out:
        print(f"\n{C.DIM}  новые коммиты:{C.RESET}")
        for line in out.splitlines()[:15]:
            print(f"    {C.CYAN}*{C.RESET} {line}")
    return True


def perform_update():
    """git fetch + reset --hard origin/<branch>; при отсутствии git — переклон."""
    print(f"\n{C.DIM}  загрузка обновления…{C.RESET}")
    if shutil.which("git"):
        rc, out = _run(["git", "fetch", "origin"], cwd=BASE_DIR, timeout=120)
        if rc != 0:
            print(f"  {C.RED}[x]{C.RESET} git fetch: {out}")
            return False
        br = _branch()
        rc, out = _run(["git", "reset", "--hard", f"origin/{br}"],
                       cwd=BASE_DIR, timeout=60)
        if rc != 0:
            print(f"  {C.RED}[x]{C.RESET} git reset: {out}")
            return False
        print(f"  {C.GREEN}[ok]{C.RESET} обновлено до {_short(_local_sha())} "
              f"(ветка {br})")
        print(f"  {C.DIM}  перезапустите систему: python3 cyberdogs.py{C.RESET}")
        return True
    print(f"  {C.RED}[x]{C.RESET} git не найден в PATH. Установите: "
          f"pkg install git")
    return False


def reinstall_clone():
    """Полная переустановка: удаление старой копии и свежий clone."""
    print(f"\n{C.YELLOW}[!]{C.RESET} ВНИМАНИЕ: текущая папка будет заменена "
          f"свежей копией репозитория.")
    print(f"     Ваши локальные изменения будут потеряны.")
    try:
        ans = input(f"{C.GREEN}  продолжить? введите YES: {C.RESET}").strip()
    except EOFError:
        return
    if ans != "YES":
        print(f"  {C.DIM}  отменено.{C.RESET}")
        return
    if not shutil.which("git"):
        print(f"  {C.RED}[x]{C.RESET} git не найден. Установите: pkg install git")
        pause()
        return
    parent = os.path.dirname(BASE_DIR)
    tmp = os.path.join(parent, "CyberDogs.new")
    print(f"{C.DIM}  клонирую в {tmp}…{C.RESET}")
    rc, out = _run(["git", "clone", REPO_URL, tmp], timeout=300)
    if rc != 0:
        print(f"  {C.RED}[x]{C.RESET} clone не удался: {out}")
        pause()
        return
    try:
        shutil.rmtree(BASE_DIR)
        os.rename(tmp, BASE_DIR)
        print(f"  {C.GREEN}[ok]{C.RESET} система переустановлена. "
              f"Запустите заново: cd CyberDogs && python3 cyberdogs.py")
    except Exception as e:
        print(f"  {C.RED}[x]{C.RESET} не удалось заменить папку: {e}")
        print(f"  {C.DIM}  свежая копия лежит в: {tmp}{C.RESET}")
    pause()


def update_menu():
    """Пункт 10 главного меню и шелл-команда update."""
    items = [
        ("1. Проверить наличие обновлений", _check_and_offer),
        ("2. Обновить автоматически (git pull)", perform_update),
        ("3. Полная переустановка (чистый clone)", reinstall_clone),
        ("4. Информация о версии и источнике", _show_info),
        ("01. ← Главное меню", None),
        ("0.  ← Назад", None),
    ]
    from core.ui import menu_loop
    menu_loop("ОБНОВЛЕНИЯ", items)


def _check_and_offer():
    """Проверка обновлений + автопредложение установить, если есть."""
    has = check_updates()
    if not has:
        pause()
        return
    try:
        ans = input(f"\n{C.GREEN}  найдено обновление — установить сейчас? (y/N): {C.RESET}").strip().lower()
    except EOFError:
        return
    if ans == "y":
        perform_update()
    pause()


def _show_info():
    clear()
    header("ОБНОВЛЕНИЯ · сведения")
    line = "─" * 46
    print(f"  {ACCENT}{line}{C.RESET}")
    print(f"  {C.CYAN}репозиторий{C.RESET} : {REPO_URL}")
    print(f"  {C.CYAN}каталог{C.RESET}     : {BASE_DIR}")
    print(f"  {C.CYAN}git{C.RESET}         : "
          + ("да" if _is_git_repo() else "нет (не git-копия)"))
    print(f"  {C.CYAN}локальный HEAD{C.RESET}: {_short(_local_sha())}")
    tok = load_token()
    print(f"  {C.CYAN}токен GitHub{C.RESET} : "
          + (f"задан ({tok[:8]}…)" if tok else "не задан"))
    if tok:
        print(f"  {C.DIM}  (env GITHUB_TOKEN или файл {TOKEN_FILE}){C.RESET}")
    print(f"  {ACCENT}{line}{C.RESET}")


if __name__ == "__main__":
    update_menu()
