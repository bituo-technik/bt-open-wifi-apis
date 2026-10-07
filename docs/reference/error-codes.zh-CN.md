# 错误码参考

> 状态：初版 ｜ 适用：全部分支、全部通道 ｜ 依据：固件源码 `userApiErrorCodes.h` 和配置子码表

## 1. 怎么读 `code`

任何通道的 JSON 应答**失败**时，会在 `msg`、`event` 之外多一个整数 `code`。**成功的应答没有 `code`**，所以判断成败请先看 `ok`（或旧格式的 `result`）。

| code | 含义 |
|------|------|
| 不出现 | 成功 |
| `-1` | 固件没有给这条失败分配具体编号，请结合 `ok`、`msg` 判断 |
| 1000 ~ 1999 | BLE 通道 |
| 2000 ~ 2999 | HTTP / HTTPS 通道 |
| 3000 ~ 3999 | MQTT 通道 |
| 4000 ~ 4999 | WebSocket 通道 |

没有 `code` 的失败也存在：例如 MQTT 命令超过 1024 字节、JSON 解析失败时，设备直接丢弃，不会回包。

**一定要同时看 `msg` 和 `event`。** 配置类错误是"通道基数 + 配置子码"，固定错误码又落在同一个区间里，两者会撞号（见 [第 6 节](#6-撞号与消歧)）。设备返回的 `msg` 是英文原文，按原文匹配最可靠。

## 2. 配置子码

业务命令（`wifi`、`mqtt`、`udp`……）失败时，英文 `msg` 对应一个子码 `s`，实际 `code = 通道基数 + s`：BLE `1000 + s`，HTTP `2000 + s`，MQTT `3000 + s`，WebSocket `4000 + s`。

| s | msg | 说明 |
|---|-----|------|
| 1 | （空 `msg`） | 未归类的失败 |
| 2 | `Error password length!` | 新密码超长 |
| 3 | `auth error` | 认证串错误或长度不符 |
| 4 | `bad value` | 数值参数不合法（如上报周期） |
| 5 | `unsupported` | 当前型号或分支不支持该命令 |
| 6 | `null` | 当前型号没有对应数据（如无日程） |
| 7 | `lorawan unsupported` | 当前型号没有 LoRaWAN |
| 8 | `lorawan rejoin failed` | LoRaWAN 重新入网失败 |
| 9 | `lorawan upload failed` | LoRaWAN 上传队列失败 |
| 10 | `lorawan region password failed` | 区域修改密码错误 |
| 11 | `lorawan region failed` | 区域更新失败 |
| 12 | `lorawan config disabled` | LoRaWAN 配置被禁用 |
| 13 | `lorawan config save failed` | LoRaWAN 配置保存失败 |
| 14 | `functionMap error` | 通道组合不合法或超过上限 |
| 15 | `unknow cmd` | 未知命令（固件原文拼写如此） |
| 16 | `Timer not found` | 定时器不存在 |
| 17 | `Invalid timer` | 定时器参数不合法 |
| 18 | `Error wifi ssid/pass required!` | 缺 SSID 或密码 |
| 19 | `Error wifi length!` | Wi-Fi 参数长度不合法 |
| 20 | `Error wifi reset in progress` | Wi-Fi 正在重连，请稍后再试 |
| 21 | `Error mqtt data empty!` | MQTT 必填字段为空 |
| 22 | `Error length!` | MQTT 等字段长度错误 |
| 23 | `cafile error` | 根证书写入流程错误 |
| 24 | `UDP full` | UDP 目标已满（5 个），或 IP / 端口无效 |
| 25 | `UDP not found` | 要删除的 UDP 目标不存在 |
| 26 | `Old Password Error` | 旧密码错误 |
| 27 | `Error name length!` | 名称超长 |
| 28 | `mda format error` | 寄存器扩展数据格式错误 |
| 29 | `mda failed` | 寄存器扩展处理失败 |
| 30 | `minvert data format error` | 反转配置数据格式错误 |
| 31 | `minvert save failed` | 反转配置保存失败 |
| 32 | `minvert data length error` | 反转配置长度错误 |
| 33 | `minvert data error` | 反转配置数据错误 |
| 34 | `minvert missing data` | 反转配置缺数据 |
| 35 | `bleota no data` | BLE OTA 没有收到数据 |
| 36 | `bleota err param` | BLE OTA 参数错误 |
| 37 | `bleota err state` | BLE OTA 状态错误（未开始或已结束） |
| 38 | `bleota err seq` | BLE OTA 包序号不连续，传输中止 |
| 39 | `bleota err crc` | BLE OTA CRC 校验失败 |
| 40 | `bleota err write` | BLE OTA 分区写入失败 |
| 41 | `bleota err size` | BLE OTA 固件总长超限 |
| 42 | `bleota err unknown` | BLE OTA 未知错误 |
| 43 | `scan busy` | Wi-Fi 扫描进行中，不能再次触发 |
| 44 | `scan not ready` | Wi-Fi 扫描结果未就绪 |
| 45 | `ota mem insufficient` | 内存不足，无法升级 |
| 46 | `Error enablehttps!` | `enablehttps` 参数不合法（仅 Pro） |

英文 `msg` 不在上表且不是错误提示的，一般表示成功或中性提示，没有 `code`。

SRS 继电器的开关扩展配置另有子码 51（`illegal cmd`）、52（`Error name!`）、53（`Error name length!`），算法相同。本仓库不覆盖 SRS 产品。

## 3. BLE 固定错误码（1000 段）

| code | msg | 说明 |
|------|-----|------|
| 1000 | `auth error` | 手机认证串与设备不符 |
| 1001 | `not authenticated` | 还没完成认证 |
| 1002 | `Please unlock` | 需要先解锁；写特征通知里 `event` 为 `pas`，读特征里为 `read` |
| 1003 | `Password Error` | BLE 密码错误 |
| 1004 | `No cmd` | 缺 `cmd` 字段 |
| 1005 | `No data received` | 开关扩展配置缺参数 |
| 1010 | `secure channel required` | 必须先建立加密通道 |
| 1011 | `cipher envelope required` | 必须使用密文信封 |
| 1012 | `decrypt failed` | 解密失败 |
| 1013 | `payload too large` | 解密后或加密载荷过长 |
| 1014 | `plain json invalid` | 解密后 JSON 无效 |
| 1015 | `missing cmd` / `cipher envelope required` | 缺命令，或密文信封不完整 |
| 1020 | `version failed` | 加密协议版本协商失败 |
| 1021 | `invalid step` | 重置流程步骤不符 |
| 1022 | — | 重置会话时 J-PAKE 未进行 |
| 1030 | `no pending round1 response` | 没有待取的 Round1 应答 |
| 1031 | `client nonce mismatch` | 客户端 nonce 不一致 |
| 1032 | `round1 response unavailable` | Round1 应答不可用 |
| 1033 | `invalid step` | J-PAKE Round1 步骤错误 |
| 1034 | `invalid round1 chunk` | 分片参数无效 |
| 1035 | `round1 chunk out of order` | 分片顺序错误 |
| 1036 | `jpake round1 failed` | J-PAKE Round1 失败 |
| 1037 | `round1 response prepare failed` | Round1 应答分片准备失败 |
| 1040 | `invalid step` | J-PAKE Round2 步骤错误 |
| 1041 | `jpake round2 failed` | J-PAKE Round2 失败 |
| 1045 | `invalid step` | 会话 nonce 阶段步骤错误 |
| 1046 | `session nonce failed` | 会话 nonce 交换失败 |
| 1047 | `cipher envelope required` / `secure channel required` | 会话状态里缺信封或通道 |
| 1050 | `payload too large` | 明文写入过长 |
| 1051 | `invalid secure json` | 加密模式下 JSON 无效 |
| 1060 | `secure encrypt failed` | 读特征加密应答失败 |
| 1061 | `secure auth required` | 读特征需要先完成加密认证 |
| 1080 起 | 动态英文 | 底层安全模块的具体错误，以设备实际返回为准 |

## 4. HTTP / HTTPS 固定错误码（2000 段）

| code | msg | 说明 |
|------|-----|------|
| 2000 | `use_https` | 当前策略要求走 HTTPS（80 端口返回 403） |
| 2001 | `need token` | 需要会话 token |
| 2002 | `invalid token` | token 无效或已过期 |
| 2003 | `wrong password` | 登录密码错误 |
| 2004 | `password too long` | 登录密码超长（上限 16） |
| 2005 | `need signin` | 需要先登录 |
| 2006 | `no password` | 设备没有设置 Web 密码（状态提示） |
| 2007 | `no password set` | 设备没有设置 Web 密码（登录场景） |
| 2008 | `missing newpass` | 缺新密码参数 |
| 2009 | `bad newpass length` | 新密码长度不符（1 ~ 16） |
| 2010 | `old password wrong` | 旧密码错误 |
| 2011 | `nvs save failed` | Web 密码写入存储失败 |
| 2012 | 日志文件未找到（中文 msg） | 日志文件不存在 |
| 2020 | `wifi not available!` | 无 Wi-Fi，无法下载远程页面 |
| 2021 | `Error on HTTP request!` | 远程 HTTP 请求失败 |
| 2022 | `Error!` | 本地页面文件打开或写入失败，或其他更新错误 |
| 2023 | `download error!` | 远程页面下载中断 |
| 2030 | `No text received.` | 证书上传没有收到正文 |
| 2040 | `No data received` | `/save-config` 没有收到正文 |
| 2041 | `payload too large` | `/save-config` 正文超长 |
| 2050 | `No data received` | `/schedule` 没有收到正文（继电器） |
| 2051 | `payload too large` | `/schedule` 正文超长（继电器） |
| 2060 | `No data received` | `/switch-config` 没有收到正文 |
| 2061 | `payload too large` | `/switch-config` 正文超长 |
| 2062 | `No data received` | `/switch-config` 缺 `configType` / `cmd` |
| 2070 | `bad json` | `/save-config` JSON 无法解析 |
| 2071 | `bad json` | `/schedule` JSON 无法解析 |
| 2072 | `bad json` | `/switch-config` JSON 无法解析 |
| 2080 | `use HTTP :80 multipart POST /upload` | 在 HTTPS 上误用上传接口 |
| 2081 | `file open failed` | 证书文件打开失败 |
| 2090 | `path not on HTTPS API` | HTTPS 上没有这条路径或方法 |
| 2091 | `html not found` | 设备里没有网页资源 |
| 2095 | `Unknown status!` | OTA 状态无法识别 |
| 2100 | `Error password length!` | BLE 密码超长 |
| 2101 | `Old password error!` | BLE 旧密码错误 |
| 2102 | `Error name length!` | 设备名超长 |
| 2110 | `Product update failure!` | 在线升级校验或写入失败 |
| 2111 | `HTTP get failed!` | 在线升级下载失败 |

## 5. MQTT 与 WebSocket 固定错误码

MQTT 固定错误码（3000 段，只出现在旧格式应答 `{"result":"failed",...}` 中；统一格式的失败按第 2 节"3000 + s"赋值）：

| code | event | 说明 |
|------|-------|------|
| 3001 | `rdata` | 数据上报发布失败 |
| 3002 | `wint` | 写上报周期失败 |
| 3010 | `switch-config` | 开关扩展配置缺类型（继电器） |
| 3011 | `wifi` | Wi-Fi 配置失败 |

WebSocket（4000 段，`event` 为 `error`）：

| code | msg | 说明 |
|------|-----|------|
| 4000 | `payload too large` | 单帧超过长度上限 |
| 4001 | `invalid json` | 消息不是 JSON 对象 |
| 4002 | `json parse error` | JSON 语法错误 |
| 4003 | `invalid cmd` | 缺命令字段或为空 |

走统一命令解析的业务命令按第 2 节的"4000 + s"赋 `code`。

## 6. 撞号与消歧

配置子码范围是 1 ~ 53，固定错误码在每个通道段内也用了这些数。因此同一个 `code` 可能有两种含义，例如：

| code | 含义 A（固定错误） | 含义 B（配置子码） |
|------|--------------------|--------------------|
| 1014 | BLE 加密 `plain json invalid` | `functionMap error` |
| 1015 | BLE 加密 `missing cmd` | `unknow cmd` |
| 1020 | BLE `version failed` | `Error wifi reset in progress` |
| 1021 | BLE `invalid step`（重置） | `Error mqtt data empty!` |
| 2002 | HTTP `invalid token` | `Error password length!` |
| 2003 | HTTP `wrong password` | `auth error` |
| 2040 | HTTP `/save-config` 没有正文 | `bleota err write` |
| 2051 | HTTP `/schedule` 正文超长 | SRS `illegal cmd` |

处理办法：

1. 用 `event` 判断是哪条命令或接口的应答。
2. 用 `msg` 英文原文匹配，不要只看 `code`。
3. 通道不同时，`code` 段不同，不会互相撞号。

## 7. 与其他文档的关系

- 命令本身和各命令的成功应答见 [业务命令参考](../ble-common/ble-business-api.zh-CN.md)，其中第 6 节只列常见的业务错误。
- 各通道怎么返回错误见 [HTTP](../http/http-api.zh-CN.md)、[MQTT](../mqtt/mqtt-api.zh-CN.md)、[WebSocket](../websocket/websocket-api.zh-CN.md)。
- 固件升级后新增的英文 `msg` 以设备实际返回为准。
