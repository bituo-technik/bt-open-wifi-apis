# AGENTS.md — 给 AI 的入口

你在使用或维护 **Bituo SPM / SDM / SXM Open Wi-Fi 设备的对外 API 文档仓**。目标有两类：

- **A. 帮用户用本仓文档写自己的 App**（BLE 配网、局域网 / 云端读电参、配置设备）。
- **B. 帮维护者改文档 / 工具。**

不确定属于哪类时，先问用户：用**哪个通道**（BLE / Modbus TCP / HTTP / WebSocket / MQTT / UDP），以及设备是哪个固件分支（Basic / Basic+ / Lite / Pro）。BLE 还要问是**明文（服务 A002）还是加密（服务 A003）**。

## A0. 写 Wi-Fi 通道的集成（Modbus TCP / HTTP / WebSocket / MQTT / UDP / mDNS）

| 要做什么 | 必读（按顺序） | 或：一个文件搞定 |
|----------|----------------|------------------|
| 不知道选哪个通道 / 分支差异 | `docs/overview/open-wifi-overview.zh-CN.md` | `dist/open-wifi-all.complete.zh-CN.md`（全量） |
| 找设备 IP | `docs/mdns/mdns-discovery.zh-CN.md` | `dist/mdns.complete.zh-CN.md` |
| Modbus TCP 轮询 | `docs/modbus-tcp/modbus-tcp-api.zh-CN.md`，机器可读：`spec/modbus-tcp-map.json` | `dist/modbus-tcp.complete.zh-CN.md` |
| HTTP / HTTPS | `docs/http/http-api.zh-CN.md` → `docs/ble-common/ble-business-api.zh-CN.md`；清单：`spec/http-endpoints.json` | `dist/http.complete.zh-CN.md` |
| WebSocket | `docs/websocket/websocket-api.zh-CN.md`；清单：`spec/websocket-api.json` | `dist/websocket.complete.zh-CN.md` |
| MQTT | `docs/mqtt/mqtt-api.zh-CN.md`；清单：`spec/mqtt-api.json` | `dist/mqtt.complete.zh-CN.md` |
| UDP 接收端 | `docs/udp/udp-api.zh-CN.md`；AES-CCM 测试向量：`spec/udp-aes-test-vector.json` | `dist/udp.complete.zh-CN.md` |
| 解析数据 / 处理失败 | `docs/reference/telemetry-payload.zh-CN.md`、`docs/reference/error-codes.zh-CN.md`；`spec/error-codes.json` | （已含在 http / mqtt / websocket 合集里） |

英文把 `zh-CN` 换成 `en`。Wi-Fi 通道的硬约束：

1. **先查 Overview 的能力矩阵**：不是所有分支都有 HTTPS / Modbus TLS / WSS / UDP 加密；拿不到 TLS 槽位时服务会**回退为明文**，客户端要能处理。
2. **成功判据看 `ok`**（统一应答 `ok/msg/event/d`），失败才有 `code`；HTTP 失败通常仍是状态码 200。`code` 与固定码会撞号，按 `event` + 英文 `msg` 判断。
3. **业务命令只在 `docs/ble-common` 里查**：HTTP 是 `POST /save-config`，MQTT 发到 `/cmd`，WebSocket 发 `{"cmd":...}`；通道页面只讲包装与限制。入站 JSON 不超过 **1024 字节**。
4. 各通道的差异和陷阱写在各自文档里（例如 HTTP `/save-config` 的特例、Modbus 的 RSSI 为绝对值、UDP 的 `counter`），照文档做，不要凭经验猜。
5. 不要在代码、示例或日志里写入固件默认的测试账号、Broker 地址或任何真实设备的 Web 密码 / MQTT 密码 / 广播密钥。
6. 没有硬件时，先用 `tools/lan/mock_device.py` 自测；它只遵循文档行为，不能代替真机验证。

## A. 写 App：BLE 读什么、怎么读

| 设备 | 必读（按顺序） | 或：一个文件搞定 |
|------|----------------|------------------|
| 明文 BLE（Basic / Basic+，`A002`） | `docs/ble-plaintext/ble-plaintext-api.zh-CN.md` → `docs/ble-common/ble-business-api.zh-CN.md` | `dist/ble-plaintext.complete.zh-CN.md`（`py -3 scripts/build_bundles.py` 生成） |
| 加密 BLE（Lite / Pro，`A003`） | `docs/ble-secured/ble-secured-api.zh-CN.md` → `docs/ble-common/ble-business-api.zh-CN.md` → `docs/ble-secured/crypto-protocol.zh-CN.md` | `dist/ble-secured.complete.zh-CN.md` |

英文把 `zh-CN` 换成 `en`。机器可读清单在 `spec/`：`ble-business-commands.json`（命令与字段）、`ble-plain-api.json` / `ble-secured-api.json`（传输层）、`ble-secured-test-vectors.json`（加密已知答案测试向量）。

### 硬约束

1. **只用文档里出现的命令、字段、UUID。** 没有就是没有，输出 TODO 并说明原因，不要编造。
2. **两个通道不可混用：** 明文 `A002 / C303 / C304 / C305`，加密 `A003 / C313 / C314 / C315`。加密通道**不要**发 `pass` / `blepassword` / `resetauth`。
3. 设备返回的 `msg`、错误码按英文原文比对；业务 JSON 键名不翻译。
4. 命令**严格串行**：写一条 → 等 `event` 匹配的应答 → 再写下一条。
5. 配网成功的唯一判据：读快照里的 `IP` 变成点分十进制 IPv4。`wifi` 命令返回成功只表示"已接受并开始连路由"。Wi-Fi 仅 2.4 GHz。
6. 不同型号命令集不同：按 `ok` / `msg` 处理失败，不要假设全部命令都存在。不要实现 `switch-config`。
7. 加密通道：算法参数（曲线 `secp256r1`、PBKDF2 10000 次、HKDF `info` 字符串、CCM nonce 构造）一个字都不要改。**先用 `spec/ble-secured-test-vectors.json` 验证自己的 PBKDF2 / HKDF / AES-CCM，再去连真机。**
8. 加密通道里遇到 `step=3` 但本地没有会话态：**断开重连**，不要再发 J-PAKE。
9. 不要在日志里默认打印 LTK / session_key / broadcast_key；示例 PIN / SN 用虚构值。

### 推荐实现顺序

扫描 → 连接 → 订阅通知 → （明文：`pass`；加密：握手）→ `wifi` → 轮询读快照的 `IP` → 再做读电参、`model`、`getFunctionMap`、`mqttdata`。每个传输层文档的 §2 有可整段复制的提示词，§9 有验收清单。

## B. 维护：改仓库前先读

1. `REPO_ORGANIZATION.md`：目录结构与**共用业务文档**规则（§3）。
2. 改业务命令 → **只改** `docs/ble-common/*`（zh 与 en 同步）+ `spec/ble-business-commands.json`；不要把命令表复制回通道文档。
3. 改通道传输层 → 只改对应 `docs/ble-plaintext` 或 `docs/ble-secured`（zh 与 en 同步，章节编号一致）。
3a. 改 Wi-Fi 通道（`docs/{mdns,modbus-tcp,http,websocket,mqtt,udp}`）→ zh 与 en 同步；字段只改 `docs/reference/telemetry-payload.*`、错误码只改 `docs/reference/error-codes.*`（并同步 `spec/error-codes.json`）；Modbus 寄存器改 `spec/modbus-tcp-map.json` 和两份文档的表（`check_docs.py` 会逐地址比对）；通道文档开头的"依据"一行写明核对过的固件版本；固件行为与线上 Gitbook 冲突时以固件源码为准，并把差异记进 CHANGELOG 的"待确认"。
4. 改了 `tools/ble-secured/web-ble-secured-console.html` 或 `ble_secured_crypto.js` → 运行 `py -3 tools/ble-secured/bundle_offline_html.py` 重新生成 `*.offline.html`（不要手改生成物）。
5. 提交前运行：

```bat
py -3 scripts/check_docs.py
py -3 scripts/check_test_vectors.py
node scripts/check_test_vectors.mjs
```

改了 `tools/lan/*.py` 后至少 `py -3 -m py_compile tools/lan/*.py`，并用 `mock_device.py` 跑一遍对应工具（见 `tools/lan/README.md`）。

6. 有改动就写进 `CHANGELOG.md`，并注明对齐的固件版本。
7. **不得提交：** `tools/ble-secured/ble_crypto_client_cache.json`、真机 PIN / LTK / 密钥、固件源码。固件仓在本机另开对照，不复制进来。
8. 事实拿不准（固件行为、型号差异）时问用户或写进 CHANGELOG 的"待确认"，**不要**在客户文档里留 `TBD` / `待确认` 之类的占位。

## 术语

固件分支 Basic / Basic+（明文 BLE）、Lite / Pro（加密 BLE）；Overview 的能力矩阵是各分支支持哪些通道的权威来源。PIN = 机身 8 位数字（二维码下 11 位可换算）；LTK = 长期密钥，设备在 Wi-Fi 关联成功后才落盘。
