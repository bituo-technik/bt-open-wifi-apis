# UDP Report

> Status: first release | Applies to: all SPM / SDM Open Wi-Fi branches (for who gets the AES-encrypted datagram see [Section 4](#4-aes-ccm-encrypted-datagram)) | Based on firmware source SXM_EW_C3 `5.1.16`, SDMV2 `1.2.12` / `3.1.19`

UDP report is **pushed by the device**: you give the meter an IP and a port, and it sends the telemetry JSON there as a UDP datagram at a fixed period. There is no connection and no handshake, so latency is low and implementation is simple. It fits scenarios that need power readings quickly, such as PV export limiting and dynamic load balancing.

## 1. Introduction

| Item | Description |
|------|-------------|
| Direction | Device → your host, **one-way**; the device does not accept commands here |
| Content | Telemetry JSON, same as MQTT `/data`, see [Telemetry Payload](../reference/telemetry-payload.en.md); on Pro it can be switched to AES-CCM ciphertext, see [Section 4](#4-aes-ccm-encrypted-datagram) |
| Targets | Up to **5** targets (IP + port); one datagram per target each period |
| Period | Default 5 s, **one period shared by all targets**, minimum 100 ms |
| Switch | Function bit 13; turned on automatically when a target is added, and deleting a target does **not** turn it off |
| Source port | The device always sends from local port **2390** (shared with time sync); use it if a firewall needs it |
| Reliability | UDP guarantees no delivery, order or retransmission. To detect loss, use the `Post` counter in the telemetry |

## 2. Configuring targets

Use the `udp`, `deleteudp` and `udpdata` commands from the [Business Command Reference](../ble-common/ble-business-api.en.md); they work over BLE, HTTP, MQTT and WebSocket.

```json
{"cmd":"udp","IpAddress":"192.168.1.100","localUdpPort":9000,"Frequency":5}
```

| Field | Description |
|-------|-------------|
| `IpAddress` | Target IP (at most 19 characters, dotted IPv4) |
| `localUdpPort` | Target port. "local" is in the name but it is the port on **your** side |
| `Frequency` | Optional period in **seconds**. If omitted the current period is kept. The device converts it to milliseconds, minimum 100 ms |

- Success: `UDP successfully`. Adding the same IP + port again only updates the period.
- When the IP is empty or the port invalid, the device also returns `UDP full` (subcode 24); do not read it literally as "full".
- A sixth target also returns `UDP full`.
- Delete: `{"cmd":"deleteudp","IpAddress":"192.168.1.100","localUdpPort":9000}`, success `UDP deleted`; if absent `UDP not found` (subcode 25).
- List: `{"cmd":"udpdata"}`; targets are in `d.udp_data`, for example `[{"ip":"192.168.1.100","port":"9000"}]`.
- The configuration is stored on the device and survives reboot.
- Targets and period also show up in the `model` response: the period is `UI` (milliseconds); in HTTP `/model` they are `udpInterval` and `UDP`.

Notes:

- Give the target a fixed IP (or a DHCP reservation on the router), otherwise the datagrams stop arriving when your computer's address changes.
- The firmware simply sends to the configured address. To reach a whole subnet you may try the subnet broadcast address (such as `192.168.1.255`), but that is not a firmware specification and you have to verify it yourself.

## 3. Datagram format

### 3.1 Plaintext datagram

Each UDP datagram is **one complete JSON text** (UTF-8), with no header, no newline delimiter and no fragmentation, at most 1024 bytes. Fields are on the [Telemetry Payload](../reference/telemetry-payload.en.md) page.

```json
{"Post":927,"Time":1782313081,"IP":"192.168.1.50","Rssi":-68,"FWVersion":"5.1.16","SerialNumber":"AABBCCDDEEFF","ProductModel":"SPM01","TP":1,"Voltage":"227.6","Current":"0.000","ActivePower":"0.000"}
```

The example shows only some fields for layout; the real datagram is the full packet. Just `JSON.parse` it, and use `SerialNumber` to tell devices apart.

With `commonmode` on, the datagram follows the generic format; see Section 6 of the telemetry page.

### 3.2 When it is sent

- It is sent when the period elapses, Wi-Fi is connected and function bit 13 is 1.
- What goes out is the packet the device "last generated". The firmware decides how often it refreshes internally; a period faster than that delivers duplicates, so deduplicate with `Post`.
- With no target configured, nothing is sent.

## 4. AES-CCM encrypted datagram

> Scope: in the source, only the **secured builds** of SDMV2 (C3 / C6) have this feature, and it takes effect only while the **HTTPS switch** (`enablehttps`) is on. SXM builds (Basic, Lite) always send plaintext. The online documentation says Lite supports it too, which does not match the source and needs firmware confirmation; see the [CHANGELOG](../../CHANGELOG.md).

When it is on, the datagram is no longer the telemetry JSON but a ciphertext JSON:

```json
{"ct":"<ciphertext base64>","tag":"<tag base64>","counter":12}
```

| Field | Description |
|-------|-------------|
| `ct` | AES-128-CCM ciphertext of the telemetry JSON, Base64 |
| `tag` | Authentication tag, **8 bytes**, Base64 |
| `counter` | 32-bit unsigned integer, **incremented every report period** (every target gets the same datagram in a period). It **restarts from 1** after a reboot |

Encryption parameters:

| Item | Value |
|------|-------|
| Algorithm | AES-128-CCM |
| Key | The **broadcast key** (16 bytes), the same one used by BLE encrypted advertising, derived from the J-PAKE result during BLE provisioning; see [Crypto Protocol 3.5](../ble-secured/crypto-protocol.en.md) |
| Nonce (12 bytes) | First 8 bytes all `00`, last 4 bytes are `counter` in **big-endian** |
| Tag length | 8 bytes (BLE long advertising uses 4 bytes; do not mix them up) |
| Additional data (AAD) | none |
| Plaintext | The complete telemetry JSON text (UTF-8) |

Decryption steps:

1. Parse the datagram to get `ct`, `tag`, `counter`, and Base64-decode the first two.
2. Build the nonce from `counter`: 8 `00` bytes + 4 bytes of big-endian `counter`.
3. Concatenate `ct` and `tag` as `ct || tag` and run AES-CCM decryption with the broadcast key and nonce (tag length 8).
4. On success you have the plaintext JSON; if the tag check fails, discard the datagram.

Python (`cryptography` library):

```python
import base64, json
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

def decrypt_udp(datagram: bytes, broadcast_key: bytes) -> dict:
    env = json.loads(datagram)
    ct = base64.b64decode(env["ct"])
    tag = base64.b64decode(env["tag"])
    nonce = b"\x00" * 8 + int(env["counter"]).to_bytes(4, "big")
    plain = AESCCM(broadcast_key, tag_length=8).decrypt(nonce, ct + tag, None)
    return json.loads(plain)
```

Notes:

- **Test vector**: [`spec/udp-aes-test-vector.json`](../../spec/udp-aes-test-vector.json) has a key, a counter, a plaintext and the expected datagram for checking your implementation. It was generated from the parameters above, not captured from a device.
- **Replay protection**: `counter` resets after a device reboot, so ordering by it alone is not reliable; `Post` inside the plaintext resets too. For replay protection, use `Time` (Unix time) in the plaintext with a window check.
- When the device has no broadcast key (for example secured provisioning was never completed), it sends an **empty datagram**. A datagram of length 0 can simply be ignored.
- After `enablehttps` is turned off, datagrams go back to plaintext. The receiver should handle both: run `JSON.parse` first and decrypt if a `ct` field exists.
- How to get the broadcast key out of the BLE provisioning result: the [BLE secured tools](../../tools/README.md) in this repository cache it locally, and the UDP listener tool can read it directly.

## 5. Receiver example

The simplest listener (Python, plaintext):

```python
import json, socket

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(("0.0.0.0", 9000))
while True:
    data, addr = s.recvfrom(2048)
    if not data:
        continue
    msg = json.loads(data)
    print(addr[0], msg.get("SerialNumber"), msg.get("Post"))
```

The [UDP listener tool](../../tools/lan/README.md) in this repository handles both plaintext and AES-CCM datagrams and detects loss.

## 6. Troubleshooting

| Symptom | Cause |
|---------|-------|
| Nothing arrives | No target is configured; function bit 13 is off; the computer's firewall blocks inbound UDP; the device and the computer are on different subnets |
| Occasional loss | Normal for UDP; count it with `Post` |
| You receive `{"ct":...}` | The device has AES on; decrypt with the broadcast key |
| You receive an empty datagram | The device has no broadcast key; redo BLE secured provisioning |
| Decryption fails | The key belongs to another device, or the device was reset after provisioning and the key changed |
| Wrong period | The period is written in **seconds** and converted to milliseconds; minimum 100 ms |
