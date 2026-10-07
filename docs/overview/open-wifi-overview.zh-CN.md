# SPM / SDM Open Wi-Fi API 总览

> 状态：初版 ｜ 适用：SPM / SDM Open Wi-Fi 系列（ESP32-8685 / C6）｜ 对应固件源码快照：SXM_EW_C3 `5.1.16`、SDMV2_EW_C3 `1.2.12`、SDMV2_EW_C6 `3.1.19`

本页是整套 API 的入口：先判断你手里设备属于哪个**固件分支**，再按用途选**通信通道**，最后进入对应通道文档。

## 1. 简介

Open Wi-Fi 系列电表提供本地与云端两类通信方式：

- **本地局域网**：HTTP / HTTPS、WebSocket、UDP 上报、Modbus TCP、mDNS 发现。
- **云端**：MQTT / MQTTS（也可作为私有部署的数据通道）。
- **手机近场**：BLE（明文或加密），用于配网和本地控制。

所有通道共用同一套**业务命令**（`cmd`）和同一种应答结构 `ok / msg / event / d`。命令只在一处维护：[BLE 业务命令参考](../ble-common/ble-business-api.zh-CN.md)。各通道文档只写"怎么连、怎么封装、有什么限制"。

## 2. 固件分支与硬件对应

产品线按固件分支区分，**不同分支支持的通道不同**，集成前请先确认。

| 固件分支 | Basic (8685) | Basic+ (8685) | Lite (8685) | Pro (C6) |
|----------|--------------|---------------|-------------|----------|
| 目标硬件 | SPM / SDM | SDM01 | SPM / SDM | SDM01 Gen2 |
| 最新版本 | B_5.1.14 / B_6.1.7 | BPlus_1.2.8 / BPlus_2.2.4 | Lite_5.1.11 / Lite_6.1.4 | Pro_V3.1.11 |
| 核心特性 | 明文 BLE，明文 Wi-Fi | 明文 BLE，Wi-Fi 可加密 | 加密 BLE，明文 Wi-Fi | 加密 BLE，Wi-Fi 可加密 |
| Wi-Fi 发射 | 0 dB | 13 dB | 0 dB | 13 dB |
| 生命周期 | NRND | NRND | Active | Active |

说明：

1. `B_6.1.7` 用于带 UART 外部烧录脚的 SDM01 Combo；`B_5.1.14` 用于 SPM01、SPM02、带 JTAG 烧录脚的 SDM01 Combo 和 SDM02。
2. Basic+ 原称 Gen1 的 EV / PV 版，已由 SDM01 Gen2 取代；同一时刻最多 **1** 路 TLS 连接。
3. Lite 的 BLE 加密覆盖配网和数据广播；Wi-Fi 侧只有 MQTT 支持 TLS 1.2 / 1.3，HTTP、Modbus TCP、WebSocket 都没有 TLS。
4. Pro 的 BLE 加密覆盖配网和数据广播；Wi-Fi 侧同一时刻最多 **2** 路 TLS 连接。

> 本仓库的固件源码用 `PRODUCT_MODEL` 和 `BLE_APP_CRYPTO_ENABLE` 编译出不同分支：SXM（C3）未开启加密为 Basic，开启为 Lite；SDMV2 C3 未开启加密为 Basic+；SDMV2 C6 开启加密为 Pro。这是根据源码和发布页版本号做的对应，不是官方对照表。

### 2.1 通过什么判断分支

| 想知道 | 怎么读 |
|--------|--------|
| 是明文还是加密 BLE | 扫描到的服务 UUID：`A002` 明文，`A003` 加密 |
| 固件版本 | MQTT `mdata.fwVer`、遥测里的 `FWVersion`、HTTP `/snapshot`、Modbus 寄存器 997 |
| 当前开了哪些通道 | `{"cmd":"getFunctionMap"}`，位定义见 [业务命令参考附录 B](../ble-common/ble-business-api.zh-CN.md#附录-b-functionmap-位) |

## 3. 通道能力矩阵

| 通道 | Basic | Basic+ | Lite | Pro |
|------|:-----:|:------:|:----:|:---:|
| BLE 明文（`A002`） | ✅ | ✅ | ❌ | ❌ |
| BLE 加密（`A003`） | ❌ | ❌ | ✅ | ✅ |
| MQTT（1883） | ✅ | ✅ | ✅ | ✅ |
| MQTTS（TLS） | ✅ | ✅ | ✅ | ✅ |
| HTTP（80，明文） | ✅ 默认开 | ✅ 默认开 | ✅ 默认关 | ✅ 默认关 |
| HTTPS（443） | ❌ | ❌ | ❌ | ✅ |
| Modbus TCP（502） | ✅ | ✅ | ✅ | ✅ |
| Modbus TCP over TLS | ❌ | ✅ | ❌ | ✅ |
| WebSocket（81） | ✅ | ✅ | ✅ | ✅ |
| WebSocket over TLS（WSS） | ❌ | ✅ | ❌ | ✅ |
| UDP 上报（明文） | ✅ | ✅ | ✅ | ✅ |
| UDP 上报（AES-CCM 加密） | ❌ | ❌ | ✅ | ✅ |
| mDNS 发现 | ✅ | ✅ | ✅ | ✅ |

HTTP 默认状态依据固件源码：非加密构建（Basic、Basic+）每次开机都会把 HTTP 位置 1；加密构建（Lite、Pro）默认关闭，要通过 BLE `enablehttp` 打开。Pro 开启 HTTPS 后，80 端口的业务接口返回 403，见 [HTTP 文档](../http/http-api.zh-CN.md#4-80-端口的访问策略)。

上面的矩阵是线上已发布的版本。**UDP AES-CCM** 一项与固件源码不同：加密报文只存在于 SDMV2 加密构建（Pro），并且只在 HTTPS 打开时生效；SXM 加密构建（Lite）始终发送明文。请以实际部署的版本为准，细节见 [UDP 第 4 节](../udp/udp-api.zh-CN.md#4-aes-ccm-加密报文)。

### 3.1 TLS 连接数限制

设备内存有限，同一时刻能同时握手的 TLS 服务数量固定：Basic+ **1** 路，Pro **2** 路。可能占用 TLS 槽的服务有：MQTTS、HTTPS（443）、WSS（81）、Modbus TLS（502）。

- 打开的 TLS 服务多于槽数时，按优先级 **MQTTS > HTTPS > WSS > Modbus TLS** 实际启动。
- 没轮到的服务：MQTTS 仍占槽位，HTTPS 不监听 443，WSS 和 Modbus 回落为明文。
- 接受新 TLS 连接前设备先检查全局槽位，不足就不握手。
- 集成时请复用已有连接，不要每次轮询新建 TLS 会话。

## 4. 怎么选通道

| 你要做的事 | 推荐通道 | 文档 |
|------------|----------|------|
| 云端持续收数据、下发命令 | MQTT / MQTTS | [MQTT](../mqtt/mqtt-api.zh-CN.md) |
| 局域网网关按需拉取、改配置 | HTTP（Pro 用 HTTPS） | [HTTP](../http/http-api.zh-CN.md) |
| 本地中枢（如 Home Assistant）收实时数据流 | WebSocket | [WebSocket](../websocket/websocket-api.zh-CN.md) |
| 光伏防逆流、动态负载均衡等低延迟读数 | UDP 上报，或 Modbus TCP | [UDP](../udp/udp-api.zh-CN.md)、[Modbus TCP](../modbus-tcp/modbus-tcp-api.zh-CN.md) |
| PLC、工业网关、EMS | Modbus TCP | [Modbus TCP](../modbus-tcp/modbus-tcp-api.zh-CN.md) |
| 自动发现局域网里的电表 | mDNS | [mDNS](../mdns/mdns-discovery.zh-CN.md) |
| 手机 App 配网、近场控制 | BLE | [BLE 明文](../ble-plaintext/ble-plaintext-api.zh-CN.md)、[BLE 加密](../ble-secured/ble-secured-api.zh-CN.md) |

## 5. 通用约定

### 5.1 命令与应答

- 命令是 JSON，`cmd` 为命令名；MQTT、WebSocket、HTTP `/save-config`、BLE 的命令名和字段**语义一致**，见 [BLE 业务命令参考](../ble-common/ble-business-api.zh-CN.md)。
- 应答统一为 `{"ok":true,"msg":"","event":"<命令名>","d":{...}}`；失败时多一个整数 `code`，成功时**没有** `code`。
- 除 BLE 外，其他通道的命令**不需要** `pass` / `auth` 握手。HTTP 在设置了 Web 密码后需要 token，见 [HTTP 文档](../http/http-api.zh-CN.md#2-会话与鉴权)。
- 单条入站 JSON 最长 **1024** 字节，超长会被拒绝或静默丢弃。

### 5.2 遥测数据

同一份遥测 JSON 同时出现在 MQTT `/data`、HTTP `/data`、WebSocket 推送、UDP 报文和 `/snapshot.data` 里，字段只在一处维护：[遥测数据格式](../reference/telemetry-payload.zh-CN.md)。

### 5.3 错误码

失败应答的 `code` 按通道分段：BLE 1000 段、HTTP 2000 段、MQTT 3000 段、WebSocket 4000 段。见 [错误码参考](../reference/error-codes.zh-CN.md)。

## 6. 文档目录

| 文档 | 内容 |
|------|------|
| [遥测数据格式](../reference/telemetry-payload.zh-CN.md) | 各型号遥测字段、`TP` 含义、通用格式 |
| [错误码参考](../reference/error-codes.zh-CN.md) | 跨通道 `code` 分段、固定错误码、配置子码 |
| [MQTT](../mqtt/mqtt-api.zh-CN.md) | 主题、数据上报、命令、MQTTS 配置 |
| [HTTP / HTTPS](../http/http-api.zh-CN.md) | 登录、接口清单、POST 封装差异 |
| [WebSocket](../websocket/websocket-api.zh-CN.md) | 连接、推送周期、心跳 |
| [UDP 上报](../udp/udp-api.zh-CN.md) | 目标配置、报文、AES-CCM 加密报文 |
| [Modbus TCP](../modbus-tcp/modbus-tcp-api.zh-CN.md) | 寄存器表、控制寄存器、连接注意事项 |
| [mDNS](../mdns/mdns-discovery.zh-CN.md) | 主机名规则、验证方法 |
| [BLE 业务命令参考](../ble-common/ble-business-api.zh-CN.md) | 全部命令的唯一说明 |
| [BLE 明文](../ble-plaintext/ble-plaintext-api.zh-CN.md) / [BLE 加密](../ble-secured/ble-secured-api.zh-CN.md) | 两种 BLE 传输层 |

给 AI 用的整合单文件见 [`AGENTS.md`](../../AGENTS.md)；机器可读的接口清单在 [`spec/`](../../spec/)。
