# Changelog

格式：按日期倒序。"对齐固件"写明文档 / 工具核对过的固件版本。

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
- 移除文档里的 `【待确认】` / `[TBD]` / `【待填】` 占位：能核实的已核实；工具托管地址改为"以发布渠道为准"。

### 工具
- 加密网页：11 位配网码、右侧栏重叠修复、`step=3` 不再重复握手、业务广播能力提示、Modbus 校验位 / 停止位 0–3、离线单文件（`window.__OFFLINE_BUNDLE__`）。
- 移除未使用的 `pinFromSn`（SN 直接推 PIN 的函数，不应对外）；自检向量改为虚构的 `12345678 / AABBCCDDEEFF`；示例配网码改为虚构值。
- 明文 / 加密帮助文本补 `parityStop 3 = N82`；加密英文帮助补全。

### 待确认 / 后续
- 明文工具（Windows GUI / 网页）的 Modbus 面板尚无校验位 / 停止位选择（固定 `parityStop=0`）。
- 官方托管的网页地址与 Windows 工具下载地址（文档 §10 已留"发布后补充"）。
- `docs/overview`、MQTT / HTTP / mDNS / WebSocket / UDP / Modbus TCP 文档尚未迁入。
- 名称前缀：文档写 `SDM` / `SPM` / `SXM`，两个网页还多接受 `SRS`（继电器产品线）；是否统一待产品确认。
- Pro 固件上 `enablehttps` 开启后 UDP 载荷为 `ct` / `tag` / `counter` 加密 JSON，其密钥与格式尚无对外文档。
