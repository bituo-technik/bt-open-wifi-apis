[中文](README.zh-CN.md)

# bt-open-wifi-apis

The **SPM / SDM Open Wi-Fi API** for system integrators and DIY builders: interface docs, runnable tools, and machine-readable manifests. Use them to write an app, or to connect a meter to a system you already have. This is a public repository. It does not contain firmware.

Published entry point: [SPM/SDM Open Wi-Fi API Overview](https://docs.bituo-technik.com/device-api/spm-sdm-open-wi-fi-api-overview) · How this repo is organized: [`REPO_ORGANIZATION.en.md`](REPO_ORGANIZATION.en.md) · AI entry: [`AGENTS.en.md`](AGENTS.en.md)

## Which document should I read?

### Wi-Fi channels (LAN or cloud: read data, change configuration)

Start with the [overview](docs/overview/open-wifi-overview.en.md). Confirm the firmware branch (Basic / Basic+ / Lite / Pro) and which channels that branch actually has, then pick a channel:

| Task | Document | Tool |
|------|----------|------|
| Find the device IP | [mDNS discovery](docs/mdns/mdns-discovery.en.md) | `discover_mdns.py` |
| PLC / industrial gateway / EMS polling | [Modbus TCP](docs/modbus-tcp/modbus-tcp-api.en.md) | `modbus_poll.py` |
| Scripts, gateways, configuration | [HTTP / HTTPS](docs/http/http-api.en.md) | `http_poll.py` |
| Local live push | [WebSocket](docs/websocket/websocket-api.en.md) | `ws_client.py` |
| Cloud or self-hosted broker | [MQTT](docs/mqtt/mqtt-api.en.md) | `mqtt_monitor.py` |
| High-rate one-way readings | [UDP](docs/udp/udp-api.en.md) | `udp_listen.py` |
| Fields and errors | [Telemetry payload](docs/reference/telemetry-payload.en.md), [error codes](docs/reference/error-codes.en.md) | |

The tools live in [`tools/lan`](tools/lan/README.en.md). Without hardware, use `mock_device.py` (a fake meter). Every channel shares one business-command set: [Business Command Reference](docs/ble-common/ble-business-api.en.md).

### BLE channels (provisioning and near-field control)

Check the Bluetooth service first. **`A002` = plaintext, `A003` = secured.** A given device exposes only one of them.

| Your device | Step 1: transport (connect, unlock / handshake) | Step 2: business layer (commands and fields) | Reference implementation |
|-------------|--------------------------------------------------|-----------------------------------------------|--------------------------|
| **Basic / Basic+** (plaintext, `A002`) | [Plaintext BLE API](docs/ble-plaintext/ble-plaintext-api.en.md) | [Business Command Reference](docs/ble-common/ble-business-api.en.md) | [`tools/ble-plaintext`](tools/ble-plaintext/README.en.md) |
| **Lite / Pro** (secured, `A003`) | [Secured BLE API](docs/ble-secured/ble-secured-api.en.md); cryptography detail in the [protocol reference](docs/ble-secured/crypto-protocol.en.md) | Same reference (shared by both channels) | [`tools/ble-secured`](tools/ble-secured/README.en.md) |

After the transport layer is unwrapped, the business JSON of the two BLE channels is **identical**, so the commands are maintained once in `docs/ble-common`. See [`REPO_ORGANIZATION.en.md` §3](REPO_ORGANIZATION.en.md).

To **get the meter onto Wi-Fi only**: read "Quick start" in the transport document you picked, then [Business Command Reference §2](docs/ble-common/ble-business-api.en.md#2-wi-fi-provisioning-business-commands). To try it yourself, see Tools below.

## Layout

```text
docs/
  overview/         Wi-Fi overview: firmware branches, channel matrix, how to choose
  mdns/ modbus-tcp/ http/ websocket/ mqtt/ udp/   one directory per Wi-Fi channel
  reference/        telemetry payload and error codes (shared by every channel)
  ble-common/       business commands shared by every channel (zh-CN / en)
  ble-plaintext/    plaintext BLE transport (A002)
  ble-secured/      secured BLE transport (A003) + protocol reference
  README.md         language choice    SUMMARY.md  Gitbook table of contents
tools/
  lan/              Wi-Fi channel CLIs + fake meter
  ble-plaintext/ ble-secured/   BLE demo tools (web + Windows)
spec/               machine-readable command lists, channel manifests, error codes, test vectors
scripts/            checks and single-file bundle generation
dist/               generated output (not committed)
```

## Tools

```bat
:: Wi-Fi channels (Python 3.9+ only). Example: find a meter and read Modbus
cd tools\lan & py -3 discover_mdns.py & py -3 modbus_poll.py <device-ip>


:: Plaintext BLE, Windows
cd tools\ble-plaintext & py -3 -m pip install -r requirements.txt & py -3 ble_plain_gui.py

:: Secured BLE, Windows
cd tools\ble-secured & py -3 -m pip install -r requirements.txt & py -3 ble_secured_gui.py
```

Web (Chrome / Edge) and phone instructions are in [`tools/README.en.md`](tools/README.en.md). The secured page to hand to a customer is the **single file** [`web-ble-secured-console.offline.html`](tools/ble-secured/web-ble-secured-console.offline.html). Host it on any HTTPS static site.

## Maintenance

| Command | What it does |
|---------|----------------|
| `py -3 scripts/check_docs.py` | Checks links / anchors, Chinese–English heading alignment, `spec` against the docs (command set, Modbus registers, error codes, mDNS names), and leftover placeholders |
| `py -3 scripts/check_test_vectors.py` · `node scripts/check_test_vectors.mjs` | The two crypto reference implementations must agree on the test vectors. The Python script also checks the UDP AES-CCM vector |
| `py -3 scripts/build_bundles.py` | Writes `dist/*.md` single-file bundles (one per channel, plus the full `open-wifi-all`) for Gitbook paste or for handing to an AI |
| `py -3 tools/ble-secured/bundle_offline_html.py` | Regenerates the offline single-file page after the secured web console changes |

Entry documents (this file, `docs/README`, `tools/**/README`, `REPO_ORGANIZATION`, `CHANGELOG`, `AGENTS`) exist in Chinese and English. Update both when you change one. `AGENTS.md` is the copy that coding tools load automatically.

## Do not commit

`tools/ble-secured/ble_crypto_client_cache.json` (it contains the LTK), and any real-device PIN / LTK / key screenshot. `.gitignore` already excludes the cache file.
