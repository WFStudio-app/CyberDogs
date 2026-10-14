#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core.stopwatch — управляемые скан-процессы для CyberDogs.

Позволяет ОСТАНОВИТЬ любое сканирование по нажатию ENTER:
  * скан крутится в фоновом потоке;
  * отдельный «наблюдатель» ждёт нажатия Enter (или Ctrl+C);
  * флаг Event останавливает рабочий поток, и он завершает работу;
  * после остановки показывается итог, затем через 5 секунд
    автоматически возвращается главное меню.
"""

import sys
import threading
import time

try:
    from core.ui import C
except ImportError:
    from core.ui import C


def _read_line_nonblocking():
    """Прочитать одну строку из stdin, не блокируя рабочий поток."""
    try:
        return sys.stdin.readline()
    except Exception:
        return ""


def _arm_ctrl_c_handler():
    """Ctrl+C тоже останавливает скан (без выхода из программы)."""
    import signal

    def _handler(signum, frame):
        raise KeyboardInterrupt

    try:
        old = signal.signal(signal.SIGINT, _handler)
        return old
    except (ValueError, OSError):
        return None


def run_with_stop(worker, title="Сканирование", summary_fn=None):
    """
    Запустить worker(stop_event, state) с возможностью остановки по ENTER.

    worker(stop_event, state):
        stop_event — threading.Event, поток обязан периодически проверять;
        state      — dict для накопления результатов/итогов.

    summary_fn(state) — необязательная функция печати итога после остановки.
    """
    stop_event = threading.Event()
    state = {}
    result_holder = {"value": None, "error": None}

    def _work():
        try:
            result_holder["value"] = worker(stop_event, state)
        except Exception as e:  # noqa: BLE001
            result_holder["error"] = e

    thread = threading.Thread(target=_work, daemon=True)
    thread.start()

    print(f"{C.DIM}  ⏹  Нажмите ENTER (или Ctrl+C), чтобы остановить {title.lower()}.{C.RESET}\n")

    import signal
    is_main = threading.current_thread() is threading.main_thread()
    old_handler = _arm_ctrl_c_handler() if is_main else None

    stopped_by_user = False
    try:
        while thread.is_alive():
            if not sys.stdin.isatty():
                # Неинтерактивный запуск (тесты/пайп) — просто ждём завершения
                thread.join()
                break
            ch = _read_line_nonblocking()
            if ch == "\n" or ch == "\r\n" or ch == "":
                # Enter нажат либо stdin закрыт → остановка
                stopped_by_user = True
                stop_event.set()
                break
            time.sleep(0.05)
    except KeyboardInterrupt:
        stopped_by_user = True
        stop_event.set()
    finally:
        if is_main and old_handler is not None:
            signal.signal(signal.SIGINT, old_handler)

    thread.join(timeout=10)

    if result_holder["error"]:
        print(f"{C.RED}  ✖ Ошибка во время работы: {result_holder['error']}{C.RESET}")

    if stopped_by_user:
        print(f"\n{C.YELLOW}  ⏹  {title} остановлено пользователем.{C.RESET}")

    if summary_fn is not None:
        try:
            summary_fn(state, result_holder["value"], stopped_by_user)
        except Exception:
            pass

    # ── автовозврат в главное меню через 5 секунд ──
    print(f"\n{C.CYAN}  ↩  Главное меню через 5 секунд…{C.RESET}")
    for i in range(5, 0, -1):
        sys.stdout.write(f"\r{C.DIM}    Осталось: {i} с   {C.RESET}")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write("\r" + " " * 40 + "\r")
    sys.stdout.flush()


def wait_or_stop(stop_event, seconds):
    """«Спать» до seconds, но проснуться сразу при остановке. True = не остановлен."""
    return not stop_event.wait(seconds)
