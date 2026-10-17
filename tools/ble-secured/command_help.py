"""加密 BLE 命令/缩写/错误码速查（中英）。面向 Lite/Pro · 服务 A003。不含明文 A002 与通断器。"""

from __future__ import annotations

from typing import Literal

Lang = Literal["zh", "en"]

FUNCTION_MAP_BITS: list[tuple[int, str]] = [
    (15, "Modbus TCP"),
    (14, "TLS（常随 Modbus）"),
    (11, "WebSocket"),
    (10, "WebSocket TLS"),
    (9, "MQTT"),
    (13, "UDP"),
    (7, "HTTP :80"),
    (5, "LoRaWAN"),
]

MODEL_ABBR: list[tuple[str, str]] = [
    ("WN", "Wi-Fi SSID"),
    ("WPN", "设备显示名 DeviceName"),
    ("MH", "MQTT 主机"),
    ("MF", "MQTT 是否已连接（model 里是布尔；mqttdata 里是数字状态码）"),
    ("MP", "MQTT 端口"),
    ("MC", "MQTT ClientId"),
    ("MI", "MQTT 上报间隔（毫秒）。mqtt.data 里 interval 字段单位是秒，写入后×1000"),
    ("MS", "MQTT 是否 TLS"),
    ("LSM", "弱信号模式 0=关 1=开"),
    ("UI", "UDP 上报间隔（毫秒）"),
    ("WI", "WebSocket 推送间隔（毫秒），无 WS 的固件可能没有"),
    ("TS", "Modbus TLS 复用状态 0空闲 1明文OK 2TLS OK 3证书错 4 socket失败 5明文失败"),
    ("MAD", "485：地址 / 波特率 / 校验，如 5 / 9600 / N81"),
]

HELP_TEXT_ZH = r"""
======== 命令 / 缩写 / 错误码速查（加密 BLE · Lite/Pro）========
GATT：服务 0xA003   写 0xC313   读快照 0xC314   通知 0xC315
PIN：机身 8 位数字（仅 0-9）。SN：通常从广播名 MODEL-SN 取后半段（12 hex）。
建链前：明文 JSON 握手。建链后：业务必须套加密信封 {nonce,ct,tag}（AES-128-CCM，tag=8）。
不要使用明文通道 UUID：A002 / C303 / C304 / C305。

-------- 安全握手（明文阶段，写 C313，应答 Notify C315）--------
ble-crypto-ver     {"cmd":"ble-crypto-ver"}
                   成功 d.ver（如 BT_Crypto_V1）、d.step（0/1/2/3）
ble-crypto-reset   {"cmd":"ble-crypto-reset"}  仅 step=0 或 1；不清除已落盘 LTK
ble-crypto-jpake-round1  带 client_nonce(16 hex) + client_round1(Base64)
                   过长可分片 client_round1_part / part_idx / part_total；设备可回 server_round1_part + fetch_next
ble-crypto-jpake-round2  {"cmd":"ble-crypto-jpake-round2","client_round2":"..."}
                   成功后 step=3，可发加密业务；LTK 落盘须待 Wi-Fi STA 成功
ble-crypto-session-nonce  step=2 时用已缓存 LTK 恢复：{"cmd":"ble-crypto-session-nonce","client_nonce":"..."}

step 含义：0 等 round1；1 等 round2；2 有 LTK 等 session-nonce；3 已建链可加密业务

-------- 加密信封（建链后）--------
写出：明文业务 JSON → AES-CCM → {"nonce":计数器(uint32),"ct":Base64,"tag":Base64}
读入：同上解包。nonce 须严格大于设备已接受值，否则 replay detected
decrypt failed = CCM 失败（密钥/密文/计数器不一致）
event=secure 且 ok=false：固件侧安全层错误，优先看 msg

-------- 业务命令（解锁=建链成功后，语义同明文客户文档，但走加密信封）--------
wifi     {"cmd":"wifi","ssid":"...","pass":"..."}  ssid/pass ≤64；可选 enableble / enablehttps（详见业务命令参考 §2.2）
         成功 WIFI successfully（开始连路由，不等于已拿到 DHCP）
wifiscan / getwifilist  同明文；列表 d.list="ssid|rssi,..."
read     {"cmd":"read"}  然后 GATT Read C314（密文快照需解密）
restart / location / zero / reset / deviceName
model / getFunctionMap / mqttdata / udpdata
enablehttp / enablewebsocket / enablemodbustcp / enabletls / enablehttps（Lite/Pro 能力见 Overview 矩阵）
mqtt / mqtr / topic1 / topic2 / udp / deleteudp
modbus   {"cmd":"modbus","baud":9600,"parityStop":0,"address":1}
         parityStop 0=N81  1=E81  2=O81  3=N82；当前 485 参数见 model.d.MAD
checkota / otaprogress / startota / setInterval / getInterval
【注意】加密通道没有明文版的 cmd=pass；建链即门禁。

-------- functionMap 位（bit15 最高）--------
bit15 Modbus TCP     bit14 TLS（常给 Modbus）
bit13 UDP            bit11 WebSocket   bit10 WebSocket TLS
bit9  MQTT           bit7  HTTP :80    bit5 LoRaWAN
例：128 = 仅 HTTP；HTTP+MQTT = 640；32896 = Modbus TCP + HTTP。

-------- 配置快照 model.d 缩写 --------
WN SSID  WPN 显示名  MH/MP/MC/MI/MS MQTT  MF 布尔已连
LSM 弱信号  UI UDP ms  WI WS ms  TS Modbus TLS  MAD 485

-------- 读特征 C314 --------
IP / RSSI / FW / SN / TP + 电参字符串。单位：V / A / kW / kWh / Hz
按键是否存在解析单相 V/I/P… 或三相 VX/VY/VZ…

-------- 握手失败 msg（明文应答，无固定 code 表时以 msg 为准）--------
connection key must be 8 digits
device locked / version required / invalid step
invalid round1 / invalid round2
round1 verify failed / round2 verify failed
shared key derive failed / ltk derive failed / session derive failed
replay detected / decrypt failed

-------- 业务错误码（与明文通道同类；成功无 code；重叠码看 msg）--------
1002 Please unlock（若仍出现：会话未就绪）
1003 Password Error（明文 pass 遗留；加密通道以 PIN/ZKP 失败为准）
1014 functionMap error
1015 unknow cmd
1018 Error wifi ssid/pass required!
1019 Error wifi length!
1021 Error mqtt data empty!
1024 UDP full   1025 UDP not found
1043 scan busy  1044 scan not ready
1050 payload too large
illegal cmd / unsupported / timeout
""".strip()

HELP_TEXT_EN = r"""
======== Commands / abbreviations / errors (secured BLE · Lite/Pro) ========
GATT: service 0xA003   write 0xC313   read 0xC314   notify 0xC315
PIN: 8 digits from meter body. SN: usually after '-' in broadcast name MODEL-SN.
Before channel up: plaintext JSON handshake. After: business uses envelope {nonce,ct,tag}.
Do NOT use plaintext UUIDs A002 / C303 / C304 / C305.

-------- Handshake (plaintext on C313 / C315) --------
ble-crypto-ver / ble-crypto-reset / ble-crypto-jpake-round1 / round2 / session-nonce
step: 0 wait round1; 1 wait round2; 2 LTK present wait session-nonce; 3 ready for crypto business
LTK persisted only after Wi-Fi STA success (same encrypted session).

-------- Envelope --------
AES-128-CCM, tag 8 bytes, counter in JSON "nonce" (uint32). Strictly increasing vs N_accept.
replay detected vs decrypt failed — see docs.

-------- Business (after step=3; same semantics as plaintext customer docs) --------
wifi / wifiscan / getwifilist / read / restart / model / getFunctionMap / mqttdata / …
No cmd=pass on this channel — handshake IS the gate.

-------- functionMap / model short keys / C314 --------
Same as plaintext customer reference (WN, MH, IP, VX…).

-------- Handshake failure msgs --------
connection key must be 8 digits / invalid step / round* verify failed /
replay detected / decrypt failed / …

-------- Business error codes --------
Prefer msg over code when codes overlap (1002–1005). See docs section 8.
""".strip()


def help_text(lang: Lang = "zh") -> str:
    return HELP_TEXT_EN if lang == "en" else HELP_TEXT_ZH


def decode_function_map(value: int, lang: Lang = "zh") -> str:
    if value == 0:
        return "No communication bits on (functionMap=0)" if lang == "en" else "未开启任何通讯位（functionMap=0）"
    on = [name for bit, name in FUNCTION_MAP_BITS if value & (1 << bit)]
    extra = value
    for bit, _ in FUNCTION_MAP_BITS:
        extra &= ~(1 << bit)
    parts = list(on)
    if extra:
        parts.append(("other=0x" if lang == "en" else "其它位=0x") + f"{extra:04X}")
    sep = ", " if lang == "en" else "、"
    prefix = "Enabled: " if lang == "en" else "已开启: "
    suffix = f"  (raw {value})" if lang == "en" else f"  (原始值 {value})"
    return prefix + sep.join(parts) + suffix


def format_model_snapshot(data: dict, lang: Lang = "zh") -> str:
    lines = ["Config snapshot:" if lang == "en" else "配置快照（缩写）："]
    known = {x[0] for x in MODEL_ABBR}
    for key, meaning in MODEL_ABBR:
        if key in data:
            lines.append(f"  {key:4}  {meaning} = {data.get(key)!r}")
    for k in data.keys():
        if k not in known:
            other = "(not in legend)" if lang == "en" else "(未列入图例)"
            lines.append(f"  {k:4}  {other} = {data.get(k)!r}")
    return "\n".join(lines)


TP_NAMES: dict[int, str] = {
    1: "单相（SPM01）",
    2: "单相（SDM01_1PN）",
    3: "三相（SPM02）",
    4: "三相（SDM01_3PN）",
    5: "两路（SDM02）",
    8: "SDM01 Gen2",
    9: "其它",
}

METER_FIELDS: list[tuple[str, str]] = [
    ("IP", "IP / Wi-Fi 状态"),
    ("RSSI", "下行 RSSI（dBm）"),
    ("FW", "固件版本"),
    ("SN", "序列号"),
    ("TP", "产品类型"),
    ("V", "电压 V（V）"),
    ("I", "电流 I（A）"),
    ("P", "有功功率 P（kW）"),
    ("PF", "功率因数"),
    ("F", "频率 F（Hz）"),
    ("FE", "正向电能 FE（kWh）"),
    ("RE", "反向电能 RE（kWh）"),
    ("VX", "电压 L1/X（V）"),
    ("VY", "电压 L2/Y（V）"),
    ("VZ", "电压 L3/Z（V）"),
    ("IX", "电流 L1/X（A）"),
    ("IY", "电流 L2/Y（A）"),
    ("IZ", "电流 L3/Z（A）"),
    ("PX", "功率 L1/X（kW）"),
    ("PY", "功率 L2/Y（kW）"),
    ("PZ", "功率 L3/Z（kW）"),
    ("PFX", "功率因数 L1/X"),
    ("PFY", "功率因数 L2/Y"),
    ("PFZ", "功率因数 L3/Z"),
    ("FEX", "正向电能 L1/X（kWh）"),
    ("FEY", "正向电能 L2/Y（kWh）"),
    ("FEZ", "正向电能 L3/Z（kWh）"),
    ("REX", "反向电能 L1/X（kWh）"),
    ("REY", "反向电能 L2/Y（kWh）"),
    ("REZ", "反向电能 L3/Z（kWh）"),
]

MQTT_MF_TEXT: dict[str, str] = {
    "-4": "超时",
    "-3": "连接丢失",
    "-2": "TCP/TLS 失败",
    "-1": "断开 / 未启用",
    "0": "已连接",
    "1": "协议拒绝",
    "2": "ClientId 拒绝",
    "3": "Broker 不可用",
    "4": "账号错误",
    "5": "未授权",
}

MQTT_FIELDS: list[tuple[str, str]] = [
    ("MF", "连接状态"),
    ("TP", "主题 topic_post"),
    ("TC", "主题 topic_set"),
    ("TR", "主题 topic_response"),
    ("TM", "主题 topic_metadata"),
    ("MU", "用户名"),
    ("MPS", "密码"),
    ("MH", "主机（model）"),
    ("MP", "端口（model）"),
    ("MC", "ClientId（model）"),
    ("MI", "上报间隔 ms（model）"),
    ("MS", "MQTT TLS（model）"),
]


def meter_rows(data: dict, lang: Lang = "zh") -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for key, meaning in METER_FIELDS:
        if key not in data:
            continue
        seen.add(key)
        val = data.get(key)
        if key == "IP":
            shown = wifi_ip_status(str(val), lang)
        elif key == "TP":
            try:
                shown = f"{val}  {TP_NAMES.get(int(val), '')}".strip()
            except (TypeError, ValueError):
                shown = str(val)
        else:
            shown = str(val)
        if lang == "en":
            meaning_en = {
                "IP": "IP / Wi-Fi status", "RSSI": "Downlink RSSI (dBm)", "FW": "Firmware", "SN": "Serial",
                "TP": "Product type", "V": "Voltage (V)", "I": "Current (A)", "P": "Power (kW)",
                "PF": "Power factor", "F": "Frequency (Hz)", "FE": "Forward energy (kWh)", "RE": "Reverse energy (kWh)",
                "VX": "Voltage L1/X (V)", "VY": "Voltage L2/Y (V)", "VZ": "Voltage L3/Z (V)",
                "IX": "Current L1/X (A)", "IY": "Current L2/Y (A)", "IZ": "Current L3/Z (A)",
                "PX": "Power L1/X (kW)", "PY": "Power L2/Y (kW)", "PZ": "Power L3/Z (kW)",
                "PFX": "PF L1/X", "PFY": "PF L2/Y", "PFZ": "PF L3/Z",
                "FEX": "Fwd energy L1/X (kWh)", "FEY": "Fwd energy L2/Y (kWh)", "FEZ": "Fwd energy L3/Z (kWh)",
                "REX": "Rev energy L1/X (kWh)", "REY": "Rev energy L2/Y (kWh)", "REZ": "Rev energy L3/Z (kWh)",
            }.get(key, meaning)
            meaning = meaning_en
        rows.append((key, meaning, shown))
    for key in data.keys():
        if key not in seen:
            rows.append((str(key), "Other field" if lang == "en" else "其它字段", str(data.get(key))))
    return rows


def format_meter_snapshot(data: dict, lang: Lang = "zh") -> str:
    if not data:
        return "No readings yet" if lang == "en" else "尚未读取电参"
    lines = ["Meter readings (GATT Read C314):" if lang == "en" else "电参（GATT Read C314）："]
    for key, meaning, shown in meter_rows(data, lang):
        lines.append(f"  {key:4}  {meaning} = {shown}")
    return "\n".join(lines)


def mqtt_mf_text(value: object, lang: Lang = "zh") -> str:
    raw = MQTT_MF_TEXT.get(str(value), str(value))
    if lang != "en":
        return raw
    en_map = {
        "-4": "Timeout", "-3": "Connection lost", "-2": "TCP/TLS failure",
        "-1": "Disconnected / not enabled", "0": "Connected", "1": "Protocol rejected",
        "2": "ClientId rejected", "3": "Broker unavailable", "4": "Bad credentials", "5": "Unauthorized",
    }
    return en_map.get(str(value), raw)


def format_comm_config(
    model: dict | None = None,
    mqtt: dict | None = None,
    udp: object = None,
    function_map: object = None,
    lang: Lang = "zh",
) -> str:
    lines: list[str] = []
    if function_map is not None:
        try:
            prefix = "Channels: " if lang == "en" else "通道："
            lines.append(prefix + decode_function_map(int(function_map), lang))
        except (TypeError, ValueError):
            lines.append(("Channels: " if lang == "en" else "通道：") + str(function_map))
        lines.append("")
    model = model or {}
    mqtt = mqtt or {}
    lines.append("[Modbus RTU / 485]" if lang == "en" else "【Modbus RTU / 485】")
    mad = model.get("MAD")
    missing = "key absent / not read" if lang == "en" else "本型号无此键或未读到"
    lines.append(f"  MAD  address/baud/parity = {mad if mad not in (None, '') else missing}")
    lines.append("")
    lines.append("[MQTT]" if lang == "en" else "【MQTT】")
    merged = dict(model)
    merged.update(mqtt)
    any_mqtt = False
    for key, meaning in MQTT_FIELDS:
        if key not in merged:
            continue
        any_mqtt = True
        val = merged.get(key)
        if key == "MF":
            val = f"{val}  {mqtt_mf_text(val, lang)}"
        lines.append(f"  {key:4}  {meaning} = {val}")
    if not any_mqtt:
        lines.append("  Not queried yet." if lang == "en" else "  尚未查询。")
    lines.append("")
    lines.append("[UDP]" if lang == "en" else "【UDP】")
    items = None
    if isinstance(udp, dict):
        items = udp.get("udp_data")
    elif isinstance(udp, list):
        items = udp
    if items is None:
        lines.append("  Not queried yet." if lang == "en" else "  尚未查询。")
    elif not items:
        lines.append("  Target list empty" if lang == "en" else "  目标列表为空")
    else:
        for i, item in enumerate(items, 1):
            if isinstance(item, dict):
                lines.append(f"  {i}. {item.get('ip', '')}:{item.get('port', '')}")
            else:
                lines.append(f"  {i}. {item}")
    wn = model.get("WN")
    if wn not in (None, ""):
        lines.append("")
        lines.append((("[Wi-Fi] " if lang == "en" else "【Wi-Fi】") + f"SSID = {wn}"))
    return "\n".join(lines).rstrip()


def wifi_ip_status(ip: str, lang: Lang = "zh") -> str:
    mapping_zh = {
        "-1": "未知/刚配网", "0": "空闲", "1": "找不到 SSID",
        "3": "已关联（通常应显示 IPv4）", "4": "连接失败", "5": "连接丢失", "6": "已断开",
    }
    mapping_en = {
        "-1": "Unknown / just provisioned", "0": "Idle", "1": "SSID not found",
        "3": "Associated (usually becomes IPv4)", "4": "Connect failed",
        "5": "Connection lost", "6": "Disconnected",
    }
    if "." in ip:
        return (f"Online {ip}" if lang == "en" else f"已联网 {ip}")
    mapping = mapping_en if lang == "en" else mapping_zh
    return mapping.get(str(ip), (f"Status code {ip}" if lang == "en" else f"状态码 {ip}"))


ONE_CLICK = [
    ("重启", "Restart", "restart"),
    ("定位快闪", "Locate blink", "location"),
    ("已开启功能", "Enabled features", "getFunctionMap"),
    ("读取配置", "Read config", "model"),
    ("UDP 列表", "UDP list", "udpdata"),
    ("OTA 检查", "OTA check", "checkota"),
    ("OTA 进度", "OTA progress", "otaprogress"),
    ("OTA 启动", "OTA start", "startota"),
    ("恢复出厂设置", "Factory reset", "reset"),
    ("启用 HTTP", "Enable HTTP", "enablehttp"),
    ("开 Modbus TCP over Wi-Fi", "Modbus TCP over Wi-Fi", "enablemodbustcp"),
    ("MQTT 状态", "MQTT status", "mqttdata"),
]


def one_click_buttons(lang: Lang = "zh") -> list[tuple[str, str]]:
    return [((en if lang == "en" else zh), cmd) for zh, en, cmd in ONE_CLICK]
