# WebSocket API

> Status: first release | Applies to: all SPM / SDM Open Wi-Fi branches (WSS needs a TLS slot, see the [overview](../overview/open-wifi-overview.en.md#3-channel-capability-matrix)) | Firmware versions covered: Basic / Lite 5.1.16, Basic+ 1.2.12, Pro 3.1.19

WebSocket suits a local hub on the LAN (for example Home Assistant or your own dashboard): once connected, the meter **pushes** telemetry periodically, with no repeated polling. The same connection can also carry commands.

## 1. Introduction

| Item | Description |
|------|-------------|
| Address | `ws://<device IP>:81/`; with TLS on, `wss://<device IP>:81/` |
| Switch | BLE command `enablewebsocket` (function bit 11); with `"enableTLS":true` it also turns on WSS (bit 10). See the [Business Command Reference](../ble-common/ble-business-api.en.md) |
| Data | Telemetry JSON is pushed automatically after connecting, identical to MQTT `/data`; see [Telemetry Payload](../reference/telemetry-payload.en.md) |
| Commands | Send a text frame `{"cmd":"..."}` and receive the unified response; see the [Business Command Reference](../ble-common/ble-business-api.en.md) |
| Connections | At most **2** clients at once, and only **1** on Basic+ (the limit is shared with Modbus TCP and equals that firmware's TLS slot count). When full, a new connection is dropped at once |
| Path | Not checked; `ws://ip:81/` and `ws://ip:81/ws` both work |
| Authentication | **None**. Anyone who can reach the port receives data and can send commands; use it only on a controlled LAN |

## 2. Connecting

### 2.1 Plain WebSocket

It is the standard RFC 6455 handshake: the client sends `GET ... HTTP/1.1` with `Upgrade: websocket` and `Sec-WebSocket-Key`, and the device answers `101 Switching Protocols`. Ordinary WebSocket libraries connect directly. The device implementation is minimal, with these limits:

- `Origin` is not checked, no subprotocol is negotiated, and extensions (such as compression) are not supported.
- **Fragmentation is not supported**: each message must be **one complete text frame** (FIN=1).
- The payload of an inbound frame is at most **1024 bytes** (**600 bytes** on WSS). Beyond that the device may drop the connection.
- Frames from the client must be masked as the standard requires (browsers and common libraries do).

After connecting, the device **first sends a welcome message** (plain WebSocket):

```json
{"ok":true,"event":"welcome","msg":"websocket connected"}
```

### 2.2 WSS (TLS)

After `enablewebsocket` with `enableTLS:true` and a restart, port 81 uses TLS.

- **TLS is used only when a TLS slot is obtained.** Slots go in the order MQTTS > HTTPS > WSS > Modbus TLS, so WSS is third. Without a slot the device **falls back to plain WebSocket** on the same port. A client should therefore cope: if `wss://` fails, try `ws://`.
- The certificate is `/server_cert.pem` + `/server_key.pem` on the device, or the shared certificate built into the firmware, which **cannot protect against impersonation**. If `/ca_cert.pem` exists on the device, a client certificate is also required.
- WSS sends no welcome message and no Ping of its own, but answers a received Ping with a Pong.

## 3. Live push

After connecting, the device sends each client one text frame per **push period**, containing the latest telemetry JSON (fields on the [Telemetry Payload](../reference/telemetry-payload.en.md) page).

| Item | Value |
|------|-------|
| Default period | 5000 ms |
| Range | 100 ms to 86400000 ms (24 hours) |
| Persistence | Saved on the device after a change; survives reboot |
| No clients | Nothing is sent |

Use `setInterval` to change the period and `getInterval` to read it:

```json
{"cmd":"setInterval","value":1000}
```

```json
{"ok":true,"msg":"","event":"setInterval","d":{"value":1000}}
```

`value` is in **milliseconds**; below 100 fails (`bad value`). The period is **shared by all WebSocket clients** and does **not** affect the MQTT or UDP periods. `wsInterval` in `HTTP /model` is the current value.

Note: the pushed data is the packet the device "last generated". The firmware decides how often telemetry is refreshed internally, so a period shorter than the refresh rate only delivers duplicate packets. Use the `Post` counter to deduplicate (see the telemetry page).

## 4. Sending commands

Send a text frame that is a JSON object with a `cmd` field.

```json
{"cmd":"location"}
```

The response goes only to the **connection that sent the command**, in the unified `ok/msg/event/d` structure:

```json
{"ok":true,"msg":"location received","event":"location"}
```

Notes:

- Only the `cmd` field is recognized, not `configType`.
- BLE-only handshake commands are unavailable; all other business commands work, with the same parameters and responses as the [Business Command Reference](../ble-common/ble-business-api.en.md).
- Push frames and response frames are both text frames and **arrive interleaved**. Tell them apart by `event`: a push frame is a telemetry object without `event`; a response frame has `event`.
- A command JSON must not exceed 1024 bytes (600 on WSS).

For a malformed frame the device returns a response with `event` set to `error` and does not disconnect:

| Case | Response |
|------|----------|
| Over 1024 bytes | `{"ok":false,"event":"error","msg":"payload too large","code":4000}` |
| Does not start with `{` | `{"ok":false,"event":"error","msg":"invalid json","code":4001}` |
| JSON syntax error | `{"ok":false,"event":"error","msg":"json parse error","code":4002}` |
| `cmd` missing or empty | `{"ok":false,"msg":"invalid cmd","event":"cmd","code":4003}` |
| The command itself failed | `code` is `4000 + subcode`, see [Error Codes](../reference/error-codes.en.md) |

## 5. Heartbeat and disconnects

- Plain WebSocket: every **30 seconds** the device sends each client a Ping frame (payload `ping`). Standard libraries answer with a Pong automatically; you need not handle it. The device does **not** drop a client for a missing Pong; a dead connection is found by TCP itself.
- If the client sends a Ping, the device returns a Pong with the same payload.
- If the client sends a Close frame, the device closes that connection.
- On device reboot, Wi-Fi reconnect or turning WebSocket off, all connections are dropped. The client should **reconnect automatically**, every 3 to 5 seconds with a back-off.
- Client slots are scarce (at most 2, Basic+ only 1). When your service reconnects, close the old connection first; otherwise the stale one holds the slot and the new one is refused.

## 6. Examples

Browser (plain):

```js
const ws = new WebSocket("ws://192.168.1.50:81/");
ws.onmessage = (e) => {
  const m = JSON.parse(e.data);
  if (m.event) {
    console.log("response", m);
  } else {
    console.log("telemetry", m.Voltage ?? m.VoltageX, m.Post);
  }
};
ws.onopen = () => ws.send(JSON.stringify({ cmd: "getInterval" }));
```

Note: a page served over `https://` is blocked by the browser from opening `ws://`. Either serve the page over `http://`, or move the device to WSS and make the browser trust the certificate (the built-in certificate cannot do that).

Python (`websockets` library):

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

The [WebSocket client tool](../../tools/lan/README.en.md) in this repository reconnects automatically and shows pushes and responses separately.

## 7. Troubleshooting

| Symptom | Cause |
|---------|-------|
| Connection refused | WebSocket is off (`enablewebsocket`), or the device is on another subnet |
| Dropped right after connecting | The client slots are all taken |
| `wss://` handshake fails | The device actually fell back to plain; use `ws://`. Or the TLS slot is held by MQTTS |
| No push arrives | The period is set too long (up to 24 hours), or the device has not generated new data |
| Browser cannot connect | The page is HTTPS but the device speaks plain WebSocket (mixed content is blocked) |
| A command gets no response | The frame was fragmented, or it exceeded 1024 bytes and the connection is already gone |
