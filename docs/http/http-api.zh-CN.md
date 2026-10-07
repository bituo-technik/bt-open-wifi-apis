# HTTP / HTTPS API

> 状态：初版 ｜ 适用：SPM / SDM Open Wi-Fi 全部分支（HTTPS 仅 Pro） ｜ 依据：固件源码 SXM_EW_C3 `5.1.16`、SDMV2 `1.2.12` / `3.1.19`

局域网里的网关、脚本、Home Assistant 等可以用 HTTP 直接读电表数据、改配置。命令和 BLE、MQTT、WebSocket 是同一套，本页写 HTTP 自己的部分：会话、接口清单、80 端口与 443 端口的差别。

## 1. 概述

| 项目 | 说明 |
|------|------|
| 地址 | `http://<设备 IP>/`，Pro 开启 HTTPS 后还有 `https://<设备 IP>/`（端口 443） |
| 开关 | BLE 命令 `enablehttp` / `enablehttps`，见[业务命令参考](../ble-common/ble-business-api.zh-CN.md)。Basic、Basic+ 每次开机默认打开 HTTP，Lite、Pro 默认关闭 |
| 找到设备 | 用 [mDNS](../mdns/mdns-discovery.zh-CN.md) 解析主机名，或从路由器看 IP |
| 方法 | 绝大多数接口是 `GET`，参数放在查询串里；写配置的接口是 `POST`，正文是 JSON |
| 应答 | 除少数接口返回纯文本或原始 JSON 外，都是统一的 `ok/msg/event/d`（失败多 `code`）。约定见[业务命令参考 1.1 节](../ble-common/ble-business-api.zh-CN.md) |
| 状态码 | **失败时 HTTP 状态码通常也是 200**，请看正文里的 `ok`。例外：80 端口被策略拒绝时是 403，日志文件不存在、HTTPS 找不到路径时是 404 |
| 并发 | 80 端口的 Web 服务一次处理一个请求，请不要并发轮询；HTTPS 的连接数受 TLS 名额限制，见[概览 3.1 节](../overview/open-wifi-overview.zh-CN.md#31-tls-连接数限制) |
| 入站大小 | 请求正文的 JSON 不能超过 1024 字节 |

接口返回的内容有三种形态，用的时候要分清：

| 形态 | 例子 | 判断成败 |
|------|------|----------|
| 原始 JSON（没有 `ok`） | `/data`、`/model`、`/status`、`/snapshot`、`/getSchedule`、`/checkota` | 能解析、字段齐全就是成功；token 出错时会返回带 `ok:false` 的小对象 |
| 统一结构 | `/restart`、`/location`、`/save-config` 等 | 看 `ok` |
| 纯文本 | `/sn`、`/logfile` | HTTP 状态码 |

## 2. 会话与鉴权

电表有一个可选的 **Web 密码**。

- **没设置 Web 密码（出厂默认）：所有接口都不需要登录**，任何能访问 IP 的人都能读数据、改配置、重启、恢复出厂。
- **设置了 Web 密码：** 除了 `/signin`，每个接口都要带 `token` 查询参数，例如 `/data?token=123456`。没带或带错会得到失败应答，不会执行动作。

### 2.1 登录换 token

```
GET /signin?password=<密码>
```

成功时设备签发一个 token：

```json
{"ok":true,"msg":"","token":1736912345}
```

之后每个请求都带 `?token=1736912345`（已经有别的查询参数时用 `&token=...`）。

可选地，你也可以**自己带一个 token 来登录**：`/signin?password=<密码>&token=<你生成的数字>`。密码对了，设备就登记你的这个 token，应答里**不再返回** `token` 字段。多个客户端可以各用各的 token。

| 情形 | 应答 |
|------|------|
| 密码正确 | `{"ok":true,"msg":"","token":N}`（自带 token 时无 `token` 字段） |
| 密码错误 | `{"ok":false,"msg":"wrong password","code":2003}` |
| 密码超过 16 个字符 | `{"ok":false,"msg":"password too long","code":2004}` |
| 设备没设置密码 | `{"ok":true,"msg":"no password set"}` |
| 不带 `password`，设备设了密码 | `{"ok":false,"msg":"need signin","code":2005}` |
| 不带 `password`，设备没设密码 | `{"ok":true,"msg":"no password"}` |

用不带 `password` 的 `/signin` 可以判断设备要不要密码。

### 2.2 token 的规则

- token 是**无符号 32 位整数**（十进制）。
- 设备最多同时记住 **5 个** token。满了以后，最久没用的会被顶掉。
- 每个 token **闲置 5 分钟**失效，每次成功使用都会续期。
- token 无效时的应答：`{"ok":false,"msg":"need token","code":2001}`（没带）或 `{"ok":false,"msg":"invalid token","code":2002}`（不认识或已过期）。收到后重新登录即可。
- 修改密码（`/changepass`）成功后，**所有 token 立刻作废**。
- 重启后 token 全部丢失。

### 2.3 修改 Web 密码

```
GET /changepass?newpass=<新密码>&oldpass=<旧密码>
```

密码长度 1 ~ 16。设备原来没有密码时可以省略 `oldpass`。失败时 `msg` 是 `missing newpass`、`bad newpass length`、`old password wrong` 或 `nvs save failed`。

### 2.4 安全提醒

- 密码和 token 都放在 URL 里。明文 HTTP 下，同一网络里的人能抓到它们。需要保护的场景请用 Pro 的 HTTPS。
- `/model`（以及 `/snapshot` 里的 `model`）会**明文返回 MQTT 密码**（`mqttUserPassword`），所以没设 Web 密码的设备不要暴露到不可信的网络。
- 只在受控的局域网里用，不要把 80 / 443 端口映射到公网。

## 3. 接口清单

下表的"需要 token"指设置了 Web 密码时。除特别写明外，接口在 80 和 443 上都有。`GET` 接口的参数都在查询串里。

### 3.1 读取数据与状态

| 接口 | 返回 | 说明 |
|------|------|------|
| `GET /data` | 原始 JSON | 最新一包遥测，字段见[遥测数据](../reference/telemetry-payload.zh-CN.md)。每次调用都会让内部计数 +1 |
| `GET /model` | 原始 JSON | 设备配置：型号、Wi-Fi 名、MQTT 主题和连接信息、各通道周期（`mqttInterval`、`udpInterval`、`wsInterval`）、`UDP` 目标列表等 |
| `GET /status` | 原始 JSON | 各通道在线状态，值是 `Online`、`Off` 或 `disconnected` |
| `GET /snapshot` | 原始 JSON | 一次拿到 `{"data":遥测,"model":配置,"status":状态}`，**推荐给网关轮询用**，省去三次请求 |
| `GET /getFunctionMap` | 统一结构 | 功能位图，`d.functionMap`；位的含义见业务命令参考附录 B |
| `GET /sn` | 纯文本 | `型号-序列号`，如 `SPM02-AABBCCDDEEFF` |
| `GET /count` | 统一结构 | `msg` 是 `/data`、`/snapshot` 被调用的累计次数 |
| `GET /checkota` | 原始 JSON | `{"otastatus":数字}`，是否有新固件 |
| `GET /low-signal-mode` | 统一结构 | `d` 为 `{"mode":数字}`；带 `mode`（或 `value`、`state`）参数则先写入再返回。HTTPS 还认 `/lowSignalMode`、`/lowsignalmode` 两个别名 |

`/status` 的字段：`MQTTStatus`、`UDPStatus`、`WebSocketStatus`、`ModbusTCPStatus`、`wsInterval`；某些型号还有 `LoRaWANStatus`。

### 3.2 控制与运维

| 接口 | 说明 |
|------|------|
| `GET /location` | 让设备闪灯或鸣叫，用来找到它 |
| `GET /zeroenergy` | 电量清零，**不可恢复** |
| `GET /restart` | 重启（先返回应答，约 1 秒后重启） |
| `GET /ota` 或 `/ota?url=<固件地址>` | 在线升级 Wi-Fi 模块固件；不带 `url` 用默认地址。成功后按设置自动重启 |
| `GET /mcuota` | 升级电表计量芯片的固件，**完成后重启** |
| `GET /erase` | **清除设备存储的全部设置并重启**，慎用 |
| `GET /deletewebpage` | 删除设备里的网页文件 |
| `GET /update` | 让设备从云端重新下载网页文件（需要设备已联网） |
| `GET /clearlog` | 清空日志（部分型号没有） |
| `GET /logfile` | 返回纯文本日志；没有日志时是 404（部分型号没有） |
| `GET /hadata` | 返回 `{"zero":"zeroenergy"}`，Home Assistant 内置页面用，可忽略 |
| `GET /` | 返回内置网页（如果设备里有） |

### 3.3 配置命令

```
POST /save-config
Content-Type: application/json

{"cmd":"wifi","ssid":"MyRouter","pass":"secret"}
```

正文就是[业务命令参考](../ble-common/ble-business-api.zh-CN.md)里的命令 JSON；`cmd` 也可以写成 `configType`。应答是统一结构，`event` 回显命令名。除蓝牙专属的握手命令外，业务命令都能用。

有几个命令在 HTTP 上**写法不同**，因为它们先被内置网页用的旧式处理拦下了。详见[第 6 节](#6-save-config-在-http-上的特例)。

### 3.4 证书上传

| 接口 | 说明 |
|------|------|
| `POST /upload` | 80 端口，`multipart/form-data` 上传一个 PEM 文件，保存为 MQTT CA（`/mqtt.pem`） |
| `POST /uploadcefile` | 内置网页用的接口：正文是带引号的字符串，换行写成 `\n`，设备会去掉引号并**丢掉首尾各一个字符**，再保存为 MQTT CA。`filename=<路径>` 参数可以指定保存路径，在 80 端口上它必须是**第一个**查询参数，设了 Web 密码时它排在 `token` 后面会失效。这些怪癖不好用，建议改用 `/upload` 或 BLE 的 `cafilestart` |
| `POST /upload`（443） | **不支持**，返回 `use HTTP :80 multipart POST /upload` |

大证书更稳妥的做法是用 BLE 或 MQTT 的 `cafilestart` / `cafiledata` 分段写入。

### 3.5 其他型号的接口

继电器（SRS 系列）还有 `/switch1`、`/switch2`、`/schedule`、`/switch-config`、`/getSchedule`。本仓库不覆盖 SRS 产品，这里不展开。

## 4. 80 端口的访问策略

Pro 加密构建在打开 HTTPS（443）之后，会**关闭 80 端口上的全部业务接口**：

```json
{"ok":false,"msg":"use_https","detail":"API only on HTTPS :443","code":2000}
```

状态码是 **403**。只有 `GET /`（内置网页）在 80 端口上还能打开。这样做是为了避免明文通道泄露密码和 token。

| 分支 | 80 端口 |
|------|---------|
| Basic、Basic+ | 一直可用（没有 HTTPS） |
| Lite | 一直可用（Lite 没有 HTTPS，默认关闭 HTTP） |
| Pro | 没开 HTTPS 时可用；开了 HTTPS 就只剩网页，业务接口返回 403 |

遇到 403 `use_https` 就改用 `https://`。

## 5. 80 端口与 443 端口的差别

两个端口提供同一组接口，行为差在下面几处：

| 项目 | 80（HTTP） | 443（HTTPS，仅 Pro） |
|------|-----------|----------------------|
| 证书 | 无 | 优先用设备里的 `/server_cert.pem` + `/server_key.pem`；没有就用**固件内置的证书**，所有设备共用同一份，**不能靠它防冒充**。设备里放了 `/ca_cert.pem` 时会要求客户端证书 |
| 方法 | 按路由 | 只接受 `GET`、`POST`、`OPTIONS`；其他返回 405 |
| `POST` 正文 | 由 Web 服务器收 | 必须带 `Content-Length`，否则 411；请求头加正文总共不能超过 **2048 字节**，否则 413。这比 1024 字节的 JSON 上限更紧，长命令要缩短 |
| JSON 解析失败 | 没检查，按"缺命令"处理，返回 `No data received`（2040） | 明确返回 `bad json`（2070） |
| 连接 | 一次一个请求 | 支持 keep-alive，同一连接上最多连续处理 32 个请求 |
| CORS | 无 | 只有当请求的 `Origin` 与设备自己的主机名相同时才回 `Access-Control-Allow-Origin` |
| 找不到路径 | Web 服务器默认 404 | 404，`{"ok":false,"msg":"path not on HTTPS API","code":2090}` |
| `/upload` | 可用 | 返回错误 2080 |

## 6. `/save-config` 在 HTTP 上的特例

这些 `configType` / `cmd` 在 HTTP 上被**优先匹配**，行为和 BLE、MQTT 上的同名命令不同。

| 命令 | HTTP 上的写法 | 说明 |
|------|--------------|------|
| `mqtt` | `{"configType":"mqtt","host":"broker.example.com","port":8883,"clientid":"dev01","username":"u","password":"p","ssltls":true,"ReportFrequency":30}` | 用**分字段**的形式，不是 `data` 竖线串。`enable:false` 会关闭 MQTT。保存后立即重建连接，不重启。应答 `MQTT sent successfully!` |
| `mqtr` | `{"cmd":"mqtr","data":"host\|clientid\|ssl\|port\|interval\|user\|pwd"}` | 在 HTTP 上要使用**竖线串**，请用这个命令（保存后设备会重启）。JSON 里的竖线直接写 `|` |
| `model` | `{"configType":"model"}` | 返回的是**不带 `ok` 的原始 JSON**，和 `GET /model` 类似 |
| `getmqtt` | `{"configType":"getmqtt"}` | `msg` 是已连上的 Broker 地址，或 `OFF` |
| `name` | `{"configType":"name","name":"..."}` | 设备名最长 30 个字符 |
| `ble` | `{"configType":"ble","opass":"旧","npass":"新"}` | 修改 BLE 密码，最长 16 |
| `topic` | `{"configType":"topic","topic_post":"..","topic_set":"..","topic_response":"..","topic_metadata":".."}` | 四个主题一起改 |
| `ota` | `{"configType":"ota","EspOTA":"true"}` | 触发升级 |
| `erase` | `{"configType":"erase"}` | 清除设置并重启 |

其他旧式类型（`getconfig`、`baudrate`、`ParityStop`、`Modbusaddress`、`clear`、`report`、`alarm`）是内置网页使用的，新开发不需要，用统一命令即可。

要点：**不要在 HTTP 上发 `{"cmd":"mqtt","data":"..."}`**，它会走上表的分字段形式，端口被读成 0，配置会被写坏。改用 `mqtr`，或者用分字段的 `mqtt`。

## 7. 示例

用 `curl`（把 IP、密码换成你自己的）：

```bash
# 没有 Web 密码：直接读一包遥测
curl http://192.168.1.50/data

# 有 Web 密码：先登录拿 token，再带上
curl "http://192.168.1.50/signin?password=mypass"
curl "http://192.168.1.50/snapshot?token=1736912345"

# 让设备闪灯
curl "http://192.168.1.50/location?token=1736912345"

# 改上报目标
curl -X POST "http://192.168.1.50/save-config?token=1736912345" \
  -H "Content-Type: application/json" \
  -d '{"cmd":"udp","IpAddress":"192.168.1.20","localUdpPort":8888,"Frequency":5}'

# Pro 的 HTTPS（内置证书是共用的，-k 跳过校验，仅用于调试）
curl -k "https://192.168.1.50/snapshot?token=1736912345"
```

`udp` 命令的参数名以[业务命令参考](../ble-common/ble-business-api.zh-CN.md)为准。

本仓库的 [HTTP 轮询工具](../../tools/lan/README.md) 会自动处理登录和 token 续期。

## 8. 排查

| 现象 | 原因 |
|------|------|
| 连接被拒或超时 | HTTP 没打开（Lite、Pro 默认关），用 BLE `enablehttp`；或设备不在同一网段 |
| 403 `use_https` | Pro 已开 HTTPS，改用 `https://` |
| `need token` / `invalid token` | 设备设了 Web 密码，先 `/signin`；token 闲置 5 分钟失效，被顶出 5 个名额，或改过密码 |
| HTTPS 握手失败 | TLS 名额被 MQTTS 占用，HTTPS 没有监听；见[概览 3.1 节](../overview/open-wifi-overview.zh-CN.md#31-tls-连接数限制) |
| HTTPS 413 | 请求头加正文超过 2048 字节 |
| `/save-config` 返回 `No data received` | 正文为空、JSON 不合法，或缺 `cmd` / `configType` |
