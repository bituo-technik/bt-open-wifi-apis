# MQTT API

> 状态：初版 ｜ 适用：SPM / SDM Open Wi-Fi 全部分支（TLS 能力见 [概览](../overview/open-wifi-overview.zh-CN.md#3-通道能力矩阵)） ｜ 依据：固件源码 SXM_EW_C3 `5.1.16`、SDMV2 `1.2.12` / `3.1.19`，以及线上 MQTT API Reference

电表可以连接你自己的 MQTT Broker：周期性发布遥测数据，订阅一个命令主题，执行后把应答发布到另一个主题。命令和 BLE、HTTP、WebSocket 是同一套，本页只写 MQTT 自己的部分：主题、连接行为、旧版命令和 MQTTS 配置。

## 1. 概述

- 电表是 MQTT **客户端**，Broker 需要你自己准备。
- 命令和应答的结构见[业务命令参考](../ble-common/ble-business-api.zh-CN.md)；遥测数据的字段见[遥测数据](../reference/telemetry-payload.zh-CN.md)；错误码见[错误码](../reference/error-codes.zh-CN.md)。
- 命令的入站 JSON 不能超过 **1024 字节**。超长或解析失败的消息会被直接丢弃，**没有任何应答**。
- 出厂时没有可用的 Broker 配置。用 BLE 命令 `mqtt` 或 Web 页面写入 Broker 地址后，设备才会连接。
- 新版固件的命令应答是统一的 `ok/msg/event/d` 结构，`seq` 字段已废弃；旧版命令仍然被识别，格式见 [5.3 节](#53-旧版命令)。

## 2. 主题

默认主题是 `{型号}/{序列号}/{后缀}`，序列号是 12 位大写十六进制。

| 后缀 | 方向 | 内容 | QoS | Retain |
|------|------|------|-----|--------|
| `/data` | 设备 → 服务器 | 周期遥测 | 0 | 否 |
| `/cmd` | 服务器 → 设备 | 命令 | 0 | 否 |
| `/cdata` | 设备 → 服务器 | 命令应答 | 0 | 否 |
| `/mdata` | 设备 → 服务器 | 设备元数据，每次连上 Broker 后发布 | 0 | **是** |

示例（型号 `SPM02`，序列号 `AABBCCDDEEFF`）：`SPM02/AABBCCDDEEFF/data`、`SPM02/AABBCCDDEEFF/cmd`。

要点：

- 设备订阅 `/cmd` 时用 QoS 0，所以 Broker 向设备投递也是 QoS 0。服务器发布命令时用 QoS 1 也可以，只是到设备这一段不会重传。
- 型号来自设备（如 `SPM01`、`SPM02`、`SDM01_1PN`、`SDM01_3PN`、`SDM02`），不同批次的型号字符串以设备 `/mdata` 或 `model` 应答为准。
- 4 个主题都可以改成自己的。用 `topic1`（`topic_post`、`topic_set`）和 `topic2`（`topic_response`、`topic_metadata`），每个主题最长 63 个字符。改完后重启才会重新订阅。当前值可用 `mqttdata` 读取，字段 `TP/TC/TR/TM` 依次是 `/data`、`/cmd`、`/cdata`、`/mdata` 的完整主题。
- 部分定制固件使用不同的主题前缀，**以 `mqttdata` 的返回为准**，不要自己拼。
- 设备没有设置遗嘱（Last Will）。判断离线请看 `/data` 是否还在更新（用 `Post` 计数和 `Time`）。

## 3. 遥测数据（`/data`）

设备按 MQTT 上报周期向 `/data` 发布一条 JSON。字段、各型号差异和示例都在[遥测数据](../reference/telemetry-payload.zh-CN.md)，这里只说 MQTT 特有的部分：

- 周期由 `mqtt` 命令的第 5 段设置（单位**秒**，最小 1 秒）。`model` 应答里的 `MI` 是**毫秒**。源码里的出厂默认是 5 秒；线上文档写的是 30 秒，请以设备上读到的 `MI` 为准。
- 只有设备已连上 Broker 时才发布；断线期间的数据**不会补发**。
- `commonmode` 打开后，`/data` 改发通用格式，见遥测文档第 6 节。

## 4. 元数据（`/mdata`）

每次连上 Broker（包括重连）后，设备向 `/mdata` 发布一条 Retain 消息，新订阅者能立刻拿到。

```json
{
  "product": "EnergySensor-SPM01-AABBCCDDEEFF",
  "Serialnumber": "AABBCCDDEEFF",
  "fwVer": "5.1.16",
  "wifiname": "MyRouter"
}
```

| 字段 | 说明 |
|------|------|
| `product` | 产品名，一般是 `EnergySensor-型号-序列号` |
| `Serialnumber` | 序列号 |
| `fwVer` | Wi-Fi 模块固件版本 |
| `wifiname` | 当前连接的路由器 SSID（部分固件没有这个字段） |

## 5. 命令与应答

### 5.1 消息格式

向 `/cmd` 发布一个 JSON 对象，至少有 `cmd`：

```json
{"cmd":"location"}
```

设备把应答发布到 `/cdata`：

```json
{"ok":true,"msg":"location received","event":"location"}
```

| 字段 | 说明 |
|------|------|
| `ok` | 成功为 `true` |
| `msg` | 结果说明或错误原文 |
| `event` | 回显命令名，用它对应请求和应答 |
| `d` | 可选，返回的数据 |
| `code` | 只在失败时出现，见[错误码](../reference/error-codes.zh-CN.md)（MQTT 为 `3000 + 子码`） |

因为没有 `seq`，同一时间只发一条命令，并按 `event` 匹配应答。

### 5.2 能用哪些命令

BLE 业务命令里除了蓝牙专属的握手命令（`pass`、`auth`、加密握手等），其余都能通过 MQTT 发送，格式相同。常用的：

| 命令 | 用途 |
|------|------|
| `getFunctionMap` / `model` / `mqttdata` | 读取能力位图、设备配置、MQTT 主题和连接状态 |
| `location` | 让设备闪灯或鸣叫 15 秒，用来找到它 |
| `zero` | 电量清零，**不可恢复** |
| `restart` | 重启 |
| `wifi` | 配置 Wi-Fi（改错会让设备掉线，MQTT 上无法纠正） |
| `mqtt` / `mqtr` | 配置 Broker，`mqtr` 保存后重启；见 [7.1 节](#71-用命令配置) |
| `udp` / `deleteudp` / `udpdata` | UDP 上报目标 |
| `enablehttp` 等 | 打开或关闭其他通道，改完要重启 |

完整的命令、参数和应答见[业务命令参考](../ble-common/ble-business-api.zh-CN.md)。以下情形有区别：

- MQTT 不需要 `pass`、`auth` 之类的认证，**能发布到 `/cmd` 就能控制设备**。要靠 Broker 的账号权限和 TLS 来保护，见 [7.3 节](#73-安全建议)。
- `setInterval`、`getInterval` 控制的是 WebSocket 推送周期，不会改 MQTT 周期。
- 型号不支持的命令会返回失败，见业务命令参考。

### 5.3 旧版命令

下面这些命令是更早的固件遗留下来的，源码里仍然处理，应答也是旧格式。新开发请用 5.2 节的统一命令。

| 命令 | 参数 | 行为 | 应答 |
|------|------|------|------|
| `rdata` | — | 立刻发布一次 `/data` | `{"result":"success","event":"rdata","seq":"<SN>"}`；发布失败时 `result` 为 `failed`，`code` 为 3001 |
| `rint` | — | 读上报周期 | `{"result":"success","event":"rint","seq":"<SN>","INTV":5}`，`INTV` 单位秒 |
| `wint` | `ReportFrequency`（秒） | 改上报周期，**成功后重启** | `event` 为 `wint`；`ReportFrequency` 缺失或为 0 时失败，`code` 为 3002 |
| `mqstep1` | `data`：`host｜clientid｜ssl｜port` | 保存 Broker 地址 | `event` 为 `mqstep1` |
| `mqstep2` | `data`：`interval｜username｜password` | 保存周期和账号，**成功后重启** | `event` 为 `mqstep2` |
| `tp1` | `data`：`topic_post｜topic_set` | 改发布和命令主题，**重启** | `event` 为 `tp1` |
| `tp2` | `data`：`topic_response｜topic_metadata` | 改应答和元数据主题 | `event` 为 `tp2` |
| `topic` | `topic_post`、`topic_set`、`topic_response`、`topic_metadata` | 一次改四个主题并重新订阅 `/cmd` | `event` 为 `topic` |
| `otaurl` | `url` | 从给定地址升级固件 | `{"type":"ACK","seq":"<SN>","flag":<n>}` |
| `ota` | — | 从默认地址升级 | 同上 |
| `cafile` | `cadata`，可选 `filename`、`writeLen` | 写入 MQTT CA 证书 | `event` 为 `cafile` |

说明：

- 上表的 `｜` 在真实命令里是半角竖线 `|`，各段按顺序排列。
- 旧版应答里的 `seq` 是**设备序列号**，不是请求序号。
- `cafile` 的 `writeLen` 为 0 时覆盖写入，非 0 时追加，用于分多次传一张证书。每次的 `cadata` 要保证整条命令不超过 1024 字节。新开发请改用 BLE 或 HTTP 的 `cafilestart` / `cafiledata`。
- `otaurl` / `ota` 会让设备下载并写入固件，能发布到 `/cmd` 的人就能触发，请按 [7.3 节](#73-安全建议)限制 `/cmd` 的发布权限。

## 6. 连接行为

了解这些行为，能解释很多"设备为什么掉线"的问题：

1. **只有启用后才连。** 设备配置了 Broker 才会尝试连接。`mqtt` / `mqtr` 成功时会自动打开功能位里的 MQTT 位（bit 9），不需要另外 `enable*`。
2. **自动重连。** 每 5 秒检查一次，断开就用保存的地址、ClientId、账号重连；连上后重新订阅 `/cmd` 并重发 `/mdata`。
3. **连续失败会重启。** 连续 11 次连接失败，且手机没有连在设备的 BLE 上，设备会自动重启。信号很弱（低信号模式）并且用 TLS 时，阈值是 1 次。内存不足以建立 TLS 时也会重启。
4. **ClientId。** 默认是 `{型号}-{序列号}`。同一个 ClientId 在 Broker 上只能有一个连接，不要让两个设备或一个测试脚本用同一个 ClientId，否则会互相踢下线。
5. **上报节奏。** 周期定时器到点时，设备已连接才发布；`rdata` 会额外立刻发一条。
6. **升级期间。** 固件升级时 MQTT 暂停处理。
7. **改配置后要重启。** `mqtt` 只保存不重启；`mqtr`、`wint`、`mqstep2`、`tp1` 保存后会重启，其余需要你再发一次 `restart`。

## 7. 配置 Broker 与 MQTTS

### 7.1 用命令配置

通过 BLE（或任何已经能通信的通道）发送：

```json
{"cmd":"mqtr","data":"broker.example.com|dev01|1|8883|30|user|pwd"}
```

`data` 的七段依次是 `host｜clientid｜ssl｜port｜interval｜username｜password`：`ssl` 为 `1` 用 TLS，`0` 用明文；`interval` 单位秒，小于 1 秒按 1 秒，写 0 或非数字时取 5 秒；`port` 写 0 或非数字时按 1883 处理。成功应答 `msg` 为 `MQTT successfully`。`mqtt` 只保存，`mqtr` 保存后重启。每一段长度必须是 1 ~ 63 个字符，**空段**或过长都会返回 `Error length!`，所以账号和密码也不能留空。

### 7.2 MQTTS（TLS）

设备支持 TLS 1.2 / 1.3，用 Broker 的根证书校验服务器。

1. **打开 TLS。** 在 `mqtt` 命令的第 3 段填 `1`，端口一般用 8883。
2. **写入 CA 证书。** 证书必须是 PEM 格式（`.pem` 或 `.crt`）。
   - BLE：先发 `cafilestart`，再分多次发 `cafiledata`，见[业务命令参考](../ble-common/ble-business-api.zh-CN.md#34-mqtt)。
   - Web 页面：打开设备 IP，进入 Edit → Forwarding → Upload MQTT CA certificate，选文件上传。Web 页面要先通过 BLE `enablehttp` 打开 HTTP。
   - 没有上传证书时，设备使用固件内置的根证书，只能连到用该根签发的 Broker。自建 Broker 或其他云商都要上传自己的 CA。
3. **重启。** 用 `mqtr` 保存，或另发 `restart`，TLS 设置才会生效。
4. **确认。** `model` 应答 `d.MF` 为 `true` 表示已连上；`mqttdata` 的 `MF` 是数字状态，`0` 为已连接。

TLS 占用设备的 TLS 连接名额（Basic+ 一个，Pro 两个），MQTTS 的优先级最高，见[概览 3.1 节](../overview/open-wifi-overview.zh-CN.md#31-tls-连接数限制)。

### 7.3 安全建议

- 为每台设备分配独立的 Broker 账号和 ClientId，用 ACL 限制它只能发布 `{型号}/{序列号}/data`、`/cdata`、`/mdata`，只能订阅自己的 `/cmd`。
- 只有服务端的控制程序有权发布到 `/cmd`。
- 生产环境用 MQTTS，并上传对应 CA。
- 不要在 `/cmd` 里发明文的 Wi-Fi 密码，除非链路是 TLS。
- `zero`、`restart`、`wifi`、`reset` 这类命令影响大，服务端要加确认流程。

## 8. 从旧版迁移

| 项目 | 旧版（5.1.13 及更早） | 新版（5.1.14 及以后） |
|------|----------------------|----------------------|
| 主题前缀 | `bituotechnik/{型号}/...` | `{型号}/...`，前缀已去掉 |
| 命令写法 | 大写，如 `RDATA`、`WINT` | 小写，和 BLE 一致，如 `location` |
| 请求追踪 | 用 `seq` | 废弃，靠应答里的 `event` |
| 应答格式 | `{"result":"SUCCESS","seq":...}` | `{"ok":true,"msg":"...","event":"...","d":{}}` |
| 相位标志 | 隐含，靠 `DeviceType` | 显式的 `TP` 字段 |
| 遥测新增字段 | — | `Time`、`IP`、`MCUVersion` |
| 元数据 | `macAddr`、`fwVer` | `product`、`Serialnumber`、`fwVer` |

三相的 `TotalActivePower`、`TotalForwardEnergy`、`TotalReverseEnergy` 从 5.1.14 起重新包含在载荷里。

## 9. 调试示例

用 Mosquitto 命令行（把地址、账号换成你自己的）：

```bash
# 订阅一台设备的全部主题
mosquitto_sub -h broker.example.com -p 1883 -u user -P pwd -t "SPM02/AABBCCDDEEFF/#" -v

# 让设备闪灯
mosquitto_pub -h broker.example.com -p 1883 -u user -P pwd -t "SPM02/AABBCCDDEEFF/cmd" -m '{"cmd":"location"}'
```

本仓库的 [MQTT 监视工具](../../tools/lan/README.zh-CN.md) 可以订阅、发送命令并按 `event` 匹配应答。
