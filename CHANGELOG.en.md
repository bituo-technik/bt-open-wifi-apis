[中文](CHANGELOG.zh-CN.md)

# Changelog

Newest first. "Firmware checked" names the firmware version the docs or tools were compared with.

## 2026-10-17 — Wording for a public repository

### Documents

- Product lines are SPM / SDM only. An internal R&D umbrella name is no longer used. Covered firmware versions are written as Basic / Lite 5.1.16, Basic+ 1.2.12, and Pro 3.1.19.
- The repository is described as public. Readers are system integrators and DIY builders. One internal note that should not be public was removed.
- Encrypted business advertising is no longer mixed into the GATT page or the crypto protocol. It has its own page, `docs/ble-secured/ble-advertising.*`.

## 2026-10-17 — Entry documents split by language

### Documents

- `README.md`, `docs/README.md`, `tools/README.md`, `tools/lan/README.md`, `tools/ble-plaintext/README.md`, `tools/ble-secured/README.md`, `REPO_ORGANIZATION.md`, and `CHANGELOG.md` are now language-choice pages. The body of each is `*.zh-CN.md` and `*.en.md` in the same directory. A page no longer mixes the two languages.
- `AGENTS.md` stays a complete Chinese document. Coding tools load that filename automatically, so it cannot shrink to a pair of language links. The English text is `AGENTS.en.md`. If the two disagree, `AGENTS.md` wins.
- Links from the API documents to the tool notes, the CHANGELOG, and AGENTS now point at the same language. The reading-path entries in `docs/SUMMARY.md` are split by language.
- `scripts/check_docs.py` now checks that every `tools/lan` script is named in both language READMEs.

## 2026-10-07 — First complete Wi-Fi channel set

**Firmware checked:** Basic / Lite `5.1.16`, Basic+ `1.2.12`, Pro `3.1.19`; also the published Gitbook pages for Overview / MQTT / mDNS / Modbus TCP (2026-05 through 2026-06).

### Documents

- `docs/overview/open-wifi-overview`: firmware branches, channel capability matrix, TLS slot limit (priority MQTTS > HTTPS > WSS > Modbus TLS), how to choose a channel.
- `docs/mdns/`, `docs/modbus-tcp/`, `docs/http/`, `docs/websocket/`, `docs/mqtt/`, `docs/udp/`: connection, limits, examples, and troubleshooting for each channel. WebSocket and UDP were written new. HTTP had no standalone document before.
- `docs/reference/telemetry-payload` (telemetry fields, shared by four channels) and `docs/reference/error-codes` (unified response, channel base + subcode, fixed codes, colliding numbers).
- Rewrote `docs/SUMMARY.md`, `docs/README.md`, the root `README.md`, `AGENTS.md`, and `REPO_ORGANIZATION.md`.

### Machine-readable files and tools

- `spec/`: `modbus-tcp-map.json` (register map), `http-endpoints.json`, `mqtt-api.json`, `websocket-api.json`, `udp-api.json`, `mdns-discovery.json`, `capabilities.json`, `error-codes.json`, `udp-aes-test-vector.json`.
- `tools/lan/`: `discover_mdns.py`, `modbus_poll.py`, `http_poll.py`, `ws_client.py`, `udp_listen.py` (can decrypt AES-CCM), `mqtt_monitor.py`, `mock_device.py` (fake meter), `cmdarg.py` (accepts the quoting style that PowerShell 5.1 leaves after it drops quotes).
- `scripts/check_docs.py` gained: `spec` validity and LF line endings, a per-address Modbus comparison against both documents, error-code subcodes / fixed codes present in both languages, the mDNS naming regex, and a check that every `tools/lan` tool is named in the README. `check_test_vectors.py` gained the UDP AES-CCM vector. `build_bundles.py` gained per-channel Wi-Fi bundles and `open-wifi-all`.

### Open points

Confirm these on a real device, or with a firmware colleague, then update the docs.

1. **Modbus locate register:** Gitbook says `10000 (0x2710)`. On the device, the Wi-Fi module's Modbus TCP handler only acts on `10001` (clear) and `10002` (locate). `10000` is the same function on the meter-side MCU.
2. **Modbus connection behavior:** Gitbook says "one connection only, socket reset after every read, must reconnect every time". The device allows up to 2 on Basic / Lite / Pro and 1 on Basic+, keeps the connection, drops it after 30 seconds idle (12 seconds on a custom firmware), and answers only the latest frame. The docs still say reconnecting every time is acceptable.
3. **Modbus register 994 (RSSI):** Gitbook says negative dBm. The device writes `-rssi` into an unsigned register, so the value read back is the absolute value (for example 68). The Gitbook examples of MCU version vs Wi-Fi firmware version are also swapped (989 is the MCU, 997 is the Wi-Fi firmware).
4. **`commonmode = 1`:** Switching this value changes both the Modbus read map and the telemetry format. The docs describe only the default layout (`commonmode = 0`). The generic-format register layout is not written down. `mda` / `minvert` are only mentioned.
5. **Which branches get UDP AES-CCM:** The published matrix says both Lite and Pro. Lite `5.1.16` always sends plaintext. The encrypted datagram appears only on Pro, and only while HTTPS is on. The matrix keeps the published statement and adds a footnote.
6. **mDNS hostname:** The published page says `VARIANT` reflects an HTTP implementation difference. In practice `_01` is Basic / Lite SDM01_3PN and SDM01_1PN, `_02` is Basic+ / Pro, and other Basic / Lite models have no variant field. The hostname is the editable device name (`deviceName`). After a rename, a prefix filter stops matching. The docs say so.
7. **MQTT default report interval:** The device default is 5 seconds; the published docs say 30 seconds. The docs tell the reader to trust the device's `MI`.
8. **`TP`:** This is a model code (always 8 on SDM01 Gen2), not a phase count. The older published claim "1 = single-phase, 3 = three-phase" holds only for SPM01 / SPM02.
9. **`/uploadcefile`** has awkward behavior (parameter order, one character dropped at each end). The docs record it as it is and recommend `/upload` or BLE `cafilestart`.
10. Idle timeout of a Modbus TLS connection, and `mqtt_monitor.py` against a real broker, are not verified yet.

### What was verified

- `check_docs.py` and `check_test_vectors.py` passed. Every `tools/lan` script compiled.
- `modbus_poll.py`, `http_poll.py` (including token re-login), `ws_client.py`, and `udp_listen.py` (plaintext and AES-CCM) ran against `mock_device.py`. `discover_mdns.py` found a real LAN device on both the built-in resolver and the zeroconf path.
- Modbus / HTTP / WebSocket / UDP were **not** verified on a real meter (the meter that was discovered had Modbus and HTTP off by default). `mqtt_monitor.py` was not run against a broker.

### Security note for maintainers

- Do not put a test broker address or account into a document, an example, or a tool.

## 2026-10-07 — Initial merge: plaintext BLE and secured BLE

**Firmware checked:** Basic `5.1.15` (example responses checked on an SDM01_3PN). The Lite / Pro secured handshake follows `BLE secured-channel API document V2` and was run on a real device with this repo's tools: handshake, encrypted provisioning, read, and write.

### Repository

- Created `bt-open-wifi-apis` by merging `Meter-BLE-Plaintext-API` and `Meter-BLE-Secured-API` (the original directories were left in place).
- Layout: `docs/{ble-common,ble-plaintext,ble-secured}`, `tools/{ble-plaintext,ble-secured}`, `spec/`, `scripts/`.
- Added `README.md` / `AGENTS.md` / `REPO_ORGANIZATION.md`. The repo is private. Cache files and keys are excluded.
- Removed `.map` / `.d.ts` from the secured tool's `vendor/` (3.4 MB down to about 1.2 MB). The offline single file was regenerated successfully.

### Documents

- **Business JSON merged into one document:** added `docs/ble-common/ble-business-api.*`. Wi-Fi provisioning, the command reference, snapshot reads, business error codes, and the appendices moved over from the old plaintext document. The plaintext and secured documents keep only the transport layer. The old secured document's §6 / §7 / §8 / appendix were summaries and already disagreed with the plaintext version; they are now one text.
- **Filled gaps:**
  - optional `wifi` fields `enableble` / `enablehttps` (on Pro, `enablehttps` also decides whether the UDP payload is encrypted);
  - the `commonmode` command (missing from the old docs, present in `spec`);
  - `parityStop = 3` (N82) for `modbus`;
  - secured channel: pairing code (11 digits under the QR) to an 8-digit PIN, the `step=3` trap, `ble-crypto-reset` limits, `nonce` direction / counter, the device folding GATT away after Wi-Fi connects, and browser / phone support;
  - the English secured document brought up to the same content as the Chinese one;
  - the authoritative crypto protocol reference (firmware team V2, Chinese and English) moved into `docs/ble-secured/crypto-protocol.*`, and external citations became in-repo links.
- Added `spec/ble-secured-test-vectors.json` (known answers for PBKDF2 / HKDF / AES-CCM / pairing code, fictional inputs) and two check scripts. The Python and JS reference implementations agree.
- Split `spec/ble-plain-api.json` into `ble-business-commands.json` (shared) + `ble-plain-api.json` + `ble-secured-api.json`. Name prefixes match the docs.
- Removed `【待确认】` / `[TBD]` / `【待填】` placeholders from the docs. What could be checked was checked. Tool hosting addresses now say they follow the publishing channel.

### Tools

- Secured web page: 11-digit pairing code, right-sidebar overlap fix, no repeated handshake on `step=3`, business-advertising capability hint, Modbus parity / stop bits 0–3, offline single file (`window.__OFFLINE_BUNDLE__`).
- Removed the unused `pinFromSn` (a function that derived a PIN directly from the SN; it should not be exposed). Self-test vectors now use the fictional `12345678 / AABBCCDDEEFF`. Example pairing codes are fictional.
- Plaintext and secured help text gained `parityStop 3 = N82`. The English secured help was filled in.

### Open points / follow-up

- The plaintext tools (Windows GUI and web page) still have no parity / stop-bit control on the Modbus panel (fixed `parityStop=0`).
- Official hosted page URL and Windows tool download URL (document §10 says they will be added when published).
- When this entry was written, `docs/overview` and the MQTT / HTTP / mDNS / WebSocket / UDP / Modbus TCP documents were not in the repo yet. The later entry from the same day added them.
- Name prefixes: the docs say `SDM` / `SPM`, while both web pages also accept `SRS` (the relay product line). Whether to unify that is a product decision.
- On Pro firmware, with `enablehttps` on, the UDP payload is encrypted JSON (`ct` / `tag` / `counter`). There is still no external document for that key and format.
