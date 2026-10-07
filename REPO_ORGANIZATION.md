# bt-open-wifi-apis：仓库架构与组织说明

> 技术笔记（对人）+ 协作约定（对 AI）。  
> 对应线上入口：[SPM/SDM Open Wi-Fi API Overview](https://docs.bituo-technik.com/device-api/spm-sdm-open-wi-fi-api-overview)  
> 文档版本：2026-10 · 状态：BLE 明文 + BLE 加密已落地；HTTP / MQTT / mDNS / Modbus TCP / WebSocket / UDP 待迁入

---

## 0. 一分钟结论

| 问题 | 答案 |
|------|------|
| 要不要每个 API 一个仓？ | **不要。** 一个仓，按通道分目录。 |
| 仓是公开还是私有？ | **私有**（`bituo-technik/bt-open-wifi-apis`），按需给合作方授权，不对所有人开放。 |
| 仓里放什么？ | 面向集成商的 API 说明（中 / 英）+ 体验工具 + 机器可读 `spec/`。 |
| 不放什么？ | ESP32 **固件源码**、产线密钥、任何真实设备的 PIN / LTK / 客户端缓存文件。 |
| 两个 BLE 通道的业务 JSON 一样，怎么维护？ | **一份共用文档** `docs/ble-common/`，两个通道文档只写各自传输层。见 §3。 |
| 和 Gitbook 什么关系？ | 本仓 = 真相源；Gitbook = 发布面，粘贴 `dist/` 里生成的单页或按 `docs/SUMMARY.md` 同步。 |
| 固件分支怎么表达？ | 用矩阵（Basic / Basic+ / Lite / Pro），不按分支拆仓。 |

---

## 1. 产品事实（来自 Overview）

按**固件分支**区分能力：

| 固件分支 | 硬件倾向 | BLE | Wi-Fi / TLS 要点 | 生命周期（文档当时） |
|----------|----------|-----|------------------|----------------------|
| Basic | SPM/SDM（8685） | 明文 `A002` | 明文 HTTP 等；无 HTTPS | NRND |
| Basic+ | SDM01（8685） | 明文 `A002` | 最多约 **1** 路 TLS | NRND |
| Lite | SPM/SDM（8685） | 加密 `A003` | Wi-Fi 侧 MQTT TLS；HTTP / Modbus / WS 无 TLS | Active |
| Pro | SDM01 Gen2（C6） | 加密 `A003` | 最多约 **2** 路 TLS；有 HTTPS | Active |

文档与工具必须按"该分支是否支持"标注，禁止假设所有设备都有全部 API。

### 和固件仓的边界

```text
[私有] ESP 固件大仓      ← 实现、NVS、编译、产线
        ↑ 仅在本机双开对照，不 submodule、不复制源码
[私有] bt-open-wifi-apis ← 协议说明 + Demo 工具 + spec
        ↓ 复制 / 同步
[发布] docs.bituo-technik.com
```

---

## 2. 目录结构

```text
bt-open-wifi-apis/
├── README.md                      仓库首页：怎么选文档、怎么跑工具
├── AGENTS.md                      给 AI 的入口与硬约束
├── REPO_ORGANIZATION.md           本文件
├── CHANGELOG.md                   文档 / 工具变更，注明对齐的固件版本
│
├── docs/
│   ├── README.md                  阅读路径
│   ├── SUMMARY.md                 Gitbook 目录
│   ├── ble-common/                两个 BLE 通道共用的业务命令参考（zh-CN / en）
│   ├── ble-plaintext/             明文 BLE 传输层（Basic / Basic+，A002）
│   ├── ble-secured/               加密 BLE 传输层（Lite / Pro，A003）+ 协议权威参考
│   └── …                          将来：overview / mqtt / http / mdns / websocket / udp / modbus-tcp
│
├── tools/
│   ├── README.md
│   ├── ble-plaintext/             Web Bluetooth 页 + Windows 工具
│   └── ble-secured/               同上，含离线单文件页与 bundle 脚本
│
├── spec/                          机器可读：命令清单、测试向量
├── scripts/                       生成单页合集、校验链接 / 测试向量
└── dist/                          生成物（不入库）
```

### 2.1 目录职责

| 路径 | 给人 | 给 AI / 程序 |
|------|------|----------------|
| `docs/**` | 阅读与 Gitbook 正文 | 实现客户端的主依据 |
| `tools/<channel>/` | 手测、演示、现场配网 | 行为样例；协议仍以 docs 为准 |
| `spec/ble-plain-api.json` | 一般不读 | 命令表；**须与 `docs/ble-common` 一致** |
| `spec/ble-secured-test-vectors.json` | 实现加密通道时自测 | 已知答案测试向量（PBKDF2 / HKDF / AES-CCM / 11 位配网码） |
| `dist/` | Gitbook 粘贴、发给 AI | 一个文件包含"传输层 + 业务层"的完整内容 |

---

## 3. 共用业务 JSON 怎么维护（这是本仓最重要的约定）

明文通道和加密通道在"解开传输层之后"的业务 JSON **完全相同**：同样的 `wifi` / `model` / `mqtt` / `modbus` / `udp` 命令、同样的快照字段、同样的错误码。两份文档各抄一遍，迟早会漂移（改了 A 忘了 B）。因此：

| 内容 | 放哪 | 写几份 |
|------|------|--------|
| 业务命令、字段、应答、快照键、业务错误码、附录（functionMap 位 / model 短键 / 低频错误码） | `docs/ble-common/ble-business-api.*.md` | **只一份**（中、英各一） |
| UUID、门禁（`pass` 或握手）、信封、重连、MTU、平台提示、通道专有错误 | `docs/ble-plaintext/` 或 `docs/ble-secured/` | 各写各的 |
| J-PAKE / ZKP 二进制布局、广播厂商数据 | `docs/ble-secured/crypto-protocol.*.md` | 固件团队提供，**冲突以它为准** |

规则：

1. 改业务命令只改 `ble-common`；通道文档里**不要**复制命令表，只链过去。
2. 通道差异只允许出现在 `ble-common` 的 §1.2 差异表里，且必须是真实的传输层差异（如 `read` 是否带 `continue`）。
3. 新增一个命令：改 `ble-common` §3 + §4 索引 + `spec/ble-plain-api.json` + 两个工具的 `command_help`（如需要）。
4. 每个通道文档仍要能"单独交给 AI 就够用"——所以 `scripts/build_bundles.py` 会把 **通道文档 + 公共文档（+ 加密协议参考）** 合成一个单文件放进 `dist/`。

> 为什么不是"各自完整、互相复制"：复制的代价是每次改动都要做 4 次并且不会有人发现漏改。
> 为什么不是"只有一份、通道只讲差异"：客户和 AI 经常只拿到一份文档；`dist/` 合集解决这个问题，而不用手工维护两份。

---

## 4. 单通道文档怎么写（模板约定）

1. 快速开始（最小闭环 + 可运行示例或伪代码）  
2. 给 AI 的提示词（可整段复制）  
3. 适用范围（哪些固件分支适用）  
4. 会话 / 鉴权 / 发现（UUID、解锁或握手、重连）  
5. 命令或资源参考（真实请求 / 应答示例）  
6. 错误码  
7. 开发清单 + 验收勾选  
8. 体验工具入口  
9. 安全说明  

约定：

- 命令名、字段名、设备 `msg`：**保持英文原样**。  
- 中英各一份：`*.zh-CN.md` / `*.en.md`，章节编号与内容对齐。  
- 不确定的事实不要写成确定：要么向固件同事核对，要么写进 CHANGELOG 的"待确认"。  
- 示例里的 PIN / SN / LTK 一律用虚构值，不放真机数据。

---

## 5. 工具怎么放

| 通道 | 工具形态 | 备注 |
|------|----------|------|
| 明文 BLE | Chrome Web Bluetooth + Windows PyQt6 / bleak | 界面中 / 英切换 |
| 加密 BLE | 同上 + 离线单文件网页 | 开发用分文件版，客户用 `*.offline.html` 单文件 |
| HTTP / MQTT / WebSocket | 后续 | 浏览器需处理 CORS / WS 入口 |

工具与文档协议必须一致；UI 语言可中 / 英，线上 JSON / `msg` 不翻译。

---

## 6. 私有仓与授权

- 默认分支 `main`；合作方用 GitHub 的 **Team / 外部协作者只读** 授权，不要开放写权限。  
- `tools/ble-secured/ble_crypto_client_cache.json` 等本地缓存已在 `.gitignore`，**不得提交**。  
- 不要把仓库地址贴到公开 Issue / 论坛；对外交付用 `dist/` 里的单文件或 Gitbook 页面。  
- 将来若要公开，先过一遍 §7 的清单，尤其是加密协议参考是否允许公开。

---

## 7. 给维护者的检查清单

- [ ] 仓内不含固件源码、密钥、真机 PIN / LTK / 缓存文件  
- [ ] `docs/ble-common` 与 `spec/ble-plain-api.json` 命令集一致  
- [ ] 中 / 英文档章节与内容对齐（`scripts/check_docs.py` 会检查标题数量与链接）  
- [ ] 运行 `scripts/check_test_vectors.py` 与 `node scripts/check_test_vectors.mjs` 全部通过  
- [ ] 改了 Web 控制台后重新生成 `*.offline.html`  
- [ ] CHANGELOG 写了对齐的固件版本  

### 本机对照固件（可选）

查协议行为时：在固件仓搜 `cmd` 字符串 / UUID，用结论回写 API 文档；不要反向把文档生成进固件，也不要把固件源码复制进本仓。

---

## 8. 演进顺序（建议）

1. ~~BLE 明文~~、~~BLE 加密~~ 已迁入  
2. 迁入 / 对齐 MQTT、HTTP、mDNS、Modbus TCP 文档  
3. 补 WebSocket、UDP  
4. 把 `docs/overview` 对齐线上 Overview（能力矩阵放这里）  
5. 需要时开通 Gitbook Git Sync（Project directory 指向 `docs/`）  

---

## 9. 术语速查

| 术语 | 含义 |
|------|------|
| Open Wi-Fi | 对集成商开放本地 / 云协议的 SPM / SDM ESP 产品族定位 |
| 固件分支 | Basic / Basic+ / Lite / Pro |
| 通道 | BLE / HTTP / MQTT / WS / UDP / Modbus TCP / mDNS 之一 |
| 明文 BLE | 服务 `A002`，UTF-8 JSON，无应用层加密 |
| 加密 BLE | 服务 `A003`，EC J-PAKE 握手 + AES-128-CCM 信封 |
| 业务 JSON | 去掉传输层（解锁 / 信封）后的命令与应答，两个 BLE 通道相同 |
| 真相源 | 以本仓 `docs/` 为准，而不是口头或只在 Gitbook 里手改 |
