# mDNS Discovery

> Status: first release | Applies to: all SPM / SDM Open Wi-Fi branches | Based on firmware source SXM_EW_C3 `5.1.16`, SDMV2 `1.2.12` / `3.1.19` and the Gitbook "mDNS Discovery" page

After the meter joins your Wi-Fi network it announces itself over mDNS (Multicast DNS). A gateway, EMS or app on the same subnet can then find the IP address of every meter **without a static IP and without scanning**, and go on to use [Modbus TCP](../modbus-tcp/modbus-tcp-api.en.md), [HTTP](../http/http-api.en.md), [WebSocket](../websocket/websocket-api.en.md) or [UDP](../udp/udp-api.en.md).

## 1. Introduction

| Item | Description |
|------|-------------|
| Service type | `_http._tcp.local.` |
| Port | `80` (the Web UI and HTTP API; the other ports are **not** announced) |
| Hostname | `<device name>.local.`, by default `EnergySensor-<model>[_<variant>]-<MAC>` (see [Section 2](#2-hostname-format)) |
| TXT records | None; the service carries no extra information |
| Address type | IPv4 |
| When | After every successful Wi-Fi connection (including reconnects) |
| Not available | Until the meter has connected to your Wi-Fi network (no announcement while it is only in provisioning state) |

## 2. Hostname format

The default hostname is generated from the model and the MAC address:

```text
EnergySensor-<MODEL>[_<VARIANT>]-<MAC>.local.
EnergySensor-SDM01_3PN_01-45705E597760.local.
```

| Field | Example | Description |
|-------|---------|-------------|
| `EnergySensor` | | Fixed prefix |
| `MODEL` | `SDM01_3PN` | Product model, the same as the model in Modbus register 984 |
| `VARIANT` | `01` / `02` | Firmware variant, see the table below. Some models have **no** variant field |
| `MAC` | `45705E597760` | The 12 hexadecimal characters of the device MAC, upper case, no separators; also the serial number used in MQTT topics |

Variant by firmware family:

| Firmware | Variant | Example |
|----------|---------|---------|
| SXM (Basic / Lite): SDM01_3PN and SDM01_1PN | `_01` | `EnergySensor-SDM01_3PN_01-45705E597760` |
| SXM (Basic / Lite): other models such as SPM02, SDM02 | none | `EnergySensor-SPM02-45705E597760` |
| SDMV2 (Basic+ / Pro) | `_02` | `EnergySensor-SDM01_3PN_02-45705E597760` |

Customer-customized builds may use a different name instead of the model.

### 2.1 Renaming the device

The hostname is the **device name**, which the user can change with the `deviceName` command (at most 30 characters, see [Business Command Reference](../ble-common/ble-business-api.en.md)) or on the Web page. The new name is announced the next time the device connects to Wi-Fi (restart it to be sure). Once renamed:

- the `EnergySensor-` prefix filter no longer finds it; discover by the **service type** `_http._tcp` and check the identity another way (see [Section 3.2](#32-confirm-the-identity-of-a-found-device));
- use only letters, digits and `-` in the name. Spaces and other characters are not valid in a hostname, and some resolvers will not resolve them.

## 3. Discovering devices

### 3.1 Filtering

1. Browse for `_http._tcp`. Many devices on the network (printers, NAS, routers) announce the same type, so you will get a list.
2. Keep entries whose name starts with `EnergySensor-`.
3. Split the name into model, variant and MAC.
4. **Only connect to variants you have validated.** The variant identifies the firmware family and thus the behavior of the HTTP API and the other interfaces (see the [Overview](../overview/open-wifi-overview.en.md)); report an unknown variant instead of assuming it is compatible.
5. Take the IPv4 address from the answer. Cache it, but be ready to look it up again: a DHCP lease can change the address. Prefer a DHCP reservation on the router for production sites.

### 3.2 Confirm the identity of a found device

Names can be changed and other products may use a similar one, so confirm before you start using the device:

- Read Modbus registers 978 ~ 988 (MAC and model); no sign-in is needed, see [Modbus TCP](../modbus-tcp/modbus-tcp-api.en.md#41-product-identification-base-address-978).
- Or call HTTP `/signin` without a password to see whether the device is protected, then `/model` with a token; see [HTTP](../http/http-api.en.md#2-session-and-authentication).

### 3.3 What to use after discovery

| Need | Interface |
|------|-----------|
| PLC / industrial gateway, polling | [Modbus TCP](../modbus-tcp/modbus-tcp-api.en.md) port 502 |
| Configuration, status, firmware update | [HTTP](../http/http-api.en.md) port 80 (443 for HTTPS) |
| Low-latency stream | [WebSocket](../websocket/websocket-api.en.md) port 81 (plain or WSS, same port) |
| Fast one-way readings | [UDP](../udp/udp-api.en.md): configure the device to send to you |

Ports other than 80 are not in the mDNS record; use the defaults above.

## 4. Verifying that mDNS works

| Platform | Command / tool |
|----------|----------------|
| Any, with Python | `python tools/lan/discover_mdns.py` (see [tools/lan](../../tools/lan/README.en.md)); lists every meter found |
| macOS | `dns-sd -B _http._tcp` and `dns-sd -L "<name>" _http._tcp local` |
| Linux | `avahi-browse -rt _http._tcp` |
| Windows | Bonjour's `dns-sd` (installed with iTunes / Bonjour Print Services), or the Python tool above |
| Android | an app such as "Service Browser", browse `_http._tcp` |
| Packet capture | Wireshark with the display filter `mdns` |

Quick check by name: `ping EnergySensor-SDM01_3PN_01-45705E597760.local`.

The tool needs the `zeroconf` package; without it, the tool falls back to a plain mDNS query that needs no package.

## 5. Troubleshooting

| Symptom | Likely cause |
|---------|--------------|
| Device not found | Phone / PC and the meter are on different subnets or VLANs; the router blocks multicast ("AP isolation", "client isolation", IGMP snooping problems); the meter is not connected to Wi-Fi |
| Found, but cannot connect | Address changed (DHCP); firewall on your side; the target interface is turned off (for example Modbus TCP bit 15) |
| Found only after a while | Announcement happens once the Wi-Fi connection is up; wait a few seconds after power-on or a router restart |
| Name differs from what you expect | The device was renamed (`deviceName`) or it is a firmware family with another variant |
| Windows cannot resolve `.local` | Install Bonjour, or use the Python tool, or use the IP address directly |
| Name resolves on one computer only | That computer has its own mDNS stack (such as Bonjour / Avahi); others need the same |

## 6. Related pages

- [Overview](../overview/open-wifi-overview.en.md)
- [Modbus TCP](../modbus-tcp/modbus-tcp-api.en.md), [HTTP](../http/http-api.en.md), [WebSocket](../websocket/websocket-api.en.md), [UDP](../udp/udp-api.en.md)
- Machine-readable description: [`spec/mdns-discovery.json`](../../spec/mdns-discovery.json)
