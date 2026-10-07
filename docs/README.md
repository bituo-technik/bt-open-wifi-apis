# 文档阅读路径 / Reading paths

## 我要通过局域网 / 云端读电表数据（Wi-Fi 通道）

1. 先读**总览**，确认你的设备属于哪个固件分支、有哪些通道可用：[overview/open-wifi-overview.zh-CN.md](overview/open-wifi-overview.zh-CN.md) · [EN](overview/open-wifi-overview.en.md)。
2. 按场景选通道（总览第 4 节有对照表）：
   - 找设备 IP：[mDNS 发现](mdns/mdns-discovery.zh-CN.md) · [EN](mdns/mdns-discovery.en.md)
   - PLC / 工业网关 / EMS 轮询：[Modbus TCP](modbus-tcp/modbus-tcp-api.zh-CN.md) · [EN](modbus-tcp/modbus-tcp-api.en.md)
   - 脚本、网关、配置设备：[HTTP / HTTPS](http/http-api.zh-CN.md) · [EN](http/http-api.en.md)
   - 本地实时推送：[WebSocket](websocket/websocket-api.zh-CN.md) · [EN](websocket/websocket-api.en.md)
   - 云端 / 自建 Broker：[MQTT](mqtt/mqtt-api.zh-CN.md) · [EN](mqtt/mqtt-api.en.md)
   - 高频单向读数（光伏限发、动态负载均衡）：[UDP](udp/udp-api.zh-CN.md) · [EN](udp/udp-api.en.md)
3. 数据字段：[遥测数据格式](reference/telemetry-payload.zh-CN.md) · [EN](reference/telemetry-payload.en.md)；失败时：[错误码](reference/error-codes.zh-CN.md) · [EN](reference/error-codes.en.md)。
4. 要发配置命令（HTTP / MQTT / WebSocket 都用同一套 `cmd`）：[业务命令参考](ble-common/ble-business-api.zh-CN.md) · [EN](ble-common/ble-business-api.en.md)。
5. 命令行工具与假电表：[`tools/lan`](../tools/lan/README.md)。

## 我要用 BLE 给电表配 Wi-Fi，或读电参、配置设备

1. 判断设备：扫描后看 GATT 服务。**`A002` = 明文（Basic / Basic+）**，**`A003` = 加密（Lite / Pro）**。
2. 读对应的**传输层**文档（怎么连、怎么解锁 / 握手、怎么重连）：
   - 明文：[ble-plaintext/ble-plaintext-api.zh-CN.md](ble-plaintext/ble-plaintext-api.zh-CN.md) · [EN](ble-plaintext/ble-plaintext-api.en.md)
   - 加密：[ble-secured/ble-secured-api.zh-CN.md](ble-secured/ble-secured-api.zh-CN.md) · [EN](ble-secured/ble-secured-api.en.md)
3. 读**业务层**（发什么命令、读什么字段，所有通道通用）：[ble-common/ble-business-api.zh-CN.md](ble-common/ble-business-api.zh-CN.md) · [EN](ble-common/ble-business-api.en.md)
4. 只有实现加密通道时才需要：[协议权威参考](ble-secured/crypto-protocol.zh-CN.md) · [EN](ble-secured/crypto-protocol.en.md)（J-PAKE / ZKP 二进制布局、广播厂商数据）。

## 我要把文档交给 AI

运行 `py -3 scripts/build_bundles.py`，把 `dist/` 里对应通道的**单个合集文件**交给 AI（见 [`AGENTS.md`](../AGENTS.md)）：

| 要做什么 | 交给 AI 的文件 |
|----------|----------------|
| Modbus TCP 集成 | `dist/modbus-tcp.complete.zh-CN.md`（或 `.en.md`） |
| HTTP / WebSocket / MQTT 集成 | `dist/http.complete.*`、`dist/websocket.complete.*`、`dist/mqtt.complete.*`（已含业务命令、遥测格式、错误码） |
| UDP 接收端 | `dist/udp.complete.*` |
| 整个 Wi-Fi 侧 | `dist/open-wifi-all.complete.*` |
| BLE 明文 / 加密 | `dist/ble-plaintext.complete.*` / `dist/ble-secured.complete.*` |

## 文档地图

| 文档 | 内容 | 维护规则 |
|------|------|----------|
| `overview/open-wifi-overview.*` | 固件分支、通道能力矩阵、TLS 槽位限制、选通道 | 入口页；通道变化时先改这里 |
| `mdns/` `modbus-tcp/` `http/` `websocket/` `mqtt/` `udp/` | 各 Wi-Fi 通道：怎么连、报文怎么包、限制、示例、排错 | 只写该通道专有内容，命令与字段链接到共用文档 |
| `reference/telemetry-payload.*` | 遥测 JSON 字段（MQTT / HTTP / WebSocket / UDP 共用） | **唯一一份** |
| `reference/error-codes.*` | 统一错误码（`code`、通道基数、子码） | **唯一一份**，与 `spec/error-codes.json` 同步 |
| `ble-common/ble-business-api.*` | 业务命令、字段、应答、附录（functionMap 位 / model 短键） | **唯一一份**，所有通道共用 |
| `ble-plaintext/ble-plaintext-api.*` | 明文 BLE 传输层：UUID、解锁（`pass`）、请求 / 应答匹配、重连、MTU | 只写明文通道专有内容 |
| `ble-secured/ble-secured-api.*` | 加密 BLE 传输层：UUID、认证材料、`step`、密钥派生摘要、信封、重连 | 只写加密通道专有内容 |
| `ble-secured/crypto-protocol.*` | 加密协议权威参考（固件团队提供） | 与上一份冲突时以它为准 |

文档约定：命令名、字段名、设备 `msg` 保持英文原样；每份文档都有 `zh-CN` 与 `en` 两个版本，章节编号一一对应；每份通道文档开头的"依据"一行写明核对过的固件版本。
