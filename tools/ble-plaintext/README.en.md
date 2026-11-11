[中文](README.zh-CN.md)

# Demo tools — plaintext BLE (Basic / Basic+, service A002)

The protocol matches [`docs/ble-plaintext/ble-plaintext-api.en.md`](../../docs/ble-plaintext/ble-plaintext-api.en.md). Business JSON follows [`docs/ble-common`](../../docs/ble-common/ble-business-api.en.md).

| File | Description |
|------|-------------|
| `web-ble-console.html` | Chrome / Edge console (desktop / tablet / phone) |
| `ble_plain_gui.py` | Windows GUI (auto-reconnect after restart) |
| `command_help.py` / `help_en.txt` | Command, abbreviation, and error cheat sheet (Chinese and English) |
| `requirements.txt` | `PyQt6`, `bleak` |

Do not use this folder for Lite / Pro (service `A003`). Use [`../ble-secured`](../ble-secured/README.en.md).

## Language

Both tools have a **中文 / English** switch (web: buttons at the top right, saved in `localStorage`; Windows GUI: combo box at the top left). JSON command names and device `msg` strings stay English.

## Windows GUI

```bat
cd tools\ble-plaintext
py -3 -m pip install -r requirements.txt
py -3 ble_plain_gui.py
```

## Web page

```bat
cd tools\ble-plaintext
py -3 -m http.server 8765
```

Open `http://127.0.0.1:8765/web-ble-console.html` in Chrome or Edge. `file://` often blocks Bluetooth; use local HTTP or HTTPS. Phones need an HTTPS host.
