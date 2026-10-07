# 遥测数据格式

> 状态：初版 ｜ 适用：SPM / SDM Open Wi-Fi 全部分支 ｜ 依据：固件源码快照 SXM_EW_C3 `5.1.16`、SDMV2 `1.2.12` / `3.1.19`

设备周期性生成一份遥测 JSON（"一包数据"）。这一份 JSON 通过多个通道原样送出，字段只在本页维护。

## 1. 哪些通道带这份数据

| 通道 | 怎么拿到 | 周期 |
|------|----------|------|
| MQTT | 订阅 `{Model}/{SN}/data` | 默认 5 s，可改（MQTT 周期，最小 1 s） |
| HTTP / HTTPS | `GET /data`；`GET /snapshot` 的 `data` 字段 | 按需，每次调用取最新一包 |
| WebSocket | 连接后设备自动推送 | 默认 5000 ms，100 ms ~ 86400000 ms |
| UDP | 发往已配置的目标 IP:端口 | 默认 5000 ms，最小 100 ms |
| Modbus TCP | 读寄存器，**不是 JSON**，见 [Modbus TCP](../modbus-tcp/modbus-tcp-api.zh-CN.md) | 按需 |
| BLE | `cmd=read` 后读特征值 | 按需 |

各通道周期互相独立，改法见 [业务命令参考](../ble-common/ble-business-api.zh-CN.md)（`mqtt`、`udp`、`setInterval`）。出厂默认值来自固件源码；以设备实际值为准，可从 `model` 应答读取（MQTT 周期 `MI`、UDP 周期 `UI`，HTTP `/model` 里是 `mqttInterval`、`udpInterval`、`wsInterval`）。

## 2. 公共字段

所有型号都有：

| 字段 | 类型 | 说明 |
|------|------|------|
| `Post` | number | 报文计数，设备每生成一包加 1，重启后归零。用来发现丢包和重复 |
| `Time` | number | Unix 时间戳（秒）。设备靠 NTP 校时，未校时前不可信 |
| `IP` | string | 设备 IPv4 |
| `Rssi` | number | Wi-Fi 信号强度，dBm，负数 |
| `FWVersion` | string | Wi-Fi 模组固件版本，例如 `"5.1.16"` |
| `MCUVersion` | string | 计量 MCU 固件版本，例如 `"003.00.13"` |
| `SerialNumber` | string | 设备序列号，12 位大写十六进制（Wi-Fi MAC） |
| `ProductModel` | string | 型号，例如 `SPM01`、`SPM02`、`SDM01_3PN` |
| `TP` | number | 型号代码，见 [第 3 节](#3-tp-型号代码) |

## 3. TP 型号代码

`TP` 是**型号代码**，不是相数。

| TP | 型号 | 相数 | 出现在 |
|----|------|------|--------|
| 1 | `SPM01` | 单相 | Basic、Lite（SXM 构建） |
| 2 | `SDM01_1PN` | 单相 | Basic、Lite（SXM 构建） |
| 3 | `SPM02` | 三相 | Basic、Lite（SXM 构建） |
| 4 | `SDM01_3PN` | 三相 | Basic、Lite（SXM 构建） |
| 5 | `SDM02` | 分相 | Basic、Lite |
| 8 | SDM01 Gen2 全部型号 | 单相或三相 | Basic+、Pro（SDMV2 C3 / C6 构建） |
| 9 | SDMV2S3 / H2 构建 | — | 其他构建，本文不覆盖 |

要点：

- SDM01 Gen2（Basic+ / Pro）的 `TP` 恒为 `8`，**不能**用它区分单相和三相。
- 解析时请按 `ProductModel` 或"字段是否存在"判断（有 `VoltageX` 就是三相，有 `VoltageL1` 就是分相，有 `Voltage` 就是单相），不要写死 `TP`。
- 早期发布页写过"`TP` 1 = 单相、3 = 三相"，这只对 SPM01 / SPM02 成立。

## 4. 各型号字段

数值都是**字符串**，小数位固定：电压 1 位，电流和功率 3 位，功率因数和频率 2 位，电能 2 位，不平衡度 0 位。单位：V、A、kW、kVA、kVAR、Hz、kWh、%。

### 4.1 单相（`SPM01`、`SDM01_1PN`）

| 字段 | 单位 | 说明 |
|------|------|------|
| `Voltage` | V | 电压 |
| `Current` | A | 电流 |
| `ActivePower` | kW | 有功功率 |
| `ApparentPower` | kVA | 视在功率 |
| `PowerFactor` | — | 功率因数 |
| `Frequency` | Hz | 频率 |
| `ForwardEnergy` | kWh | 正向（购入）有功电能 |
| `ReverseEnergy` | kWh | 反向（送出）有功电能 |
| `TotalEnergy` | kWh | 正向 + 反向 |

### 4.2 分相（`SDM02`）

| 字段 | 单位 |
|------|------|
| `VoltageL1`、`VoltageL2` | V |
| `CurrentL1`、`CurrentL2`、`TotalCurrent` | A |
| `ActivePowerL1`、`ActivePowerL2`、`TotalActivePower` | kW |
| `ReactivePowerL1`、`ReactivePowerL2`、`TotalReactivePower` | kVAR |
| `ApparentPowerL1`、`ApparentPowerL2`、`TotalApparentPower` | kVA |
| `PowerFactorL1`、`PowerFactorL2`、`OverallPowerFactor` | — |
| `AverageVoltageL_N` | V |
| `AverageLineCurrent` | A |
| `Frequency` | Hz |
| `ForwardEnergyL1`、`ForwardEnergyL2`、`TotalForwardEnergy` | kWh |
| `ReverseEnergyL1`、`ReverseEnergyL2`、`TotalReverseEnergy` | kWh |
| `TotalEnergyL1`、`TotalEnergyL2`、`TotalEnergy` | kWh |

### 4.3 三相（`SPM02`、`SDM01_3PN`）

`X`、`Y`、`Z` 依次对应 A、B、C 相。

| 字段 | 单位 |
|------|------|
| `VoltageX`、`VoltageY`、`VoltageZ` | V |
| `CurrentX`、`CurrentY`、`CurrentZ`、`TotalCurrent` | A |
| `ActivePowerX`、`ActivePowerY`、`ActivePowerZ`、`TotalActivePower` | kW |
| `ReactivePowerX`、`ReactivePowerY`、`ReactivePowerZ`、`TotalReactivePower` | kVAR |
| `ApparentPowerX`、`ApparentPowerY`、`ApparentPowerZ`、`TotalApparentPower` | kVA |
| `PowerFactorX`、`PowerFactorY`、`PowerFactorZ`、`OverallPowerFactor` | — |
| `AverageVoltageL_N` | V |
| `AverageLineCurrent` | A |
| `UnbalanceLineCurrents` | % |
| `Frequency` | Hz |
| `ForwardEnergyX`、`ForwardEnergyY`、`ForwardEnergyZ`、`TotalForwardEnergy` | kWh |
| `ReverseEnergyX`、`ReverseEnergyY`、`ReverseEnergyZ`、`TotalReverseEnergy` | kWh |
| `TotalEnergyX`、`TotalEnergyY`、`TotalEnergyZ`、`TotalEnergy` | kWh |

不同固件版本的字段略有增减（例如 `TotalCurrent`、`TotalReactivePower`、`TotalApparentPower`、`AverageVoltageL_N`、`AverageLineCurrent`、`TotalEnergy*` 在 5.1.16 源码里有，更早的版本可能没有）。解析时请按"有则用，无则忽略"处理。

## 5. 示例

单相：

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

三相：

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

## 6. 通用格式（`commonmode`）

`{"cmd":"commonmode","value":1}` 把上报格式从默认的"BT 格式"（上面各节）切换成"通用格式"，格式兼容常见的智能电表 `NotifyStatus` 消息；`value=0` 切回。设置会保存，重启后保持。

通用格式的差异：

- 公共字段用小写键：`tp`、`src`（设备全名）、`dst`（固定 `"*"`）、`method`（固定 `"NotifyStatus"`）、`ip`、`rssi`、`fwversion`、`serialnumber`、`mcuversion`、`post`。
- 测量值放在 `params` 里，时间戳是 `params.ts`，测量值是 `params["em:0"]`，数值为**数字**而不是字符串。
- 功率单位是 **W**、电能单位是 **Wh**（BT 格式是 kW、kWh，设备乘 1000 后输出）。
- 单相键：`act_power`、`aprt_power`、`current`、`freq`、`pf`、`voltage`、`act_energy`、`act_ret_energy`。
- 三相键：`a_` / `b_` / `c_` 加 `act_power`、`aprt_power`、`current`、`freq`、`pf`、`voltage`，另有 `total_act_power`、`total_aprt_power`、`total_current`、`a_total_act_energy`、`a_total_act_ret_energy`（B、C 相同理）、`total_act`、`total_act_ret`。某相电压不高于 50 V 时，该相的 `*_freq` 输出 0。
- `params["emdata:0"]` 总是空对象，电能读 `em:0` 里的键。

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

开启通用格式后，Modbus TCP 的寄存器布局也会按该风格改变，本文档**不**覆盖那套布局；需要标准寄存器表时请保持 `commonmode=0`。

## 7. 解析建议

1. 先看 `ProductModel` 和字段名，再决定按单相、分相还是三相解析；不要依赖 `TP`。
2. 数值字符串用十进制解析成浮点；不要假设小数位固定不变。
3. 用 `Post` 判断是否重复或丢包；设备重启后 `Post` 会回到小数值，不要把"变小"当成错误。
4. 用 `Time` 之前先检查它是不是明显偏小（未校时）。
5. 未知字段忽略，缺字段不当作错误。
