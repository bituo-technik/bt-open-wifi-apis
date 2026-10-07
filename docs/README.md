# 文档阅读路径 / Reading paths

## 我要用 BLE 给电表配 Wi-Fi，或读电参、配置设备

1. 判断设备：扫描后看 GATT 服务。**`A002` = 明文（Basic / Basic+）**，**`A003` = 加密（Lite / Pro）**。
2. 读对应的**传输层**文档（怎么连、怎么解锁 / 握手、怎么重连）：
   - 明文：[ble-plaintext/ble-plaintext-api.zh-CN.md](ble-plaintext/ble-plaintext-api.zh-CN.md) · [EN](ble-plaintext/ble-plaintext-api.en.md)
   - 加密：[ble-secured/ble-secured-api.zh-CN.md](ble-secured/ble-secured-api.zh-CN.md) · [EN](ble-secured/ble-secured-api.en.md)
3. 读**业务层**（发什么命令、读什么字段，两个通道通用）：[ble-common/ble-business-api.zh-CN.md](ble-common/ble-business-api.zh-CN.md) · [EN](ble-common/ble-business-api.en.md)
4. 只有实现加密通道时才需要：[协议权威参考](ble-secured/crypto-protocol.zh-CN.md) · [EN](ble-secured/crypto-protocol.en.md)（J-PAKE / ZKP 二进制布局、广播厂商数据）。

## 我要把文档交给 AI

运行 `py -3 scripts/build_bundles.py`，把 `dist/` 里对应设备的**单个合集文件**交给 AI（见 [`AGENTS.md`](../AGENTS.md)）。传输层文档 §2 有可复制的提示词。

## 文档地图

| 文档 | 内容 | 维护规则 |
|------|------|----------|
| `ble-common/ble-business-api.*` | 业务命令、字段、应答、读快照字段、业务错误码、附录（functionMap 位 / model 短键 / 低频错误码） | **唯一一份**，两个 BLE 通道共用 |
| `ble-plaintext/ble-plaintext-api.*` | 明文通道传输层：UUID、解锁（`pass`）、请求 / 应答匹配、重连、MTU、开发清单 | 只写明文通道专有内容 |
| `ble-secured/ble-secured-api.*` | 加密通道传输层：UUID、认证材料、`step`、密钥派生摘要、信封、重连、常见陷阱 | 只写加密通道专有内容 |
| `ble-secured/crypto-protocol.*` | 加密协议权威参考（固件团队提供） | 与上一份冲突时以它为准 |

文档约定：命令名、字段名、设备 `msg` 保持英文原样；每份文档都有 `zh-CN` 与 `en` 两个版本，章节编号一一对应。
