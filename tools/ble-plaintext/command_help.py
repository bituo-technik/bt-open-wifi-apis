"""明文 BLE 命令/缩写/错误码速查（中英）。面向未加密 BLE + Wi-Fi C3 产品。不含加密通道与通断器。"""

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

HELP_TEXT = r"""
======== 命令 / 缩写 / 错误码速查（明文 BLE · Wi-Fi C3）========
GATT：服务 0xA002   写命令 0xC303   读快照 0xC304   通知应答 0xC305
出厂 BLE 密码 1234。连接后先订阅 C305，再 cmd=pass。业务 JSON 全部要先解锁。
成功应答：ok=true，无 code 键。失败：ok=false，有 code，msg 为英文原样。

-------- 会话 --------
pass     写C303  {"cmd":"pass","pas":"1234","continue":true}
         成功 msg=Password Correct  event=pass
         失败 Password Error / 1003；缺密码 Please unlock / 1002 event=pas
         continue:true 后本连接内后续命令不必再带 pas；可反复 GATT Read C304
         可选 newpas≤16 同时改密；可选 auth≤40 手机绑定
blepassword  写C303  {"cmd":"blepassword","old":"1234","new":"654321"}
         成功 Password yes；旧密码错 Old Password Error / 1026
read     写C303  {"cmd":"read","continue":true}  成功 msg=ready
         然后 GATT Read C304。未解锁读 C304：Please unlock / 1002 event=read
resetauth  写C303  清除手机绑定

-------- Wi-Fi 配网（仅 2.4 GHz）--------
wifi     写C303  {"cmd":"wifi","ssid":"...","pass":"..."}  ssid/pass ≤64
         成功 WIFI successfully（开始连路由，不等于已拿到 DHCP）
         缺字段 Error wifi ssid/pass required! / 1018
         过长 Error wifi length! / 1019
wifiscan 写C303  成功 scan started；进行中 scan busy / 1043
getwifilist 写C303  成功 d.list="ssid|rssi,ssid2|rssi2" 最多10条 RSSI降序
         未好 scan not ready / 1044

-------- 常用控制 --------
restart  写C303  restart received  随后 GATT 必断，须重连再 pass
location 写C303  location received  约 4Hz 闪 15 秒
reset    写C303  reset received  出厂并重启（危险）
zero     写C303  电能清零，不可恢复
deviceName 写C303  {"cmd":"deviceName","name":"..."}  name≤30
         过长 Error name length! / 1027

-------- 查询 --------
model    写C303  {"cmd":"model","type":1}  d 内短键见下方「配置快照缩写」
getFunctionMap 写C303  d.functionMap 为 uint16，按位见下方
mqttdata 写C303  d.MF 连接状态 TP/TC/TR/TM 主题 MU/MPS 账号
udpdata  写C303  UDP 目标列表
getInterval 写C303  d.value WebSocket 推送 ms（无 WS 则 unsupported / 1005）
getModbusTlsMuxSetupStatus  仅带局域网 TLS 的型号；Basic / Lite 上常为 unsupported

-------- 通讯开关（改 functionMap，部分需重启才监听端口）--------
enablehttp  {"cmd":"enablehttp","enable":true|false}  明文 HTTP :80  成功 http yes / http off
enablewebsocket  {"cmd":"enablewebsocket","enable":true}  可选 enableTLS
enablemodbustcp  {"cmd":"enablemodbustcp","enable":true}
enabletls   {"cmd":"enabletls","enable":true}
enablehttps 仅 PRO/带局域网 TLS 的型号；Basic 上常为 unsupported
functionMap  {"cmd":"functionMap","value":整数}  整图覆盖，吃内存通道最多同时 2 个，慎用
         非法组合 functionMap error / 1014

-------- MQTT / UDP / Modbus / OTA --------
mqtt     {"cmd":"mqtt","data":"host|clientid|ssl|port|interval秒|user|pass"}
mqtr     同上，配置完重启。空 data → Error mqtt data empty! / 1021
topic1   {"cmd":"topic1","topic_post":"...","topic_set":"..."}
topic2   {"cmd":"topic2","topic_response":"...","topic_metadata":"..."}
modbus   {"cmd":"modbus","baud":9600,"parityStop":0,"address":1}
         parityStop 0=N81  1=E81  2=O81  3=N82（以设备为准）
udp      新增 UDP 目标；满了 UDP full / 1024
deleteudp 删除；不存在 UDP not found / 1025
checkota  d.otastatus：200 有升级包  404 已最新  199 内存不足  其它网络错
otaprogress  查询进度，只读
startota  开始升级；可选 reboot
setInterval  {"cmd":"setInterval","value":1000}  只改 WebSocket 推送 ms（100～86400000）
         非法 bad value / 1004。不改 MQTT 的 MI、不改 UDP 的 UI
cafilestart / cafiledata  MQTT TLS 证书分片（需要证书时）
keepalive  明文固件空闲关 GATT 已关闭，可忽略

-------- functionMap 位（bit15 最高）--------
bit15 Modbus TCP     bit14 TLS（常给 Modbus）
bit13 UDP            bit12 保留（UDP 无 TLS 伴生位）
bit11 WebSocket      bit10 WebSocket TLS
bit9  MQTT           bit8  草稿残留，勿依赖
bit7  HTTP :80       bit6  草稿残留，勿依赖
bit5  LoRaWAN        bit4～0 保留
例：128 = 仅 HTTP。HTTP+MQTT = 128+512 = 640。
解析：functionMap & (1<<n) 非 0 则该位开启。

-------- 配置快照 model.d 缩写 --------
WN   Wi-Fi SSID
WPN  设备显示名
MH   MQTT 主机（空=未配）
MF   MQTT 是否已连接（布尔）
MP   MQTT 端口（0=未配）
MC   MQTT ClientId
MI   MQTT 上报间隔，毫秒（默认常 5000）
MS   MQTT 是否 TLS
LSM  弱信号模式 0/1
UI   UDP 间隔，毫秒
WI   WebSocket 推送间隔，毫秒（可无此键）
TS   Modbus TLS 复用 0～5（可无此键）
MAD  485 地址/波特率/校验  例 "5 / 9600 / N81"

-------- 读特征 C304 公共键 --------
IP    已联网=IPv4。未联网=WiFi.status 十进制：-1未知 0空闲 1找不到SSID 3已连(通常改写成IPv4) 4失败 5丢失 6断开
RSSI  路由器→电表 下行 dBm（整数）。调电表发射功率一般不改这个数
FW    固件版本    SN 序列号    TP 产品类型
电参多为十进制字符串。先看 TP：1/2 单相 V I P PF F FE RE；3/4 三相后缀 X/Y/Z；5 两路 X/Y。

-------- mqttdata.d.MF（MQTT 已启用时）--------
-4 超时  -3 丢失  -2 TCP/TLS 失败  -1 断开  0 已连接
1 协议拒  2 ClientId 拒  3 Broker 不可用  4 账号错  5 未授权
未启用 MQTT 时 MF 也常为 -1，需结合是否已配置 MQTT 区分。

======== 错误码（明文 BLE 通道，code=1000 段）========
成功包没有 code。配置类失败时常为 1000+子码 s。

【固定】
1000  auth error              手机绑定串不匹配
1001  not authenticated       未完成绑定认证
1002  Please unlock           未解锁。写通道 event=pas；读 C304 event=read
                              （配置子码 s=2「密码过长」组合后也是 1002，看 msg 区分）
1003  Password Error          BLE 密码错（出厂 1234）
1004  No cmd                  缺少 cmd。或 setInterval 等 bad value（s=4 → 1004，看 msg）
1005  No data received        缺必要参数。或 unsupported（s=5 → 1005，看 msg）
1050  payload too large       明文写入超长，缩短 JSON / 提高 MTU

【Wi-Fi 扫描】
1043  scan busy               正在扫，勿重复 wifiscan
1044  scan not ready          结果未好，等 2～3 秒再 getwifilist

【配置子码 → BLE code = 1000 + s】（msg 以设备英文为准）
1002  Error password length!     新密码超过 16（与 Please unlock 同码，用 msg 区分）
1003  auth error                 鉴权串策略（与 Password Error 同码时看 msg）
1004  bad value                  数值非法（如间隔 <100）
1005  unsupported                当前型号无此命令（Basic / Lite 上 enablehttps、setInterval 等常见）
1006  null                       非对应型号无数据
1014  functionMap error          功能位组合非法（吃内存通道超过 2 个等）
1015  unknow cmd                 未知命令
1016  Timer not found            定时器不存在
1017  Invalid timer              定时器参数非法
1018  Error wifi ssid/pass required!  Wi-Fi 缺 SSID 或密码
1019  Error wifi length!         Wi-Fi 参数过长
1020  Error wifi reset in progress  Wi-Fi 重置冲突
1021  Error mqtt data empty!     MQTT data 为空
1022  Error length!              MQTT 等字段长度错误
1023  cafile error               证书流程异常
1024  UDP full                   UDP 目标已满
1025  UDP not found              要删的 UDP 不存在
1026  Old Password Error         blepassword 旧密码错
1027  Error name length!         显示名过长
1028  mda format error           寄存器扩展格式错
1029  mda failed                 寄存器扩展失败
1030  minvert data format error  取反配置格式错
1031  minvert save failed        取反配置保存失败
1032  minvert data length error  取反配置长度错
1033  minvert data error         取反配置数据错
1034  minvert missing data       取反配置缺数据
1035  bleota no data             BLE OTA 无数据
1036  bleota err param           BLE OTA 参数非法
1037  bleota err state           BLE OTA 状态错
1038  bleota err seq             包序号不连续
1039  bleota err crc             CRC 失败
1040  bleota err write           分区写入失败
1041  bleota err size            固件过大
1042  bleota err unknown         BLE OTA 未知错

【本产品线请忽略】
1010～1047、1051、1060 起  应用层加密 BLE（未正式发布）
1007～1013                LoRaWAN（非 C3 Wi-Fi 主线）
1046  Error enablehttps!  仅 PRO HTTPS 开关
开关子码 51～53           SRS 通断器（未正式发布）

【无 code 的常见 msg】
illegal cmd / unsupported  命令不支持（有的固件只给 msg）
timeout                    客户端等待通知超时：未订阅 C305、设备重启、距离过远
""".strip()

HELP_TEXT_ZH = HELP_TEXT

HELP_TEXT_EN = r"""
======== Commands / abbreviations / errors (plaintext BLE · Wi-Fi C3) ========
GATT: service 0xA002   write 0xC303   read snapshot 0xC304   notify 0xC305
Factory BLE password 1234. Subscribe to C305 first, then cmd=pass. Unlock before business JSON.
Success: ok=true, no code. Failure: ok=false, with code; msg is English verbatim.

-------- Session --------
pass     write C303  {"cmd":"pass","pas":"1234","continue":true}
         success msg=Password Correct  event=pass
         fail Password Error / 1003; locked Please unlock / 1002 event=pas
         with continue:true later cmds need no pas; GATT Read C304 may repeat
         optional newpas<=16; optional auth<=40 phone binding
blepassword  write C303  {"cmd":"blepassword","old":"1234","new":"654321"}
         success Password yes; wrong old password Old Password Error / 1026
read     write C303  {"cmd":"read","continue":true}  success msg=ready
         then GATT Read C304. Locked read: Please unlock / 1002 event=read
resetauth  write C303  clear phone binding

-------- Wi-Fi provisioning (2.4 GHz only) --------
wifi     write C303  {"cmd":"wifi","ssid":"...","pass":"..."}  ssid/pass <=64
         success WIFI successfully (starts associating; not yet DHCP)
         missing fields Error wifi ssid/pass required! / 1018
         too long Error wifi length! / 1019
wifiscan write C303  success scan started; busy scan busy / 1043
getwifilist write C303  success d.list="ssid|rssi,..." max 10, RSSI desc
         not ready scan not ready / 1044

-------- Control --------
restart  write C303  restart received  GATT then drops; reconnect + pass
location write C303  location received  LED ~4 Hz for 15 s
reset    write C303  reset received  factory reset + reboot (danger)
zero     write C303  clear energy counters (irreversible)
deviceName write C303  {"cmd":"deviceName","name":"..."}  name<=30
         too long Error name length! / 1027

-------- Query --------
model    write C303  {"cmd":"model","type":1}  short keys below
getFunctionMap write C303  d.functionMap uint16, bits below
mqttdata write C303  topics TP/TC/TR/TM, MU/MPS; MF only if MQTT enabled
udpdata  write C303  UDP target list in d.udp_data
getInterval write C303  d.value WebSocket push ms (unsupported / unknow cmd if no WS)
getModbusTlsMuxSetupStatus  LAN-TLS models only; often unsupported on Basic / Lite

-------- LAN switches (change functionMap; recommend restart after) --------
enablehttp  {"cmd":"enablehttp","enable":true|false}  plain HTTP :80  http yes / http off
enablewebsocket  {"cmd":"enablewebsocket","enable":true}  optional enableTLS
enablemodbustcp  {"cmd":"enablemodbustcp","enable":true}
enabletls   {"cmd":"enabletls","enable":true}
enablehttps PRO / LAN-TLS models only; often unsupported on Basic
functionMap  {"cmd":"functionMap","value":int}  overwrites full map; use with care
         illegal combo functionMap error / 1014

-------- MQTT / UDP / Modbus / OTA --------
mqtt     {"cmd":"mqtt","data":"host|clientid|ssl|port|intervalSec|user|pass"}
mqtr     same, then reboot. empty data -> Error mqtt data empty! / 1021
topic1   {"cmd":"topic1","topic_post":"...","topic_set":"..."}
topic2   {"cmd":"topic2","topic_response":"...","topic_metadata":"..."}
modbus   {"cmd":"modbus","baud":9600,"parityStop":0,"address":1}
         parityStop 0=N81  1=E81  2=O81  3=N82
udp      add UDP target; full or bad IP/port -> UDP full / 1024
deleteudp delete; missing -> UDP not found / 1025
checkota  d.otastatus: 200 update / 404 latest / 199 low memory / other net (~8s)
otaprogress  progress, read-only
startota  start upgrade; optional reboot
setInterval  {"cmd":"setInterval","value":1000}  WebSocket push ms only (100-86400000)
cafilestart / cafiledata  MQTT TLS cert chunks

-------- functionMap bits (bit15 highest) --------
bit15 Modbus TCP     bit14 TLS (often with Modbus)
bit13 UDP            bit12 reserved
bit11 WebSocket      bit10 WebSocket TLS
bit9  MQTT           bit7  HTTP :80
bit5  LoRaWAN        others reserved
e.g. 128 = HTTP only; HTTP+MQTT = 640; 32896 = Modbus TCP + HTTP.
Test: functionMap & (1<<n) != 0

-------- model.d short keys --------
WN   Wi-Fi SSID
WPN  display name
MH   MQTT host (empty=unset)
MF   MQTT connected (boolean in model)
MP   MQTT port (0=unset)
MC   MQTT ClientId
MI   MQTT interval, milliseconds
MS   MQTT TLS
LSM  weak-signal mode 0/1
UI   UDP interval, ms
WI   WebSocket push interval, ms (may be absent)
TS   Modbus TLS mux 0-5 (may be absent)
MAD  485 address/baud/parity  e.g. "5 / 9600 / N81"

-------- Read characteristic C304 --------
IP    online=IPv4; offline=WiFi.status: -1 unknown 0 idle 1 SSID missing 3 assoc 4 fail 5 lost 6 disc
RSSI  router->meter downlink dBm
FW / SN / TP
Electrical values are decimal strings. Parse by key presence: single-phase V I P...; three-phase VX/VY/VZ...
Units: V / A / kW / kWh / Hz

-------- mqttdata.d.MF (when MQTT enabled) --------
-4 timeout  -3 lost  -2 TCP/TLS fail  -1 disconnected  0 connected
1 protocol rejected  2 ClientId rejected  3 broker unavailable  4 bad auth  5 unauthorized
If MQTT is off, MF may be absent (or some firmware still return -1).

======== Error codes (plaintext BLE, 1000-range) ========
Success has no code. Config failures often use 1000+subcode. Prefer msg over code.

[Common]
1000  auth error
1001  not authenticated
1002  Please unlock           (write path event=pas)
1003  Password Error          (factory 1234)
1004  No cmd / bad value
1005  No data / unsupported
1014  functionMap error
1015  unknow cmd              (spelling is intentional)
1018  Error wifi ssid/pass required!
1019  Error wifi length!
1021  Error mqtt data empty!
1024  UDP full                (full or invalid IP/port)
1025  UDP not found
1026  Old Password Error
1027  Error name length!
1043  scan busy
1044  scan not ready
1050  payload too large

[No code]
illegal cmd / unsupported / timeout
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
    6: "单相+开关（未发布）",
    7: "两路+开关（未发布）",
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
        return "No readings yet (click Read IP / meter)" if lang == "en" else "尚未读取电参（点「读 IP / 电参」）"
    lines = ["Meter readings (GATT Read C304):" if lang == "en" else "电参（GATT Read C304）："]
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
        lines.append("  Not queried yet. Use MQTT status or Refresh communication." if lang == "en" else "  尚未查询。点「MQTT 状态」或「刷新通讯配置」。")
    lines.append("")
    lines.append("[UDP]" if lang == "en" else "【UDP】")
    items = None
    if isinstance(udp, dict):
        items = udp.get("udp_data")
    elif isinstance(udp, list):
        items = udp
    if items is None:
        lines.append("  Not queried yet. Use UDP list or Refresh communication." if lang == "en" else "  尚未查询。点「UDP 列表」或「刷新通讯配置」。")
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
        "-1": "未知/刚配网",
        "0": "空闲",
        "1": "找不到 SSID",
        "3": "已关联（通常应显示 IPv4）",
        "4": "连接失败",
        "5": "连接丢失",
        "6": "已断开",
    }
    mapping_en = {
        "-1": "Unknown / just provisioned",
        "0": "Idle",
        "1": "SSID not found",
        "3": "Associated (usually becomes IPv4)",
        "4": "Connect failed",
        "5": "Connection lost",
        "6": "Disconnected",
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
    ("恢复出厂", "Factory reset", "reset"),
    ("启用 HTTP", "Enable HTTP", "enablehttp"),
    ("启用 ModbusTCP", "Enable Modbus TCP", "enablemodbustcp"),
    ("MQTT 状态", "MQTT status", "mqttdata"),
]


def one_click_buttons(lang: Lang = "zh") -> list[tuple[str, str]]:
    return [((en if lang == "en" else zh), cmd) for zh, en, cmd in ONE_CLICK]
