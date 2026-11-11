# SPM / SDM Open Wi-Fi API Overview

> Status: first release | Applies to: SPM / SDM Open Wi-Fi series (ESP32-8685 / C6) | Firmware versions covered: Basic / Lite 5.1.16, Basic+ 1.2.12, Pro 3.1.19

This page is the entry to the whole API. Read it in this order, and do not start with the crypto protocol:

1. Section 2: confirm the meter is Basic, Basic+, Lite, or Pro.
2. Section 4: pick one channel for the job you actually have.
3. Open only that page. Provisioning and read/write go through GATT. If you need electrical values with no connection, open encrypted business advertising.

## 1. Introduction

Open Wi-Fi meters offer local and cloud communication:

- **Local network**: HTTP / HTTPS, WebSocket, UDP reports, Modbus TCP, mDNS discovery.
- **Cloud**: MQTT / MQTTS (also usable with a private broker).
- **Near-field from a phone**: BLE (plaintext or secured) for provisioning and local control.

All channels share one set of **business commands** (`cmd`) and one response shape `ok / msg / event / d`. Commands are maintained in a single place: the [BLE Business Command Reference](../ble-common/ble-business-api.en.md). Each channel page only describes how to connect, how messages are wrapped, and the limits.

## 2. Firmware branches and hardware

Product lines are separated by firmware branch. **Channels differ between branches**, so check before integrating.

| Branch | Basic (8685) | Basic+ (8685) | Lite (8685) | Pro (C6) |
|--------|--------------|---------------|-------------|----------|
| Target hardware | SPM / SDM | SDM01 | SPM / SDM | SDM01 Gen2 |
| Latest version | B_5.1.14 / B_6.1.7 | BPlus_1.2.8 / BPlus_2.2.4 | Lite_5.1.11 / Lite_6.1.4 | Pro_V3.1.11 |
| Core features | Plaintext BLE, plaintext Wi-Fi | Plaintext BLE, Wi-Fi can be encrypted | Secured BLE, plaintext Wi-Fi | Secured BLE, Wi-Fi can be encrypted |
| Wi-Fi TX power | 0 dB | 13 dB | 0 dB | 13 dB |
| Lifecycle | NRND | NRND | Active | Active |

Notes:

1. `B_6.1.7` is for the SDM01 Combo with the UART external flashing pins; `B_5.1.14` is for SPM01, SPM02, the SDM01 Combo with JTAG flashing pins, and SDM02.
2. Basic+ was the Gen1 EV / PV version and has been replaced by SDM01 Gen2. At most **1** TLS connection at a time.
3. Lite's BLE encryption covers provisioning and data advertising. On Wi-Fi only MQTT supports TLS 1.2 / 1.3; HTTP, Modbus TCP and WebSocket have no TLS.
4. Pro's BLE encryption covers provisioning and data advertising. On Wi-Fi at most **2** TLS connections at a time.

### 2.1 How to tell the branch

| You want to know | How to read it |
|------------------|----------------|
| Plaintext or secured BLE | Advertised service UUID: `A002` plaintext, `A003` secured |
| Firmware version | MQTT `mdata.fwVer`, `FWVersion` in telemetry, HTTP `/snapshot`, Modbus register 997 |
| Which channels are on | `{"cmd":"getFunctionMap"}`; bits are in [Business Command Reference Appendix B](../ble-common/ble-business-api.en.md#appendix-b-functionmap-bits) |

## 3. Channel capability matrix

| Channel | Basic | Basic+ | Lite | Pro |
|---------|:-----:|:------:|:----:|:---:|
| BLE plaintext (`A002`) | ✅ | ✅ | ❌ | ❌ |
| BLE secured (`A003`) | ❌ | ❌ | ✅ | ✅ |
| MQTT (1883) | ✅ | ✅ | ✅ | ✅ |
| MQTTS (TLS) | ✅ | ✅ | ✅ | ✅ |
| HTTP (80, plaintext) | ✅ on by default | ✅ on by default | ✅ off by default | ✅ off by default |
| HTTPS (443) | ❌ | ❌ | ❌ | ✅ |
| Modbus TCP (502) | ✅ | ✅ | ✅ | ✅ |
| Modbus TCP over TLS | ❌ | ✅ | ❌ | ✅ |
| WebSocket (81) | ✅ | ✅ | ✅ | ✅ |
| WebSocket over TLS (WSS) | ❌ | ✅ | ❌ | ✅ |
| UDP report (plaintext) | ✅ | ✅ | ✅ | ✅ |
| UDP report (AES-CCM) | ❌ | ❌ | ✅ | ✅ |
| mDNS discovery | ✅ | ✅ | ✅ | ✅ |

Factory HTTP state: Basic and Basic+ turn HTTP on at every boot. Lite and Pro leave it off until the BLE command `enablehttp` turns it on. On Pro, once HTTPS is on, business endpoints on port 80 return 403; see the [HTTP page](../http/http-api.en.md#4-access-policy-on-port-80).

For **UDP AES-CCM**, trust the meter in front of you. The published matrix says both Lite and Pro support it. On Lite `5.1.16` the datagram is always plaintext. The encrypted datagram appears only on Pro `3.1.19`, and only while HTTPS is on. Details are in [UDP Section 4](../udp/udp-api.en.md#4-aes-ccm-encrypted-datagram).

### 3.1 TLS connection limit

Device memory only allows a fixed number of TLS services at once: Basic+ **1**, Pro **2**. Services that can take a TLS slot are MQTTS, HTTPS (443), WSS (81) and Modbus TLS (502).

- When more TLS services are enabled than there are slots, they start in priority order **MQTTS > HTTPS > WSS > Modbus TLS**.
- A service that does not get a slot behaves as follows: MQTTS keeps its slot, HTTPS does not listen on 443, WSS and Modbus fall back to plaintext.
- Before accepting a new TLS connection the device checks the global slots and does not handshake if none is free.
- Reuse existing connections; do not open a new TLS session for every poll.

## 4. Choosing a channel

| What you want to do | Recommended channel | Page |
|---------------------|---------------------|------|
| Stream data to the cloud and send commands | MQTT / MQTTS | [MQTT](../mqtt/mqtt-api.en.md) |
| LAN gateway polling on demand, changing settings | HTTP (HTTPS on Pro) | [HTTP](../http/http-api.en.md) |
| Local hub (for example Home Assistant) receiving a live stream | WebSocket | [WebSocket](../websocket/websocket-api.en.md) |
| Low-latency readings for export limiting or dynamic load balancing | UDP report or Modbus TCP | [UDP](../udp/udp-api.en.md), [Modbus TCP](../modbus-tcp/modbus-tcp-api.en.md) |
| PLC, industrial gateway, EMS | Modbus TCP | [Modbus TCP](../modbus-tcp/modbus-tcp-api.en.md) |
| Discover meters on the LAN automatically | mDNS | [mDNS](../mdns/mdns-discovery.en.md) |
| Phone app provisioning and near-field control | BLE | [BLE plaintext](../ble-plaintext/ble-plaintext-api.en.md), [BLE secured](../ble-secured/ble-secured-api.en.md) |

## 5. Common conventions

### 5.1 Commands and responses

- A command is JSON with `cmd` as the command name. Command names and fields mean the same on MQTT, WebSocket, HTTP `/save-config` and BLE; see the [BLE Business Command Reference](../ble-common/ble-business-api.en.md).
- Responses are `{"ok":true,"msg":"","event":"<command>","d":{...}}`. A failure adds an integer `code`; a success has **no** `code`.
- Apart from BLE, channels need **no** `pass` / `auth` handshake. HTTP needs a token once a Web password is set; see the [HTTP page](../http/http-api.en.md#2-session-and-authentication).
- One inbound JSON message is at most **1024** bytes; longer ones are rejected or silently dropped.

### 5.2 Telemetry

The same telemetry JSON appears in MQTT `/data`, HTTP `/data`, WebSocket pushes, UDP datagrams and `/snapshot.data`. Fields are maintained in one place: [Telemetry payload](../reference/telemetry-payload.en.md).

### 5.3 Error codes

`code` in a failure response is split by channel: BLE 1000s, HTTP 2000s, MQTT 3000s, WebSocket 4000s. See the [Error code reference](../reference/error-codes.en.md).

## 6. Documentation map

| Page | Content |
|------|---------|
| [Telemetry payload](../reference/telemetry-payload.en.md) | Fields per model, meaning of `TP`, generic format |
| [Error code reference](../reference/error-codes.en.md) | `code` ranges, fixed codes, configuration subcodes |
| [MQTT](../mqtt/mqtt-api.en.md) | Topics, data reports, commands, MQTTS setup |
| [HTTP / HTTPS](../http/http-api.en.md) | Sign-in, endpoint list, POST body differences |
| [WebSocket](../websocket/websocket-api.en.md) | Connection, push interval, heartbeat |
| [UDP report](../udp/udp-api.en.md) | Target setup, datagram, AES-CCM datagram |
| [Modbus TCP](../modbus-tcp/modbus-tcp-api.en.md) | Register map, control registers, connection notes |
| [mDNS](../mdns/mdns-discovery.en.md) | Hostname rules, verification |
| [BLE Business Command Reference](../ble-common/ble-business-api.en.md) | The only description of all commands |
| [BLE plaintext](../ble-plaintext/ble-plaintext-api.en.md) / [BLE secured](../ble-secured/ble-secured-api.en.md) | The two BLE transports |
| [Encrypted business advertising](../ble-secured/ble-advertising.en.md) | Read electrical values from advertising, with no GATT connection (Lite / Pro only) |

For AI use, single-file bundles are described in [`AGENTS.en.md`](../../AGENTS.en.md); machine-readable interface lists are in [`spec/`](../../spec/).
