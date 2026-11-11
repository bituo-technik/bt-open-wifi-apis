[English](README.en.md)

# 体验工具 — 加密 BLE（Lite / Pro，服务 A003）

协议与 [`docs/ble-secured/ble-secured-api.zh-CN.md`](../../docs/ble-secured/ble-secured-api.zh-CN.md) 一致；业务 JSON 见 [`docs/ble-common`](../../docs/ble-common/ble-business-api.zh-CN.md)。

| 文件 | 说明 |
|------|------|
| `ble_secured_gui.py` | **Windows 图形界面**：完整 EC J-PAKE 握手 + 加密业务命令 + 业务广播监听 |
| `ble_crypto_core.py` | Python 参考实现：握手、AES-CCM 信封、PIN / 11 位配网码、广播解密 |
| `web-ble-secured-console.html` | **网页开发源**：分文件，Chrome / Edge，完整 EC J-PAKE + AES-CCM |
| `web-ble-secured-console.offline.html` | **给客户的构建**：一个自包含文件（约 108 KB），可放到任意 HTTPS 静态托管。**生成物，不要手改** |
| `bundle_offline_html.py` | 从分文件源重新生成离线 HTML（需要 Node.js 的 `npx esbuild`） |
| `ble_secured_crypto.js` | JS 参考实现（内置 `@noble` + 本地 AES-CCM），与 `ble_crypto_core.py` 对应 |
| `help_text.js` / `command_help.py` | 网页 / Windows 图形界面的速查文本（中文 + 英文），两边手工保持同步 |
| `vendor/` | 离线 JS 密码学依赖（运行时不访问 CDN） |
| `requirements.txt` | `PyQt6`、`bleak`、`cryptography`、`ecdsa` |

用已知答案测试向量交叉核对两份参考实现：

```bat
py -3 scripts\check_test_vectors.py
node scripts\check_test_vectors.mjs
```

## 适用固件

| 分支 | BLE | 本目录 |
|------|-----|--------|
| **Lite / Pro** | 加密（`0xA003`） | **用这套** |
| Basic / Basic+ | 明文（`0xA002`） | 不用，请用 [`../ble-plaintext`](../ble-plaintext/README.zh-CN.md) |

两套 UUID 不要混用。设备只暴露 `A002` 时，用明文工具。

## Windows 图形界面

```bat
cd tools\ble-secured
py -3 -m pip install -r requirements.txt
py -3 ble_secured_gui.py
```

需要蓝牙适配器，以及电表上的**配网码**：二维码下面的 11 位数字，或 8 位 PIN（SN 通常从广播名 `MODEL-SN` 推断）。语言：左上角下拉框。

`restart` / `mqtr` / `reset` 之后打开自动重连。若 LTK 已经落盘（Wi-Fi 至少成功关联过一次），工具用本地缓存 `ble_crypto_client_cache.json` 走 `ble-crypto-session-nonce` 恢复会话（**已在 `.gitignore` 中，不要提交**）。

## 网页

配网路径与 Windows 图形界面对齐：Web Bluetooth 选择器、完整 EC J-PAKE（或用 `localStorage` 里的 LTK 做 `session-nonce` 恢复）、加密的 Wi-Fi / 快捷命令 / Modbus 485（校验位 + 停止位）/ 自定义 JSON / 读 `C314`、GATT 断线后自动重连并恢复会话，以及中英速查。

### 两份页面

| 给谁 | 文件 |
|------|------|
| 开发者 / 改功能的 AI | `web-ble-secured-console.html` + `ble_secured_crypto.js` + `help_text.js` + `vendor/` |
| 客户（Cloudflare R2 / 阿里云 OSS / 任意 HTTPS 托管） | **只给** `web-ble-secured-console.offline.html` |

改过分文件页面、密码学代码或帮助文本之后，重新生成客户文件：

```bat
cd tools\ble-secured
py -3 bundle_offline_html.py
```

离线文件内嵌 J-PAKE / AES-CCM（不走 jsDelivr），不再加载额外 `.js`，也不引用 Google Fonts，首屏不等字体服务器。请用 HTTPS（或 `http://127.0.0.1`）托管。Web Bluetooth 需要安全上下文；从磁盘打开（`file://`）没有验证过，不要依赖这种方式。

### 运行开发版

```bat
cd tools\ble-secured
py -3 -m http.server 8765
```

用 **Chrome 或 Edge** 打开 `http://127.0.0.1:8765/web-ble-secured-console.html`（`file://` 加载不了开发版的 ES module）。

**Windows 上设备列表是空的：** 保持勾选「显示附近全部 BLE」（默认）。名称前缀过滤经常匹配不到，因为 Windows / Chrome 不一定暴露广播名。先断开 Python 图形界面和手机，已连接的电表会停止广播。

**已连接但还没进入加密（`step=2`）：** 把已知的 32 位十六进制 LTK 贴进页面，或把电表恢复出厂以清掉 LTK，再用配网码做完整 J-PAKE。**`step=3` 且本地没有会话：** 断开再连（见文档「常见陷阱」）。排查 GATT 掉线时先关掉自动重连。

**调试密钥：** 勾选 Debug，面板里会显示 LTK / session_key / broadcast_key（同时写入日志）。

**业务广播：** 完整 J-PAKE 之后才有 `broadcast_key`，然后用广播页。网页需要 `watchAdvertisements`，Windows 上的 Chrome 通常没有。请用 Windows 图形界面，它用 bleak 扫描并实时解密长包。

**手机：** Android 上的 Chrome / Edge 走 HTTPS 可用；iOS Safari 没有 Web Bluetooth。

## 安全说明

- 示例里不要放真实客户 PIN，用占位值（`12345678`、`00852607537`）。
- 只有打开 **Debug** 才显示密钥；密钥按机密处理。
- 握手成功后，浏览器 `localStorage` 可能按同一 SN 记住 LTK。恢复出厂的演示做完后，清掉站点数据。
