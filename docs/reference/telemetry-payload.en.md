# Telemetry Payload

> Status: first release | Applies to: all SPM / SDM Open Wi-Fi branches | Firmware versions covered: Basic / Lite 5.1.16, Basic+ 1.2.12, Pro 3.1.19

The device periodically builds one telemetry JSON (a "packet"). The same JSON is sent unchanged over several channels, so its fields are maintained only on this page.

## 1. Which channels carry it

| Channel | How to get it | Period |
|---------|---------------|--------|
| MQTT | Subscribe to `{Model}/{SN}/data` | Default 5 s, configurable (MQTT period, minimum 1 s) |
| HTTP / HTTPS | `GET /data`; the `data` field of `GET /snapshot` | On demand, latest packet on every call |
| WebSocket | Pushed automatically after you connect | Default 5000 ms, 100 ms to 86400000 ms |
| UDP | Sent to the configured target IP:port | Default 5000 ms, minimum 100 ms |
| Modbus TCP | Register reads, **not JSON**; see [Modbus TCP](../modbus-tcp/modbus-tcp-api.en.md) | On demand |
| BLE | `cmd=read`, then read the characteristic | On demand |

The periods are independent; how to change them is in the [Business Command Reference](../ble-common/ble-business-api.en.md) (`mqtt`, `udp`, `setInterval`). The value on the device wins over any factory default and can be read from the `model` response (MQTT period `MI`, UDP period `UI`; in HTTP `/model` they are `mqttInterval`, `udpInterval`, `wsInterval`).

## 2. Common fields

Present on every model:

| Field | Type | Description |
|-------|------|-------------|
| `Post` | number | Packet counter, +1 for each packet built, back to 0 after a reboot. Use it to spot loss and duplicates |
| `Time` | number | Unix timestamp (seconds). The device syncs by NTP; do not trust it before the first sync |
| `IP` | string | Device IPv4 |
| `Rssi` | number | Wi-Fi signal strength in dBm, negative |
| `FWVersion` | string | Wi-Fi module firmware version, for example `"5.1.16"` |
| `MCUVersion` | string | Metering MCU firmware version, for example `"003.00.13"` |
| `SerialNumber` | string | Device serial number, 12 uppercase hex characters (Wi-Fi MAC) |
| `ProductModel` | string | Model, for example `SPM01`, `SPM02`, `SDM01_3PN` |
| `TP` | number | Model code, see [Section 3](#3-tp-model-code) |

## 3. TP model code

`TP` is a **model code**, not a phase count.

| TP | Model | Phases | Seen on |
|----|-------|--------|---------|
| 1 | `SPM01` | single | Basic, Lite |
| 2 | `SDM01_1PN` | single | Basic, Lite |
| 3 | `SPM02` | three | Basic, Lite |
| 4 | `SDM01_3PN` | three | Basic, Lite |
| 5 | `SDM02` | split | Basic, Lite |
| 8 | all SDM01 Gen2 models | single or three | Basic+, Pro |
| 9 | other models | — | not covered here |

Points to remember:

- On SDM01 Gen2 (Basic+ / Pro) `TP` is always `8`, so it **cannot** tell single phase from three phase.
- Decide by `ProductModel` or by which fields exist (`VoltageX` means three-phase, `VoltageL1` means split-phase, `Voltage` means single-phase). Do not hard-code `TP`.
- An earlier published page said "`TP` 1 = single phase, 3 = three phase"; that is only true for SPM01 / SPM02.

## 4. Fields per model

Values are **strings** with fixed decimals: voltage 1, current and power 3, power factor and frequency 2, energy 2, unbalance 0. Units: V, A, kW, kVA, kVAR, Hz, kWh, %.

### 4.1 Single-phase (`SPM01`, `SDM01_1PN`)

| Field | Unit | Description |
|-------|------|-------------|
| `Voltage` | V | Voltage |
| `Current` | A | Current |
| `ActivePower` | kW | Active power |
| `ApparentPower` | kVA | Apparent power |
| `PowerFactor` | — | Power factor |
| `Frequency` | Hz | Frequency |
| `ForwardEnergy` | kWh | Forward (import) active energy |
| `ReverseEnergy` | kWh | Reverse (export) active energy |
| `TotalEnergy` | kWh | Forward + reverse |

### 4.2 Split-phase (`SDM02`)

| Field | Unit |
|-------|------|
| `VoltageL1`, `VoltageL2` | V |
| `CurrentL1`, `CurrentL2`, `TotalCurrent` | A |
| `ActivePowerL1`, `ActivePowerL2`, `TotalActivePower` | kW |
| `ReactivePowerL1`, `ReactivePowerL2`, `TotalReactivePower` | kVAR |
| `ApparentPowerL1`, `ApparentPowerL2`, `TotalApparentPower` | kVA |
| `PowerFactorL1`, `PowerFactorL2`, `OverallPowerFactor` | — |
| `AverageVoltageL_N` | V |
| `AverageLineCurrent` | A |
| `Frequency` | Hz |
| `ForwardEnergyL1`, `ForwardEnergyL2`, `TotalForwardEnergy` | kWh |
| `ReverseEnergyL1`, `ReverseEnergyL2`, `TotalReverseEnergy` | kWh |
| `TotalEnergyL1`, `TotalEnergyL2`, `TotalEnergy` | kWh |

### 4.3 Three-phase (`SPM02`, `SDM01_3PN`)

`X`, `Y`, `Z` are phases A, B, C.

| Field | Unit |
|-------|------|
| `VoltageX`, `VoltageY`, `VoltageZ` | V |
| `CurrentX`, `CurrentY`, `CurrentZ`, `TotalCurrent` | A |
| `ActivePowerX`, `ActivePowerY`, `ActivePowerZ`, `TotalActivePower` | kW |
| `ReactivePowerX`, `ReactivePowerY`, `ReactivePowerZ`, `TotalReactivePower` | kVAR |
| `ApparentPowerX`, `ApparentPowerY`, `ApparentPowerZ`, `TotalApparentPower` | kVA |
| `PowerFactorX`, `PowerFactorY`, `PowerFactorZ`, `OverallPowerFactor` | — |
| `AverageVoltageL_N` | V |
| `AverageLineCurrent` | A |
| `UnbalanceLineCurrents` | % |
| `Frequency` | Hz |
| `ForwardEnergyX`, `ForwardEnergyY`, `ForwardEnergyZ`, `TotalForwardEnergy` | kWh |
| `ReverseEnergyX`, `ReverseEnergyY`, `ReverseEnergyZ`, `TotalReverseEnergy` | kWh |
| `TotalEnergyX`, `TotalEnergyY`, `TotalEnergyZ`, `TotalEnergy` | kWh |

Field sets differ slightly between firmware versions (for example `TotalCurrent`, `TotalReactivePower`, `TotalApparentPower`, `AverageVoltageL_N`, `AverageLineCurrent` and `TotalEnergy*` exist on 5.1.16 and may be missing on older versions). Use a field if it is there and ignore it if it is not.

## 5. Examples

Single-phase:

```json
{
  "Post": 927,
  "Time": 1782313081,
  "IP": "192.168.1.20",
  "Rssi": -68,
  "FWVersion": "5.1.16",
  "SerialNumber": "AABBCCDDEEFF",
  "ProductModel": "SPM01",
  "MCUVersion": "003.00.13",
  "TP": 1,
  "Voltage": "227.6",
  "Current": "0.000",
  "ActivePower": "0.000",
  "ApparentPower": "0.000",
  "PowerFactor": "1.00",
  "Frequency": "50.09",
  "ForwardEnergy": "0.00",
  "ReverseEnergy": "0.00",
  "TotalEnergy": "0.00"
}
```

Three-phase:

```json
{
  "Post": 1842,
  "Time": 1782312995,
  "IP": "192.168.1.21",
  "Rssi": -72,
  "FWVersion": "5.1.16",
  "SerialNumber": "AABBCCDDEE01",
  "ProductModel": "SPM02",
  "MCUVersion": "001.01.01",
  "TP": 3,
  "VoltageX": "226.3", "VoltageY": "226.2", "VoltageZ": "226.2",
  "CurrentX": "0.000", "CurrentY": "0.000", "CurrentZ": "0.000", "TotalCurrent": "0.000",
  "ActivePowerX": "0.000", "ActivePowerY": "0.000", "ActivePowerZ": "0.000", "TotalActivePower": "0.000",
  "ReactivePowerX": "0.000", "ReactivePowerY": "0.000", "ReactivePowerZ": "0.000", "TotalReactivePower": "0.000",
  "ApparentPowerX": "0.000", "ApparentPowerY": "0.000", "ApparentPowerZ": "0.000", "TotalApparentPower": "0.000",
  "PowerFactorX": "0.00", "PowerFactorY": "0.00", "PowerFactorZ": "1.00", "OverallPowerFactor": "0.00",
  "AverageVoltageL_N": "226.2", "AverageLineCurrent": "0.000", "UnbalanceLineCurrents": "0",
  "Frequency": "50.01",
  "ForwardEnergyX": "0.85", "ForwardEnergyY": "0.02", "ForwardEnergyZ": "0.02", "TotalForwardEnergy": "0.89",
  "ReverseEnergyX": "0.00", "ReverseEnergyY": "0.00", "ReverseEnergyZ": "0.00", "TotalReverseEnergy": "0.00",
  "TotalEnergyX": "0.85", "TotalEnergyY": "0.02", "TotalEnergyZ": "0.02", "TotalEnergy": "0.89"
}
```

## 6. Generic format (`commonmode`)

`{"cmd":"commonmode","value":1}` switches the report format from the default "BT format" (the sections above) to a "generic format" that follows the common smart-meter `NotifyStatus` message shape; `value=0` switches back. The setting is saved and survives reboots.

What changes in the generic format:

- Common fields use lowercase keys: `tp`, `src` (full device name), `dst` (always `"*"`), `method` (always `"NotifyStatus"`), `ip`, `rssi`, `fwversion`, `serialnumber`, `mcuversion`, `post`.
- Measurements sit under `params`: the timestamp is `params.ts`, the values are in `params["em:0"]`, and they are **numbers**, not strings.
- Power is in **W** and energy in **Wh** (the BT format uses kW and kWh; the device multiplies by 1000).
- Single-phase keys: `act_power`, `aprt_power`, `current`, `freq`, `pf`, `voltage`, `act_energy`, `act_ret_energy`.
- Three-phase keys: prefix `a_` / `b_` / `c_` with `act_power`, `aprt_power`, `current`, `freq`, `pf`, `voltage`; plus `total_act_power`, `total_aprt_power`, `total_current`, `a_total_act_energy`, `a_total_act_ret_energy` (same for B and C), `total_act`, `total_act_ret`. When a phase voltage is 50 V or lower, that phase's `*_freq` is 0.
- `params["emdata:0"]` is always an empty object; read energy from the keys in `em:0`.

```json
{
  "tp": 1,
  "src": "EnergySensor-SPM01-AABBCCDDEEFF",
  "dst": "*",
  "method": "NotifyStatus",
  "ip": "192.168.1.20",
  "rssi": -68,
  "fwversion": "5.1.16",
  "serialnumber": "AABBCCDDEEFF",
  "mcuversion": "003.00.13",
  "post": 12,
  "params": {
    "ts": 1782313081,
    "em:0": {
      "act_power": 123.0, "aprt_power": 125.0, "current": 0.54,
      "freq": 50.01, "pf": 0.98, "voltage": 227.6,
      "act_energy": 1234.0, "act_ret_energy": 0.0
    },
    "emdata:0": {}
  }
}
```

With the generic format on, the Modbus TCP register layout also changes to that style. This documentation does **not** cover that layout; keep `commonmode=0` if you need the standard register map.

## 7. Parsing advice

1. Look at `ProductModel` and the field names to choose single-phase, split-phase or three-phase parsing; do not rely on `TP`.
2. Parse numeric strings as decimal floats and do not assume the number of decimals stays fixed.
3. Use `Post` to detect duplicates and loss; after a reboot `Post` returns to a small value, so do not treat a decrease as an error.
4. Before using `Time`, check that it is not obviously small (not yet synced).
5. Ignore unknown fields and do not treat missing fields as errors.
