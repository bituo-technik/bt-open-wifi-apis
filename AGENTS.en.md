[中文](AGENTS.md)

# AGENTS.md — entry point for coding agents

Coding tools load [`AGENTS.md`](AGENTS.md) automatically. This file is the English text of the same rules. If the two disagree, follow `AGENTS.md`.

You are using or maintaining the **external API documentation repository for Bituo SPM / SDM Open Wi-Fi devices**. The readers are system integrators and DIY builders. There are two kinds of task:

- **A. Help a user write their own app from these docs** (BLE provisioning, LAN or cloud reads, device configuration).
- **B. Help a maintainer change the docs or the tools.**

If you are not sure which one it is, ask which **channel** they are using (BLE / Modbus TCP / HTTP / WebSocket / MQTT / UDP) and which firmware branch the device is (Basic / Basic+ / Lite / Pro). For BLE, also ask whether it is **plaintext (service A002) or secured (service A003)**.

## A0. Integrate a Wi-Fi channel (Modbus TCP / HTTP / WebSocket / MQTT / UDP / mDNS)

| Task | Read, in order | Or one file |
|------|----------------|-------------|
| Unsure which channel, or how branches differ | `docs/overview/open-wifi-overview.en.md` | `dist/open-wifi-all.complete.en.md` (everything) |
| Find the device IP | `docs/mdns/mdns-discovery.en.md` | `dist/mdns.complete.en.md` |
| Modbus TCP polling | `docs/modbus-tcp/modbus-tcp-api.en.md`, machine-readable: `spec/modbus-tcp-map.json` | `dist/modbus-tcp.complete.en.md` |
| HTTP / HTTPS | `docs/http/http-api.en.md` → `docs/ble-common/ble-business-api.en.md`; manifest: `spec/http-endpoints.json` | `dist/http.complete.en.md` |
| WebSocket | `docs/websocket/websocket-api.en.md`; manifest: `spec/websocket-api.json` | `dist/websocket.complete.en.md` |
| MQTT | `docs/mqtt/mqtt-api.en.md`; manifest: `spec/mqtt-api.json` | `dist/mqtt.complete.en.md` |
| UDP receiver | `docs/udp/udp-api.en.md`; AES-CCM test vector: `spec/udp-aes-test-vector.json` | `dist/udp.complete.en.md` |
| Parse data / handle failure | `docs/reference/telemetry-payload.en.md`, `docs/reference/error-codes.en.md`; `spec/error-codes.json` | (already inside the http / mqtt / websocket bundles) |

For Chinese, replace `en` with `zh-CN`. Hard rules for Wi-Fi channels:

1. **Read the overview capability matrix first.** Not every branch has HTTPS / Modbus TLS / WSS / UDP encryption. When a TLS slot is not available the service **falls back to plaintext**, and the client has to handle that.
2. **Success is `ok`** (unified response `ok/msg/event/d`). `code` appears only on failure. HTTP failure is usually still status 200. `code` can collide with a fixed code; decide by `event` plus the English `msg`.
3. **Look up business commands only in `docs/ble-common`.** HTTP is `POST /save-config`, MQTT goes to `/cmd`, WebSocket sends `{"cmd":...}`. A channel page describes framing and limits only. Inbound JSON is at most **1024 bytes**.
4. Channel-specific traps are in that channel's document (for example the HTTP `/save-config` exception, Modbus RSSI as an absolute value, the UDP `counter`). Follow the document. Do not guess from experience.
5. Do not write the firmware's default test account, broker address, or any real device's web password / MQTT password / broadcast key into code, examples, or logs.
6. Without hardware, test first with `tools/lan/mock_device.py`. It follows the documented behavior only and does not replace a test on a real device.

## A. Write an app: what to read for BLE, and how

| Device | Read, in order | Or one file |
|--------|----------------|-------------|
| Plaintext BLE (Basic / Basic+, `A002`) | `docs/ble-plaintext/ble-plaintext-api.en.md` → `docs/ble-common/ble-business-api.en.md` | `dist/ble-plaintext.complete.en.md` (generate with `py -3 scripts/build_bundles.py`) |
| Secured BLE (Lite / Pro, `A003`) | `docs/ble-secured/ble-secured-api.en.md` → `docs/ble-common/ble-business-api.en.md` → `docs/ble-secured/ble-advertising.en.md` only when reading values from advertising; `docs/ble-secured/crypto-protocol.en.md` for the handshake byte layout | `dist/ble-secured.complete.en.md` |

For Chinese, replace `en` with `zh-CN`. Machine-readable manifests are in `spec/`: `ble-business-commands.json` (commands and fields), `ble-plain-api.json` / `ble-secured-api.json` (transport), `ble-secured-test-vectors.json` (known-answer crypto vectors).

### Hard rules

1. **Use only commands, fields, and UUIDs that appear in the docs.** If it is not there, it does not exist. Emit a TODO and say why. Do not invent one.
2. **Do not mix the two channels.** Plaintext is `A002 / C303 / C304 / C305`. Secured is `A003 / C313 / C314 / C315`. On the secured channel, **do not** send `pass` / `blepassword` / `resetauth`.
3. Compare the device's `msg` and error codes as English text. Do not translate business JSON keys.
4. Commands are **strictly serial**: write one → wait for the response whose `event` matches → then write the next.
5. The only proof that provisioning succeeded is the snapshot `IP` becoming a dotted IPv4 address. A successful `wifi` response means only "accepted, starting to join the router". Wi-Fi is 2.4 GHz only.
6. Command sets differ by model. Handle failure from `ok` / `msg`. Do not assume every command exists. Do not implement `switch-config`.
7. Secured channel: do not change a single character of the algorithm parameters (curve `secp256r1`, PBKDF2 10000 iterations, HKDF `info` strings, CCM nonce construction). **Check your own PBKDF2 / HKDF / AES-CCM against `spec/ble-secured-test-vectors.json` before connecting to a real device.**
8. On the secured channel, `step=3` with no local session state means **disconnect and reconnect**. Do not send J-PAKE again.
9. Do not log LTK / session_key / broadcast_key by default. Example PIN / SN values are fictional.

### Suggested implementation order

Scan → connect → subscribe to notifications → (plaintext: `pass`; secured: handshake) → `wifi` → poll the snapshot `IP` → then electrical reads, `model`, `getFunctionMap`, `mqttdata`. Section 2 of each transport document has a prompt you can copy whole. Section 9 is the acceptance checklist.

## B. Maintenance: read this before editing the repo

1. [`REPO_ORGANIZATION.en.md`](REPO_ORGANIZATION.en.md): layout and the **shared business document** rule (§3). Entry pages are a language choice; the body is `.zh-CN.md` / `.en.md`.
2. A business-command change goes **only** into `docs/ble-common/*` (Chinese and English together) plus `spec/ble-business-commands.json`. Do not copy the command table back into a channel document.
3. A transport change goes only into `docs/ble-plaintext` or `docs/ble-secured` (Chinese and English together, same section numbers).
3a. A Wi-Fi channel change (`docs/{mdns,modbus-tcp,http,websocket,mqtt,udp}`) updates Chinese and English together. Fields change only in `docs/reference/telemetry-payload.*`. Error codes change only in `docs/reference/error-codes.*` (and `spec/error-codes.json`). Modbus registers change in `spec/modbus-tcp-map.json` and in both documents' tables (`check_docs.py` compares every address). The firmware-version line at the top of a channel document names the versions that were checked. When behavior disagrees with a published page, record it under "Open points" in both `CHANGELOG.zh-CN.md` and `CHANGELOG.en.md`, and write the page from what the device does.
3b. An entry-page change (root `README`, `docs/README`, `tools/**/README`, `REPO_ORGANIZATION`, `CHANGELOG`, `AGENTS`) updates both languages. Do not shrink `AGENTS.md` to a page that only links to the two languages.
4. After editing `tools/ble-secured/web-ble-secured-console.html` or `ble_secured_crypto.js`, run `py -3 tools/ble-secured/bundle_offline_html.py` to regenerate `*.offline.html` (do not hand-edit the generated file).
5. Before committing, run:

```bat
py -3 scripts/check_docs.py
py -3 scripts/check_test_vectors.py
node scripts/check_test_vectors.mjs
```

After editing `tools/lan/*.py`, at least run `py -3 -m py_compile tools/lan/*.py` and exercise the matching tool against `mock_device.py` (see [`tools/lan/README.en.md`](tools/lan/README.en.md)).

6. Record the change in both `CHANGELOG.zh-CN.md` and `CHANGELOG.en.md`, and name the firmware version it was checked against. `CHANGELOG.md` is only the language-choice page.
7. **Do not commit:** `tools/ble-secured/ble_crypto_client_cache.json`, a real-device PIN / LTK / key, or firmware. Do not put internal build codenames into the docs.
8. When a fact is uncertain (firmware behavior, model differences), ask the user or record it under "Open points" in the CHANGELOG. **Do not** leave a `TBD` or similar placeholder in a customer-facing document.

## Terms

Firmware branches: Basic / Basic+ (plaintext BLE), Lite / Pro (secured BLE). The overview capability matrix is the authority for which channels each branch supports. PIN = the 8 digits on the meter body (the 11 digits under the QR convert to it). LTK = long-term key; the device persists it only after Wi-Fi association succeeds.
