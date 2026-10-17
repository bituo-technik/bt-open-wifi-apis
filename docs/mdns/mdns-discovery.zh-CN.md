# mDNS 发现

> 状态：初版 | 适用：所有 SPM / SDM Open Wi-Fi 分支 | 依据固件源码 SXM_EW_C3 `5.1.16`、SDMV2 `1.2.12` / `3.1.19` 以及 Gitbook「mDNS Discovery」页面

电表连上 Wi-Fi 后，会通过 mDNS（组播 DNS）广播自己。同一网段里的网关、EMS 或手机 App 不需要静态 IP、也不需要扫描，就能找到每一台电表的 IP 地址，再使用 [Modbus TCP](../modbus-tcp/modbus-tcp-api.zh-CN.md)、[HTTP](../http/http-api.zh-CN.md)、[WebSocket](../websocket/websocket-api.zh-CN.md) 或 [UDP](../udp/udp-api.zh-CN.md)。

## 1. 简介

| 项目 | 说明 |
|------|------|
| 服务类型 | `_http._tcp.local.` |
| 端口 | `80`（Web 页面与 HTTP API；其它端口**不会**广播） |
| 主机名 | `<设备名称>.local.`，默认为 `EnergySensor-<型号>[_<变体>]-<MAC>`（见[第 2 节](#2-主机名格式)） |
| TXT 记录 | 无，服务不携带额外信息 |
| 地址类型 | IPv4 |
| 广播时机 | 每次 Wi-Fi 连接成功后（包括重连） |
| 不可用 | 电表连上你的 Wi-Fi 之前（只处于配网状态时不会广播） |

## 2. 主机名格式

默认主机名由型号和 MAC 地址生成：

```text
EnergySensor-<MODEL>[_<VARIANT>]-<MAC>.local.
EnergySensor-SDM01_3PN_01-45705E597760.local.
```

| 字段 | 示例 | 说明 |
|------|------|------|
| `EnergySensor` | | 固定前缀 |
| `MODEL` | `SDM01_3PN` | 产品型号，与 Modbus 寄存器 984 中的型号相同 |
| `VARIANT` | `01` / `02` | 固件变体，见下表；部分型号**没有**变体字段 |
| `MAC` | `45705E597760` | 设备 MAC 的 12 位十六进制字符，大写、无分隔符；也是 MQTT 主题里的序列号 |

按固件家族区分的变体：

| 固件 | 变体 | 示例 |
|------|------|------|
| SXM（Basic / Lite）：SDM01_3PN 与 SDM01_1PN | `_01` | `EnergySensor-SDM01_3PN_01-45705E597760` |
| SXM（Basic / Lite）：其它型号，如 SPM02、SDM02 | 无 | `EnergySensor-SPM02-45705E597760` |
| SDMV2（Basic+ / Pro） | `_02` | `EnergySensor-SDM01_3PN_02-45705E597760` |

客户定制固件可能用别的名字替换型号。

### 2.1 修改设备名称

主机名就是**设备名称**，用户可以用 `deviceName` 指令（最长 30 个字符，见[业务指令参考](../ble-common/ble-business-api.zh-CN.md)）或网页修改。新名称在设备下一次连接 Wi-Fi 时广播（想确保生效可以重启设备）。改名之后：

- 按 `EnergySensor-` 前缀过滤就找不到它了；请按**服务类型** `_http._tcp` 发现，再用别的方式确认身份（见[第 3.2 节](#32-确认发现到的设备身份)）；
- 名称只用字母、数字和 `-`。空格等字符不是合法的主机名字符，有些解析器无法解析。

## 3. 发现设备

### 3.1 过滤

1. 浏览 `_http._tcp`。网络里的打印机、NAS、路由器也会广播同一类型，所以会得到一个列表。
2. 只保留名称以 `EnergySensor-` 开头的条目。
3. 把名称拆成型号、变体和 MAC。
4. **只连接你验证过的变体。** 变体标识固件家族，也就决定了 HTTP API 和其它接口的行为（见[总览](../overview/open-wifi-overview.zh-CN.md)）；遇到不认识的变体请上报，不要默认兼容。
5. 从应答里取 IPv4 地址。可以缓存，但要准备好重新查询：DHCP 租约变化时地址会变。正式现场建议在路由器上做 DHCP 保留。

### 3.2 确认发现到的设备身份

名称可以被修改，其它产品也可能用相似的名字，所以开始使用前先确认：

- 读取 Modbus 寄存器 978 ~ 988（MAC 与型号），不需要登录，见 [Modbus TCP](../modbus-tcp/modbus-tcp-api.zh-CN.md#41-产品识别基地址-978)。
- 或者先不带密码调用 HTTP `/signin`，看设备是否有保护，再带 token 调用 `/model`；见 [HTTP](../http/http-api.zh-CN.md#2-会话与鉴权)。

### 3.3 发现之后用什么

| 需求 | 接口 |
|------|------|
| PLC / 工业网关轮询 | [Modbus TCP](../modbus-tcp/modbus-tcp-api.zh-CN.md) 端口 502 |
| 配置、状态、固件升级 | [HTTP](../http/http-api.zh-CN.md) 端口 80（HTTPS 为 443） |
| 低延迟数据流 | [WebSocket](../websocket/websocket-api.zh-CN.md) 端口 81（明文与 WSS 同一端口） |
| 高频单向读数 | [UDP](../udp/udp-api.zh-CN.md)：配置设备向你发送 |

mDNS 记录里只有 80 端口，其它端口请使用上面的默认值。

## 4. 验证 mDNS 是否工作

| 平台 | 命令 / 工具 |
|------|-------------|
| 任意平台，有 Python | `python tools/lan/discover_mdns.py`（见 [tools/lan](../../tools/lan/README.zh-CN.md)），列出找到的所有电表 |
| macOS | `dns-sd -B _http._tcp` 与 `dns-sd -L "<名称>" _http._tcp local` |
| Linux | `avahi-browse -rt _http._tcp` |
| Windows | Bonjour 的 `dns-sd`（随 iTunes / Bonjour Print Services 安装），或上面的 Python 工具 |
| Android | 「Service Browser」之类的 App，浏览 `_http._tcp` |
| 抓包 | Wireshark，显示过滤器 `mdns` |

按名称快速检查：`ping EnergySensor-SDM01_3PN_01-45705E597760.local`。

工具需要 `zeroconf` 包；没有安装时，工具会退回到不需要任何包的简单 mDNS 查询。

## 5. 常见问题

| 现象 | 可能原因 |
|------|----------|
| 找不到设备 | 手机 / 电脑与电表不在同一网段或 VLAN；路由器屏蔽组播（「AP 隔离」「客户端隔离」、IGMP snooping 问题）；电表没有连上 Wi-Fi |
| 找到了但连不上 | 地址变了（DHCP）；你这边的防火墙；目标接口被关掉（例如 Modbus TCP 的 bit 15） |
| 过一会儿才找到 | 广播发生在 Wi-Fi 连上之后；通电或路由器重启后请等几秒 |
| 名称与预期不同 | 设备被改名（`deviceName`），或者是变体不同的固件家族 |
| Windows 解析不了 `.local` | 安装 Bonjour，或用 Python 工具，或直接用 IP 地址 |
| 只有一台电脑能解析名称 | 那台电脑有自己的 mDNS 组件（如 Bonjour / Avahi），其它电脑也要有 |

## 6. 相关页面

- [总览](../overview/open-wifi-overview.zh-CN.md)
- [Modbus TCP](../modbus-tcp/modbus-tcp-api.zh-CN.md)、[HTTP](../http/http-api.zh-CN.md)、[WebSocket](../websocket/websocket-api.zh-CN.md)、[UDP](../udp/udp-api.zh-CN.md)
- 机器可读描述：[`spec/mdns-discovery.json`](../../spec/mdns-discovery.json)
