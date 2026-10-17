# MQTT API

> Status: first release | Applies to: all SPM / SDM Open Wi-Fi branches (TLS support: see the [overview](../overview/open-wifi-overview.en.md#3-channel-capability-matrix)) | Firmware versions covered: Basic / Lite 5.1.16, Basic+ 1.2.12, Pro 3.1.19, and the online MQTT API Reference

The meter can connect to your own MQTT broker: it publishes telemetry periodically, subscribes to a command topic, and publishes each result to a response topic. The commands are the same set as on BLE, HTTP and WebSocket. This page covers only what is specific to MQTT: topics, connection behavior, legacy commands and MQTTS setup.

## 1. Introduction

- The meter is an MQTT **client**. You provide the broker.
- Command and response structure: [Business Command Reference](../ble-common/ble-business-api.en.md). Telemetry fields: [Telemetry Payload](../reference/telemetry-payload.en.md). Error codes: [Error Codes](../reference/error-codes.en.md).
- An inbound command JSON must not exceed **1024 bytes**. A message that is too long or fails to parse is dropped and **gets no response**.
- No usable broker is configured at the factory. The device starts connecting once a broker address is written with the BLE `mqtt` command or the Web page.
- New firmware answers commands in the unified `ok/msg/event/d` structure and the `seq` field is deprecated. Legacy commands are still recognized; see [Section 5.3](#53-legacy-commands).

## 2. Topics

The default topic is `{Model}/{SerialNumber}/{suffix}`; the serial number is 12 uppercase hex characters.

| Suffix | Direction | Content | QoS | Retain |
|--------|-----------|---------|-----|--------|
| `/data` | Device → server | Periodic telemetry | 0 | No |
| `/cmd` | Server → device | Commands | 0 | No |
| `/cdata` | Device → server | Command responses | 0 | No |
| `/mdata` | Device → server | Device metadata, published every time the broker connection is made | 0 | **Yes** |

Example (model `SPM02`, serial `AABBCCDDEEFF`): `SPM02/AABBCCDDEEFF/data`, `SPM02/AABBCCDDEEFF/cmd`.

Notes:

- The device subscribes to `/cmd` at QoS 0, so the broker delivers to it at QoS 0. You may publish commands at QoS 1, but the last hop to the device is not retransmitted.
- The model comes from the device (for example `SPM01`, `SPM02`, `SDM01_1PN`, `SDM01_3PN`, `SDM02`). The exact string for a batch is whatever the device reports in `/mdata` or the `model` response.
- All four topics can be changed. Use `topic1` (`topic_post`, `topic_set`) and `topic2` (`topic_response`, `topic_metadata`); each topic is at most 63 characters. Restart afterwards so the new `/cmd` is subscribed. Read the current values with `mqttdata`; `TP/TC/TR/TM` are the full `/data`, `/cmd`, `/cdata`, `/mdata` topics in that order.
- Some customized firmware uses a different topic prefix. **Use what `mqttdata` returns**; do not build the topic yourself.
- The device sets no Last Will. To detect it going offline, watch whether `/data` keeps updating (use `Post` and `Time`).

## 3. Telemetry (`/data`)

At each MQTT report period the device publishes one JSON to `/data`. Fields, per-model differences and examples are on the [Telemetry Payload](../reference/telemetry-payload.en.md) page. Only the MQTT-specific parts are here:

- The period is set by the fifth segment of the `mqtt` command (in **seconds**, minimum 1 s). `MI` in the `model` response is in **milliseconds**. The factory default on the device is 5 s; the online documentation says 30 s. Trust the `MI` you read from the device.
- It is published only while connected to the broker; data from an offline period is **not replayed**.
- With `commonmode` on, `/data` carries the generic format; see Section 6 of the telemetry page.

## 4. Metadata (`/mdata`)

Every time the device connects (including reconnects) it publishes one retained message to `/mdata`, so a new subscriber gets it immediately.

```json
{
  "product": "EnergySensor-SPM01-AABBCCDDEEFF",
  "Serialnumber": "AABBCCDDEEFF",
  "fwVer": "5.1.16",
  "wifiname": "MyRouter"
}
```

| Field | Description |
|-------|-------------|
| `product` | Product name, usually `EnergySensor-Model-Serial` |
| `Serialnumber` | Serial number |
| `fwVer` | Wi-Fi module firmware version |
| `wifiname` | SSID of the connected router (absent on some firmware) |

## 5. Commands and responses

### 5.1 Message format

Publish a JSON object with at least `cmd` to `/cmd`:

```json
{"cmd":"location"}
```

The device publishes the response to `/cdata`:

```json
{"ok":true,"msg":"location received","event":"location"}
```

| Field | Description |
|-------|-------------|
| `ok` | `true` on success |
| `msg` | Result text or the original error text |
| `event` | Echo of the command name; use it to pair a request with its response |
| `d` | Optional returned data |
| `code` | Only on failure; see [Error Codes](../reference/error-codes.en.md) (on MQTT it is `3000 + subcode`) |

There is no `seq`, so send one command at a time and match the response by `event`.

### 5.2 Which commands are available

Apart from the BLE-only handshake commands (`pass`, `auth`, the secured handshake and so on), all BLE business commands can be sent over MQTT in the same format. The common ones:

| Command | Purpose |
|---------|---------|
| `getFunctionMap` / `model` / `mqttdata` | Read the capability bitmap, device configuration, MQTT topics and connection status |
| `location` | Flash or beep for 15 s to find the device |
| `zero` | Reset energy counters; **irreversible** |
| `restart` | Reboot |
| `wifi` | Configure Wi-Fi (a wrong value drops the device and MQTT cannot fix it) |
| `mqtt` / `mqtr` | Configure the broker; `mqtr` saves then reboots; see [Section 7.1](#71-configure-with-a-command) |
| `udp` / `deleteudp` / `udpdata` | UDP report targets |
| `enablehttp` and others | Turn other channels on or off; restart afterwards |

The full commands, parameters and responses are in the [Business Command Reference](../ble-common/ble-business-api.en.md). Differences on MQTT:

- MQTT needs no `pass` / `auth`. **Anyone who can publish to `/cmd` controls the device.** Protect it with broker accounts and TLS; see [Section 7.3](#73-security-advice).
- `setInterval` / `getInterval` control the WebSocket push period, not the MQTT period.
- A command the model does not support returns a failure; see the business command reference.

### 5.3 Legacy commands

These commands remain from older firmware. The device still handles them and the responses use the old format. Use the unified commands from Section 5.2 for new development.

| Command | Parameters | Behavior | Response |
|---------|------------|----------|----------|
| `rdata` | none | Publish `/data` once immediately | `{"result":"success","event":"rdata","seq":"<SN>"}`; on failure `result` is `failed` and `code` is 3001 |
| `rint` | none | Read the report period | `{"result":"success","event":"rint","seq":"<SN>","INTV":5}`, `INTV` in seconds |
| `wint` | `ReportFrequency` (seconds) | Set the report period; **reboots on success** | `event` is `wint`; if `ReportFrequency` is missing or 0 it fails with `code` 3002 |
| `mqstep1` | `data`: `host｜clientid｜ssl｜port` | Save the broker address | `event` is `mqstep1` |
| `mqstep2` | `data`: `interval｜username｜password` | Save period and account; **reboots on success** | `event` is `mqstep2` |
| `tp1` | `data`: `topic_post｜topic_set` | Change the publish and command topics; **reboots** | `event` is `tp1` |
| `tp2` | `data`: `topic_response｜topic_metadata` | Change the response and metadata topics | `event` is `tp2` |
| `topic` | `topic_post`, `topic_set`, `topic_response`, `topic_metadata` | Change all four topics and re-subscribe `/cmd` | `event` is `topic` |
| `otaurl` | `url` | Upgrade firmware from the given URL | `{"type":"ACK","seq":"<SN>","flag":<n>}` |
| `ota` | none | Upgrade from the default URL | Same as above |
| `cafile` | `cadata`, optional `filename`, `writeLen` | Write the MQTT CA certificate | `event` is `cafile` |

Notes:

- The `｜` in the table stands for the ASCII pipe `|` in a real command; segments are positional.
- In a legacy response `seq` is the **device serial number**, not a request counter.
- `cafile` overwrites when `writeLen` is 0 and appends otherwise, so one certificate can be sent in several pieces. Keep each whole command within 1024 bytes. For new work use `cafilestart` / `cafiledata` over BLE or HTTP.
- `otaurl` / `ota` make the device download and write firmware, and anyone able to publish to `/cmd` can trigger them. Restrict publish rights on `/cmd` as in [Section 7.3](#73-security-advice).

## 6. Connection behavior

These behaviors explain most "why did the device drop" questions:

1. **It connects only once enabled.** The device tries to connect only after a broker is configured. A successful `mqtt` / `mqtr` also sets the MQTT bit (bit 9) in the function map, so no separate `enable*` is needed.
2. **Automatic reconnect.** Every 5 s the device checks the link and, if it is down, reconnects with the saved address, ClientId and account. After connecting it re-subscribes `/cmd` and republishes `/mdata`.
3. **Repeated failures cause a reboot.** After 11 consecutive failed connections, and with no phone connected over BLE, the device restarts. In weak-signal mode with TLS the threshold is 1. It also restarts when there is not enough memory to set up TLS.
4. **ClientId.** The default is `{Model}-{SerialNumber}`. A broker allows only one connection per ClientId, so do not let two devices or a test script share one, or they will kick each other off.
5. **Report cadence.** When the period timer fires the device publishes if connected; `rdata` adds one more at once.
6. **During an upgrade.** MQTT handling pauses while firmware is being upgraded.
7. **Restart after changes.** `mqtt` saves without restarting. `mqtr`, `wint`, `mqstep2` and `tp1` restart after saving; for others you send `restart` yourself.

## 7. Configuring the broker and MQTTS

### 7.1 Configure with a command

Send over BLE (or any channel that already works):

```json
{"cmd":"mqtr","data":"broker.example.com|dev01|1|8883|30|user|pwd"}
```

The seven `data` segments are `host｜clientid｜ssl｜port｜interval｜username｜password`. `ssl` is `1` for TLS and `0` for plaintext. `interval` is in seconds; 0 or non-numeric becomes 5 s. A `port` of 0 or non-numeric becomes 1883. A successful response has `msg` `MQTT successfully`. `mqtt` only saves; `mqtr` saves and reboots. Each segment must be 1 to 63 characters; an **empty segment** or a too-long one returns `Error length!`, so username and password cannot be left blank either.

### 7.2 MQTTS (TLS)

The device supports TLS 1.2 / 1.3 and verifies the server with the broker's root certificate.

1. **Turn TLS on.** Put `1` in the third segment of the `mqtt` command; the port is usually 8883.
2. **Write the CA certificate.** It must be PEM (`.pem` or `.crt`).
   - BLE: send `cafilestart`, then `cafiledata` in several pieces; see the [Business Command Reference](../ble-common/ble-business-api.en.md#34-mqtt).
   - Web page: open the device IP, go to Edit → Forwarding → Upload MQTT CA certificate and upload the file. The Web page needs HTTP turned on first with BLE `enablehttp`.
   - Without an uploaded certificate the device uses the root certificate built into the firmware, which only works for brokers signed by that root. A self-hosted broker or another cloud needs its own CA uploaded.
3. **Restart.** Save with `mqtr`, or send `restart`, for the TLS settings to apply.
4. **Check.** `d.MF` in the `model` response is `true` once connected; `MF` in `mqttdata` is a number where `0` means connected.

TLS uses one of the device's TLS slots (Basic+ one, Pro two). MQTTS has the highest priority; see [Overview Section 3.1](../overview/open-wifi-overview.en.md#31-tls-connection-limit).

### 7.3 Security advice

- Give each device its own broker account and ClientId, and use ACLs so it can publish only `{Model}/{SerialNumber}/data`, `/cdata`, `/mdata` and subscribe only to its own `/cmd`.
- Only your control backend may publish to `/cmd`.
- Use MQTTS in production and upload the matching CA.
- Do not send a Wi-Fi password in `/cmd` unless the link is TLS.
- `zero`, `restart`, `wifi` and `reset` have a large effect; add a confirmation step in the backend.

## 8. Migrating from the legacy API

| Item | Legacy (5.1.13 and earlier) | New (5.1.14 and later) |
|------|-----------------------------|------------------------|
| Topic prefix | `bituotechnik/{Model}/...` | `{Model}/...`, prefix removed |
| Command style | Uppercase, such as `RDATA`, `WINT` | Lowercase, same as BLE, such as `location` |
| Request tracking | `seq` | Deprecated; use `event` in the response |
| Response format | `{"result":"SUCCESS","seq":...}` | `{"ok":true,"msg":"...","event":"...","d":{}}` |
| Phase indicator | Implicit, via `DeviceType` | Explicit `TP` field |
| New telemetry fields | none | `Time`, `IP`, `MCUVersion` |
| Metadata | `macAddr`, `fwVer` | `product`, `Serialnumber`, `fwVer` |

The three-phase `TotalActivePower`, `TotalForwardEnergy` and `TotalReverseEnergy` are included in the payload again from 5.1.14.

## 9. Debugging examples

With the Mosquitto command line (replace the address and account with yours):

```bash
# Subscribe to every topic of one device
mosquitto_sub -h broker.example.com -p 1883 -u user -P pwd -t "SPM02/AABBCCDDEEFF/#" -v

# Make the device flash
mosquitto_pub -h broker.example.com -p 1883 -u user -P pwd -t "SPM02/AABBCCDDEEFF/cmd" -m '{"cmd":"location"}'
```

The [MQTT monitor tool](../../tools/lan/README.en.md) in this repository can subscribe, send commands and match responses by `event`.
