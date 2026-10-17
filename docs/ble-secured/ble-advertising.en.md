[中文](ble-advertising.zh-CN.md)

# Encrypted business advertising

> Applies to: Lite / Pro (secured BLE, service `A003`) | Firmware versions covered: Lite 5.1.16, Pro 3.1.19

This page is only about reading voltage, current, power, and energy **without a GATT connection**. Provisioning, the handshake, and the read/write characteristics are in the [Secured BLE API](ble-secured-api.en.md). The handshake and key derivation are in the [crypto protocol](crypto-protocol.en.md).

## 1. Whether you need this page

| What you are building | Where to read |
|-----------------------|---------------|
| Provisioning, commands, snapshots | [Secured BLE API](ble-secured-api.en.md). Skip this page |
| A phone or gateway that reads electrical values from advertising, with no connection | This page |
| Your own decryptor | Section 4 below. Key derivation is [crypto protocol §3.5.1](crypto-protocol.en.md#351-broadcast-key) |

The long packet's `broadcast_key` is derived when the first J-PAKE succeeds, and the device stores it together with the LTK **after Wi-Fi association succeeds**. A meter that has never finished secured provisioning has no such key, and the long packet cannot be decrypted.

The GATT business envelope and the advertising AES-CCM **do not share parameters** (tag length and nonce construction differ). Do not reuse one for the other.

## 2. Two packet lengths

Only secured-BLE meters switch between a short and a long manufacturer payload. Plaintext BLE (Basic / Basic+) does not use these packets.

The device's `step` (see [crypto protocol section 5](crypto-protocol.en.md#5-protocol-phases)) chooses the length:

| Condition | Length | Contents |
|-----------|--------|----------|
| `step = 0` (still waiting for J-PAKE round 1) | **5 bytes** | Plaintext, so a scanner can tell meters apart |
| `step ≠ 0` | **26 bytes** | AES-128-CCM ciphertext carrying the electrical values |

In the long-packet case the advertising interval is about **200 ms**. After each packet the meter rotates phase or circuit, so consecutive packets may be phase A, then B, then C. The phase count depends on the model.

## 3. Short format (5 bytes)

Multi-byte integers are **little-endian**.

| Offset | Length | Contents |
|--------|--------|----------|
| 0–1 | 2 | Fixed `0xFF 0xFF` |
| 2 | 1 | Provisioning state: the whole byte `0` means still waiting for J-PAKE round 1; `1` means a later phase |
| 3–4 | 2 | 12-bit discriminator. Take the first 3 hex digits of the SN (12 hex digits) and place them in the low 12 bits of this 16-bit field |

The short packet is not encrypted, and it does not contain voltage or current.

## 4. Long format (26 bytes)

The whole block is **one** manufacturer-data entry in the advertisement.

| Offset | Length | Contents |
|--------|--------|----------|
| 0–1 | 2 | Fixed `0xFF 0xFF` |
| 2 | 1 | Control byte, see below |
| 3–6 | 4 | Advertising counter, unsigned 32-bit, **little-endian**, increments by 1 for each packet that goes on air |
| 7–21 | 15 | CCM ciphertext. Decrypted, this is the 15 bytes in section 4.1 |
| 22–25 | 4 | CCM authentication tag, **4 bytes** (the GATT envelope does not use this length) |

**Control byte**

| Bits | Meaning |
|------|---------|
| bit7 | Whether the application GATT provisioning service is still in the advertisement (1 = yes) |
| bit6–4 | Encoding version. Current value is **1**, which means section 4.1 |
| bit3–2 | Phase or circuit index |
| bit1–0 | Product class |

| bit1–0 | Models |
|--------|--------|
| `0b11` (3) | Three-phase: `SDM01_3PN` / `SPM02` |
| `0b10` (2) | Two circuits: `SDM02` |
| `0b01` (1) | Single-phase: `SDM01_1PN` / `SPM01` |
| `0b00` (0) | Other (including `SRS01A` / `SRS01B`) |

**Decrypt parameters**

- Key: `broadcast_key`, 16 bytes. An open GATT connection is not required.
- Nonce (12 bytes): the first 8 bytes are `0x00`, the last 4 bytes are the counter above in **big-endian**. The counter in the advertisement is little-endian; the numeric value is the same.
- 15-byte plaintext, no AAD, 4-byte tag.

`nonce_12 = 0^8 || BE32(counter)`.

### 4.1 The 15 bytes after decrypt

The plaintext is fixed-length binary, **not JSON**. Multi-byte integers are little-endian. Encoding version 1 (control bits 6–4) uses this layout.

| Plaintext offset | Length | Type | Scale | Quantity | Unit |
|------------------|--------|------|-------|----------|------|
| 0–1 | 2 | unsigned `uint16` | ÷10 | voltage `V` | V |
| 2–3 | 2 | unsigned `uint16` | ÷100 | current `I` | A |
| 4–6 | 3 | signed `int24` | ÷1000 | active power `P` | kW |
| 7–10 | 4 | unsigned `uint32` | ÷100 | import energy `FE` | kWh |
| 11–14 | 4 | unsigned `uint32` | ÷100 | export energy `RE` | kWh |

Physical value = integer ÷ scale. A voltage field of `0x08FC` (little-endian `FC 08`) is `2300 / 10 = 230.0` V.

`int24`: combine three bytes as `b0 | (b1<<8) | (b2<<16)`. If bit 7 of `b2` is 1, treat the value as negative (subtract `0x1000000`). Power may be negative.

A non-finite measurement is encoded as 0. `uint16` saturates at `0…65535`. `int24` saturates at `−0x800000…0x7FFFFF`.

Control bits 3–2 say which circuit this packet belongs to. A single-circuit model keeps the index at 0.

| Product class | Circuits | Index 0 | Index 1 | Index 2 |
|---------------|----------|---------|---------|---------|
| `0b01` single-phase | 1 | the only circuit | — | — |
| `0b00` and `SRS01A` | 1 | the only circuit | — | — |
| `0b00` and `SRS01B` | 2 | circuit 1 | circuit 2 | — |
| `0b10` `SDM02` | 2 | circuit 1 | circuit 2 | — |
| `0b11` three-phase | 3 | phase A | phase B | phase C |

On `SRS01A` / `SRS01B` the four export-energy bytes are always 0. An unrecognized model fills all 15 bytes with 0.

The units match the read-characteristic short keys `V` / `I` / `P` / `FE` / `RE`. Advertising is fixed-point binary; the read characteristic uses decimal strings. See [Business Command Reference §5](../ble-common/ble-business-api.en.md#5-snapshot-read-ip-and-electrical-readings).

## 5. Advertising and GATT when Wi-Fi is connected

After Wi-Fi connects, if provisioning did **not** include `enableble:true`, the meter removes the application service UUID from advertising and stops exposing the application GATT. Advertising then mainly carries the manufacturer data. You can still read electrical values from the air, and you cannot open GATT.

Sending `enableble:true` in the provisioning command (see [Business Command Reference §2.2](../ble-common/ble-business-api.en.md#22-send-ssid-and-password)) stores that choice. On the next boot, GATT and the service UUID stay even when Wi-Fi is already connected, and the dynamic manufacturer data keeps updating.

Factory reset clears that choice, and also clears the LTK and the broadcast key.
