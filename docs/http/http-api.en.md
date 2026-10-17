# HTTP / HTTPS API

> Status: first release | Applies to: all SPM / SDM Open Wi-Fi branches (HTTPS on Pro only) | Firmware versions covered: Basic / Lite 5.1.16, Basic+ 1.2.12, Pro 3.1.19

A gateway, script or Home Assistant on the LAN can read meter data and change settings over plain HTTP. The commands are the same set as on BLE, MQTT and WebSocket. This page covers what is specific to HTTP: sessions, the endpoint list, and how port 80 differs from port 443.

## 1. Introduction

| Item | Description |
|------|-------------|
| Address | `http://<device IP>/`; on Pro with HTTPS on, also `https://<device IP>/` (port 443) |
| Switch | BLE commands `enablehttp` / `enablehttps`, see the [Business Command Reference](../ble-common/ble-business-api.en.md). Basic and Basic+ turn HTTP on at every boot; Lite and Pro leave it off |
| Finding the device | Resolve the hostname with [mDNS](../mdns/mdns-discovery.en.md), or read the IP from your router |
| Methods | Most endpoints are `GET` with parameters in the query string; endpoints that write settings are `POST` with a JSON body |
| Responses | Apart from a few endpoints that return plain text or raw JSON, responses use the unified `ok/msg/event/d` (failures add `code`). Conventions: [Business Command Reference 1.1](../ble-common/ble-business-api.en.md) |
| Status code | **A failure usually still has HTTP status 200**; read `ok` in the body. Exceptions: 403 when port 80 is refused by policy, 404 when the log file is missing or HTTPS has no such path |
| Concurrency | The port 80 web server handles one request at a time; do not poll in parallel. HTTPS connections are limited by the TLS slots, see [Overview 3.1](../overview/open-wifi-overview.en.md#31-tls-connection-limit) |
| Inbound size | The JSON body of a request must not exceed 1024 bytes |

Responses come in three shapes. Tell them apart:

| Shape | Examples | How to judge success |
|-------|----------|----------------------|
| Raw JSON (no `ok`) | `/data`, `/model`, `/status`, `/snapshot`, `/getSchedule`, `/checkota` | If it parses and the fields are there it succeeded; a token error returns a small object with `ok:false` |
| Unified structure | `/restart`, `/location`, `/save-config` and others | Read `ok` |
| Plain text | `/sn`, `/logfile` | HTTP status code |

## 2. Session and authentication

The meter has an optional **Web password**.

- **No Web password (factory default): no endpoint needs a sign-in.** Anyone who can reach the IP can read data, change settings, reboot and factory-reset.
- **With a Web password:** every endpoint except `/signin` needs a `token` query parameter, for example `/data?token=123456`. Without it, or with a wrong one, you get a failure response and nothing is executed.

### 2.1 Sign in to get a token

```
GET /signin?password=<password>
```

On success the device issues a token:

```json
{"ok":true,"msg":"","token":1736912345}
```

Add `?token=1736912345` to every later request (use `&token=...` when other query parameters exist).

Optionally you can **bring your own token** when signing in: `/signin?password=<password>&token=<number you generated>`. If the password is right the device registers your token and the response has **no** `token` field. Several clients can each use their own token.

| Case | Response |
|------|----------|
| Right password | `{"ok":true,"msg":"","token":N}` (no `token` field when you brought your own) |
| Wrong password | `{"ok":false,"msg":"wrong password","code":2003}` |
| Password over 16 characters | `{"ok":false,"msg":"password too long","code":2004}` |
| Device has no password | `{"ok":true,"msg":"no password set"}` |
| No `password`, device has one | `{"ok":false,"msg":"need signin","code":2005}` |
| No `password`, device has none | `{"ok":true,"msg":"no password"}` |

`/signin` without `password` tells you whether the device needs a password at all.

### 2.2 Token rules

- A token is an **unsigned 32-bit integer** (decimal).
- The device remembers at most **5** tokens at once. When full, the least recently used one is dropped.
- A token **expires after 5 minutes idle**; every successful use renews it.
- Responses for a bad token: `{"ok":false,"msg":"need token","code":2001}` (missing) or `{"ok":false,"msg":"invalid token","code":2002}` (unknown or expired). Sign in again.
- After a successful password change (`/changepass`), **all tokens are revoked** at once.
- A reboot forgets all tokens.

### 2.3 Change the Web password

```
GET /changepass?newpass=<new password>&oldpass=<old password>
```

The length is 1 to 16. When the device has no password yet, `oldpass` may be omitted. Failure `msg` values are `missing newpass`, `bad newpass length`, `old password wrong` and `nvs save failed`.

### 2.4 Security reminders

- Password and token travel in the URL. On plain HTTP, anyone on the same network can capture them. Use HTTPS on Pro where protection matters.
- `/model` (and the `model` part of `/snapshot`) returns the **MQTT password in clear text** (`mqttUserPassword`), so do not expose a device without a Web password to an untrusted network.
- Use it only on a controlled LAN. Never forward port 80 / 443 to the Internet.

## 3. Endpoint list

"Needs a token" below means when a Web password is set. Unless noted, an endpoint exists on both 80 and 443. All `GET` parameters go in the query string.

### 3.1 Reading data and state

| Endpoint | Returns | Description |
|----------|---------|-------------|
| `GET /data` | Raw JSON | The latest telemetry packet; fields are on the [Telemetry Payload](../reference/telemetry-payload.en.md) page. Each call increments an internal counter |
| `GET /model` | Raw JSON | Device configuration: model, Wi-Fi name, MQTT topics and connection, per-channel periods (`mqttInterval`, `udpInterval`, `wsInterval`), the `UDP` target list and more |
| `GET /status` | Raw JSON | Online state of each channel, valued `Online`, `Off` or `disconnected` |
| `GET /snapshot` | Raw JSON | One call returns `{"data":telemetry,"model":configuration,"status":state}`; **recommended for gateway polling** instead of three requests |
| `GET /getFunctionMap` | Unified | The function bitmap in `d.functionMap`; bits are in Appendix B of the business command reference |
| `GET /sn` | Plain text | `Model-SerialNumber`, such as `SPM02-AABBCCDDEEFF` |
| `GET /count` | Unified | `msg` is the cumulative number of `/data` and `/snapshot` calls |
| `GET /checkota` | Raw JSON | `{"otastatus":number}`, whether new firmware exists |
| `GET /low-signal-mode` | Unified | `d` is `{"mode":number}`; with a `mode` (or `value`, `state`) parameter it writes first and then returns. HTTPS also accepts the aliases `/lowSignalMode` and `/lowsignalmode` |

Fields of `/status`: `MQTTStatus`, `UDPStatus`, `WebSocketStatus`, `ModbusTCPStatus`, `wsInterval`; some models also have `LoRaWANStatus`.

### 3.2 Control and maintenance

| Endpoint | Description |
|----------|-------------|
| `GET /location` | Flash or beep to find the device |
| `GET /zeroenergy` | Reset energy counters; **irreversible** |
| `GET /restart` | Reboot (the response is sent first, the reboot follows about 1 s later) |
| `GET /ota` or `/ota?url=<firmware URL>` | Upgrade the Wi-Fi module firmware online; without `url` the default is used. Reboots by itself on success when configured to |
| `GET /mcuota` | Upgrade the meter's metering chip firmware, **reboots when done** |
| `GET /erase` | **Erase all stored settings and reboot**; use with care |
| `GET /deletewebpage` | Delete the web page file stored on the device |
| `GET /update` | Make the device download the web page file again from the cloud (needs Internet access) |
| `GET /clearlog` | Clear the log (absent on some models) |
| `GET /logfile` | Plain-text log; 404 if there is none (absent on some models) |
| `GET /hadata` | Returns `{"zero":"zeroenergy"}`, used by the built-in page for Home Assistant; ignore it |
| `GET /` | The built-in web page, when the device has one |

### 3.3 Configuration commands

```
POST /save-config
Content-Type: application/json

{"cmd":"wifi","ssid":"MyRouter","pass":"secret"}
```

The body is a command JSON from the [Business Command Reference](../ble-common/ble-business-api.en.md); `cmd` may also be written as `configType`. The response is the unified structure with `event` echoing the command. Except for the BLE-only handshake commands, all business commands work.

A few commands are **written differently** on HTTP because the older handlers used by the built-in page catch them first. See [Section 6](#6-save-config-special-cases-on-http).

### 3.4 Certificate upload

| Endpoint | Description |
|----------|-------------|
| `POST /upload` | Port 80, `multipart/form-data` upload of one PEM file, saved as the MQTT CA (`/mqtt.pem`) |
| `POST /uploadcefile` | Used by the built-in page: the body is a quoted string with newlines written as `\n`; the device strips the quotes and **drops one character at each end** before saving it as the MQTT CA. The `filename=<path>` parameter sets the path, but on port 80 it must be the **first** query parameter, so with a Web password it sits after `token` and is ignored. These quirks are awkward; prefer `/upload` or BLE `cafilestart` |
| `POST /upload` (443) | **Not supported**; returns `use HTTP :80 multipart POST /upload` |

For a large certificate, the safer way is writing it in pieces with `cafilestart` / `cafiledata` over BLE or MQTT.

### 3.5 Endpoints of other models

Relay products (SRS series) also have `/switch1`, `/switch2`, `/schedule`, `/switch-config` and `/getSchedule`. SRS products are not covered by this repository, so they are not described here.

## 4. Access policy on port 80

When HTTPS (443) is on, the Pro secured build **turns off every business endpoint on port 80**:

```json
{"ok":false,"msg":"use_https","detail":"API only on HTTPS :443","code":2000}
```

The status is **403**. Only `GET /` (the built-in page) still opens on port 80. This prevents password and token leaks over the plaintext channel.

| Branch | Port 80 |
|--------|---------|
| Basic, Basic+ | Always available (no HTTPS) |
| Lite | Always available (Lite has no HTTPS and HTTP is off by default) |
| Pro | Available while HTTPS is off; once HTTPS is on only the page remains and business endpoints return 403 |

On a 403 `use_https`, switch to `https://`.

## 5. Port 80 versus port 443

Both ports offer the same endpoints. They differ in these ways:

| Item | 80 (HTTP) | 443 (HTTPS, Pro only) |
|------|-----------|-----------------------|
| Certificate | none | Uses `/server_cert.pem` + `/server_key.pem` from the device when present; otherwise the **certificate built into the firmware**, which is shared by all devices and **cannot protect against impersonation**. If `/ca_cert.pem` is on the device, a client certificate is required |
| Methods | per route | Only `GET`, `POST`, `OPTIONS`; anything else gets 405 |
| `POST` body | Read by the web server | `Content-Length` is required, otherwise 411; the request headers plus body must not exceed **2048 bytes** in total, otherwise 413. That is tighter than the 1024-byte JSON limit, so shorten long commands |
| JSON parse failure | Not checked; treated as a missing command and returns `No data received` (2040) | Explicit `bad json` (2070) |
| Connections | One request at a time | keep-alive supported, up to 32 requests in a row on one connection |
| CORS | none | `Access-Control-Allow-Origin` is returned only when the request's `Origin` has the same host as the device |
| Unknown path | Web server default 404 | 404, `{"ok":false,"msg":"path not on HTTPS API","code":2090}` |
| `/upload` | Works | Returns error 2080 |

## 6. `/save-config` special cases on HTTP

These `configType` / `cmd` values are **matched first** on HTTP, and behave differently from the same-named commands on BLE and MQTT.

| Command | How to write it on HTTP | Description |
|---------|-------------------------|-------------|
| `mqtt` | `{"configType":"mqtt","host":"broker.example.com","port":8883,"clientid":"dev01","username":"u","password":"p","ssltls":true,"ReportFrequency":30}` | Uses **separate fields**, not the pipe-separated `data`. `enable:false` turns MQTT off. The connection is rebuilt immediately, no reboot. Response `MQTT sent successfully!` |
| `mqtr` | `{"cmd":"mqtr","data":"host\|clientid\|ssl\|port\|interval\|user\|pwd"}` | To use the **pipe string** on HTTP, use this command (the device reboots after saving). Write a plain `|` in the JSON |
| `model` | `{"configType":"model"}` | Returns **raw JSON without `ok`**, similar to `GET /model` |
| `getmqtt` | `{"configType":"getmqtt"}` | `msg` is the connected broker address, or `OFF` |
| `name` | `{"configType":"name","name":"..."}` | Device name up to 30 characters |
| `ble` | `{"configType":"ble","opass":"old","npass":"new"}` | Change the BLE password, up to 16 |
| `topic` | `{"configType":"topic","topic_post":"..","topic_set":"..","topic_response":"..","topic_metadata":".."}` | Changes all four topics |
| `ota` | `{"configType":"ota","EspOTA":"true"}` | Starts an upgrade |
| `erase` | `{"configType":"erase"}` | Erase settings and reboot |

Other legacy types (`getconfig`, `baudrate`, `ParityStop`, `Modbusaddress`, `clear`, `report`, `alarm`) belong to the built-in page; new development does not need them, use the unified commands.

The point: **do not send `{"cmd":"mqtt","data":"..."}` on HTTP**. It takes the separate-field path above, the port is read as 0 and the configuration is corrupted. Use `mqtr`, or the separate-field `mqtt`.

## 7. Examples

With `curl` (replace the IP and password with yours):

```bash
# No Web password: read one telemetry packet directly
curl http://192.168.1.50/data

# With a Web password: sign in for a token, then use it
curl "http://192.168.1.50/signin?password=mypass"
curl "http://192.168.1.50/snapshot?token=1736912345"

# Make the device flash
curl "http://192.168.1.50/location?token=1736912345"

# Change the report target
curl -X POST "http://192.168.1.50/save-config?token=1736912345" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"udp","IpAddress":"192.168.1.20","localUdpPort":8888,"Frequency":5}'

# Pro HTTPS (the built-in certificate is shared; -k skips verification, debugging only)
curl -k "https://192.168.1.50/snapshot?token=1736912345"
```

The parameter names of the `udp` command follow the [Business Command Reference](../ble-common/ble-business-api.en.md).

The [HTTP polling tool](../../tools/lan/README.en.md) in this repository handles sign-in and token renewal for you.

## 8. Troubleshooting

| Symptom | Cause |
|---------|-------|
| Connection refused or timeout | HTTP is off (Lite and Pro default to off), use BLE `enablehttp`; or the device is on another subnet |
| 403 `use_https` | Pro has HTTPS on; use `https://` |
| `need token` / `invalid token` | The device has a Web password, sign in with `/signin`; a token expires after 5 idle minutes, is pushed out of the 5 slots, or was revoked by a password change |
| HTTPS handshake fails | The TLS slots are taken by MQTTS and HTTPS is not listening; see [Overview 3.1](../overview/open-wifi-overview.en.md#31-tls-connection-limit) |
| HTTPS 413 | Request headers plus body exceed 2048 bytes |
| `/save-config` returns `No data received` | The body is empty, the JSON is invalid, or `cmd` / `configType` is missing |
