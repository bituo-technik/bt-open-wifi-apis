[English](README.en.md)

# 体验工具 — 明文 BLE（Basic / Basic+，服务 A002）

协议与 [`docs/ble-plaintext/ble-plaintext-api.zh-CN.md`](../../docs/ble-plaintext/ble-plaintext-api.zh-CN.md) 一致；业务 JSON 见 [`docs/ble-common`](../../docs/ble-common/ble-business-api.zh-CN.md)。

| 文件 | 说明 |
|------|------|
| `web-ble-console.html` | Chrome / Edge 控制台（桌面 / 平板 / 手机） |
| `ble_plain_gui.py` | Windows 图形界面（重启后自动重连） |
| `command_help.py` / `help_en.txt` | 命令、缩写、错误码速查（中文 + 英文） |
| `requirements.txt` | `PyQt6`、`bleak` |

Lite / Pro（服务 `A003`）不要用这套，请用 [`../ble-secured`](../ble-secured/README.zh-CN.md)。

## 语言

两个工具都有 **中文 / English** 开关（网页：右上角按钮，记在 `localStorage`；Windows 图形界面：左上角下拉框）。JSON 命令名和设备 `msg` 保持英文。

## Windows 图形界面

```bat
cd tools\ble-plaintext
py -3 -m pip install -r requirements.txt
py -3 ble_plain_gui.py
```

## 网页

```bat
cd tools\ble-plaintext
py -3 -m http.server 8765
```

用 Chrome 或 Edge 打开 `http://127.0.0.1:8765/web-ble-console.html`。`file://` 经常拦下蓝牙，请用本地 HTTP 或 HTTPS。手机必须用 HTTPS 托管。
