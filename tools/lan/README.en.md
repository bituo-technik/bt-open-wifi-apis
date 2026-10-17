[中文](README.zh-CN.md)

# LAN channel tools

Command-line tools for the Wi-Fi channels (HTTP, WebSocket, UDP, Modbus TCP, MQTT, mDNS). **Apart from `mqtt_monitor.py` they need only the Python 3.9+ standard library.** The protocol matches `docs/`.

| Tool | Purpose | Document |
|------|---------|----------|
| `discover_mdns.py` | Find meters on the LAN (`_http._tcp`, `EnergySensor-*`). Uses `zeroconf` when installed, otherwise the built-in query | [mDNS](../../docs/mdns/mdns-discovery.en.md) |
| `modbus_poll.py` | Read identification and measurements; `--locate`, `--reset-energy` | [Modbus TCP](../../docs/modbus-tcp/modbus-tcp-api.en.md) |
| `http_poll.py` | Poll `/snapshot` and similar paths, sign in automatically, refresh the token when it expires, send business commands with `--cmd` | [HTTP](../../docs/http/http-api.en.md) |
| `ws_client.py` | WebSocket client with auto-reconnect; falls back from WSS to ws | [WebSocket](../../docs/websocket/websocket-api.en.md) |
| `udp_listen.py` | Receive UDP reports, optionally decrypt AES-CCM with the broadcast key, and detect loss | [UDP](../../docs/udp/udp-api.en.md) |
| `mqtt_monitor.py` | Subscribe to `/data` `/cdata` `/mdata`, send commands, and wait for the response (needs `paho-mqtt`) | [MQTT](../../docs/mqtt/mqtt-api.en.md) |
| `mock_device.py` | **Fake meter** for developing and testing an integration without hardware (HTTP, Modbus, WebSocket, UDP) | The channel documents |
| `cmdarg.py` | Command-line argument parser (see quoting below) | |

## Quick start

```text
python discover_mdns.py                          # find the meter IP
python modbus_poll.py 192.168.1.50 -i 2          # read every 2 seconds
python http_poll.py 192.168.1.50 --password 123456 -i 5
python ws_client.py 192.168.1.50 --interval 1000
python udp_listen.py --port 9000                 # point the meter here first; see below
```

Point the meter's UDP reports at this computer (any channel can send the command; this example uses HTTP):

```text
python http_poll.py 192.168.1.50 --cmd "udp IpAddress=192.168.1.100 localUdpPort=9000 Frequency=5"
```

Without hardware, start the fake meter, then point the tools above at the matching port on `127.0.0.1`:

```text
python mock_device.py --password 123456 --udp-to 127.0.0.1:9000
python modbus_poll.py 127.0.0.1 -p 1502
python http_poll.py 127.0.0.1 -p 8080 --password 123456
python ws_client.py 127.0.0.1 -p 8081
python udp_listen.py --port 9000
```

The fake meter follows the documented behavior (unified response, token rules, the 1024-byte limit, Modbus answering only the latest frame). It is **not** the device firmware and cannot prove how a real meter behaves.

## Quoting commands

Windows PowerShell 5.1 strips double quotes inside arguments, so `'{"cmd":"location"}'` arrives as `{cmd:location}`. Every `--cmd` accepts any of these three forms:

```text
--cmd "location"
--cmd "udp IpAddress=192.168.1.100 localUdpPort=9000 Frequency=5"      # command name + key=value
--cmd '{"cmd":"getFunctionMap"}'                                       # standard JSON (bash, PowerShell 7)
```

Numbers, `true`, and `false` are converted automatically; everything else stays a string. When a value contains a comma or a space (for example a Wi-Fi password), use standard JSON in bash or PowerShell 7.

## Encrypted UDP datagrams

Pro can send UDP as AES-CCM ciphertext (see [UDP section 4](../../docs/udp/udp-api.en.md#4-aes-ccm-encrypted-datagram)). Decryption needs `pip install cryptography` and the broadcast key:

```text
python udp_listen.py --key 00112233445566778899aabbccddeeff
python udp_listen.py --cache ../ble-secured/ble_crypto_client_cache.json --sn AABBCCDDEEFF
```

The second form reads the cache written by the secured BLE tool after a full provisioning session. That file contains keys, **is listed in `.gitignore`, and must not be committed**.

## Exit codes

`0` success, `1` connection or protocol error (including a device response of `ok:false`), `2` bad arguments or a missing confirmation (for example `--reset-energy` without `--yes`).

## Requirements

See [`requirements.txt`](requirements.txt): `zeroconf` (optional), `cryptography` (decrypt UDP, or let the fake meter encrypt), `paho-mqtt` (only `mqtt_monitor.py` needs it).
