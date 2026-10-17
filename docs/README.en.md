[中文](README.zh-CN.md)

# Reading paths

## Read meter data over the LAN or the cloud (Wi-Fi channels)

1. Read the **overview** first and confirm the firmware branch and which channels it has: [overview/open-wifi-overview.en.md](overview/open-wifi-overview.en.md).
2. Pick a channel (section 4 of the overview is the comparison):
   - Find the device IP: [mDNS discovery](mdns/mdns-discovery.en.md)
   - PLC / industrial gateway / EMS polling: [Modbus TCP](modbus-tcp/modbus-tcp-api.en.md)
   - Scripts, gateways, device configuration: [HTTP / HTTPS](http/http-api.en.md)
   - Local live push: [WebSocket](websocket/websocket-api.en.md)
   - Cloud or self-hosted broker: [MQTT](mqtt/mqtt-api.en.md)
   - High-rate one-way readings (PV export limit, dynamic load balancing): [UDP](udp/udp-api.en.md)
3. Data fields: [telemetry payload](reference/telemetry-payload.en.md). On failure: [error codes](reference/error-codes.en.md).
4. Configuration commands (HTTP, MQTT, and WebSocket share one `cmd` set): [Business Command Reference](ble-common/ble-business-api.en.md).
5. Command-line tools and the fake meter: [`tools/lan`](../tools/lan/README.en.md).

## Provision Wi-Fi over BLE, or read electrical values and configure the device

1. Identify the device: after scanning, look at the GATT service. **`A002` = plaintext (Basic / Basic+)**, **`A003` = secured (Lite / Pro)**.
2. Read the matching **transport** document (how to connect, unlock or handshake, and reconnect):
   - Plaintext: [ble-plaintext/ble-plaintext-api.en.md](ble-plaintext/ble-plaintext-api.en.md)
   - Secured: [ble-secured/ble-secured-api.en.md](ble-secured/ble-secured-api.en.md)
3. Read the **business layer** (which commands to send and which fields to read; shared by every channel): [ble-common/ble-business-api.en.md](ble-common/ble-business-api.en.md).
4. Only when implementing the secured channel: [protocol reference](ble-secured/crypto-protocol.en.md) (J-PAKE / ZKP binary layout, advertising manufacturer data).

## Hand the documentation to an AI

Run `py -3 scripts/build_bundles.py` and give the AI the **single bundle file** for that channel from `dist/` (see [`AGENTS.en.md`](../AGENTS.en.md)):

| Task | File to give the AI |
|------|---------------------|
| Modbus TCP integration | `dist/modbus-tcp.complete.en.md` |
| HTTP / WebSocket / MQTT integration | `dist/http.complete.en.md`, `dist/websocket.complete.en.md`, `dist/mqtt.complete.en.md` (business commands, telemetry, and error codes are already included) |
| UDP receiver | `dist/udp.complete.en.md` |
| The whole Wi-Fi side | `dist/open-wifi-all.complete.en.md` |
| Plaintext / secured BLE | `dist/ble-plaintext.complete.en.md` / `dist/ble-secured.complete.en.md` |

## Document map

| Document | Contents | Maintenance rule |
|----------|----------|------------------|
| `overview/open-wifi-overview.en.md` | Firmware branches, channel matrix, TLS slot limits, how to choose a channel | Entry page; change this first when a channel changes |
| `mdns/` `modbus-tcp/` `http/` `websocket/` `mqtt/` `udp/` | Each Wi-Fi channel: connection, framing, limits, examples, troubleshooting | Channel-specific only. Link commands and fields to the shared docs |
| `reference/telemetry-payload.en.md` | Telemetry JSON fields (shared by MQTT / HTTP / WebSocket / UDP) | **One** English body; Chinese is the sibling `.zh-CN.md` |
| `reference/error-codes.en.md` | Unified error codes (`code`, channel base, subcodes) | **One** English body, kept in sync with `spec/error-codes.json` |
| `ble-common/ble-business-api.en.md` | Business commands, fields, responses, appendices (functionMap bits / model short keys) | **One** English body, shared by every channel |
| `ble-plaintext/ble-plaintext-api.en.md` | Plaintext BLE transport: UUIDs, unlock (`pass`), request / response matching, reconnect, MTU | Plaintext-channel specifics only |
| `ble-secured/ble-secured-api.en.md` | Secured BLE transport: UUIDs, credentials, `step`, key-derivation summary, envelope, reconnect | Secured-channel specifics only |
| `ble-secured/crypto-protocol.en.md` | Authoritative secured-channel protocol reference (from the firmware team) | If it conflicts with the previous document, this one wins |

Command names, field names, and device `msg` strings stay in English as the device sends them. Every API document has a `zh-CN` and an `en` version with matching section numbers. The "Source" line at the top of each channel document names the firmware version it was checked against.
