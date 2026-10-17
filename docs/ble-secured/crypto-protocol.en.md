# BLE Secure Channel API Documentation V2

This document is for third-party apps, gateways, or debugging tools integrating with the device BLE secure channel protocol. It describes only externally visible interface protocol, field definitions, interaction phases, key derivation rules, and message formats.

> **Where this fits in the repo:** this is the **authoritative protocol reference** for the secured channel (Lite / Pro): J-PAKE / ZKP binary layout, key derivation, and the GATT envelope. Integration entry: [Secured BLE API](ble-secured-api.en.md). Values read from advertising without a connection: [Encrypted business advertising](ble-advertising.en.md). Business commands: [Business Command Reference](../ble-common/ble-business-api.en.md). If this document and the API page disagree about the handshake or the envelope, **this one wins**.

## 1. Authentication Material

### 1.1 PIN

- `PIN` is the base passphrase material for the device secure channel.
- `PIN` is a fixed `8`-digit numeric string.
- Only characters `0-9` are allowed.
- `PIN` can only be obtained from the device body label.

### 1.2 SN

- `SN` is the device serial number, used in key derivation.
- `SN` is the fixed unique device identifier.

## 2. Communication Method

- The client sends JSON strings via the BLE write characteristic.
- The device returns JSON strings via the BLE notify characteristic.
- Before the secure channel is established, all traffic is plaintext JSON.
- After the secure channel is established, all business messages use encrypted envelope JSON.
- On firmware that enables this secure channel, application GATT **service and characteristic UUIDs** differ from “plaintext-only business” firmware: service **`0xA003`**, write **`0xC313`**, read **`0xC314`**, notify **`0xC315`** (full 128-bit UUIDs are in [Secured BLE API §4.1](ble-secured-api.en.md#41-uuids)).

## 3. Basic Terminology

### 3.1 Version Number

- The protocol version is returned by the device in `d.ver` via `ble-crypto-ver`.
- The client must use the literal value of `d.ver` and the matching specification so handshake, derivation, and encryption rules align with that version.

### 3.2 nonce

- `client_nonce` and `device_nonce` are fixed `8`-byte random values.
- In JSON they are represented as `16` hexadecimal characters, e.g. `0011223344556677`.
- `client_nonce` is the random value provided by the client when initiating handshake or session recovery.
- `device_nonce` is the random value returned by the device.

### 3.3 PBKDF2

- The device and client first run `PBKDF2-HMAC-SHA256` on the `8`-digit `PIN`.
- Derived output length is `32` bytes.
- `salt = SN || protocol version || "PBKDF2"`.
- Iteration count is the protocol constant: **`10000`** (device and client must match).

### 3.4 EC J-PAKE

- The device and client use the `PBKDF2` output as passphrase material for `EC J-PAKE`.
- Curve: `secp256r1`.
- Hash: `SHA-256`.
- `round1` and `round2` messages are transmitted in `base64`.
- Both parties obtain the same shared secret only when `PIN` matches.

#### 3.4.1 Detailed Computation Flow

Notation:

- `G`: secp256r1 base point (generator)
- `n`: curve order (ORDER)
- `s`: 32-byte key material from `PBKDF2`, interpreted as a big-endian unsigned integer
- Client identity `"client"`, device identity `"server"`

##### 3.4.1.1 Schnorr Zero-Knowledge Proof (ZKP)

ZKP proves the prover knows a private key `x` (with `X = x·G`) and binds PIN-derived `s` into the proof so parties with different PINs cannot pass verification.

**Generate proof** `ZKP-Write(G, x, X, id, s)`:

1. Choose random `v ∈ [1, n-1]`
2. Compute `V = v·G`
3. Compute `h = Hash(G, V, X, id, s)` (see hash definition below)
4. Compute `r = (v - h·x) mod n`
5. Output `V || len(r) || r`

**Verify proof** `ZKP-Read(G, X, id, s, V, r)`:

1. Compute `h = Hash(G, V, X, id, s)`
2. Compute `V' = h·X + r·G`
3. Verify `V' == V`; reject if not equal

**Hash function** `Hash(G, V, X, id, s)`:

```
payload = len(G_raw) || G_raw || len(V_raw) || V_raw || len(X_raw) || X_raw || len(id) || id || len(s_bytes) || s_bytes
```

where `G_raw`, `V_raw`, `X_raw` are uncompressed EC point encodings (`0x04 || x || y`, 65 bytes each), `id` is an ASCII string, and `s_bytes` is the minimal big-endian byte representation of `s`. Each field is prefixed with a 4-byte big-endian length.

```
hash = SHA-256(payload)
h = bytes_to_big_endian(hash) mod n
```

> **Key point**: `s` (PIN-derived key) participates in the hash. Different PIN → different `s` → different `h` → ZKP verification fails. This detects PIN mismatch as early as Round1.

##### 3.4.1.2 Key Pair with Proof (KKP)

`KKP-Write(G, x, X, id, s)`: generate key pair with ZKP

1. Generate random key pair `(x, X = x·G)`
2. Output `X || ZKP-Write(G, x, X, id, s)`

`KKP-Read(G, id, s, data)`: read and verify key pair and its ZKP

1. Read point `X` from data; verify it is not the point at infinity
2. Read and verify `ZKP-Read(G, X, id, s, ...)`
3. Return verified public key `X`

##### 3.4.1.3 Round1

Each side generates two ephemeral key pairs with ZKP and sends them to the peer.

**Client generates and sends**:

```
x1 = random [1, n-1],  X1 = x1·G
x2 = random [1, n-1],  X2 = x2·G
client_round1 = KKP-Write(G, x1, X1, "client", s) || KKP-Write(G, x2, X2, "client", s)
```

**After device receives**:

1. Parse and verify client Round1: `KKP-Read(G, "client", s, data)` → obtain `Xp1, Xp2`
   - ZKP verification uses the device’s own `s` (derived from device PIN)
   - If PIN differs → `s` differs → hash differs → ZKP fails → Round1 fails
2. Generate device Round1:
   ```
   xm1 = random [1, n-1],  Xm1 = xm1·G
   xm2 = random [1, n-1],  Xm2 = xm2·G
   server_round1 = KKP-Write(G, xm1, Xm1, "server", s) || KKP-Write(G, xm2, Xm2, "server", s)
   ```
3. Return `device_nonce` + `server_round1`

**Round1 data layout** (each party):

```
[point X] 1-byte length + 65-byte uncompressed point
[V]       1-byte length + 65-byte uncompressed point
[r]       1-byte length + r bytes
```

Each key pair is about 133 bytes; Round1 contains two key pairs, about 266 bytes total.

##### 3.4.1.4 Round2

Round2 uses PIN material `s` to compute a shared base point, then generates one key pair with ZKP.

**Client**:

```
Ga = X1 + X3 + X4          (own first point + device’s two points)
xc = (x2 · s) mod n        (using PIN-derived s)
Xc = xc · Ga
client_round2 = KKP-Write(Ga, xc, Xc, "client", s)
```

**Device**:

```
Gb = Xp1 + Xp2 + Xm1       (client’s two points + own first point)

// Verify client Round2 (PIN check) before generating response
// Verify: parse Xc and ZKP from client_round2; verify with Gb as base
KKP-Read(Gb, "client", s, client_round2)  → continue only if verification passes

// Generate device Round2
xs = (xm2 · s) mod n
Xs = xs · Gb
server_round2 = GROUP_ID || KKP-Write(Gb, xs, Xs, "server", s)
```

> **Security design**: The device verifies client Round2 before generating its own response. If PIN is wrong, the device does not leak its own key material.

##### 3.4.1.5 Shared Key Derivation

After Round2 completes, each side computes the shared key:

**Client**:

```
x2s = (x2 · s) mod n
K = x2 · (Xs - x2s·X4)       // Xs = device Round2 public key, X4 = device second Round1 public key
shared_key = SHA-256(K.x)     // x-coordinate of K, 32 bytes
```

**Device**:

```
xm2s = (xm2 · s) mod n
K = xm2 · (Xp - xm2s·Xp2)    // Xp = client Round2 public key, Xp2 = client second Round1 public key
shared_key = SHA-256(K.x)
```

If PIN matches, both sides compute the same `K` and thus the same `shared_key`. If PIN differs, `s` differs → Round1 or Round2 ZKP fails before this step.

##### 3.4.1.6 Full Key Derivation Chain

```
PIN (8 digits)
  │
  ▼ PBKDF2-HMAC-SHA256 (salt=SN||ver||"PBKDF2", iter=10000)
s (32 bytes)
  │
  ▼ EC J-PAKE (secp256r1, SHA-256)
shared_key (32 bytes)
  │
  ▼ HKDF-SHA256 (salt=device_nonce||client_nonce, info=SN||ver||"LTK")
LTK (16 bytes)
  ├─► HKDF (info=SN||ver||"session")     → session_key (16 bytes)
  ├─► HKDF (info=SN||ver||"broadcast")   → broadcast_key (16 bytes)
  └─► Persist after Wi‑Fi association succeeds (see §3.5.2)
```

### 3.5 LTK and session key

- `LTK` and `session key` are derived with `HKDF-SHA256`.
- `LTK` derivation:
  - Input key material: `EC J-PAKE shared key`
  - `salt = device_nonce || client_nonce`
  - `info = SN || protocol version || "LTK"`
- `session key` derivation:
  - Input key material: `LTK`
  - `salt = device_nonce || client_nonce`
  - `info = SN || protocol version || "session"`

### 3.5.1 Broadcast key

- Used for **AES-128-CCM** encryption of the **long format (26-byte)** payload in **BLE advertising manufacturer data** (byte layout: [Encrypted business advertising](ble-advertising.en.md)).
- Uses the **same** `salt = device_nonce || client_nonce` as `LTK` (8 bytes each, same order as LTK).
- `info = SN || protocol version || "broadcast"` (interpret as ASCII byte sequence; **no** extra terminators from JSON or debug output).
- Input key material: `LTK` (16 bytes).
- Output length: 16 bytes as **broadcast-only key**; same lifecycle as **LTK**, persistence per **§3.5.2**. **Not** recomputed on `ble-crypto-session-nonce` session recovery (session only recomputes `session key` and GATT business CCM bases).

### 3.5.2 Persistence of LTK and broadcast key

After Wi-Fi association succeeds, the device stores the **LTK** and the **broadcast key**. A later BLE disconnect or reboot can restore the GATT session with **`ble-crypto-session-nonce`**, and the long advertising packet in [Encrypted business advertising](ble-advertising.en.md) can be decrypted without a connection. Storage happens only after the secure handshake has finished and Wi-Fi association has succeeded.

#### Storage form

- Persistence uses device **non-volatile storage** (same namespace as business configuration).
- **LTK** and **broadcast key** are stored as **32-character hexadecimal strings** (16-byte binary keys); integrators must handle the full 32 characters when reading, caching, or backing up.

#### First provisioning: deferred commit

| Phase | Device behavior |
|------|----------|
| **`ble-crypto-jpake-round2` success** | Derive **LTK**, **broadcast key**, and current **session key** in memory; secure channel is immediately usable (`step=3`), **not yet** written to persistent storage. |
| **Wi‑Fi config over encrypted channel** | Device saves SSID/password and starts STA association; enters **“LTK pending commit”** state. |
| **STA association success** | **One-time** write of in-memory **LTK** and **broadcast key** to persistent storage; after reboot or reconnect, `ble-crypto-ver` may return **`step=2`**. |
| **STA association failure** | **Do not** persist LTK from this J-PAKE round; after the agreed wait window, discard pending keys in memory and roll back session state; J-PAKE must be repeated to provision again. |

During **“LTK pending commit”**, the device **will not** write LTK or broadcast key to persistent storage through any other path.

#### Later connections: read-only load

- When LTK is already persisted, the client sends **`ble-crypto-session-nonce`** with new `client_nonce` / `device_nonce`; the device **reads** LTK and broadcast key from storage and recomputes **session key** and **§3.6** CCM bases.
- This flow **does not** update persisted LTK or broadcast key.

#### Clear and invalidation

- **Clear device configuration** (factory reset or equivalent debug entry) deletes persisted LTK and broadcast key; first-time provisioning must be repeated.
- If connection passphrase (PIN-related material) changes and invalidates long-term keys, the device should clear persisted LTK and broadcast key accordingly.

#### Relation to typical flows

- After J-PAKE Round2 in **§6.1**, encrypted business is available immediately; **LTK commit** requires **Wi‑Fi configuration and STA success** in the same encrypted session (see [Business Command Reference §2.2](../ble-common/ble-business-api.en.md#22-send-ssid-and-password)).
- **§6.2** applies when **LTK is already persisted**; **§7.5** only restores session keys and does not trigger re-commit.

### 3.6 AES-CCM and 12-byte nonce derivation (**GATT business JSON ciphertext envelopes only**)

This section describes **JSON ciphertext over Notify/Write** (Section 8), **not** the long advertising packet in [Encrypted business advertising](ble-advertising.en.md) (that tag is **4 bytes**).

GATT business ciphertext uses **`AES-128-CCM`**: **no additional authenticated data (AAD length 0)**, authentication tag **`tag` length 8 bytes**.  
The **full 12-byte CCM `nonce` is not sent in JSON**; the JSON **`nonce` field is only a 32-bit unsigned counter** (Section 8). Both sides assemble 12 bytes locally per this section before CCM encrypt/decrypt.

#### 3.6.1 Structure

The 12-byte nonce is two parts (**big-endian / network byte order**):

| Offset | Length | Meaning |
|------|------|------|
| 0–7 | 8 bytes | Session-fixed **nonce base** (from HKDF output) |
| 8–11 | 4 bytes | Message counter **`counter`** as **big-endian** `uint32_t` |

Notation: `nonce_12 = nonce_base_8 || BE32(counter)`.

#### 3.6.2 Base: HKDF-SHA256 (fixed 8-byte output)

After **`session key`** is derived and both sides agree on this round’s `device_nonce` and `client_nonce` (8 bytes each), **each side** computes **two directions** of 8-byte bases (HKDF **`salt` is empty**, length 0; **`info`** is the byte sequence of the **ASCII strings below**, **without** trailing **NUL** from language runtimes):

1. **Device → client**  
   - `IKM = device_nonce || client_nonce` (16 bytes)  
   - `info = "ccm-tx-nonce"`  
   - `nonce_base_tx = HKDF-SHA256(salt=∅, IKM, info, L=8)`

2. **Client → device**  
   - `IKM = client_nonce || device_nonce` (16 bytes, **opposite order** from above)  
   - `info = "ccm-rx-nonce"`  
   - `nonce_base_rx = HKDF-SHA256(salt=∅, IKM, info, L=8)`

Both **first J-PAKE link** and **`ble-crypto-session-nonce` recovery** recompute these bases and **`session key`** after exchanging new `device_nonce` / `client_nonce`. Counter rules after base or session key change are in Section 8.

#### 3.6.3 Direction and base (device / client)

| Operation | 8-byte base used | JSON `nonce` field |
|------|-------------------|-------------------------|
| **Decrypt** ciphertext from device Notify | `nonce_base_tx` | Matches `counter` in device envelope |
| **Encrypt** ciphertext sent via Write | `nonce_base_rx` | Client-maintained sequence for this direction |

Symmetric on device: **outbound to client** uses `nonce_base_tx` and device send sequence per **§8.1**; **inbound from client** uses `nonce_base_rx` and envelope `nonce`.

## 4. Common Response Format

All plaintext responses use this structure:

```json
{
  "ok": true,
  "msg": "",
  "event": "ble-crypto-ver",
  "d": {
    "ver": "xxx",
    "step": 0
  }
}
```

Field descriptions:

- `ok`: Boolean, whether the request succeeded.
- `msg`: String; reason on failure, usually empty on success.
- `event`: String; command this response belongs to.
- `d`: Object, optional; business data for the command.

## 5. Protocol Phases

The device reports secure channel phase via `step`:

- `0`: Waiting for client `ble-crypto-jpake-round1`
- `1`: Waiting for client `ble-crypto-jpake-round2`
- `2`: Device has long-term keys; waiting for client `ble-crypto-session-nonce` to restore session
- `3`: Secure channel established; encrypted business messages allowed

## 6. Typical Flows

### 6.1 First-time secure channel establishment

1. `ble-crypto-ver`
2. `ble-crypto-jpake-round1`
3. `ble-crypto-jpake-round2` (LTK and session key in memory; encrypted traffic immediately)
4. (Recommended) Send **Wi‑Fi configuration** in the same encrypted session; after STA success, **LTK and broadcast key are committed** (**§3.5.2**)
5. Subsequent business uses encrypted envelopes

If step 4 is incomplete or Wi‑Fi association fails, LTK is **not** persisted; after reboot, J-PAKE must be repeated.

### 6.2 Restore secure channel after device reboot

1. `ble-crypto-ver`
2. If `step=2`, send `ble-crypto-session-nonce`
3. Proceed with encrypted business

## 7. Plaintext Commands

### 7.1 Query protocol version

Request:

```json
{
  "cmd": "ble-crypto-ver"
}
```

Success response example:

```json
{
  "ok": true,
  "msg": "",
  "event": "ble-crypto-ver",
  "d": {
    "ver": "BT_Crypto_V1",
    "step": 0
  }
}
```

Common failure response:

```json
{
  "ok": false,
  "msg": "connection key must be 8 digits",
  "event": "ble-crypto-ver"
}
```

### 7.2 Reset current handshake

Request:

```json
{
  "cmd": "ble-crypto-reset"
}
```

Notes:

- Allowed only when `step=0` or `step=1`.
- Does **not** clear existing device `LTK`.

### 7.3 J-PAKE round 1

Request:

```json
{
  "cmd": "ble-crypto-jpake-round1",
  "client_nonce": "0011223344556677",
  "client_round1": "BASE64_ROUND1"
}
```

When `client_round1` is too long, the client may upload in parts:

```json
{
  "cmd": "ble-crypto-jpake-round1",
  "client_nonce": "0011223344556677",
  "part_idx": 0,
  "part_total": 2,
  "client_round1_part": "BASE64_PART_0"
}
```

```json
{
  "cmd": "ble-crypto-jpake-round1",
  "client_nonce": "0011223344556677",
  "part_idx": 1,
  "part_total": 2,
  "client_round1_part": "BASE64_PART_1"
}
```

Success response example:

```json
{
  "ok": true,
  "msg": "",
  "event": "ble-crypto-jpake-round1",
  "d": {
    "device_nonce": "8899aabbccddeeff",
    "server_round1": "BASE64_ROUND1"
  }
}
```

If `server_round1` is too long, the device returns one part per request. After the first part, the client must request the next:

```json
{
  "ok": true,
  "msg": "",
  "event": "ble-crypto-jpake-round1",
  "d": {
    "device_nonce": "8899aabbccddeeff",
    "server_round1_part": "BASE64_PART_0",
    "part_idx": 0,
    "part_total": 2,
    "done": false
  }
}
```

```json
{
  "cmd": "ble-crypto-jpake-round1",
  "client_nonce": "0011223344556677",
  "fetch_next": true
}
```

```json
{
  "ok": true,
  "msg": "",
  "event": "ble-crypto-jpake-round1",
  "d": {
    "device_nonce": "8899aabbccddeeff",
    "server_round1_part": "BASE64_PART_1",
    "part_idx": 1,
    "part_total": 2,
    "done": true
  }
}
```

When multipart upload is not yet complete, the device may return continue-upload confirmation:

```json
{
  "ok": true,
  "msg": "",
  "event": "ble-crypto-jpake-round1",
  "d": {
    "part_idx": 0,
    "part_total": 2,
    "status": "continue"
  }
}
```

Field descriptions:

- `client_nonce`: Client random for this round.
- `client_round1`: Full client J-PAKE round 1 data, `base64` encoded.
- `client_round1_part`: Client J-PAKE round 1 fragment, `base64` encoded.
- `part_idx`: Current fragment index, starting at `0`.
- `part_total`: Total fragment count.
- `device_nonce`: Device random.
- `server_round1`: Full device J-PAKE round 1 data, `base64` encoded.
- `server_round1_part`: Device J-PAKE round 1 fragment, `base64` encoded.
- `done`: When `true`, this is the last fragment.
- `fetch_next`: Client requests the next `server_round1_part`.

Additional notes:

- If a single packet suffices, the client may send `client_round1` directly.
- If too long, use `client_round1_part` fragments.
- The device runs J-PAKE round1 verification and response only after the last upload fragment.
- If the device returns `server_round1_part`, the client must send `fetch_next=true` until `done=true`.
- Only `round1` supports fragmentation; `round2` remains single-packet.

### 7.4 J-PAKE round 2

Request:

```json
{
  "cmd": "ble-crypto-jpake-round2",
  "client_round2": "BASE64_ROUND2"
}
```

Success response example:

```json
{
  "ok": true,
  "msg": "",
  "event": "ble-crypto-jpake-round2",
  "d": {
    "server_round2": "BASE64_ROUND2"
  }
}
```

Notes:

- Allowed only when `step=1`.
- On success, both sides derive **LTK**, **broadcast key**, and **session key** from `EC J-PAKE shared key`; secure channel is immediately usable (`step=3`).
- **LTK and broadcast key persistence** waits for **Wi‑Fi configuration and STA success** per **§3.5.2**; until then they exist only in device memory.
- After first link success, **no** `ble-crypto-session-nonce` is needed on the current connection; after reboot with persisted LTK, use **§7.5** on reconnect.

### 7.5 Restore secure session

Request:

```json
{
  "cmd": "ble-crypto-session-nonce",
  "client_nonce": "0011223344556677"
}
```

Success response example:

```json
{
  "ok": true,
  "msg": "",
  "event": "ble-crypto-session-nonce",
  "d": {
    "device_nonce": "8899aabbccddeeff"
  }
}
```

Notes:

- Allowed only when `step=2` (device **has persisted LTK**, see **§3.5.2**).
- After exchanging new `client_nonce` / `device_nonce`, the device recomputes **session key** and **§3.6** CCM bases from stored **LTK**; **does not** rewrite persisted LTK or broadcast key.

## 8. Encrypted Envelope Format

After the secure channel is established, business messages use this JSON envelope:

```json
{
  "nonce": 1,
  "ct": "BASE64_CIPHERTEXT",
  "tag": "BASE64_TAG"
}
```

Field descriptions:

- `nonce`: **32-bit unsigned integer**, the **`counter`** in this section (matches the **last 4 bytes big-endian** of the 12-byte nonce in Section 3.6). **Not** the hex string of `client_nonce` / `device_nonce`.
- `ct`: `AES-CCM` ciphertext, **Base64** (RFC 4648, standard alphabet and `=` padding).
- `tag`: `AES-CCM` authentication tag (`8` bytes), **Base64** encoded.
- Full 12-byte CCM `nonce` is assembled locally per **Section 3.6** from “8-byte HKDF base for that direction + `BE32(nonce field)`”.

### 8.1 Device-side sequence conventions

For alignment with **§8.2**, the device maintains two internal 32-bit counters (not extra JSON field names; semantics only):

- **`N_send` (device → client)**  
  - When encrypted business is allowed, device outbound ciphertext uses **`N_send` initial value `1`**.  
  - Each successfully encrypted and sent packet (e.g. via Notify) has envelope **`nonce` equal to current `N_send`**, then **`N_send ← N_send + 1`** (arithmetic mod **2³²**; redeploy should re-handshake or rotate session before wrap to avoid nonce reuse).
- **`N_accept` (last accepted client nonce)**  
  - New session starts at **`0`**.  
  - After each successful decrypt of a **client write** ciphertext, **`N_accept ←` that packet’s envelope `nonce`**.

The client should **mirror**: track device `nonce` for decrypt; use an independent sequence for writes toward the device per **§8.2** relative to device **`N_accept`**.

### 8.2 `nonce` (counter) and replay protection (client → device)

When processing **client write** ciphertext, the device must:

- If envelope **`nonce ≤ N_accept`** (unsigned 32-bit compare), **reject** with **`replay detected`**: **do not** update **`N_accept`**, **do not** decrypt.  
- Only if **`nonce > N_accept`**, decrypt with **§3.6** **`nonce_base_rx` + `BE32(nonce)`**; on success **`N_accept ← nonce`**.

Therefore:

1. **Strict increase vs device accepted value**: each new client ciphertext must have **`nonce` greater than current `N_accept`**; equal or smaller is rejected.  
2. **Gaps allowed**: e.g. after accepting `nonce=5`, next may be `10` if `10 > 5`.  
3. **No “late” smaller values**: if `N_accept=10`, later `nonce=5` is replay and rejected.  
4. **Retransmit**: second packet with **`nonce` not greater than `N_accept`** returns **`replay detected`**.  
5. **Non-incrementing or reused counters**: rejected except possibly the first packet; encrypting different plaintext under the **same `session key` and same full 12-byte CCM `nonce`** violates CCM usage and risks **keystream reuse**.

**Device → client**: device increments **`N_send`** in send order. This protocol **does not require** extra anti-replay fields for that direction; **clients should** verify monotonic `nonce` on receive to reduce replay and state confusion (symmetric to device **`N_accept`** rules above).

### 8.3 Difference from `decrypt failed`

- **`replay detected`**: counter check failed; CCM not entered.  
- **`decrypt failed`**: counter passed but **CCM authenticated decrypt failed** (wrong key, corrupted `ct`/`tag`, `nonce` mismatch with encrypting side, etc.).

## 9. BLE Advertising Manufacturer Data (Dynamic Advertising)

Encrypted business advertising has its own page: [Encrypted business advertising](ble-advertising.en.md).

This document keeps the handshake, key derivation (including the §3.5 broadcast key), and the GATT envelope. Packet layout, decrypt parameters, and the electrical fields are defined on that page.


## 10. Failure Conditions

Common failure reasons include:

- `device locked`
- `version required`
- `invalid step`
- `invalid round1`
- `invalid round2`
- `round1 verify failed`
- `round2 verify failed`
- `shared key derive failed`
- `ltk derive failed`
- `session derive failed`
- `replay detected`: see **Section 8.2** (client → device ciphertext **`nonce` not greater than** device **`N_accept`**).
- `decrypt failed`: CCM verify or decrypt failed, see **Section 8.3**.

## 11. Compatibility Notes

- This document corresponds to the new `PBKDF2 + EC J-PAKE + HKDF` handshake protocol.
- Legacy `ble-crypto-client-nonce` and `ble-crypto-client-response` are deprecated.
- Clients must upgrade per this document; otherwise first-time link establishment will fail.
