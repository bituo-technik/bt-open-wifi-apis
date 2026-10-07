# 局域网通道工具 / LAN channel tools

Wi-Fi 通道（HTTP、WebSocket、UDP、Modbus TCP、MQTT、mDNS）的命令行工具。**除 `mqtt_monitor.py` 外只依赖 Python 3.9+ 标准库**，协议与 `docs/` 完全一致。Command-line tools for the Wi-Fi channels; apart from `mqtt_monitor.py` they need only the Python 3.9+ standard library.

| 工具 / Tool | 用途 / Purpose | 文档 / Doc |
|-------------|----------------|------------|
| `discover_mdns.py` | 发现局域网内的电表（`_http._tcp`，`EnergySensor-*`）。有 `zeroconf` 用 zeroconf，没有则用内置查询 / find meters; built-in resolver when `zeroconf` is missing | [mDNS](../../docs/mdns/mdns-discovery.zh-CN.md) |
| `modbus_poll.py` | 读识别信息与电参量，`--locate`、`--reset-energy` / read identification and measurements | [Modbus TCP](../../docs/modbus-tcp/modbus-tcp-api.zh-CN.md) |
| `http_poll.py` | 轮询 `/snapshot` 等，自动登录并在 token 过期时重新登录，`--cmd` 发业务命令 / polling with token handling | [HTTP](../../docs/http/http-api.zh-CN.md) |
| `ws_client.py` | WebSocket 客户端，自动重连，WSS 失败回退 ws / client with auto-reconnect | [WebSocket](../../docs/websocket/websocket-api.zh-CN.md) |
| `udp_listen.py` | 接收 UDP 上报，可用广播密钥解密 AES-CCM，并检测丢包 / receiver, optional AES-CCM decryption, loss detection | [UDP](../../docs/udp/udp-api.zh-CN.md) |
| `mqtt_monitor.py` | 订阅 `/data` `/cdata` `/mdata`，发送命令并等待响应（需要 `paho-mqtt`）/ MQTT monitor | [MQTT](../../docs/mqtt/mqtt-api.zh-CN.md) |
| `mock_device.py` | **假电表**：没有硬件也能开发和测试集成（HTTP、Modbus、WebSocket、UDP）/ fake meter for development | 全部 |
| `cmdarg.py` | 命令行参数解析（见下文引号说明）/ command-argument parser | |

## 快速开始 / Quick start

```text
python discover_mdns.py                          # 找到电表 IP
python modbus_poll.py 192.168.1.50 -i 2          # 每 2 秒读一次
python http_poll.py 192.168.1.50 --password 123456 -i 5
python ws_client.py 192.168.1.50 --interval 1000
python udp_listen.py --port 9000                 # 先让电表往这里发，见下
```

让电表把 UDP 报文发到这台电脑（任何通道都能发这个命令，这里用 HTTP）：

```text
python http_poll.py 192.168.1.50 --cmd "udp IpAddress=192.168.1.100 localUdpPort=9000 Frequency=5"
```

没有硬件时，先启动假电表，再用上面的工具连 `127.0.0.1` 的对应端口：

```text
python mock_device.py --password 123456 --udp-to 127.0.0.1:9000
python modbus_poll.py 127.0.0.1 -p 1502
python http_poll.py 127.0.0.1 -p 8080 --password 123456
python ws_client.py 127.0.0.1 -p 8081
python udp_listen.py --port 9000
```

假电表遵循文档描述的行为（统一响应、token 规则、1024 字节限制、Modbus 只应答最新帧），**不等于**真机固件，不能用来证明真机行为。 The mock follows the documented behavior; it does not prove real-device behavior.

## 命令行引号 / Quoting commands

Windows PowerShell 5.1 会吞掉参数里的双引号，`'{"cmd":"location"}'` 到工具手里变成 `{cmd:location}`。所有 `--cmd` 都接受三种写法，随便用哪种：

```text
--cmd "location"
--cmd "udp IpAddress=192.168.1.100 localUdpPort=9000 Frequency=5"      # 命令名 + key=value
--cmd '{"cmd":"getFunctionMap"}'                                       # 标准 JSON（bash、PowerShell 7 可用）
```

数字、`true`、`false` 会自动转换，其它按字符串处理。值里有逗号或空格（例如 Wi-Fi 密码）时请在 bash 或 PowerShell 7 里用标准 JSON。

## UDP 加密报文 / Encrypted UDP

Pro 可以把 UDP 报文改为 AES-CCM 密文（见 [UDP 第 4 节](../../docs/udp/udp-api.zh-CN.md#4-aes-ccm-加密报文)）。解密需要 `pip install cryptography` 和广播密钥：

```text
python udp_listen.py --key 00112233445566778899aabbccddeeff
python udp_listen.py --cache ../ble-secured/ble_crypto_client_cache.json --sn AABBCCDDEEFF
```

第二种直接读取加密 BLE 工具完整配网后保存的缓存（含密钥，**已被 `.gitignore` 排除，不要提交**）。Keys in that cache file are secrets and git-ignored.

## 退出码 / Exit codes

`0` 成功，`1` 连接或协议错误（含设备返回 `ok:false`），`2` 参数错误或缺少确认（例如 `--reset-energy` 没有 `--yes`）。

## 依赖 / Requirements

见 [`requirements.txt`](requirements.txt)：`zeroconf`（可选）、`cryptography`（解密 UDP 或让假电表加密）、`paho-mqtt`（只有 `mqtt_monitor.py` 需要）。
