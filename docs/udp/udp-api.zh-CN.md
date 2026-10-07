# UDP 上报

> 状态：初版 ｜ 适用：SPM / SDM Open Wi-Fi 全部分支（AES 加密报文的适用范围见 [4 节](#4-aes-ccm-加密报文)） ｜ 依据：固件源码 SXM_EW_C3 `5.1.16`、SDMV2 `1.2.12` / `3.1.19`

UDP 上报是**设备主动推**：你告诉电表一个 IP 和端口，电表就按固定周期把遥测 JSON 作为 UDP 报文发过去。没有连接、没有握手，延迟低、实现简单，适合光伏防逆流、动态负载均衡这类要快速拿到功率的场景。

## 1. 概述

| 项目 | 说明 |
|------|------|
| 方向 | 设备 → 你的主机，**单向**，设备不接收命令 |
| 内容 | 遥测 JSON，与 MQTT `/data` 相同，见[遥测数据](../reference/telemetry-payload.zh-CN.md)；Pro 开启后可改为 AES-CCM 密文，见 [4 节](#4-aes-ccm-加密报文) |
| 目标 | 最多 **5 个**目标（IP + 端口），每个周期向每个目标各发一个报文 |
| 周期 | 默认 5 秒，所有目标**共用一个周期**，最小 100 ms |
| 开关 | 功能位 bit 13；添加目标时自动打开，删除目标**不会**关闭 |
| 来源端口 | 设备固定用本地 **2390** 端口发送（和校时共用一个套接字），防火墙要放行的话以它为准 |
| 可靠性 | UDP 不保证送达、不保证顺序、不重发。要判断丢包，请用遥测里的 `Post` 计数 |

## 2. 配置目标

用[业务命令参考](../ble-common/ble-business-api.zh-CN.md)里的 `udp`、`deleteudp`、`udpdata` 命令，BLE、HTTP、MQTT、WebSocket 都能发。

```json
{"cmd":"udp","IpAddress":"192.168.1.100","localUdpPort":9000,"Frequency":5}
```

| 字段 | 说明 |
|------|------|
| `IpAddress` | 目标 IP（最长 19 个字符，用 IPv4 点分写法） |
| `localUdpPort` | 目标端口。字段名里有 local，实际是**你那一端**的端口 |
| `Frequency` | 可选，周期，单位**秒**。不写则保持当前周期。设备内部换算成毫秒，最小 100 ms |

- 成功：`UDP successfully`。重复添加同一个 IP + 端口只会更新周期。
- IP 为空或端口无效时，设备也返回 `UDP full`（子码 24），不要按字面理解成"满了"。
- 超过 5 个目标同样返回 `UDP full`。
- 删除：`{"cmd":"deleteudp","IpAddress":"192.168.1.100","localUdpPort":9000}`，成功 `UDP deleted`；不存在返回 `UDP not found`（子码 25）。
- 列表：`{"cmd":"udpdata"}`，目标在 `d.udp_data`，如 `[{"ip":"192.168.1.100","port":"9000"}]`。
- 配置保存在设备里，重启不丢。
- 目标列表和周期也能在 `model` 应答里看到：周期是 `UI`（毫秒），HTTP `/model` 里是 `udpInterval` 与 `UDP`。

要点：

- 把目标设成电脑的固定 IP（或路由器上做 DHCP 保留），否则电脑换 IP 后就收不到了。
- 固件只是把报文发给你配置的地址。想发给整个网段，可以试着填子网广播地址（如 `192.168.1.255`），但这不是固件的规格承诺，需要自己验证。

## 3. 报文格式

### 3.1 明文报文

每个 UDP 报文就是**一个完整的 JSON 文本**（UTF-8），没有头、没有换行分隔、不分片，长度不超过 1024 字节。字段见[遥测数据](../reference/telemetry-payload.zh-CN.md)。

```json
{"Post":927,"Time":1782313081,"IP":"192.168.1.50","Rssi":-68,"FWVersion":"5.1.16","SerialNumber":"AABBCCDDEEFF","ProductModel":"SPM01","TP":1,"Voltage":"227.6","Current":"0.000","ActivePower":"0.000"}
```

上面为了排版只列了一部分字段，实际是完整的一包。收到后直接 `JSON.parse` 即可，用 `SerialNumber` 区分是哪台设备。

用 `commonmode` 打开通用格式后，报文也跟着变，见遥测文档第 6 节。

### 3.2 什么时候发

- 到周期且已连上 Wi-Fi、功能位 bit 13 为 1 时发。
- 发的是设备"最近一次生成"的那包，内部刷新的节奏由固件决定；周期设得比刷新还快会收到重复包，用 `Post` 去重。
- 没有配置目标时什么都不发。

## 4. AES-CCM 加密报文

> 范围：源码里，只有 SDMV2（C3 / C6）的**加密构建**才有这个功能，而且要**打开 HTTPS 开关**（`enablehttps`）才会启用。SXM 构建（Basic、Lite）始终发明文。线上文档写 Lite 也支持，与源码不符，需要固件确认，见 [CHANGELOG](../../CHANGELOG.md)。

打开后，UDP 报文不再是遥测 JSON，而是一个密文 JSON：

```json
{"ct":"<密文 base64>","tag":"<标签 base64>","counter":12}
```

| 字段 | 说明 |
|------|------|
| `ct` | 遥测 JSON 的 AES-128-CCM 密文，Base64 |
| `tag` | 认证标签，**8 字节**，Base64 |
| `counter` | 32 位无符号整数，**每个上报周期加 1**（同一周期发给各个目标的报文相同）。设备重启后**从 1 重新开始** |

加密参数：

| 项目 | 值 |
|------|----|
| 算法 | AES-128-CCM |
| 密钥 | **广播密钥 broadcast_key**（16 字节），与 BLE 加密广播用的是同一个，来自 BLE 配网时的 J-PAKE 结果，见[加密协议 3.5 节](../ble-secured/crypto-protocol.zh-CN.md) |
| Nonce（12 字节） | 前 8 字节全为 `00`，后 4 字节是 `counter` 的**大端**表示 |
| 标签长度 | 8 字节（BLE 广播长包是 4 字节，别弄混） |
| 附加数据 AAD | 无 |
| 明文 | 完整的遥测 JSON 文本（UTF-8） |

解密步骤：

1. 解析报文得到 `ct`、`tag`、`counter`，两个 Base64 解码。
2. 用 `counter` 拼出 nonce：8 个 `00` 字节 + 4 字节大端的 `counter`。
3. 把 `ct` 和 `tag` 拼成 `ct || tag`，用 broadcast_key 和 nonce 做 AES-CCM 解密（标签长度 8）。
4. 解密成功得到明文 JSON；标签校验失败就丢弃这个报文。

Python（`cryptography` 库）：

```python
import base64, json
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

def decrypt_udp(datagram: bytes, broadcast_key: bytes) -> dict:
    env = json.loads(datagram)
    ct = base64.b64decode(env["ct"])
    tag = base64.b64decode(env["tag"])
    nonce = b"\x00" * 8 + int(env["counter"]).to_bytes(4, "big")
    plain = AESCCM(broadcast_key, tag_length=8).decrypt(nonce, ct + tag, None)
    return json.loads(plain)
```

注意：

- **测试向量**：[`spec/udp-aes-test-vector.json`](../../spec/udp-aes-test-vector.json) 给出了密钥、counter、明文和期望的报文，用来检查你的实现。它是按上面的参数生成的，不是从真机抓取的。
- **防重放**：`counter` 在设备重启后会重置，所以只靠它判断先后顺序并不可靠；明文里的 `Post` 同样会重置。需要防重放时，用明文里的 `Time`（Unix 时间）配合窗口判断。
- 设备没有拿到广播密钥时（例如还没完成加密配网），会发出**空报文**。收到长度为 0 的报文可以直接忽略。
- 关闭 `enablehttps` 后，UDP 报文回到明文。接收端要同时处理两种格式：先 `JSON.parse`，有 `ct` 字段就解密。
- 广播密钥怎么从 BLE 配网结果里取出来：本仓库的 [BLE 加密工具](../../tools/README.md)会把它缓存在本地，UDP 监听工具可以直接读。

## 5. 接收端示例

最简单的监听（Python，明文）：

```python
import json, socket

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", 9000))
while True:
    data, addr = s.recvfrom(2048)
    if not data:
        continue
    msg = json.loads(data)
    print(addr[0], msg.get("SerialNumber"), msg.get("Post"))
```

本仓库的 [UDP 监听工具](../../tools/lan/README.md)支持明文和 AES-CCM 两种报文，并检测丢包。

## 6. 排查

| 现象 | 原因 |
|------|------|
| 一直收不到 | 没有配置目标；功能位 bit 13 没开；电脑防火墙拦截了入站 UDP；设备和电脑不在同一网段 |
| 偶尔丢包 | 正常，UDP 不保证送达；用 `Post` 统计 |
| 收到的是 `{"ct":...}` | 设备已启用 AES，需要用 broadcast_key 解密 |
| 收到空报文 | 设备没有广播密钥，需要重新做一次 BLE 加密配网 |
| 解密失败 | 密钥不是当前设备的；或配网后设备重置过，密钥已更新 |
| 周期不对 | 周期按**秒**写入，设备换成毫秒；最小 100 ms |
