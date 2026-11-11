# BLE 安全通道 API 文档 V2

本文档用于第三方 App、网关或调试工具对接设备 BLE 安全通道协议。本文档仅描述外部可见的接口协议、字段定义、交互阶段、密钥派生规则与报文格式。

> **在本仓库中的位置：** 这是加密通道（Lite / Pro）的**协议权威参考**（J-PAKE / ZKP 二进制布局、密钥派生、GATT 信封）。集成入口见 [加密 BLE 接口说明](ble-secured-api.zh-CN.md)，不连接就能读到的电参见 [业务加密广播](ble-advertising.zh-CN.md)，业务命令见 [业务命令参考](../ble-common/ble-business-api.zh-CN.md)。握手和信封与接口说明冲突时，**以本文为准**。

## 1. 认证材料

### 1.1 PIN

- `PIN` 是设备安全通道的基础口令材料。
- `PIN` 固定为 `8` 位数字字符串。
- 仅允许字符 `0-9`。
- `PIN` 只能通过设备机身获取。

### 1.2 SN

- `SN` 是设备序列号，用于参与密钥派生。
- `SN` 固定为设备唯一标识。

## 2. 通讯方式

- 客户端通过 BLE 写特征发送 JSON 字符串。
- 设备通过 BLE 通知特征返回 JSON 字符串。
- 在安全通道建立前，收发均为明文 JSON。
- 在安全通道建立后，业务报文收发均为加密信封 JSON。
- 启用本安全通道的固件上，应用 GATT **服务与特征 UUID** 与「仅明文业务」固件不同：服务 **`0xA003`**，写 **`0xC313`**，读 **`0xC314`**，通知 **`0xC315`**（完整 128 位 UUID 见 [加密 BLE 接口说明 §4.1](ble-secured-api.zh-CN.md#41-uuid)）。

## 3. 基本术语

### 3.1 版本号

- 协议版本由设备通过 `ble-crypto-ver` 在 `d.ver` 中返回。
- 客户端须以 `d.ver` 的字面量与配套规范为准，使握手、派生与加密规则与该版本一致。

### 3.2 nonce

- `client_nonce` 与 `device_nonce` 固定为 `8` 字节随机数。
- 在 JSON 中使用 `16` 个十六进制字符表示，例如 `0011223344556677`。
- `client_nonce` 表示客户端发起握手或恢复会话时提供的随机数。
- `device_nonce` 表示设备返回的随机数。

### 3.3 PBKDF2

- 设备与客户端先对 `8` 位数字 `PIN` 执行 `PBKDF2-HMAC-SHA256`。
- 派生输出长度为 `32` 字节。
- `salt = SN || 协议版本 || "PBKDF2"`。
- 迭代次数为本协议约定常数：**`10000`**（设备与客户端须一致）。

### 3.4 EC J-PAKE

- 设备与客户端使用 `PBKDF2` 输出作为口令材料进行 `EC J-PAKE`。
- 曲线使用 `secp256r1`。
- 哈希使用 `SHA-256`。
- `round1` 和 `round2` 报文都使用 `base64` 传输。
- 双方只有在 `PIN` 一致时，才能得到相同的共享密钥。

#### 3.4.1 详细计算流程

以下记法：

- `G`：secp256r1 基点（生成元）
- `n`：曲线阶（ORDER）
- `s`：`PBKDF2` 输出的 32 字节密钥材料，解释为大端无符号整数
- 客户端身份标识 `"client"`，设备身份标识 `"server"`

##### 3.4.1.1 Schnorr 零知识证明（ZKP）

ZKP 用于证明生成者知道某个私钥 `x`（满足 `X = x·G`），同时将 PIN 派生的 `s` 绑定到证明中，使得 PIN 不同的双方无法通过验证。

**生成证明** `ZKP-Write(G, x, X, id, s)`：

1. 选取随机数 `v ∈ [1, n-1]`
2. 计算 `V = v·G`
3. 计算 `h = Hash(G, V, X, id, s)`（见下方 hash 定义）
4. 计算 `r = (v - h·x) mod n`
5. 输出 `V || len(r) || r`

**验证证明** `ZKP-Read(G, X, id, s, V, r)`：

1. 计算 `h = Hash(G, V, X, id, s)`
2. 计算 `V' = h·X + r·G`
3. 验证 `V' == V`，不等则拒绝

**Hash 函数定义** `Hash(G, V, X, id, s)`：

```
payload = len(G_raw) || G_raw || len(V_raw) || V_raw || len(X_raw) || X_raw || len(id) || id || len(s_bytes) || s_bytes
```

其中 `G_raw`、`V_raw`、`X_raw` 为非压缩格式 EC 点编码（`0x04 || x || y`，各 65 字节），`id` 为 ASCII 字符串，`s_bytes` 为 `s` 的最小大端字节表示。每个字段前有 4 字节大端长度前缀。

```
hash = SHA-256(payload)
h = bytes_to_big_endian(hash) mod n
```

> **关键**：`s`（PIN 派生密钥）参与 hash 计算。PIN 不同 → `s` 不同 → `h` 不同 → ZKP 验证失败。这确保 Round1 阶段就能检测到 PIN 不匹配。

##### 3.4.1.2 带证明的密钥对（KKP）

`KKP-Write(G, x, X, id, s)`：生成密钥对并附带 ZKP

1. 生成随机密钥对 `(x, X = x·G)`
2. 输出 `X || ZKP-Write(G, x, X, id, s)`

`KKP-Read(G, id, s, data)`：读取并验证密钥对及其 ZKP

1. 从数据中读取点 `X`，验证非无穷远点
2. 从数据中读取并验证 `ZKP-Read(G, X, id, s, ...)`
3. 返回验证通过的公钥 `X`

##### 3.4.1.3 Round1

双方各生成两个临时密钥对，附带 ZKP 发送给对方。

**客户端生成并发送**：

```
x1 = random [1, n-1],  X1 = x1·G
x2 = random [1, n-1],  X2 = x2·G
client_round1 = KKP-Write(G, x1, X1, "client", s) || KKP-Write(G, x2, X2, "client", s)
```

**设备收到后**：

1. 解析并验证客户端 Round1：`KKP-Read(G, "client", s, data)` → 得到 `Xp1, Xp2`
   - 验证 ZKP 时使用设备自己的 `s`（由设备 PIN 派生）
   - 若 PIN 不同 → `s` 不同 → hash 不同 → ZKP 验证失败 → Round1 失败
2. 生成设备自己的 Round1：
   ```
   xm1 = random [1, n-1],  Xm1 = xm1·G
   xm2 = random [1, n-1],  Xm2 = xm2·G
   server_round1 = KKP-Write(G, xm1, Xm1, "server", s) || KKP-Write(G, xm2, Xm2, "server", s)
   ```
3. 返回 `device_nonce` + `server_round1`

**Round1 数据结构**（每一方）：

```
[点X] 1字节长度 + 65字节非压缩点
[V]   1字节长度 + 65字节非压缩点
[r]   1字节长度 + r字节
```

每个密钥对约 133 字节，Round1 包含两个密钥对，约 266 字节。

##### 3.4.1.4 Round2

Round2 使用 PIN 材料 `s` 计算共享基点，然后生成一个带 ZKP 的密钥对。

**客户端**：

```
Ga = X1 + X3 + X4          （自己的第一个点 + 设备的两个点）
xc = (x2 · s) mod n        （用 PIN 派生的 s）
Xc = xc · Ga
client_round2 = KKP-Write(Ga, xc, Xc, "client", s)
```

**设备**：

```
Gb = Xp1 + Xp2 + Xm1       （客户端的两个点 + 自己的第一个点）

// 先验证客户端 Round2（PIN 校验），再生成响应
// 验证：从 client_round2 解析 Xc 和 ZKP，用 Gb 作为基点验证
KKP-Read(Gb, "client", s, client_round2)  → 验证通过才继续

// 生成设备 Round2
xs = (xm2 · s) mod n
Xs = xs · Gb
server_round2 = GROUP_ID || KKP-Write(Gb, xs, Xs, "server", s)
```

> **安全设计**：设备先验证客户端 Round2，再生成自己的响应。这样即使 PIN 错误，设备也不会泄漏自己的密钥材料。

##### 3.4.1.5 共享密钥派生

Round2 完成后，双方各自计算共享密钥：

**客户端**：

```
x2s = (x2 · s) mod n
K = x2 · (Xs - x2s·X4)       // Xs 为设备 Round2 公钥，X4 为设备第二个 Round1 公钥
shared_key = SHA-256(K.x)     // 取 K 点的 x 坐标，32 字节
```

**设备**：

```
xm2s = (xm2 · s) mod n
K = xm2 · (Xp - xm2s·Xp2)    // Xp 为客户端 Round2 公钥，Xp2 为客户端第二个 Round1 公钥
shared_key = SHA-256(K.x)
```

若 PIN 相同，双方算出的 `K` 相同，因此 `shared_key` 相同。若 PIN 不同，`s` 不同 → Round1 或 Round2 的 ZKP 验证就会失败，不会到达此步。

##### 3.4.1.6 完整密钥派生链

```
PIN (8位数字)
  │
  ▼ PBKDF2-HMAC-SHA256 (salt=SN||ver||"PBKDF2", iter=10000)
s (32字节)
  │
  ▼ EC J-PAKE (secp256r1, SHA-256)
shared_key (32字节)
  │
  ▼ HKDF-SHA256 (salt=device_nonce||client_nonce, info=SN||ver||"LTK")
LTK (16字节)
  ├─► HKDF (info=SN||ver||"session")     → session_key (16字节)
  ├─► HKDF (info=SN||ver||"broadcast")   → broadcast_key (16字节)
  └─► 待 Wi‑Fi 关联成功后持久化（见 §3.5.2）
```

### 3.5 LTK 与 session key

- `LTK` 与 `session key` 使用 `HKDF-SHA256` 派生。
- `LTK` 派生规则如下：
  - 输入密钥材料：`EC J-PAKE shared key`
  - `salt = device_nonce || client_nonce`
  - `info = SN || 协议版本 || "LTK"`
- `session key` 派生规则如下：
  - 输入密钥材料：`LTK`
  - `salt = device_nonce || client_nonce`
  - `info = SN || 协议版本 || "session"`

### 3.5.1 广播密钥（broadcast key）

- 用于 **BLE 广播厂商自定义数据** 中 **长格式（26 字节）** 载荷的 **AES-128-CCM** 加密（字节布局见 [业务加密广播](ble-advertising.zh-CN.md)）。
- 与 `LTK` 使用 **相同** 的 `salt = device_nonce || client_nonce`（各 8 字节，顺序与 LTK 一致）。
- `info = SN || 协议版本 || "broadcast"`（按 ASCII 字节序列理解即可，**不含** JSON 或调试输出里常见的额外终止符）。
- 输入密钥材料：`LTK`（16 字节）。
- 输出长度：16 字节，作为 **广播专用密钥**；与 **LTK** 同生命周期，持久化规则见 **§3.5.2**。**不**随 `ble-crypto-session-nonce` 会话恢复而重算（会话仅重算 `session key` 与 GATT 业务侧 CCM 所用基底）。

### 3.5.2 LTK 与广播密钥的持久化

设备在 Wi-Fi 关联成功后保存 **LTK** 与 **广播密钥**，以便 BLE 断开或重启后用 **`ble-crypto-session-nonce`** 恢复 GATT 加密会话，并在不连接的情况下解密 [业务加密广播](ble-advertising.zh-CN.md) 里的长包。保存发生在安全协商完成且 Wi-Fi 关联成功之后。

#### 存储形态

- 持久化介质为设备 **非易失性存储**（与业务配置共用命名空间）。
- **LTK** 与 **广播密钥** 均以 **32 位十六进制字符串**（对应 16 字节二进制密钥）保存；集成方读取、缓存或备份时须按完整 32 字符处理。

#### 首次配网：延迟落盘

| 阶段 | 设备行为 |
|------|----------|
| **`ble-crypto-jpake-round2` 成功** | 在内存中派生 **LTK**、**广播密钥** 及当前 **session key**；安全通道立即可用（`step=3`），**尚未** 写入持久化存储。 |
| **加密通道内下发 Wi‑Fi 配置** | 设备保存 SSID/密码并发起 STA 关联；进入 **「LTK 待提交」** 状态。 |
| **STA 关联成功** | 将内存中的 **LTK** 与 **广播密钥** **一次性** 写入持久化存储；此后重启或重连时 `ble-crypto-ver` 可返回 **`step=2`**。 |
| **STA 关联失败** | **不** 落盘本轮 J-PAKE 派生的 LTK；在约定等待窗口后丢弃内存中的待提交密钥并回退会话状态，须重新完成 J-PAKE 方可再次配网。 |

在 **「LTK 待提交」** 期间，设备 **不会** 通过其他路径将 LTK 或广播密钥提前写入持久化存储。

#### 后续连接：只读加载

- 设备已持久化 LTK 时，客户端通过 **`ble-crypto-session-nonce`** 交换新的 `client_nonce` / `device_nonce`，设备从持久化存储 **读取** LTK 与广播密钥，并据此重算 **session key** 与 **§3.6** CCM 基底。
- 该流程 **不** 更新持久化存储中的 LTK 或广播密钥。

#### 清除与作废

- 执行 **清除设备配置**（含恢复出厂或等效调试入口）时，持久化存储中的 LTK 与广播密钥一并删除；此后须重新完成首次配网流程。
- 若连接口令（PIN 相关材料）变更导致长期密钥作废，设备应同步清除已持久化的 LTK 与广播密钥。

#### 与典型流程的对应关系

- **§6.1** 中 J-PAKE Round2 成功后即可进行加密业务；**LTK 落盘** 以集成方在同一加密会话内完成 **Wi‑Fi 配置且 STA 关联成功** 为前提（见 [业务命令参考 §2.2](../ble-common/ble-business-api.zh-CN.md#22-下发-ssid-与密码)）。
- **§6.2** 适用于 **已落盘 LTK** 的设备；**§7.5** 仅恢复会话密钥，不触发重新落盘。

### 3.6 AES-CCM 与 12 字节 nonce 派生（**仅 GATT 业务 JSON 密文信封**）

本节描述的是 **经 Notify/Write 传输的 JSON 密文包**（见第 8 节），**不是** [业务加密广播](ble-advertising.zh-CN.md) 里的长包（广播标签是 **4 字节**）。

GATT 业务密文使用 **`AES-128-CCM`**：**无附加认证数据（AAD 长度为 0）**，认证标签 **`tag` 长度为 8 字节**。  
**完整 12 字节 CCM `nonce` 不在 JSON 中直接传输**；JSON 中的 **`nonce` 字段仅为 32 位无符号计数器**（见第 8 节），双方按本节在本地拼出 12 字节后再进行 CCM 加解密。

#### 3.6.1 结构

12 字节 nonce 由两段拼接（**大端序 / 网络字节序**）：

| 偏移 | 长度 | 含义 |
|------|------|------|
| 0–7 | 8 字节 | 会话内固定的 **nonce 基底**（由 HKDF 输出） |
| 8–11 | 4 字节 | 报文计数器 **`counter`** 的 **大端** `uint32_t` |

记法：`nonce_12 = nonce_base_8 || BE32(counter)`。

#### 3.6.2 基底：HKDF-SHA256（输出长度固定 8 字节）

在 **`session key` 已派生** 且双方已就本轮的 `device_nonce`、`client_nonce`（各 8 字节）达成一致后，**双方各自**按下述 HKDF 计算 **两个方向** 的 8 字节基底（HKDF 的 **`salt` 为空**、长度为 0；**`info`** 取下列 **ASCII 字符串的字节序列**，**不包含** 语言实现里常见的字符串尾 **NUL** 字节）：

1. **设备→客户端方向**  
   - `IKM = device_nonce || client_nonce`（共 16 字节）  
   - `info = "ccm-tx-nonce"`  
   - `nonce_base_tx = HKDF-SHA256(salt=∅, IKM, info, L=8)`

2. **客户端→设备方向**  
   - `IKM = client_nonce || device_nonce`（共 16 字节，**顺序与上一条相反**）  
   - `info = "ccm-rx-nonce"`  
   - `nonce_base_rx = HKDF-SHA256(salt=∅, IKM, info, L=8)`

**J-PAKE 首次建链**与 **`ble-crypto-session-nonce` 会话恢复**在交换新的 `device_nonce` / `client_nonce` 后，都会用当前这对随机数 **重新计算** 上述两个基底，并重新派生 **`session key`**。基底或会话密钥变更后，客户端与设备上的 **计数器约定** 见第 8 节。

#### 3.6.3 方向与基底（设备 / 客户端）

| 操作 | 使用的 8 字节基底 | JSON 里的 `nonce` 字段 |
|------|-------------------|-------------------------|
| **解密**设备经 Notify 下发的密文 | `nonce_base_tx` | 与设备信封中的 `counter` 一致 |
| **加密**经 Write 发往设备的密文 | `nonce_base_rx` | 客户端为该方向维护的序号，写入信封 |

设备侧与之对称：**发往客户端的密文**使用 `nonce_base_tx` 与 **§8.1** 中的设备发送序号；**处理客户端写入的密文**使用 `nonce_base_rx` 与信封中的 `nonce`。

## 4. 响应通用格式

所有明文响应统一使用以下结构：

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

字段说明：

- `ok`：布尔值，表示请求是否成功。
- `msg`：字符串，失败时返回原因，成功时通常为空。
- `event`：字符串，对应当前响应所属命令。
- `d`：对象，可选，表示当前命令的业务数据。

## 5. 协议阶段

设备通过 `step` 告知当前安全通道所处阶段：

- `0`：等待客户端发送 `ble-crypto-jpake-round1`
- `1`：等待客户端发送 `ble-crypto-jpake-round2`
- `2`：设备已具备长期密钥，等待客户端发起 `ble-crypto-session-nonce` 恢复会话
- `3`：安全通道已建立，可以发送加密业务报文

## 6. 典型流程

### 6.1 首次建立安全通道

1. `ble-crypto-ver`
2. `ble-crypto-jpake-round1`
3. `ble-crypto-jpake-round2`（内存中已有 LTK 与 session key，可立即加密通讯）
4. （推荐）在同一加密会话内下发 **Wi‑Fi 配置**；STA 关联成功后 **LTK 与广播密钥落盘**（**§3.5.2**）
5. 后续业务经加密信封通讯

若步骤 4 未完成或 Wi‑Fi 关联失败，LTK **不会** 持久化；设备重启后须重新 J-PAKE。

### 6.2 设备重启后恢复安全通道

1. `ble-crypto-ver`
2. 若返回 `step=2`，发送 `ble-crypto-session-nonce`
3. 进入加密业务通讯

## 7. 明文命令

### 7.1 查询协议版本

请求：

```json
{
  "cmd": "ble-crypto-ver"
}
```

成功响应示例：

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

常见失败响应：

```json
{
  "ok": false,
  "msg": "connection key must be 8 digits",
  "event": "ble-crypto-ver"
}
```

### 7.2 重置当前握手流程

请求：

```json
{
  "cmd": "ble-crypto-reset"
}
```

说明：

- 该命令仅允许在 `step=0` 或 `step=1` 时调用。
- 该命令不会清除设备中已有的 `LTK`。

### 7.3 J-PAKE 第一轮

请求：

```json
{
  "cmd": "ble-crypto-jpake-round1",
  "client_nonce": "0011223344556677",
  "client_round1": "BASE64_ROUND1"
}
```

当 `client_round1` 过长时，客户端也可以改为分包上传：

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

成功响应示例：

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

如果 `server_round1` 过长，设备会拆成多片返回，但每次请求只返回一片。客户端需要在收到第一片后继续请求下一片：

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

对于分包上传但尚未收齐的情况，设备会返回继续上传确认：

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

字段说明：

- `client_nonce`：客户端本轮随机数。
- `client_round1`：客户端 J-PAKE 第一轮完整数据，使用 `base64` 编码。
- `client_round1_part`：客户端 J-PAKE 第一轮分片数据，使用 `base64` 编码。
- `part_idx`：当前分片索引，从 `0` 开始。
- `part_total`：总分片数。
- `device_nonce`：设备随机数。
- `server_round1`：设备 J-PAKE 第一轮完整数据，使用 `base64` 编码。
- `server_round1_part`：设备 J-PAKE 第一轮分片数据，使用 `base64` 编码。
- `done`：当为 `true` 时表示这是最后一片。
- `fetch_next`：客户端请求设备继续返回下一片 `server_round1_part`。

补充说明：

- 若单包足够，客户端可继续直接发送 `client_round1`。
- 若单包过长，客户端应改为发送 `client_round1_part` 分片。
- 设备收到最后一片后才会真正执行 J-PAKE round1 校验与生成响应。
- 如果设备返回的是 `server_round1_part`，客户端必须继续发送 `fetch_next=true` 请求，直到收到 `done=true`。
- 当前仅 `round1` 需要分包；`round2` 仍保持单包传输。

### 7.4 J-PAKE 第二轮

请求：

```json
{
  "cmd": "ble-crypto-jpake-round2",
  "client_round2": "BASE64_ROUND2"
}
```

成功响应示例：

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

说明：

- 该命令仅允许在 `step=1` 时调用。
- 成功后，双方基于 `EC J-PAKE shared key` 派生 **LTK**、**广播密钥** 与 **session key**；安全通道立即可用（`step=3`）。
- **LTK 与广播密钥的持久化** 须待 **Wi‑Fi 配置且 STA 关联成功** 后完成，规则见 **§3.5.2**；在此之前仅存在于设备内存。
- 首次建链成功后，当前连接内 **无需** 再发送 `ble-crypto-session-nonce`；设备重启且 LTK 已落盘后，重连时使用 **§7.5**。

### 7.5 恢复安全会话

请求：

```json
{
  "cmd": "ble-crypto-session-nonce",
  "client_nonce": "0011223344556677"
}
```

成功响应示例：

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

说明：

- 该命令仅允许在 `step=2` 时调用（表示设备 **已持久化 LTK**，见 **§3.5.2**）。
- 双方交换新的 `client_nonce` / `device_nonce` 后，设备基于已存储的 **LTK** 重算 **session key** 与 **§3.6** CCM 基底；**不** 改写持久化存储中的 LTK 或广播密钥。

## 8. 加密信封格式

安全通道建立后，业务报文统一使用以下 JSON 信封：

```json
{
  "nonce": 1,
  "ct": "BASE64_CIPHERTEXT",
  "tag": "BASE64_TAG"
}
```

字段说明：

- `nonce`：**32 位无符号整数**，表示本节中的 **`counter`**（与第 3.6 节 12 字节 nonce 中 **最后 4 字节大端值** 一致）。**不是** `client_nonce` / `device_nonce` 的十六进制串。
- `ct`：`AES-CCM` 密文，**Base64**（RFC 4648，标准字母表与 `=` 填充）。
- `tag`：`AES-CCM` 认证标签（`8` 字节），**Base64** 编码。
- 完整 12 字节 CCM `nonce` 按 **第 3.6 节** 由「对应方向的 8 字节 HKDF 基底 + `BE32(nonce字段)`」在本地拼出。

### 8.1 设备侧序号约定

为便于与 **§8.2** 对照，定义设备内部两个无符号 32 位序号（不向 JSON 额外暴露字段名，仅说明语义）：

- **`N_send`（设备→客户端）**  
  - 进入可加密业务通讯后，设备对发往客户端的密文，**`N_send` 初值为 `1`**。  
  - 每成功加密并发出一包（如经 Notify 送达），该包信封中的 **`nonce` 等于当前 `N_send`**，随后设备将 **`N_send ← N_send + 1`**（算术在模 **2³²** 下进行；实际部署宜在接近回绕前重新握手或更换会话，以免序号复用）。
- **`N_accept`（已接受的客户端序号）**  
  - 新会话起始为 **`0`**。  
  - 每成功解密一包**客户端写入**的密文后，设备令 **`N_accept ←` 该包信封中的 `nonce`**。

客户端应 **镜像维护**：记录设备下发的 `nonce` 以正确解密；向设备发送密文时使用**本方向**独立序号，并满足 **§8.2** 相对设备 **`N_accept`** 的约束。

### 8.2 `nonce`（counter）与防重放（客户端→设备）

设备处理**客户端写入的密文**时须满足：

- 若信封中 **`nonce ≤ N_accept`**（按无符号 32 位比较），则 **拒绝该包**，错误信息为 **`replay detected`**：**不**更新 **`N_accept`**，**不**解密。  
- 仅当 **`nonce > N_accept`** 时，使用 **§3.6** 的 **`nonce_base_rx` + `BE32(nonce)`** 进行 CCM 解密；成功后 **`N_accept ← nonce`**。

因此：

1. **相对设备已接受值的严格增大**：客户端每一包发往设备的新密文，信封中 **`nonce` 必须大于设备当前的 `N_accept`**；与上一已接受包相同或更小均被拒绝。  
2. **允许跳空**：例如设备已接受 `nonce=5` 后，下一包可为 `10`（只要 `10 > 5`）。  
3. **不允许“迟到”的更小序号**：若设备已接受 `nonce=10`（此时 `N_accept=10`），之后再送达 `nonce=5` 会被判为重放并拒绝。  
4. **重复发送**：第二包若 **`nonce` 不大于当前 `N_accept`**，返回 **`replay detected`**。  
5. **计数器不递增或复用**：除首包外极易被拒绝；若在**相同 `session key` 与相同完整 12 字节 CCM `nonce`** 下加密不同明文，则违反 CCM 使用要求，存在 **密钥流复用** 风险。

**设备→客户端**方向：设备按发送顺序递增 **`N_send`**。本协议**未规定**设备须对该方向再做额外防重放字段；**客户端宜**对收到的 `nonce` 做单调递增校验，以降低重放与状态错乱风险（与上节设备对 **`N_accept`** 的约束对称）。

### 8.3 与 `decrypt failed` 的区别

- **`replay detected`**：未进入 CCM，仅计数器检查失败。  
- **`decrypt failed`**：计数器已通过，但 **CCM 认证解密失败**（密钥错误、`ct`/`tag` 损坏、`nonce` 与加密方不一致等）。

## 9. BLE 广播厂商数据（动态广播）

业务加密广播单独成篇，不在本文展开：[业务加密广播](ble-advertising.zh-CN.md)。

本文保留握手、密钥派生（含 §3.5 广播密钥）和 GATT 信封。短包 / 长包的字节布局、解密参数和电参字段以那一篇为准。


## 10. 失败条件

常见失败原因包括：

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
- `replay detected`：见 **第 8.2 节**（客户端→设备密文的 **`nonce` 未大于** 设备当前 **`N_accept`**）。
- `decrypt failed`：CCM 校验或解密失败，见 **第 8.3 节**。

## 11. 兼容性说明

- 本文档对应新的 `PBKDF2 + EC J-PAKE + HKDF` 握手协议。
- 旧版 `ble-crypto-client-nonce` 与 `ble-crypto-client-response` 已废弃。
- 客户端必须按本文档同步升级，否则无法完成首次建链。
