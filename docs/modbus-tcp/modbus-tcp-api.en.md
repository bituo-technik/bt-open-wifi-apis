# Modbus TCP

> Status: first release | Applies to: all SPM / SDM Open Wi-Fi branches (Modbus TCP over TLS only on Basic+ and Pro) | Based on firmware source SXM_EW_C3 `5.1.16`, SDMV2 `1.2.12` / `3.1.19`; map identical to the Gitbook "Modbus TCP Map - ESP32-8685"

Modbus TCP is the most common way for PLCs, industrial gateways and EMS to read the meter. The device is a **Modbus TCP server (slave)** on port **502**: you poll it and read the electrical values from fixed registers. It does not push anything by itself.

## 1. Introduction

| Item | Description |
|------|-------------|
| Port | `502` |
| Unit ID (Slave ID) | The firmware **does not check** the Unit ID and echoes it back; use `1` |
| Function codes | `0x03` read holding registers, `0x04` read input registers (**same data**), `0x06` write single register (control registers only) |
| Readable window | Registers **978 ~ 1077** (100 registers), see [Section 4](#4-register-map) |
| Word order | A 32-bit value uses two registers, **high word at the lower address (ABCD, big-endian)** |
| Switch | Function bit 15 (`enablemodbustcp`, see [Business Command Reference](../ble-common/ble-business-api.en.md)); the server runs only when the bit is set |
| Concurrent connections | Basic / Lite: **2**, Basic+: **1**, Pro: **2** (the same number as the TLS slots, see [Overview](../overview/open-wifi-overview.en.md#31-tls-connection-limit)) |
| Frame size | At most 600 bytes per receive |

Which map to use (single / split / three phase) is decided by the product model; read the model string from register 984 (for example `SDM01_3PN`) or from the `model` command.

| Type | Products (ordering numbers) |
|------|-----------------------------|
| Single-phase | SPM01-D2EW, SPM01-D1EW, SPM01-U1EW |
| Split-phase | SDM02-EW-12, SDM02-EW-20, SDM02-EW-10U |
| Three-phase | SPM02-D2EW, SPM02-D1EW, SPM02-U1EW, SDM01-EWM-12, SDM01-EWM-20 |

## 2. Connecting

### 2.1 Plain connection

Open a TCP connection to `<device IP>:502` and send standard Modbus TCP frames (MBAP header + PDU). Find the IP with [mDNS discovery](../mdns/mdns-discovery.en.md) or from the router.

Connection behavior of the firmware:

- A connection may stay open and be reused. If it is idle for **30 seconds** the device closes it (custom builds may use 12 s). A client that polls more slowly than that must reconnect.
- When all slots are in use, a new connection is not accepted until one slot is released.
- The device answers **one** request at a time. If several complete frames are already queued in the receive buffer, only the **newest** one is answered. Always wait for the response before sending the next request.
- A frame whose declared length does not match is dropped **without a response**; the client sees a timeout.
- Recommended minimum interval between two requests: **150 ms**. Polling faster than about once per second is normally unnecessary for energy data.

> The Gitbook page says the device accepts only one connection and resets the socket after every read, and asks you to reconnect for every request. The firmware source does not do that: it keeps the connection. Reconnecting for every request still works and is the safest choice for simple clients, so the recommendation stays compatible. See the CHANGELOG entry for this discrepancy.

### 2.2 Modbus TCP over TLS

On Basic+ and Pro you can enable Modbus TLS (function bit 14 plus bit 15 in `enabletls` / `enablemodbustcp`); the TLS server then also listens on **502**. TLS slots are shared with MQTTS, HTTPS and WSS; the service priority is MQTTS > HTTPS > WSS > Modbus TLS, and a Modbus service without a slot **falls back to plaintext**. Details and limits are in the [Overview](../overview/open-wifi-overview.en.md#31-tls-connection-limit). Many PLCs and gateways cannot do Modbus over TLS; in that case keep the plaintext connection on a trusted network segment.

## 3. Function codes and exceptions

| Function code | Behavior |
|---------------|----------|
| `0x03` / `0x04` | Read registers inside the 978 ~ 1077 window. Start address plus quantity must stay inside the window |
| `0x06` | Only the two control registers in [Section 5](#5-control-registers) are writable |
| Any other | Exception `01` |

Exception responses:

| Exception code | When |
|----------------|------|
| `01` Illegal function | Function code other than 03 / 04 / 06 (including 0x10 write multiple registers) |
| `02` Illegal data address | Read range outside 978 ~ 1077, or write address that is not a control register |
| `03` Illegal data value | Control register written with a value other than the magic value |
| `05` | Frame shorter than 12 bytes (non-standard use of this code) |

## 4. Register map

The map below is for the default report mode `commonmode = 0`. When the device is switched to the generic format (`commonmode = 1`, see the Business Command Reference), the Modbus read map is switched to a different layout and the tables below **do not apply**. The device also has `mda` / `minvert` commands (SXM and SDMV2 firmware) that remap register addresses or swap bytes for custom integrations; they are not covered here, and `mda` also sets `commonmode` back to 0 and turns Modbus TCP on. The factory layout is the one below.

### 4.1 Product identification (base address 978)

Identical on all models. Strings are ASCII packed two characters per register, **first character in the high byte**. Unused characters are `0`.

| Address (DEC) | Address (HEX) | Description | Registers | Type | Example |
|---------------|---------------|-------------|-----------|------|---------|
| 978 | `0x03D2` | MAC address | 6 | String (12 characters) | `45705E597760` |
| 984 | `0x03D8` | Product model | 5 | String (10 characters) | `SDM01_3PN` |
| 989 | `0x03DD` | MCU firmware version | 5 | String (10 characters) | `003.00.13` |
| 994 | `0x03E2` | Wi-Fi signal strength | 1 | UINT16 | `68` means **-68 dBm** |
| 995 | `0x03E3` | System time | 2 | UINT32, high word first | Unix seconds |
| 997 | `0x03E5` | Wi-Fi firmware version | 3 | String (6 characters) | `5.1.16` |

> Register 994 holds the **absolute value** of the RSSI (the firmware writes `-rssi` into an unsigned register). The Gitbook page describes it as a negative dBm value; in the data you read a positive number. Register 989 is the MCU firmware, register 997 the Wi-Fi firmware (the two examples on the Gitbook page are swapped).

### 4.2 Single-phase metering data

| Address (DEC) | Address (HEX) | Description | Type | Range | Unit |
| --- | --- | --- | --- | --- | --- |
| 1000 | `0x03E8` | Voltage | FLOAT32 | 0 ~ 1000 | V |
| 1002 | `0x03EA` | Current | FLOAT32 | 0 ~ 1000 | A |
| 1004 | `0x03EC` | Active power | FLOAT32 | -1000 ~ 1000 | kW |
| 1006 | `0x03EE` | Power factor | FLOAT32 | -1.0 ~ 1.0 | — |
| 1008 | `0x03F0` | Frequency | FLOAT32 | 0 ~ 1000 | Hz |
| 1010 | `0x03F2` | Import active energy | FLOAT32 | ±1999999999 | kWh |
| 1012 | `0x03F4` | Export active energy | FLOAT32 | ±1999999999 | kWh |
| 1014 | `0x03F6` | Total active energy (import + export) | FLOAT32 | ±1999999999 | kWh |

### 4.3 Split-phase metering data

| Address (DEC) | Address (HEX) | Description | Type | Range | Unit |
| --- | --- | --- | --- | --- | --- |
| 1000 | `0x03E8` | Voltage L1-N | FLOAT32 | 0 ~ 1000 | V |
| 1002 | `0x03EA` | Voltage L2-N | FLOAT32 | 0 ~ 1000 | V |
| 1006 | `0x03EE` | Current L1 | FLOAT32 | 0 ~ 1000 | A |
| 1008 | `0x03F0` | Current L2 | FLOAT32 | 0 ~ 1000 | A |
| 1012 | `0x03F4` | Active power L1 | FLOAT32 | -1000 ~ 1000 | kW |
| 1014 | `0x03F6` | Active power L2 | FLOAT32 | -1000 ~ 1000 | kW |
| 1018 | `0x03FA` | Reactive power L1 | FLOAT32 | -1000 ~ 1000 | kVAR |
| 1020 | `0x03FC` | Reactive power L2 | FLOAT32 | -1000 ~ 1000 | kVAR |
| 1024 | `0x0400` | Apparent power L1 | FLOAT32 | -1000 ~ 1000 | kVA |
| 1026 | `0x0402` | Apparent power L2 | FLOAT32 | -1000 ~ 1000 | kVA |
| 1030 | `0x0406` | Power factor L1 | FLOAT32 | -1.0 ~ 1.0 | — |
| 1032 | `0x0408` | Power factor L2 | FLOAT32 | -1.0 ~ 1.0 | — |
| 1036 | `0x040C` | Average voltage L-N | FLOAT32 | 0 ~ 1000 | V |
| 1038 | `0x040E` | Average line current | FLOAT32 | 0 ~ 1000 | A |
| 1040 | `0x0410` | Unbalanced line currents | FLOAT32 | -300 ~ 300 | % |
| 1042 | `0x0412` | Total line currents | FLOAT32 | 0 ~ 3000 | A |
| 1044 | `0x0414` | Total active power | FLOAT32 | -3000 ~ 3000 | kW |
| 1046 | `0x0416` | Total reactive power | FLOAT32 | -3000 ~ 3000 | kVAR |
| 1048 | `0x0418` | Total apparent power | FLOAT32 | -3000 ~ 3000 | kVA |
| 1050 | `0x041A` | Total power factor | FLOAT32 | -1.0 ~ 1.0 | — |
| 1052 | `0x041C` | Frequency | FLOAT32 | 0 ~ 1000 | Hz |
| 1054 | `0x041E` | Total import active energy | FLOAT32 | ±1999999999 | kWh |
| 1056 | `0x0420` | Total export active energy | FLOAT32 | ±1999999999 | kWh |
| 1058 | `0x0422` | Total import & export active energy | FLOAT32 | ±1999999999 | kWh |
| 1060 | `0x0424` | L1 import active energy | FLOAT32 | ±1999999999 | kWh |
| 1062 | `0x0426` | L1 export active energy | FLOAT32 | ±1999999999 | kWh |
| 1064 | `0x0428` | L1 import & export active energy | FLOAT32 | ±1999999999 | kWh |
| 1066 | `0x042A` | L2 import active energy | FLOAT32 | ±1999999999 | kWh |
| 1068 | `0x042C` | L2 export active energy | FLOAT32 | ±1999999999 | kWh |
| 1070 | `0x042E` | L2 import & export active energy | FLOAT32 | ±1999999999 | kWh |

### 4.4 Three-phase metering data

| Address (DEC) | Address (HEX) | Description | Type | Range | Unit |
| --- | --- | --- | --- | --- | --- |
| 1000 | `0x03E8` | Voltage A-N | FLOAT32 | 0 ~ 1000 | V |
| 1002 | `0x03EA` | Voltage B-N | FLOAT32 | 0 ~ 1000 | V |
| 1004 | `0x03EC` | Voltage C-N | FLOAT32 | 0 ~ 1000 | V |
| 1006 | `0x03EE` | Current A | FLOAT32 | 0 ~ 1000 | A |
| 1008 | `0x03F0` | Current B | FLOAT32 | 0 ~ 1000 | A |
| 1010 | `0x03F2` | Current C | FLOAT32 | 0 ~ 1000 | A |
| 1012 | `0x03F4` | Active power A | FLOAT32 | -1000 ~ 1000 | kW |
| 1014 | `0x03F6` | Active power B | FLOAT32 | -1000 ~ 1000 | kW |
| 1016 | `0x03F8` | Active power C | FLOAT32 | -1000 ~ 1000 | kW |
| 1018 | `0x03FA` | Reactive power A | FLOAT32 | -1000 ~ 1000 | kVAR |
| 1020 | `0x03FC` | Reactive power B | FLOAT32 | -1000 ~ 1000 | kVAR |
| 1022 | `0x03FE` | Reactive power C | FLOAT32 | -1000 ~ 1000 | kVAR |
| 1024 | `0x0400` | Apparent power A | FLOAT32 | -1000 ~ 1000 | kVA |
| 1026 | `0x0402` | Apparent power B | FLOAT32 | -1000 ~ 1000 | kVA |
| 1028 | `0x0404` | Apparent power C | FLOAT32 | -1000 ~ 1000 | kVA |
| 1030 | `0x0406` | Power factor A | FLOAT32 | -1.0 ~ 1.0 | — |
| 1032 | `0x0408` | Power factor B | FLOAT32 | -1.0 ~ 1.0 | — |
| 1034 | `0x040A` | Power factor C | FLOAT32 | -1.0 ~ 1.0 | — |
| 1036 | `0x040C` | Average voltage L-N | FLOAT32 | 0 ~ 1000 | V |
| 1038 | `0x040E` | Average line current | FLOAT32 | 0 ~ 1000 | A |
| 1040 | `0x0410` | Unbalanced line currents | FLOAT32 | -300 ~ 300 | % |
| 1042 | `0x0412` | Total line currents | FLOAT32 | 0 ~ 3000 | A |
| 1044 | `0x0414` | Total active power | FLOAT32 | -3000 ~ 3000 | kW |
| 1046 | `0x0416` | Total reactive power | FLOAT32 | -3000 ~ 3000 | kVAR |
| 1048 | `0x0418` | Total apparent power | FLOAT32 | -3000 ~ 3000 | kVA |
| 1050 | `0x041A` | Total power factor | FLOAT32 | -1.0 ~ 1.0 | — |
| 1052 | `0x041C` | Frequency | FLOAT32 | 0 ~ 1000 | Hz |
| 1054 | `0x041E` | Total import active energy | FLOAT32 | ±1999999999 | kWh |
| 1056 | `0x0420` | Total export active energy | FLOAT32 | ±1999999999 | kWh |
| 1058 | `0x0422` | Total import & export active energy | FLOAT32 | ±1999999999 | kWh |
| 1060 | `0x0424` | Phase A import active energy | FLOAT32 | ±1999999999 | kWh |
| 1062 | `0x0426` | Phase A export active energy | FLOAT32 | ±1999999999 | kWh |
| 1064 | `0x0428` | Phase A import & export active energy | FLOAT32 | ±1999999999 | kWh |
| 1066 | `0x042A` | Phase B import active energy | FLOAT32 | ±1999999999 | kWh |
| 1068 | `0x042C` | Phase B export active energy | FLOAT32 | ±1999999999 | kWh |
| 1070 | `0x042E` | Phase B import & export active energy | FLOAT32 | ±1999999999 | kWh |
| 1072 | `0x0430` | Phase C import active energy | FLOAT32 | ±1999999999 | kWh |
| 1074 | `0x0432` | Phase C export active energy | FLOAT32 | ±1999999999 | kWh |
| 1076 | `0x0434` | Phase C import & export active energy | FLOAT32 | ±1999999999 | kWh |

### 4.5 Reading FLOAT32 values

All measurements are **FLOAT32**, two registers each, **high word first**. For example the registers `0x435C 0x0000` are `0x435C0000` = `220.0`. In most libraries this is "Big Endian, word order big / ABCD". If the numbers look wrong (for example `1.6e-41` or huge values) your tool is using word-swapped order (CDAB): switch the setting.

- Units: power in **kW** / kVAR / kVA, energy in **kWh**, voltage V, current A. This is the same unit as the telemetry JSON in [Telemetry Payload](../reference/telemetry-payload.en.md); the firmware copies the meter chip registers, so values are not rescaled.
- Addresses that are not listed in a table (for example 1004 on the split-phase map) are inside the window but have no defined meaning; do not use them.

## 5. Control registers

Write with function code `0x06`. These registers are **outside** the read window and **cannot be read**.

| Address (DEC) | Address (HEX) | Function | Value to write |
|---------------|---------------|----------|----------------|
| 10001 | `0x2711` | Reset energy accumulators | `0x51AA` (20906) |
| 10002 | `0x2712` | Locate: blink the LED | `0x5055` (20565) |

- A wrong value returns exception `03`; a wrong address returns `02`.
- Locate blinks the LED (about 15 seconds according to the Gitbook page) so you can find the physical meter in a crowded panel; it does the same as the `location` command.
- **Reset energy is irreversible.** It is the same as the `zero` command.

> The Gitbook page lists the locate register at **10000** (`0x2710`). In the firmware source the Wi-Fi module does not handle 10000 over Modbus TCP: locate is at **10002** (`0x2712`). 10000 is the address of the same function on the meter-side MCU, which probably explains the page. Reset energy at 10001 is the same in both. This page follows the source. Please confirm on a device; the CHANGELOG records the item.

## 6. Examples

### 6.1 `mbpoll`

```text
# read three-phase total active power (1044, one FLOAT32 = 2 registers), word order ABCD
mbpoll -m tcp -a 1 -0 -B -t 3:float -r 1044 -c 1 192.168.1.50
```

`-0` makes the address zero-based (otherwise `mbpoll` counts from 1 and you would need `-r 1045`), `-B` selects the big-endian word order. Compare with the same value in the HTTP `/data` response to check the setup.

### 6.2 Raw Python

The tool [`tools/lan/modbus_poll.py`](../../tools/lan/README.en.md) does this with no extra libraries, and also decodes the identification block. The core is:

```python
import socket, struct

def read_regs(sock, start, count, unit=1, fc=3, tid=1):
    pdu = struct.pack(">BHH", fc, start, count)
    sock.sendall(struct.pack(">HHHB", tid, 0, len(pdu) + 1, unit) + pdu)
    head = sock.recv(7)                                  # MBAP: tid, pid, length, unit
    body = b""
    while len(body) < struct.unpack(">H", head[4:6])[0] - 1:
        body += sock.recv(256)
    if body[0] & 0x80:
        raise RuntimeError("Modbus exception %d" % body[1])
    return body[2:2 + body[1]]

s = socket.create_connection(("192.168.1.50", 502), timeout=3)
raw = read_regs(s, 1044, 2)
print(struct.unpack(">f", raw)[0], "kW")
```

## 7. Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Connection refused / timeout | Function bit 15 is off (`getFunctionMap`), the device is not on the same subnet, or all connection slots are in use |
| Connected, no response | Frame length wrong or several requests sent without waiting; a bad frame is dropped silently |
| Exception 02 | Range outside 978 ~ 1077 (for example reading 1078 or more in one request) |
| Exception 01 | Function code not 03 / 04 / 06 |
| Strange float values | Wrong word order (use ABCD), or the address is off by one (some tools count from 1) |
| Signal strength shows positive | It is the absolute value, see [Section 4.1](#41-product-identification-base-address-978) |
| Disconnects after about 30 s | Idle timeout; poll more often or reconnect |
| TLS handshake fails on 502 | The device has no TLS slot (it fell back to plaintext) or the client does not accept the device certificate; see the [Overview](../overview/open-wifi-overview.en.md#31-tls-connection-limit) |

## 8. Related pages

- [Overview](../overview/open-wifi-overview.en.md)
- [Telemetry Payload](../reference/telemetry-payload.en.md): the same values in JSON
- [Business Command Reference](../ble-common/ble-business-api.en.md): `enablemodbustcp`, `enabletls`, `getFunctionMap`, `modbus` (RS485 side)
- Machine-readable map: [`spec/modbus-tcp-map.json`](../../spec/modbus-tcp-map.json)
