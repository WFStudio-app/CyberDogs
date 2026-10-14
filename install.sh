#!/usr/bin/env bash
# CyberDogs — установка зависимостей для Termux
# Запуск:  bash install.sh

set -e

echo "[*] Обновляю списки пакетов…"
pkg update -y

echo "[*] Базовые пакеты…"
pkg install -y python git which

echo "[*] Сетевые утилиты (для сканирования сетей/Wi-Fi)…"
pkg install -y nmap iproute2 termux-api || true

echo "[*] Python-библиотеки для раздела «Подбор / Взлом»…"
pip install --upgrade pywifi paramiko || true

echo ""
echo "[✔] Готово! Не забудьте:"
echo "    1) Установить приложение Termux:API (из F-Droid / GitHub)"
echo "       — оно нужно для Bluetooth/Wi-Fi-сканирования."
echo "    2) Выдать Termux разрешения в Android."
echo ""
echo "[*] Запуск:  python3 cyberdogs.py"
