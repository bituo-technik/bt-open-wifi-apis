# BLE 安全通道 API 文档 V2

本文档用于第三方 App、网关或调试工具对接设备 BLE 安全通道协议。本文档仅描述外部可见的接口协议、字段定义、交互阶段、密钥派生规则与报文格式。

> **在本仓库中的位置：** 这是加密通道（Lite / Pro）的**协议权威参考**（J-PAKE / ZKP 二进制布局、密钥派生、信封、广播厂商数据）。集成入口见 [加密 BLE 接口说明](ble-secured-api.zh-CN.md)，业务命令见 [业务命令参考](../ble-common/ble-business-api.zh-CN.md)。两份文档冲突时，**以本文为准**。

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

- 用于 **BLE 广播厂商自定义数据** 中 **长格式（26 字节）** 载荷的 **AES-128-CCM** 加密（见 **第 9 节**）。
- 与 `LTK` 使用 **相同** 的 `salt = device_nonce || client_nonce`（各 8 字节，顺序与 LTK 一致）。
- `info = SN || 协议版本 || "broadcast"`（按 ASCII 字节序列理解即可，**不含** JSON 或调试输出里常见的额外终止符）。
- 输入密钥材料：`LTK`（16 字节）。
- 输出长度：16 字节，作为 **广播专用密钥**；与 **LTK** 同生命周期，持久化规则见 **§3.5.2**。**不**随 `ble-crypto-session-nonce` 会话恢复而重算（会话仅重算 `session key` 与 GATT 业务侧 CCM 所用基底）。

### 3.5.2 LTK 与广播密钥的持久化

设备将 **LTK** 与 **广播密钥** 写入非易失性存储，以便在 BLE 断开或设备重启后，通过 **`ble-crypto-session-nonce`** 恢复 GATT 加密会话，并在无需连接的情况下解密 **§9** 所述广播长包。持久化采用 **「安全协商完成且 Wi‑Fi 关联成功后再落盘」** 策略，避免在未验证网络环境的情况下固化长期密钥。

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

本节描述的是 **经 Notify/Write 传输的 JSON 密文包**（见第 8 节），**不是**第 9 节里的 **广播厂商长包**（广播为 **4 字节 tag**，见 **§9.3**）。

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

以下行为仅在设备 **提供本安全通道协议（应用层 BLE 加密）** 的型号/固件上存在；未提供该能力的设备不写入本节所述厂商自定义数据，广播保持常规静态策略（无本节所述短包/长包切换）。

### 9.1 协议阶段与两种长度

设备对外的安全阶段 **`step`**（见 **第 5 节**）决定广播 **厂商特定数据（Manufacturer Specific Data）** 的形态：

| 条件 | 厂商数据长度 | 说明 |
|------|----------------|------|
| `step = 0`（等待 `ble-crypto-jpake-round1`） | **5 字节** | 短格式：明文鉴别与配网状态，便于扫描发现设备 |
| `step ≠ 0` | **26 字节** | 长格式：AES-128-CCM 密文 + 标签，可轮询多路测量数据等 |

动态长包场景下广播间隔可约为 **200 ms** 量级；长包成功更新到空中接口后，设备可按产品策略轮换 **相位槽**，在广播中轮询不同测量通道（具体相位数与型号有关，集成方以实测为准）。

### 9.2 短格式（5 字节）

多字节整数均为 **小端**。

| 偏移 | 长度 | 内容 |
|------|------|------|
| 0–1 | 2 | 固定 `0xFF 0xFF`（厂商数据常见前缀） |
| 2 | 1 | **配网状态字节**：整字节 **`0`** 表示仍处于 J-PAKE 首轮等待；**`1`** 表示已进入后续阶段（与长格式控制字节的高四位编码无关，保持简单两态） |
| 3–4 | 2 | **12 bit 鉴别器**（16 位字段仅低 12 位有效）：由设备 **SN**（12 位 hex → 48 bit）取 **最高 12 bit**（即 hex 串从左起前 3 个十六进制位），直接作为鉴别器，供扫描侧区分设备 |

### 9.3 长格式（26 字节，AES-128-CCM）

整段作为 **一条厂商自定义数据** 出现在广播中（总长 26 字节）。

| 偏移 | 长度 | 内容 |
|------|------|------|
| 0–1 | 2 | 固定 `0xFF 0xFF` |
| 2 | 1 | **控制字节**（见下表拆分）：bit7 应用层 GATT 配网服务是否已安装（1=已安装）；bit6–4 编码版本（0–7，当前为 **1**，对应 **§9.3.1** 明文布局）；bit3–2 **相位/回路索引**；bit1–0 **产品类别** |
| 3–6 | 4 | **广播计数器**：32 位无符号整数，**小端**，每成功发布一包递增 |
| 7–21 | 15 | **CCM 密文**：解密后为 **§9.3.1** 的 15 字节明文（与密文等长） |
| 22–25 | 4 | **CCM 认证标签**（4 字节） |

**控制字节 bit1–0（产品类别）**

| 取值 | 型号 |
|------|------|
| `0b11`（3） | 三相：`SDM01_3PN` / `SPM02` |
| `0b10`（2） | 两路：`SDM02` |
| `0b01`（1） | 单相：`SDM01_1PN` / `SPM01` |
| `0b00`（0） | 其它（含 `SRS01A` / `SRS01B`） |

**CCM 参数（与 GATT 业务信封不同）**

- **密钥**：**广播密钥**（见 **§3.5.1**），16 字节；与 **§3.5.2** 持久化的广播密钥材料一致，**不要求**当前已建立 GATT 或已交换会话 nonce。
- **Nonce（12 字节）**：**不**使用 BLE 会话里的 `device_nonce`（被动扫描场景下可能从未连接、未交换会话 nonce）。固定为 **前 8 字节全 `0x00`**，后 4 字节为 **与表中字节 3–6 同一广播计数器** 的 **大端** `uint32_t`（表中为小端，集成方须按同一数值自行转换字节序）。
- **明文长度**：15 字节；**无 AAD**；**认证标签长度** 4 字节。

记法：`nonce_12 = 0^8 || BE32(counter)`，`counter` 与 AD 偏移 3–6 的小端值相同。

**谁可以解密**：须持有与设备 **§3.5.2** 持久化一致的 **广播密钥**，并从广播 AD 读取 **小端计数器** 拼出上述 nonce 即可 **无需连接** 解密。广播密钥的 HKDF 派生发生在 **首次 J-PAKE 成功** 时；**落盘时机** 与 LTK 相同（Wi‑Fi 关联成功后），与「之后是否再连 BLE」无关。

### 9.3.1 长格式明文（解密后 15 字节，对应 AD 偏移 7–21）

CCM 解密成功后得到 **15 字节** 定长二进制，**不是 JSON**。多字节整数均为 **小端**。编码版本（控制字节 bit6–4）为 **1** 时使用本布局。

| 明文偏移 | 长度 | 类型 | 倍率 | 物理量 | 单位 |
|----------|------|------|------|--------|------|
| 0–1 | 2 | 无符号 `uint16` | ÷10 | 电压 `V` | V |
| 2–3 | 2 | 无符号 `uint16` | ÷100 | 电流 `I` | A |
| 4–6 | 3 | 有符号 `int24` | ÷1000 | 有功功率 `P` | kW |
| 7–10 | 4 | 无符号 `uint32` | ÷100 | 正向有功电能 `FE` | kWh |
| 11–14 | 4 | 无符号 `uint32` | ÷100 | 反向有功电能 `RE` | kWh |

物理值 = 整型字段 ÷ 倍率。例如电压原始值 `0x08FC`（小端 `FC 08`）→ `2300 / 10 = 230.0` V。

**`int24` 有符号小端**：三字节按 `b0 | (b1<<8) | (b2<<16)` 拼成 24 位数；若最高位（`b2` 的 bit7）为 1，则按负数处理（等价于减去 `0x1000000`）。功率可正可负（发电/反向）。

**饱和与无效值**

- 源测量非有限数时，对应字段编码为 **0**。
- `uint16` 饱和到 `0…65535`（电压最大约 6553.5 V，电流最大约 655.35 A）。
- `int24` 饱和到 `−0x800000…0x7FFFFF`（功率约 −8388.608…8388.607 kW）。

**相位/回路索引（控制字节 bit3–2）** 表示本包明文属于哪一路；设备在长包成功上屏后轮询切换。单路型号该字段固定为 `0`。

| 产品类别 | 相位数 | 索引 `0` | 索引 `1` | 索引 `2` |
|----------|--------|----------|----------|----------|
| `0b01` 单相 | 1 | 本机唯一一路 | — | — |
| `0b00` 且 `SRS01A` | 1 | 本机唯一一路 | — | — |
| `0b00` 且 `SRS01B` | 2 | 回路 1 | 回路 2 | — |
| `0b10` `SDM02` | 2 | 回路 1 | 回路 2 | — |
| `0b11` 三相 | 3 | A 相 | B 相 | C 相 |

**型号差异**

- `SRS01A` / `SRS01B` **不广播反向电能**：`RE` 四字节恒为 `0`。
- 未识别型号：15 字节明文全 `0`。
- 量纲与读特征短键 `V` / `I` / `P` / `FE` / `RE` 一致；广播为定点二进制，读特征为十进制字符串。读特征 JSON 见 [业务命令参考 §5](../ble-common/ble-business-api.zh-CN.md#5-读快照ip-与电参)。

### 9.4 Wi‑Fi 已连接时的 GATT 与广播 UUID

在 **已启用本安全通道** 的设备上，若用户 **未** 另行要求「配网后仍保持 BLE」：

- **Wi‑Fi 站模式已连接** 时，设备可从广播中去掉 **应用层 Service UUID**，并停止对外暴露应用 **GATT** 服务，仅保留广播中的厂商数据等，以降低暴露面。

若通过 **Wi‑Fi 配置接口**（见 [业务命令参考 §2.2](../ble-common/ble-business-api.zh-CN.md#22-下发-ssid-与密码)）在请求体中加入 **`enableble`** 且解析为 **开启**，设备将把该偏好 **写入持久化存储**（与 **长期密钥 LTK** 使用 **同一存储分区与同类定长文本记录方式**；约定以单字符 **`1`** 表示开启、**`0`** 表示关闭，其余填充为零）。下次上电成功读出为 **开启** 时，**即便 Wi‑Fi 已连接**，仍保持应用 **GATT** 与广播中的 **Service UUID**，并继续按本节规则更新 **动态厂商数据**。

执行 **恢复出厂** 时，该偏好通常与 LTK 等安全配置一并清除，具体以厂商说明为准。

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
