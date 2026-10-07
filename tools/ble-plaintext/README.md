# 体验工具 / Demo tools — 明文 BLE（Basic / Basic+，服务 A002）

Protocol matches [`docs/ble-plaintext/ble-plaintext-api.zh-CN.md`](../../docs/ble-plaintext/ble-plaintext-api.zh-CN.md) / [`.en.md`](../../docs/ble-plaintext/ble-plaintext-api.en.md); business JSON follows [`docs/ble-common`](../../docs/ble-common/ble-business-api.zh-CN.md).

| File | Description |
|------|-------------|
| `web-ble-console.html` | Chrome / Edge console (desktop / tablet / phone) |
| `ble_plain_gui.py` | Windows GUI (auto-reconnect after restart) |
| `command_help.py` / `help_en.txt` | Command / abbreviation / error cheat sheet (zh + en) |
| `requirements.txt` | `PyQt6`, `bleak` |

Not for Lite / Pro (service `A003`) — use [`../ble-secured`](../ble-secured/).

## Language / 语言

Both tools have a **中文 / English** switch (web: top-right buttons, saved in `localStorage`; Windows GUI: combo box at the top left). JSON command names and device `msg` strings stay English.

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

Open `http://127.0.0.1:8765/web-ble-console.html` in Chrome or Edge. (`file://` often blocks Bluetooth; use local HTTP or HTTPS. Phones need an HTTPS host.)
