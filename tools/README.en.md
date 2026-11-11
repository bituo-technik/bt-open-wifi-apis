[中文](README.zh-CN.md)

# Demo tools

Each BLE channel has its own tools. The protocol matches `docs/`. Use them to **see how the device behaves before writing an app**, and for on-site provisioning.

## Choose a tool

| Device | Service | Tool directory | Document |
|--------|---------|----------------|----------|
| Basic / Basic+ | `0xA002` (plaintext) | [`ble-plaintext/`](ble-plaintext/README.en.md) | [Plaintext BLE API](../docs/ble-plaintext/ble-plaintext-api.en.md) |
| Lite / Pro | `0xA003` (secured) | [`ble-secured/`](ble-secured/README.en.md) | [Secured BLE API](../docs/ble-secured/ble-secured-api.en.md) |

The Wi-Fi channels (mDNS discovery, Modbus TCP, HTTP, WebSocket, UDP, MQTT) have a separate set of command-line tools and a **fake meter** (so you can develop without hardware). See [`lan/`](lan/README.en.md).

If you do not know which kind of device you have: after scanning, look at the GATT service. `A002` uses the plaintext tools, `A003` uses the secured tools.

The business JSON (Wi-Fi, queries, MQTT, Modbus, UDP, OTA, …) is the same on both channels: [Business Command Reference](../docs/ble-common/ble-business-api.en.md).

## Common tasks

| Task | Use |
|------|-----|
| On-site provisioning from a phone (Android Chrome / Edge) | A web page hosted on HTTPS: plaintext `web-ble-console.html`, secured `web-ble-secured-console.offline.html` (one file) |
| Full debugging on Windows, including business advertising | `ble_plain_gui.py` / `ble_secured_gui.py` |
| Change the web UI, or have an AI change it | Secured: `web-ble-secured-console.html` (split files). After editing, run `bundle_offline_html.py` |
| Check your own crypto implementation | `spec/ble-secured-test-vectors.json` + `scripts/check_test_vectors.*` |

iOS Safari has no Web Bluetooth. Chrome on Windows usually does not support `watchAdvertisements` (use the Windows tool to listen for business advertising).
