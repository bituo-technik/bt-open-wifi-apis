# WebSocket API

> 状态：初版 ｜ 适用：SPM / SDM Open Wi-Fi 全部分支（WSS 需要 TLS 名额，见[概览](../overview/open-wifi-overview.zh-CN.md#3-通道能力矩阵)） ｜ 依据：固件源码 SXM_EW_C3 `5.1.16`、SDMV2 `1.2.12` / `3.1.19`

WebSocket 适合局域网里的本地中枢（例如 Home Assistant、自己写的看板）：连上之后电表**主动、周期性**地推送遥测数据，不用反复轮询；同一条连接上还可以发命令。

## 1. 概述

| 项目 | 说明 |
|------|------|
| 地址 | `ws://<设备 IP>:81/`，启用 TLS 后是 `wss://<设备 IP>:81/` |
| 开关 | BLE 命令 `enablewebsocket`（功能位 bit 11），带 `"enableTLS":true` 同时打开 WSS（bit 10）。见[业务命令参考](../ble-common/ble-business-api.zh-CN.md) |
| 数据 | 连上后自动推送遥测 JSON，内容与 MQTT `/data` 完全相同，见[遥测数据](../reference/telemetry-payload.zh-CN.md) |
| 命令 | 发一条文本帧 `{"cmd":"..."}`，收到统一结构的应答，见[业务命令参考](../ble-common/ble-business-api.zh-CN.md) |
| 连接数 | 同时最多 **2 个**客户端，Basic+ 只有 **1 个**（这个上限和 Modbus TCP 共用同一个设置，等于该固件的 TLS 名额数）。满了以后新连接被直接断开 |
| 路径 | 不检查，`ws://ip:81/`、`ws://ip:81/ws` 都行 |
| 鉴权 | **没有**。能连上端口就能收数据、发命令，只在受控局域网里用 |

## 2. 连接

### 2.1 明文 WebSocket

标准的 RFC 6455 握手：客户端发 `GET ... HTTP/1.1`，带 `Upgrade: websocket` 和 `Sec-WebSocket-Key`，设备回 `101 Switching Protocols`。普通的 WebSocket 库直接就能连。设备实现很精简，有这些限制：

- 不检查 `Origin`，不协商子协议，不支持扩展（如压缩）。
- **不支持分片**：每条消息必须是**单个完整的文本帧**（FIN=1）。
- 入站帧的负载最长 **1024 字节**（WSS 是 **600 字节**）。超过时设备可能直接断开连接。
- 客户端发来的帧必须按标准做掩码（浏览器和常见库都会）。
连上后，设备**先发一条欢迎消息**（明文 WebSocket）：

```json
{"ok":true,"event":"welcome","msg":"websocket connected"}
```

### 2.2 WSS（TLS）

在 `enablewebsocket` 里带 `enableTLS:true` 并重启后，端口 81 改为 TLS。

- **只有拿到 TLS 名额才会用 TLS**。名额按 MQTTS > HTTPS > WSS > Modbus TLS 的优先级分配，WSS 排在第三。没拿到名额时，设备会**回落成明文 WebSocket**，端口不变。所以客户端要能判断：用 `wss://` 连不上时，再试 `ws://`。
- 证书用设备里的 `/server_cert.pem` + `/server_key.pem`；没有就用固件内置的共用证书，**不能靠它防冒充**。设备里有 `/ca_cert.pem` 时还会要求客户端证书。
- WSS 不会发欢迎消息，也不会主动发 Ping，但收到 Ping 会回 Pong。

## 3. 实时推送

连上之后，设备按**推送周期**向每个客户端发送一条文本帧，内容就是最新一包遥测 JSON（字段见[遥测数据](../reference/telemetry-payload.zh-CN.md)）。

| 项目 | 值 |
|------|----|
| 默认周期 | 5000 ms |
| 范围 | 100 ms ~ 86400000 ms（24 小时） |
| 保存 | 改过之后保存在设备里，重启不丢 |
| 没有客户端时 | 不发 |

改周期用命令 `setInterval`，读用 `getInterval`：

```json
{"cmd":"setInterval","value":1000}
```

```json
{"ok":true,"msg":"","event":"setInterval","d":{"value":1000}}
```

`value` 单位是**毫秒**，小于 100 返回失败（`bad value`）。这个周期是**所有 WebSocket 客户端共用**的，也**不影响** MQTT 和 UDP 的周期。`HTTP /model` 里的 `wsInterval` 是当前值。

注意：推送的数据是设备"最近一次生成"的那包。设备内部生成遥测的节奏由固件决定，所以把周期设得比数据刷新更快，只会收到重复的包。用 `Post` 计数可以去重（见遥测文档）。

## 4. 发命令

发一条文本帧，必须是 JSON 对象，并且有 `cmd` 字段。

```json
{"cmd":"location"}
```

应答只发给**发命令的那个连接**，结构是统一的 `ok/msg/event/d`：

```json
{"ok":true,"msg":"location received","event":"location"}
```

要点：

- 只认 `cmd` 字段，不认 `configType`。
- 蓝牙专属的握手命令不能用，其余业务命令都可以，参数和应答同[业务命令参考](../ble-common/ble-business-api.zh-CN.md)。
- 推送帧和应答帧都是文本帧，**会交错到达**。用 `event` 字段区分：推送帧是遥测对象，没有 `event`；应答帧有 `event`。
- 命令的 JSON 不能超过 1024 字节（WSS 600 字节）。

帧格式错误时，设备返回 `event` 为 `error` 的应答，不会断开连接：

| 情形 | 应答 |
|------|------|
| 超过 1024 字节 | `{"ok":false,"event":"error","msg":"payload too large","code":4000}` |
| 不是 `{` 开头 | `{"ok":false,"event":"error","msg":"invalid json","code":4001}` |
| JSON 语法错误 | `{"ok":false,"event":"error","msg":"json parse error","code":4002}` |
| 没有 `cmd` 或为空 | `{"ok":false,"msg":"invalid cmd","event":"cmd","code":4003}` |
| 命令本身失败 | `code` 是 `4000 + 子码`，见[错误码](../reference/error-codes.zh-CN.md) |

## 5. 心跳与断线

- 明文 WebSocket：设备每 **30 秒**向每个客户端发一个 Ping 帧（负载 `ping`）。标准库会自动回 Pong，你不需要处理。设备**不会**因为没收到 Pong 就断开客户端，断线靠 TCP 本身检测。
- 客户端发 Ping，设备回 Pong（负载原样返回）。
- 客户端发 Close 帧，设备关闭这个连接。
- 设备重启、Wi-Fi 重连、关闭 WebSocket 开关时，所有连接会被断开。客户端要**自动重连**，建议间隔 3 ~ 5 秒，并带退避。
- 客户端名额很少（最多 2 个，Basic+ 只有 1 个），你的服务重连时要先关掉旧连接，否则旧连接占着名额，会让新连接被拒。

## 6. 示例

浏览器（明文）：

```js
const ws = new WebSocket("ws://192.168.1.50:81/");
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.event) {
    console.log("应答", m);
  } else {
    console.log("遥测", m.Voltage ?? m.VoltageX, m.Post);
  }
};
ws.onopen = () => ws.send(JSON.stringify({ cmd: "getInterval" }));
```

注意：页面是 `https://` 时，浏览器会禁止它连接 `ws://`，要么页面用 `http://`，要么设备改 WSS 并让浏览器信任证书（内置证书做不到）。

Python（`websockets` 库）：

```python
import asyncio, json, websockets

async def main():
    async with websockets.connect("ws://192.168.1.50:81/") as ws:
        await ws.send(json.dumps({"cmd": "getInterval"}))
        async for text in ws:
            msg = json.loads(text)
            print(msg.get("event") or "telemetry", msg)

asyncio.run(main())
```

本仓库的 [WebSocket 客户端工具](../../tools/lan/README.zh-CN.md) 带自动重连，并能把推送和应答分开显示。

## 7. 排查

| 现象 | 原因 |
|------|------|
| 连接被拒绝 | WebSocket 没开（`enablewebsocket`），或设备在别的网段 |
| 连上就被断开 | 客户端名额已被占满 |
| `wss://` 握手失败 | 设备实际回落成了明文，改用 `ws://`；或 TLS 名额被 MQTTS 占用 |
| 收不到推送 | 周期设得太长（最大 24 小时）；或设备没有生成新数据 |
| 浏览器连不上 | 页面是 HTTPS 而设备是明文 WebSocket（混合内容被拦截） |
| 命令没有应答 | 帧太长、被分片，或超过 1024 字节后连接已断 |
