[English](CHANGELOG.en.md)

# Changelog

按日期倒序。「对齐固件」写明文档 / 工具核对过的固件版本。

## 2026-10-17 — 按公开仓库整理用词

### 文档

- 产品系列只写 SPM / SDM，不再使用内部研发统称。文档对应固件版本写 Basic / Lite 5.1.16、Basic+ 1.2.12、Pro 3.1.19。
- 仓库按公开来写：读者是系统集成商和 DIY 用户。删掉了一处不该对外的内部备注。
- 业务加密广播从 GATT 接口说明和加密协议里拆出，单独成篇 `docs/ble-secured/ble-advertising.*`。

## 2026-10-17 — 入口文档拆成中英两份

### 文档

- 根目录 `README.md`、`docs/README.md`、`tools/README.md`、`tools/lan/README.md`、`tools/ble-plaintext/README.md`、`tools/ble-secured/README.md`、`REPO_ORGANIZATION.md`、`CHANGELOG.md` 改为语言选择页。正文分别在同目录的 `*.zh-CN.md` 与 `*.en.md`，页内不再中英夹写。
- `AGENTS.md` 仍是完整中文说明。编码工具按这个文件名自动读取，所以它不能收成只有语言链接。英文对照是 `AGENTS.en.md`；两份不一致时以 `AGENTS.md` 为准。
- 接口文档里指向工具说明、CHANGELOG、AGENTS 的链接改为同语言文件。`docs/SUMMARY.md` 的阅读路径按语言分开。
- `scripts/check_docs.py` 改为检查 `tools/lan` 的每个脚本都出现在中英两份 README 里。

## 2026-10-07 — 初版补全：Wi-Fi 侧全部通道

**对齐固件：** Basic / Lite `5.1.16`、Basic+ `1.2.12`、Pro `3.1.19`；并对照过线上 Gitbook 的 Overview / MQTT / mDNS / Modbus TCP 页面（2026-05 ~ 2026-06 版本）。

### 文档

- `docs/overview/open-wifi-overview`：固件分支、通道能力矩阵、TLS 槽位限制（优先级 MQTTS > HTTPS > WSS > Modbus TLS）、选通道。
- `docs/mdns/`、`docs/modbus-tcp/`、`docs/http/`、`docs/websocket/`、`docs/mqtt/`、`docs/udp/`：各通道的连接方式、限制、示例、排错；WebSocket、UDP 为全新编写，HTTP 此前没有独立文档。
- `docs/reference/telemetry-payload`（遥测字段，四个通道共用）、`docs/reference/error-codes`（统一应答、通道基数 + 子码、固定码、撞号说明）。
- 重写 `docs/SUMMARY.md`、`docs/README.md`、根 `README.md`、`AGENTS.md`、`REPO_ORGANIZATION.md`。

### 机器可读与工具

- `spec/`：`modbus-tcp-map.json`（寄存器表）、`http-endpoints.json`、`mqtt-api.json`、`websocket-api.json`、`udp-api.json`、`mdns-discovery.json`、`capabilities.json`、`error-codes.json`、`udp-aes-test-vector.json`。
- `tools/lan/`：`discover_mdns.py`、`modbus_poll.py`、`http_poll.py`、`ws_client.py`、`udp_listen.py`（可解 AES-CCM）、`mqtt_monitor.py`、`mock_device.py`（假电表）、`cmdarg.py`（兼容 PowerShell 5.1 丢引号的命令行写法）。
- `scripts/check_docs.py` 增加：`spec` 合法性与 LF 行尾、Modbus 地址与两份文档逐项比对、错误码子码 / 固定码在两种语言文档里都存在、mDNS 命名正则、`tools/lan` 的工具都在 README 里。`check_test_vectors.py` 增加 UDP AES-CCM 向量。`build_bundles.py` 增加各 Wi-Fi 通道合集和 `open-wifi-all`。

### 待确认

请用真机或固件同事核实后更新。

1. **Modbus 定位寄存器**：Gitbook 写 `10000 (0x2710)`；设备上 Wi-Fi 模块通过 Modbus TCP 只处理 `10001`（清零）和 `10002`（定位），`10000` 是表侧 MCU 上同一功能的地址。
2. **Modbus 连接行为**：Gitbook 写「只支持 1 个连接、每次读后复位 socket、必须每次重连」；设备上 Basic / Lite / Pro 最多 2 个、Basic+ 最多 1 个，连接保持，空闲 30 秒（定制固件 12 秒）断开，一次只应答最新一帧。文档保留了「每次重连也可用」的建议。
3. **Modbus 寄存器 994（RSSI）**：Gitbook 写负的 dBm；设备把 `-rssi` 写入无符号寄存器，读到的是绝对值（如 68）。Gitbook 里 MCU 版本 / Wi-Fi 固件版本的示例也写反了（989 是 MCU，997 是 Wi-Fi 固件）。
4. **`commonmode = 1`**：切到这个值后，Modbus 读取映射和遥测格式都会变。文档只描述默认布局（`commonmode = 0`），通用格式的寄存器布局未写入；`mda` / `minvert` 仅提及。
5. **UDP AES-CCM 适用分支**：已发布的矩阵写 Lite、Pro 都支持。Lite `5.1.16` 始终发明文；加密报文只在 Pro 且 HTTPS 打开时出现。矩阵保留线上说法并加了脚注。
6. **mDNS 主机名**：已发布页面说 `VARIANT` 反映 HTTP 实现差异。实际是 Basic / Lite 的 SDM01_3PN、SDM01_1PN 用 `_01`，Basic+ / Pro 用 `_02`，其它 Basic / Lite 型号没有变体字段。主机名就是可改的设备名称（`deviceName`），改名后前缀过滤会失效，文档已说明。
7. **MQTT 默认上报间隔**：设备默认 5 秒，线上文档写 30 秒；文档提示以设备 `MI` 为准。
8. **`TP`**：它实际是型号代码（SDM01 Gen2 恒为 8），不是相数；此前线上「1 = 单相、3 = 三相」只对 SPM01 / SPM02 成立。
9. **`/uploadcefile`** 的参数顺序、首尾各丢一个字符等行为很别扭，文档如实记录并推荐 `/upload` 或 BLE `cafilestart`。
10. Modbus TLS 连接的空闲超时、`mqtt_monitor.py` 对真实 Broker 的行为尚未验证。

### 验证范围

- `check_docs.py`、`check_test_vectors.py` 通过；全部 `tools/lan` 脚本编译通过。
- `modbus_poll.py`、`http_poll.py`（含 token 重新登录）、`ws_client.py`、`udp_listen.py`（明文与 AES-CCM）已对 `mock_device.py` 跑通；`discover_mdns.py` 内置解析与 zeroconf 两种路径在局域网真机上都找到了设备。
- **没有**对真机验证 Modbus / HTTP / WebSocket / UDP（发现到的那台真机 Modbus 与 HTTP 默认关闭）；`mqtt_monitor.py` 未联调（没有 Broker）。

### 安全提示

- 文档、示例和工具里不要写入测试用的 Broker 地址或账号。

## 2026-10-07 — 初始合并：BLE 明文 + BLE 加密

**对齐固件：** Basic `5.1.15`（SDM01_3PN 实机校对示例应答）；Lite / Pro 加密握手以 `BLE 安全通道 API 文档 V2` 为准，已用本仓工具在真机上跑通握手、加密配网与读写。

### 仓库

- 新建 `bt-open-wifi-apis`，合并 `Meter-BLE-Plaintext-API` 与 `Meter-BLE-Secured-API`（原目录保持不变）。
- 目录：`docs/{ble-common,ble-plaintext,ble-secured}`、`tools/{ble-plaintext,ble-secured}`、`spec/`、`scripts/`。
- 新增 `README.md` / `AGENTS.md` / `REPO_ORGANIZATION.md`，仓库为私有，缓存文件与密钥已排除。
- 加密工具的 `vendor/` 去掉 `.map` / `.d.ts`（3.4 MB → 约 1.2 MB），离线单文件重新生成通过。

### 文档

- **业务 JSON 合并为一份**：新增 `docs/ble-common/ble-business-api.*`，原明文文档的 Wi-Fi 配网、命令参考、读快照、业务错误码、附录整体迁入；明文 / 加密文档只保留传输层。加密文档此前 §6 / §7 / §8 / 附录只是摘要且与明文版已不一致，现统一。
- **补充此前缺失的信息：**
  - `wifi` 命令的可选字段 `enableble` / `enablehttps`（Pro 上还会影响 UDP 载荷是否加密）；
  - `commonmode` 命令（原文档遗漏，`spec` 中有）；
  - `modbus` 的 `parityStop = 3`（N82）；
  - 加密通道：配网码（二维码下 11 位）→ 8 位 PIN、`step=3` 陷阱、`ble-crypto-reset` 限制、`nonce` 方向 / 计数器、Wi-Fi 连接后设备收起 GATT 的行为、浏览器 / 手机支持范围；
  - 加密英文版补全到与中文版同等内容；
  - 加密协议权威参考（固件团队 V2 文档，中 / 英）并入 `docs/ble-secured/crypto-protocol.*`，外部引用改成仓内链接。
- 新增 `spec/ble-secured-test-vectors.json`（虚构输入的 PBKDF2 / HKDF / AES-CCM / 配网码已知答案）和两个校验脚本，Python 与 JS 参考实现结果一致。
- `spec/ble-plain-api.json` 拆成 `ble-business-commands.json`（共用）+ `ble-plain-api.json` + `ble-secured-api.json`；名称前缀与文档对齐。
- 移除文档里的 `【待确认】` / `[TBD]` / `【待填】` 占位：能核实的已核实；工具托管地址改为「以发布渠道为准」。

### 工具

- 加密网页：11 位配网码、右侧栏重叠修复、`step=3` 不再重复握手、业务广播能力提示、Modbus 校验位 / 停止位 0–3、离线单文件（`window.__OFFLINE_BUNDLE__`）。
- 移除未使用的 `pinFromSn`（SN 直接推 PIN 的函数，不应对外）；自检向量改为虚构的 `12345678 / AABBCCDDEEFF`；示例配网码改为虚构值。
- 明文 / 加密帮助文本补 `parityStop 3 = N82`；加密英文帮助补全。

### 待确认 / 后续

- 明文工具（Windows GUI / 网页）的 Modbus 面板尚无校验位 / 停止位选择（固定 `parityStop=0`）。
- 官方托管的网页地址与 Windows 工具下载地址（文档 §10 已留「发布后补充」）。
- 写这条时，`docs/overview`、MQTT / HTTP / mDNS / WebSocket / UDP / Modbus TCP 文档尚未迁入。同日稍后的条目已经补上。
- 名称前缀：文档写 `SDM` / `SPM`，两个网页还多接受 `SRS`（继电器产品线）；是否统一待产品确认。
- Pro 固件上 `enablehttps` 开启后 UDP 载荷为 `ct` / `tag` / `counter` 加密 JSON，其密钥与格式尚无对外文档。
