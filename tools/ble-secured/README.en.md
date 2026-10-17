[中文](README.zh-CN.md)

# Demo tools — secured BLE (Lite / Pro, service A003)

The protocol matches [`docs/ble-secured/ble-secured-api.en.md`](../../docs/ble-secured/ble-secured-api.en.md). Business JSON follows [`docs/ble-common`](../../docs/ble-common/ble-business-api.en.md).

| File | Description |
|------|-------------|
| `ble_secured_gui.py` | **Windows GUI** — full EC J-PAKE handshake, encrypted business commands, and a business-advertising listener |
| `ble_crypto_core.py` | Python reference implementation: handshake, AES-CCM envelope, PIN / 11-digit code, advertising decrypt |
| `web-ble-secured-console.html` | **Dev source** of the web page — split files, Chrome / Edge, full EC J-PAKE + AES-CCM |
| `web-ble-secured-console.offline.html` | **Customer build** — one self-contained file (~108 KB) for any HTTPS static host. **Generated; do not edit** |
| `bundle_offline_html.py` | Rebuilds the offline HTML from the split sources (needs Node.js for `npx esbuild`) |
| `ble_secured_crypto.js` | JS reference implementation (vendored `@noble` + local AES-CCM); mirrors `ble_crypto_core.py` |
| `help_text.js` / `command_help.py` | Cheat-sheet text (Chinese and English) for the web page and the Windows GUI — keep them in sync by hand |
| `vendor/` | Offline JS crypto dependencies (no CDN at runtime) |
| `requirements.txt` | `PyQt6`, `bleak`, `cryptography`, `ecdsa` |

Cross-check the two reference implementations with the known-answer vectors:

```bat
py -3 scripts\check_test_vectors.py
node scripts\check_test_vectors.mjs
```

## Firmware

| Branch | BLE | This folder |
|--------|-----|-------------|
| **Lite / Pro** | Secured (`0xA003`) | **Yes** |
| Basic / Basic+ | Plaintext (`0xA002`) | No — use [`../ble-plaintext`](../ble-plaintext/README.en.md) |

Do not mix the two UUID sets. If the device only exposes `A002`, use the plaintext tools.

## Windows GUI

```bat
cd tools\ble-secured
py -3 -m pip install -r requirements.txt
py -3 ble_secured_gui.py
```

Needs a Bluetooth adapter, and the **pairing code** from the meter: the 11 digits under the QR code, or the 8-digit PIN (the SN is normally inferred from the advertised name `MODEL-SN`). Language: combo box at the top left.

After `restart` / `mqtr` / `reset`, enable auto-reconnect. If the LTK was persisted (Wi-Fi associated successfully once), the tool resumes with `ble-crypto-session-nonce` using the local cache file `ble_crypto_client_cache.json` (**git-ignored; do not commit it**).

## Web page

The provisioning path matches the Windows GUI: Web Bluetooth picker, full EC J-PAKE (or `session-nonce` resume with an LTK kept in `localStorage`), encrypted Wi-Fi / quick commands / Modbus 485 (parity + stop bits) / custom JSON / read `C314`, automatic GATT reconnect with session resume, and the Chinese / English cheat sheet.

### Two copies

| Who | File |
|-----|------|
| Developers, or an AI editing features | `web-ble-secured-console.html` + `ble_secured_crypto.js` + `help_text.js` + `vendor/` |
| Customers (Cloudflare R2, Aliyun OSS, or any HTTPS host) | **only** `web-ble-secured-console.offline.html` |

After changing the split page, the crypto code, or the help text, rebuild the customer file:

```bat
cd tools\ble-secured
py -3 bundle_offline_html.py
```

The offline file inlines J-PAKE / AES-CCM (no jsDelivr), loads no extra `.js`, and omits Google Fonts so the first paint does not wait on a font server. Host it on HTTPS (or `http://127.0.0.1`). Web Bluetooth needs a secure context. Opening it from disk (`file://`) has not been verified, so do not rely on that.

### Run the dev copy

```bat
cd tools\ble-secured
py -3 -m http.server 8765
```

Open `http://127.0.0.1:8765/web-ble-secured-console.html` in **Chrome or Edge** (a `file://` page cannot load the ES modules of the dev copy).

**Empty device picker on Windows:** keep "Show all nearby BLE" ticked (default). Name-prefix filters often match nothing because Windows / Chrome does not always expose the advertised name. Also disconnect the Python GUI and the phone first — a connected meter stops advertising.

**Connected but not secured (`step=2`):** paste the known 32-hex LTK into the page field, or factory-reset the meter to clear the LTK and redo the full J-PAKE with the pairing code. **`step=3` with no local session:** disconnect and reconnect (see the docs, "Common pitfalls"). Leave auto-reconnect off while debugging GATT drops.

**Debug keys:** tick "Debug" to show LTK / session_key / broadcast_key in the panel (also logged).

**Business broadcast:** after a full J-PAKE (so `broadcast_key` exists), use the Broadcast tab. The web page needs `watchAdvertisements`, which Chrome on Windows usually lacks — use the Windows GUI, which scans with bleak and decrypts the long packets live.

**Phones:** Android Chrome / Edge over HTTPS works; iOS Safari has no Web Bluetooth.

## Security notes

- Do not put real customer PINs in examples; use placeholders (`12345678`, `00852607537`).
- Keys stay hidden unless **Debug** is on; treat them as secrets.
- Browser `localStorage` may keep the LTK for the same SN after a successful handshake. Clear site data after a factory-reset demo.
