# 体验工具 / Demo tools

两个 BLE 通道各有一套工具，协议与 `docs/` 完全一致。工具用来**先看清设备行为再写自己的 App**，也可以现场配网。

| 设备 | 服务 | 工具目录 | 文档 |
|------|------|----------|------|
| Basic / Basic+ | `0xA002`（明文） | [`ble-plaintext/`](ble-plaintext/) | [明文 BLE 接口说明](../docs/ble-plaintext/ble-plaintext-api.zh-CN.md) |
| Lite / Pro | `0xA003`（加密） | [`ble-secured/`](ble-secured/) | [加密 BLE 接口说明](../docs/ble-secured/ble-secured-api.zh-CN.md) |

不知道设备属于哪一种：扫描后看 GATT 服务，`A002` 用明文工具，`A003` 用加密工具。

业务 JSON（Wi-Fi、查询、MQTT、Modbus、UDP、OTA …）两个通道相同：[业务命令参考](../docs/ble-common/ble-business-api.zh-CN.md)。

| 想做的事 | 用什么 |
|----------|--------|
| 现场配网、手机上用（Android Chrome / Edge） | 网页（HTTPS 托管）：明文用 `web-ble-console.html`，加密用 `web-ble-secured-console.offline.html`（单文件） |
| Windows 上完整调试（含业务广播） | `ble_plain_gui.py` / `ble_secured_gui.py` |
| 改网页功能 / 让 AI 改 | 加密：`web-ble-secured-console.html`（分文件），改完运行 `bundle_offline_html.py` |
| 验证自己实现的加密算法 | `spec/ble-secured-test-vectors.json` + `scripts/check_test_vectors.*` |

注意：iOS Safari 没有 Web Bluetooth；Windows 上的 Chrome 通常不支持 `watchAdvertisements`（听业务广播请用 Windows 工具）。
