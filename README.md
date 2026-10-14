# 🐶 CyberDogs

**CyberDogs** — мультиинструментальный сетевой комбайн для **Termux** в стиле **Flipper Zero**.
Интерактивное меню в терминале телефона: сканируй сети, сигналы и Wi-Fi вокруг себя.

> ⚠️ Проект предназначен только для образовательных целей и легального
> тестирования собственных сетей. Не используйте его против чужих устройств.

---

## 📋 Возможности (текущая версия v0.1.0)

Главное меню:

```
1. Сканирование
0. Выход
```

Раздел **«Сканирование»**:

| № | Функция | Описание |
|---|---------|----------|
| 1 | Сканирование сетей вокруг | Определяет локальные подсети устройства и обходит `/24` через ping, показывая активные хосты и их имена |
| 2 | Сканирование сигналов | Обзор радиосигналов: Bluetooth-адаптер и устройства (Termux:API), справка по доступным радиомодулям |
| 3 | Сканирование Wi-Fi вокруг | Список окружающих Wi-Fi сетей: SSID, BSSID, уровень сигнала, защита, канал (nmcli → termux-api → iw; без root — данные о текущем подключении) |

В планах: пинометр портов, fingerprint-сканер, работа с Sub-GHz/NFC через внешнее железо, плагины.

---

## 🚀 Установка и запуск (Termux)

### 1. Установите Termux
Лучше из **F-Droid** (из Google Play — устаревшая версия):
👉 https://f-droid.org/packages/com.termux/

### 2. Скачайте CyberDogs

```bash
pkg update -y && pkg install -y git python
git clone https://github.com/WFStudio-app/CyberDogs.git
cd CyberDogs
```

### 3. Установите зависимости

```bash
bash install.sh
```

или вручную:

```bash
pkg install -y python nmap iproute2 termux-api
```

### 4. (Рекомендуется) Termux:API
Для Bluetooth/Wi-Fi-сканирования установите приложение **Termux:API**
(той же подписи, что и Termux — F-Droid / GitHub) и выдайте разрешения Android.

### 5. Запуск

```bash
python3 cyberdogs.py
```

Быстрая строка «всё в одном»:

```bash
pkg update -y && pkg install -y git python && git clone https://github.com/WFStudio-app/CyberDogs.git && cd CyberDogs && bash install.sh && python3 cyberdogs.py
```

---

## 🗂 Структура проекта

```
CyberDogs/
├── cyberdogs.py            # точка входа, меню
├── install.sh              # установка зависимостей для Termux
├── core/
│   └── ui.py               # баннер, цвета, меню-движок
└── modules/
    └── scan/
        ├── networks.py     # 1. сканирование сетей (ping /24)
        ├── signals.py      # 2. сканирование сигналов (BT / радио)
        └── wifi.py         # 3. сканирование Wi-Fi (nmcli/termux-api/iw)
```

Добавлять новые функции просто: создайте модуль в `modules/…`
и зарегистрируйте пункт меню в `cyberdogs.py`.

---

## 📱 Обновление

```bash
cd CyberDogs && git pull
```

---

## License
MIT
