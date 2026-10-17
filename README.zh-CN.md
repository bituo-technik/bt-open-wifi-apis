[English](README.en.md)

# bt-open-wifi-apis

Bituo SPM / SDM / SXM 电能表 **Open Wi-Fi API** 的对外接口文档、体验工具和机器可读清单。**私有仓库**，按需授权给合作方；不含固件源码。

线上入口：[SPM/SDM Open Wi-Fi API Overview](https://docs.bituo-technik.com/device-api/spm-sdm-open-wi-fi-api-overview)　|　组织与维护约定：[`REPO_ORGANIZATION.zh-CN.md`](REPO_ORGANIZATION.zh-CN.md)　|　AI 入口：[`AGENTS.md`](AGENTS.md)

## 我该读哪份文档？

### Wi-Fi 通道（局域网 / 云端读数据、改配置）

先读 [总览](docs/overview/open-wifi-overview.zh-CN.md)，确认设备的固件分支（Basic / Basic+ / Lite / Pro）和可用通道，再按场景选：

| 场景 | 文档 | 工具 |
|------|------|------|
| 找到设备的 IP | [mDNS 发现](docs/mdns/mdns-discovery.zh-CN.md) | `discover_mdns.py` |
| PLC / 工业网关 / EMS 轮询 | [Modbus TCP](docs/modbus-tcp/modbus-tcp-api.zh-CN.md) | `modbus_poll.py` |
| 脚本、网关、改配置 | [HTTP / HTTPS](docs/http/http-api.zh-CN.md) | `http_poll.py` |
| 本地实时推送 | [WebSocket](docs/websocket/websocket-api.zh-CN.md) | `ws_client.py` |
| 云端 / 自建 Broker | [MQTT](docs/mqtt/mqtt-api.zh-CN.md) | `mqtt_monitor.py` |
| 高频单向读数 | [UDP](docs/udp/udp-api.zh-CN.md) | `udp_listen.py` |
| 字段与错误 | [遥测数据格式](docs/reference/telemetry-payload.zh-CN.md)、[错误码](docs/reference/error-codes.zh-CN.md) | |

工具都在 [`tools/lan`](tools/lan/README.zh-CN.md)，没有硬件时用 `mock_device.py`（假电表）。各通道共用同一套业务命令，见 [业务命令参考](docs/ble-common/ble-business-api.zh-CN.md)。

### BLE 通道（配网、近场控制）

先确认设备的蓝牙服务：**`A002` = 明文，`A003` = 加密**（同一台设备只有其中一种）。

| 你的设备 | 第 1 步：传输层（怎么连、怎么解锁 / 握手） | 第 2 步：业务层（发什么命令、读什么字段） | 参考实现 |
|----------|------------------------------------------|------------------------------------------|----------|
| **Basic / Basic+**（明文，`A002`） | [明文 BLE 接口说明](docs/ble-plaintext/ble-plaintext-api.zh-CN.md) | [业务命令参考](docs/ble-common/ble-business-api.zh-CN.md) | [`tools/ble-plaintext`](tools/ble-plaintext/README.zh-CN.md) |
| **Lite / Pro**（加密，`A003`） | [加密 BLE 接口说明](docs/ble-secured/ble-secured-api.zh-CN.md)；密码学细节见 [协议权威参考](docs/ble-secured/crypto-protocol.zh-CN.md) | 同上（两个通道共用） | [`tools/ble-secured`](tools/ble-secured/README.zh-CN.md) |

两个 BLE 通道解开传输层之后的业务 JSON **完全一致**，所以业务命令只在 `docs/ble-common` 维护一份，见 [`REPO_ORGANIZATION.zh-CN.md` §3](REPO_ORGANIZATION.zh-CN.md)。

只想**让设备连上 Wi-Fi**：读所选传输层文档的「快速开始」，再用 [业务命令参考 §2](docs/ble-common/ble-business-api.zh-CN.md#2-wi-fi-配网业务命令)。想直接试：见下面「工具」。

## 目录

```text
docs/
  overview/         Wi-Fi 总览：固件分支、通道能力矩阵、选通道
  mdns/ modbus-tcp/ http/ websocket/ mqtt/ udp/   各 Wi-Fi 通道
  reference/        遥测数据格式、错误码（各通道共用）
  ble-common/       所有通道共用的业务命令参考（zh-CN / en）
  ble-plaintext/    明文 BLE 传输层（A002）
  ble-secured/      加密 BLE 传输层（A003）+ 协议权威参考
  README.md         语言选择    SUMMARY.md  Gitbook 目录
tools/
  lan/              Wi-Fi 通道命令行工具 + 假电表
  ble-plaintext/ ble-secured/   BLE 体验工具（网页 + Windows）
spec/               机器可读：命令清单、各通道清单、错误码、测试向量
scripts/            校验与单页合集生成
dist/               生成物（不入库）
```

## 工具

```bat
:: Wi-Fi 通道（只需 Python 3.9+），例如找设备并读 Modbus
cd tools\lan & py -3 discover_mdns.py & py -3 modbus_poll.py <设备IP>


:: 明文 BLE，Windows
cd tools\ble-plaintext & py -3 -m pip install -r requirements.txt & py -3 ble_plain_gui.py

:: 加密 BLE，Windows
cd tools\ble-secured & py -3 -m pip install -r requirements.txt & py -3 ble_secured_gui.py
```

网页版（Chrome / Edge）和手机使用说明见 [`tools/README.zh-CN.md`](tools/README.zh-CN.md)。给客户用的加密网页是**单个文件** [`web-ble-secured-console.offline.html`](tools/ble-secured/web-ble-secured-console.offline.html)，放到任意 HTTPS 静态托管即可。

## 维护

| 命令 | 作用 |
|------|------|
| `py -3 scripts/check_docs.py` | 校验链接 / 锚点、中英章节对齐、`spec` 与文档一致（命令集、Modbus 寄存器、错误码、mDNS 命名）、无遗留占位符 |
| `py -3 scripts/check_test_vectors.py` · `node scripts/check_test_vectors.mjs` | 两份参考实现对加密测试向量的结果必须一致；Python 另外校验 UDP AES-CCM 向量 |
| `py -3 scripts/build_bundles.py` | 生成 `dist/*.md` 单页合集（每个通道一份 + `open-wifi-all` 全量），用于粘贴 Gitbook 或整份交给 AI |
| `py -3 tools/ble-secured/bundle_offline_html.py` | 改了加密网页后重新生成离线单文件 |

入口页（本文件、`docs/README`、`tools/**/README`、`REPO_ORGANIZATION`、`CHANGELOG`、`AGENTS`）中英各一份，改动时两份一起更新。`AGENTS.md` 是编码工具自动读取的正本。

## 不要提交

`tools/ble-secured/ble_crypto_client_cache.json`（含 LTK）、任何真机 PIN / LTK / 密钥截图、固件源码。`.gitignore` 已排除缓存文件。
