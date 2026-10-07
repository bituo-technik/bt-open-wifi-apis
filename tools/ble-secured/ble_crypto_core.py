#!/usr/bin/env python3
"""BLE 安全通道核心（Lite/Pro · 服务 A003）。

提炼自固件仓已验证的 test/ble/ble_secure_client.py 握手与 AES-CCM 流程。
协议事实以 assets/API/BLE_Crypto_API_Documentation.md 为准。
本模块供 ble_secured_gui.py 使用；不要打印完整 session_key / LTK（调试模式除外）。
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import ipaddress
import json
import re
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

try:
    from bleak import BleakClient
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency 'bleak'. Install with: pip install -r requirements.txt"
    ) from exc

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.ciphers.aead import AESCCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency 'cryptography'. Install with: pip install -r requirements.txt"
    ) from exc

try:
    from ecdsa import NIST256p, ellipticcurve
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Missing dependency 'ecdsa'. Install with: pip install -r requirements.txt"
    ) from exc


# Lite/Pro 加密通道 GATT（与明文 A002 互斥）
SERVICE_UUID = "0000a003-0000-1000-8000-00805f9b34fb"
READ_CHARACTERISTIC_UUID = "0000c314-0000-1000-8000-00805f9b34fb"
WRITE_CHARACTERISTIC_UUID = "0000c313-0000-1000-8000-00805f9b34fb"
NOTIFY_CHARACTERISTIC_UUID = "0000c315-0000-1000-8000-00805f9b34fb"

ROUND1_CHUNK_LEN = 220
PBKDF2_ITERATIONS = 10000
PIN_DERIVED_LEN = 32
SESSION_KEY_LEN = 16
SESSION_NONCE_LEN = 8
CCM_NONCE_LEN = 12
CCM_TAG_LEN = 8
ADV_CCM_TAG_LEN = 4
ADV_PLAIN_LEN = 15
ADV_MFG_PAYLOAD_LEN = 26
ADV_COMPANY_ID = 0xFFFF
WIFI_LINK_UNKNOWN = -1
PROTOCOL_VERSION_FALLBACK = "BT_Crypto_V1"
GROUP_TLS_NAMED_CURVE_SECP256R1 = b"\x03\x00\x17"

CURVE = NIST256p.curve
GENERATOR = NIST256p.generator
ORDER = NIST256p.order
INFINITY = ellipticcurve.INFINITY


class ProtocolError(RuntimeError):
    pass


def _json_dumps(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def _u32be(value: int) -> bytes:
    return value.to_bytes(4, "big")


def _hex(data: bytes) -> str:
    return data.hex()


def _bytes_from_hex(value: str) -> bytes:
    return bytes.fromhex(value)


def _minimal_int_bytes(value: int) -> bytes:
    if value == 0:
        return b"\x00"
    length = (value.bit_length() + 7) // 8
    return value.to_bytes(length, "big")


def _as_affine(point: Any) -> Any:
    if point == INFINITY:
        return point
    if hasattr(point, "to_affine"):
        return point.to_affine()
    return point


def _point_add(*points: Any) -> Any:
    acc = None
    for point in points:
        point = _as_affine(point)
        if point == INFINITY:
            continue
        acc = point if acc is None else _as_affine(acc + point)
    return INFINITY if acc is None else _as_affine(acc)


def _point_mul(scalar: int, point: Any) -> Any:
    scalar %= ORDER
    if scalar == 0:
        return INFINITY
    return _as_affine(_as_affine(point) * scalar)


def _point_neg(point: Any) -> Any:
    point = _as_affine(point)
    if point == INFINITY:
        return point
    return ellipticcurve.Point(CURVE, point.x(), (-point.y()) % CURVE.p(), ORDER)


def _point_sub(left: Any, right: Any) -> Any:
    return _point_add(left, _point_neg(right))


def _point_equal(left: Any, right: Any) -> bool:
    left = _as_affine(left)
    right = _as_affine(right)
    if left == INFINITY or right == INFINITY:
        return left == right
    return left.x() == right.x() and left.y() == right.y()


def _point_to_raw(point: Any) -> bytes:
    point = _as_affine(point)
    if point == INFINITY:
        raise ProtocolError("point at infinity is not serializable")
    return b"\x04" + point.x().to_bytes(32, "big") + point.y().to_bytes(32, "big")


def _tls_write_point(point: Any) -> bytes:
    raw = _point_to_raw(point)
    if len(raw) > 255:
        raise ProtocolError("unexpected point length")
    return bytes([len(raw)]) + raw


def _read_exact(buf: bytes, offset: int, length: int) -> tuple[bytes, int]:
    end = offset + length
    if end > len(buf):
        raise ProtocolError("buffer too short")
    return buf[offset:end], end


def _tls_read_point(buf: bytes, offset: int) -> tuple[Any, int]:
    point_len_bytes, offset = _read_exact(buf, offset, 1)
    point_len = point_len_bytes[0]
    raw, offset = _read_exact(buf, offset, point_len)
    if len(raw) != 65 or raw[0] != 0x04:
        raise ProtocolError("invalid EC point encoding")
    x = int.from_bytes(raw[1:33], "big")
    y = int.from_bytes(raw[33:65], "big")
    if not CURVE.contains_point(x, y):
        raise ProtocolError("point is not on secp256r1")
    return ellipticcurve.Point(CURVE, x, y, ORDER), offset


def _ecjpake_hash(generator_point: Any, v_point: Any, x_point: Any, identity: str, secret_int: Optional[int] = None) -> int:
    g_raw = _point_to_raw(generator_point)
    v_raw = _point_to_raw(v_point)
    x_raw = _point_to_raw(x_point)
    ident = identity.encode("ascii")
    payload = (
        len(g_raw).to_bytes(4, "big")
        + g_raw
        + len(v_raw).to_bytes(4, "big")
        + v_raw
        + len(x_raw).to_bytes(4, "big")
        + x_raw
        + len(ident).to_bytes(4, "big")
        + ident
    )
    # 将 PIN 派生的 secret 追加到 hash 输入中，使 ZKP 与密码绑定
    if secret_int is not None and secret_int != 0:
        secret_bytes = _minimal_int_bytes(secret_int)
        payload += len(secret_bytes).to_bytes(4, "big") + secret_bytes
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest, "big") % ORDER


def _zkp_write(generator_point: Any, secret_scalar: int, public_point: Any, identity: str, secret_int: Optional[int] = None) -> bytes:
    for _ in range(8):
        v = secrets.randbelow(ORDER - 1) + 1
        v_point = _point_mul(v, generator_point)
        h = _ecjpake_hash(generator_point, v_point, public_point, identity, secret_int)
        r = (v - (secret_scalar * h)) % ORDER
        r_bytes = _minimal_int_bytes(r)
        if len(r_bytes) <= 255:
            return _tls_write_point(v_point) + bytes([len(r_bytes)]) + r_bytes
    raise ProtocolError("failed to generate Schnorr proof")


def _zkp_read(
    generator_point: Any,
    public_point: Any,
    identity: str,
    buf: bytes,
    offset: int,
    secret_int: Optional[int] = None,
) -> int:
    v_point, offset = _tls_read_point(buf, offset)
    r_len_raw, offset = _read_exact(buf, offset, 1)
    r_len = r_len_raw[0]
    if r_len == 0:
        raise ProtocolError("invalid Schnorr proof length")
    r_bytes, offset = _read_exact(buf, offset, r_len)
    r = int.from_bytes(r_bytes, "big")
    h = _ecjpake_hash(generator_point, v_point, public_point, identity, secret_int)
    vv = _point_add(_point_mul(h, public_point), _point_mul(r, generator_point))
    if not _point_equal(vv, v_point):
        raise ProtocolError("Schnorr proof verification failed")
    return offset


def _kkp_write(generator_point: Any, secret_scalar: int, public_point: Any, identity: str, secret_int: Optional[int] = None) -> bytes:
    return _tls_write_point(public_point) + _zkp_write(generator_point, secret_scalar, public_point, identity, secret_int)


def _kkp_read(generator_point: Any, identity: str, buf: bytes, offset: int, secret_int: Optional[int] = None) -> tuple[Any, int]:
    public_point, offset = _tls_read_point(buf, offset)
    if public_point == INFINITY:
        raise ProtocolError("peer public point is infinity")
    offset = _zkp_read(generator_point, public_point, identity, buf, offset, secret_int)
    return public_point, offset


class EcJpakeClient:
    def __init__(self, secret_material: bytes) -> None:
        self._secret_int = int.from_bytes(secret_material, "big")
        self._x1: Optional[int] = None
        self._x2: Optional[int] = None
        self._X1: Any = None
        self._X2: Any = None
        self._X3: Any = None
        self._X4: Any = None
        self._Xs: Any = None

    def write_round1(self) -> bytes:
        self._x1 = secrets.randbelow(ORDER - 1) + 1
        self._x2 = secrets.randbelow(ORDER - 1) + 1
        self._X1 = _point_mul(self._x1, GENERATOR)
        self._X2 = _point_mul(self._x2, GENERATOR)
        return _kkp_write(GENERATOR, self._x1, self._X1, "client", self._secret_int) + _kkp_write(
            GENERATOR, self._x2, self._X2, "client", self._secret_int
        )

    def read_round1(self, payload: bytes) -> None:
        offset = 0
        self._X3, offset = _kkp_read(GENERATOR, "server", payload, offset, self._secret_int)
        self._X4, offset = _kkp_read(GENERATOR, "server", payload, offset, self._secret_int)
        if offset != len(payload):
            raise ProtocolError("extra bytes found in round1 payload")

    def write_round2(self) -> bytes:
        if None in (self._x1, self._x2, self._X1, self._X3, self._X4):
            raise ProtocolError("round1 must complete before round2")
        ga = _point_add(self._X1, self._X3, self._X4)
        xc = (self._x2 * self._secret_int) % ORDER
        xc_point = _point_mul(xc, ga)
        return _kkp_write(ga, xc, xc_point, "client", self._secret_int)

    def read_round2(self, payload: bytes) -> None:
        if None in (self._X1, self._X2, self._X3):
            raise ProtocolError("round1 state is incomplete")
        offset = 0
        group_bytes, offset = _read_exact(payload, offset, len(GROUP_TLS_NAMED_CURVE_SECP256R1))
        if group_bytes != GROUP_TLS_NAMED_CURVE_SECP256R1:
            raise ProtocolError("unexpected EC group in server round2")
        gb = _point_add(self._X1, self._X2, self._X3)
        self._Xs, offset = _kkp_read(gb, "server", payload, offset, self._secret_int)
        if offset != len(payload):
            raise ProtocolError("extra bytes found in round2 payload")

    def derive_shared_key(self) -> bytes:
        if None in (self._x2, self._X4, self._Xs):
            raise ProtocolError("round2 must complete before shared key derivation")
        x2s = (self._x2 * self._secret_int) % ORDER
        k_point = _point_mul(self._x2, _point_sub(self._Xs, _point_mul(x2s, self._X4)))
        k_point = _as_affine(k_point)
        if k_point == INFINITY:
            raise ProtocolError("derived shared point is infinity")
        return hashlib.sha256(k_point.x().to_bytes(32, "big")).digest()



def pin_from_manual_pairing_code(code11: str) -> str:
    """Matter 11-digit manual pairing code → 8-digit setup PIN (Verhoeff-checked).

    Also accepts an already-decoded 8-digit PIN.
    """
    s = "".join(ch for ch in str(code11 or "") if ch.isdigit())
    if len(s) == 8:
        return s
    if len(s) != 11:
        raise ProtocolError("pairing code must be 11 digits (or 8-digit PIN)")
    body, check = s[:10], s[10]
    if _verhoeff_check_digit(body) != check:
        raise ProtocolError("pairing code checksum invalid")
    middle = int(body[1:6])
    end = int(body[6:10])
    pin = ((end << 14) | (middle & 0x3FFF)) & 0x7FFFFFF
    if pin < 1 or pin > 99999998:
        raise ProtocolError("decoded PIN out of range")
    return f"{pin:08d}"


def _verhoeff_check_digit(num: str) -> str:
    d = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
        [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
        [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
        [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
        [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
        [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
        [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
        [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
        [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
    ]
    p = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
        [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
        [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
        [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
        [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
        [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
        [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
        [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
    ]
    inv = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]
    c = 0
    for i, ch in enumerate(reversed(num)):
        c = d[c][p[(i + 1) % 8][int(ch)]]
    return str(inv[c])


def derive_pin_key(pin: str, sn: str, version: str) -> bytes:
    if len(pin) != 8 or not pin.isdigit():
        raise ProtocolError("PIN must be exactly 8 digits")
    salt = f"{sn}{version}PBKDF2".encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", pin.encode("ascii"), salt, PBKDF2_ITERATIONS, PIN_DERIVED_LEN)


def hkdf_sha256(ikm: bytes, length: int, info: bytes, salt: Optional[bytes] = None) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def derive_ltk(shared_key: bytes, device_nonce: bytes, client_nonce: bytes, sn: str, version: str) -> bytes:
    salt = device_nonce + client_nonce
    info = f"{sn}{version}LTK".encode("utf-8")
    return hkdf_sha256(shared_key, SESSION_KEY_LEN, info, salt)


def derive_session_key(ltk: bytes, device_nonce: bytes, client_nonce: bytes, sn: str, version: str) -> bytes:
    salt = device_nonce + client_nonce
    info = f"{sn}{version}session".encode("utf-8")
    return hkdf_sha256(ltk, SESSION_KEY_LEN, info, salt)


def derive_broadcast_key(ltk: bytes, device_nonce: bytes, client_nonce: bytes, sn: str, version: str) -> bytes:
    """§3.5.1：与 LTK 相同 salt，info 后缀为 broadcast。"""
    salt = device_nonce + client_nonce
    info = f"{sn}{version}broadcast".encode("utf-8")
    return hkdf_sha256(ltk, SESSION_KEY_LEN, info, salt)


def sn_eid_to_uint48(sn: str) -> int:
    """设备 eID：12 位 hex → 48 bit（与固件 eidHexToUint48 一致）。"""
    s = sn.strip()
    if len(s) != 12 or not re.fullmatch(r"[0-9A-Fa-f]{12}", s):
        return 0
    return int(s, 16) & 0xFFFFFFFFFFFF


def expected_short_discriminator_12(sn: str) -> int:
    v48 = sn_eid_to_uint48(sn)
    return (v48 >> 36) & 0xFFF


def extract_manufacturer_blob(manufacturer_data: dict[int, bytes]) -> Optional[tuple[str, bytes]]:
    """
    从扫描结果取出厂商数据。
    NimBLE setManufacturerData 常见为 Company ID 0xFFFF；Bleak 的 value 可能不含前两字节 FF FF。
    """
    if not manufacturer_data:
        return None
    raw: Optional[bytes] = manufacturer_data.get(ADV_COMPANY_ID)
    if raw is None and len(manufacturer_data) == 1:
        raw = next(iter(manufacturer_data.values()))
    if raw is None:
        return None
    if len(raw) == ADV_MFG_PAYLOAD_LEN and raw[0:2] == b"\xff\xff":
        return ("long26", raw)
    if len(raw) == ADV_MFG_PAYLOAD_LEN - 2:
        return ("long26", b"\xff\xff" + raw)
    if len(raw) == 5 and raw[0:2] == b"\xff\xff":
        return ("short5", raw)
    if len(raw) == 3:
        return ("short5", b"\xff\xff" + raw)
    if len(raw) > 0:
        return ("unknown", raw)
    return None


def _normalize_ble_address(addr: str) -> str:
    """小写并去掉冒号/横线，便于比较「无冒号 MAC」与 Bleak 返回地址。"""
    return addr.lower().replace(":", "").replace("-", "").replace(" ", "")


def discover_result_to_device_adv_pairs(discovered: Any) -> list[tuple[Any, Any]]:
    """
    BleakScanner.discover(return_adv=True) 在不同 bleak 版本可能返回:
    - dict[address, (BLEDevice, AdvertisementData)]  （当前常见）
    - list[(BLEDevice, AdvertisementData)]
    若误对 dict 做 for x in discovered，x 会是 str，导致 AttributeError。
    """
    pairs: list[tuple[Any, Any]] = []
    if discovered is None:
        return pairs
    if isinstance(discovered, dict):
        for _addr_key, entry in discovered.items():
            if isinstance(entry, tuple) and len(entry) >= 2:
                pairs.append((entry[0], entry[1]))
            elif entry is not None:
                pairs.append((entry, None))
        return pairs
    for x in discovered:
        if isinstance(x, tuple) and len(x) >= 2:
            pairs.append((x[0], x[1]))
        else:
            pairs.append((x, None))
    return pairs


def ble_identifier_matches_device(device_addr: str, device_name: str, needle: str) -> bool:
    """--device 为地址子串、无冒号 MAC、或名称子串时匹配。"""
    n = needle.lower()
    addr_l = device_addr.lower()
    name_l = (device_name or "").lower()
    if n in addr_l or (device_name and n in name_l):
        return True
    need_hex = _normalize_ble_address(n)
    addr_hex = _normalize_ble_address(device_addr)
    if need_hex and need_hex == addr_hex:
        return True
    if need_hex and len(need_hex) >= 6 and need_hex in addr_hex:
        return True
    return False


# 固件 CUSTOM_ID==1 时广播名: Pulse-<12位hex eID>，例如 Pulse-85EAF5DBC964
PULSE_SN_BLE_NAME_RE = re.compile(r"^Pulse-([0-9A-Fa-f]{12})$", re.IGNORECASE)


def is_pulse_sn_ble_name(name: Optional[str]) -> bool:
    if not name:
        return False
    return PULSE_SN_BLE_NAME_RE.match(name.strip()) is not None


def sn_from_pulse_sn_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    match = PULSE_SN_BLE_NAME_RE.match(name.strip())
    return match.group(1).upper() if match else None


def verify_short_broadcast(blob5: bytes, sn: str, log: Any = print) -> bool:
    """step0 短包：FF FF + 状态字节 + 12bit 鉴别器（小端 16 位低 12 位）。"""
    if len(blob5) != 5 or blob5[0:2] != b"\xff\xff":
        log("[ADV] 短包长度或前缀不符")
        return False
    state_b = blob5[2]
    disc = int.from_bytes(blob5[3:5], "little") & 0x0FFF
    exp = expected_short_discriminator_12(sn)
    log(f"[ADV] 短包 state={state_b} disc=0x{disc:03x} 期望(由SN)={exp:03x}")
    if disc != exp:
        log("[ADV] 警告：鉴别器与 SN 推导不一致（仍可能为其它字段定义或扫描合并差异）")
        return False
    log("[ADV] 短包鉴别器与 SN 一致")
    return True


def decrypt_long_manufacturer(blob26: bytes, broadcast_key: bytes, log: Any = print) -> bytes:
    """26 字节长包：§9.3，CCM tag=4。"""
    if len(blob26) != ADV_MFG_PAYLOAD_LEN or blob26[0:2] != b"\xff\xff":
        raise ProtocolError("长广播长度或前缀错误")
    ctr = int.from_bytes(blob26[3:7], "little")
    nonce = bytes(8) + ctr.to_bytes(4, "big")
    ct = blob26[7 : 7 + ADV_PLAIN_LEN]
    tag = blob26[7 + ADV_PLAIN_LEN : ADV_MFG_PAYLOAD_LEN]
    log(f"[ADV] 长包 counter(LE)={ctr} ctrl=0x{blob26[2]:02x} nonce12={nonce.hex()}")
    aes = AESCCM(broadcast_key, tag_length=ADV_CCM_TAG_LEN)
    plain = aes.decrypt(nonce, ct + tag, None)
    log(f"[ADV] 长包明文15字节 hex={plain.hex()}")
    return plain


def _int24_le(b0: int, b1: int, b2: int) -> int:
    raw = b0 | (b1 << 8) | (b2 << 16)
    if raw & 0x800000:
        raw -= 0x1000000
    return raw


def parse_long_adv_fields(ctrl: int, plain15: bytes) -> dict[str, Any]:
    """§9.3.1 明文 15 字节 → 可读字段（含相位槽）。"""
    if len(plain15) != ADV_PLAIN_LEN:
        raise ProtocolError("adv plaintext must be 15 bytes")
    product = ctrl & 0x03
    phase = (ctrl >> 2) & 0x03
    version = (ctrl >> 4) & 0x07
    gatt_up = bool(ctrl & 0x80)
    phase_name = {0: "A/L1", 1: "B/L2", 2: "C"}.get(phase, str(phase))
    product_name = {0: "other", 1: "1P", 2: "2ch", 3: "3P"}.get(product, str(product))
    v = int.from_bytes(plain15[0:2], "little") / 10.0
    i_a = int.from_bytes(plain15[2:4], "little") / 100.0
    p_kw = _int24_le(plain15[4], plain15[5], plain15[6]) / 1000.0
    fe = int.from_bytes(plain15[7:11], "little") / 100.0
    re_e = int.from_bytes(plain15[11:15], "little") / 100.0
    return {
        "ctrl": ctrl,
        "version": version,
        "gatt_installed": gatt_up,
        "product": product_name,
        "phase": phase_name,
        "phase_idx": phase,
        "V": round(v, 1),
        "I": round(i_a, 3),
        "P": round(p_kw, 3),
        "FE": round(fe, 2),
        "RE": round(re_e, 2),
    }


def classify_ble_read_ip_field(ip_field: Any) -> tuple[str, Optional[str], Any]:
    """
    与固件 onRead：已连返回 IPv4 字符串；未连返回 wifiLastLinkStatus。
    返回 (state, ip_or_none, raw)。state: connected | disconnected | wifi_status
    """
    raw = ip_field
    if raw is None:
        return ("disconnected", None, raw)
    if isinstance(raw, bool):
        return ("wifi_status", None, raw)
    if isinstance(raw, (int, float)):
        n = int(raw)
        if n == WIFI_LINK_UNKNOWN:
            return ("disconnected", None, raw)
        return ("wifi_status", None, raw)
    s = str(raw).strip()
    if s in ("", "null", "None"):
        return ("disconnected", None, raw)
    if s == "-1" or s == str(WIFI_LINK_UNKNOWN):
        return ("disconnected", None, raw)
    try:
        ipo = ipaddress.ip_address(s)
        if ipo.version == 4:
            if ipo.is_unspecified or str(ipo) == "0.0.0.0":
                return ("disconnected", None, raw)
            return ("connected", str(ipo), raw)
    except ValueError:
        pass
    try:
        int(float(s))
        return ("wifi_status", None, raw)
    except (TypeError, ValueError):
        return ("wifi_status", None, raw)



def extract_ip_field_from_read_doc(doc: dict[str, Any]) -> Any:
    ip = doc.get("IP")
    if ip is not None:
        return ip
    d = doc.get("d")
    if isinstance(d, dict):
        return d.get("IP")
    return None


def derive_nonce_base(first: bytes, second: bytes, label: str) -> bytes:
    return hkdf_sha256(first + second, CCM_NONCE_LEN - 4, label.encode("ascii"), None)


@dataclass
class SessionState:
    protocol_version: str
    sn: str
    client_nonce: bytes
    device_nonce: bytes
    ltk: bytes
    session_key: bytes
    tx_nonce_base: bytes
    rx_nonce_base: bytes
    broadcast_key: Optional[bytes] = None
    tx_counter: int = 1
    rx_counter: int = 0


class CacheStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"devices": {}}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"cache file is invalid JSON: {self.path}") from exc

    def save(self, data: dict[str, Any]) -> None:
        self.path.write_text(_json_dumps(data), encoding="utf-8")

    def load_device(self, sn: str) -> Optional[dict[str, Any]]:
        return self.load().get("devices", {}).get(sn)

    def save_device(
        self,
        sn: str,
        protocol_version: str,
        ltk: bytes,
        address: Optional[str],
        broadcast_key: Optional[bytes] = None,
    ) -> None:
        data = self.load()
        devices = data.setdefault("devices", {})
        entry: dict[str, Any] = {
            "protocol_version": protocol_version,
            "ltk_hex": ltk.hex(),
            "address": address or "",
        }
        if broadcast_key is not None:
            entry["broadcast_key_hex"] = broadcast_key.hex()
        devices[sn] = entry
        self.save(data)


class BleSecureClient:
    def __init__(
        self,
        client: BleakClient,
        sn: str,
        cache: CacheStore,
        log: Optional[Callable[[str], None]] = None,
        *,
        debug_keys: bool = False,
    ) -> None:
        self.client = client
        self.sn = sn
        self.cache = cache
        self._log = log or (lambda _m: None)
        self.debug_keys = debug_keys
        self.notifications: asyncio.Queue[str] = asyncio.Queue()
        self.session: Optional[SessionState] = None

    def _notification_callback(self, _: Any, data: bytearray) -> None:
        text = bytes(data).decode("utf-8", errors="strict")
        self._log(f"[RX] {text}")
        self.notifications.put_nowait(text)

    async def start(self) -> None:
        await self.client.start_notify(NOTIFY_CHARACTERISTIC_UUID, self._notification_callback)

    async def stop(self) -> None:
        if not self.client.is_connected:
            return
        try:
            await self.client.stop_notify(NOTIFY_CHARACTERISTIC_UUID)
        except Exception:
            pass

    async def _write_text(self, text: str) -> None:
        self._log(f"[TX] {text}")
        await self.client.write_gatt_char(WRITE_CHARACTERISTIC_UUID, text.encode("utf-8"), response=True)

    async def _write_json(self, payload: dict[str, Any]) -> None:
        await self._write_text(_json_dumps(payload))

    def _drain_notifications(self) -> None:
        while not self.notifications.empty():
            self.notifications.get_nowait()

    async def _wait_raw_notification(self, timeout: float) -> str:
        return await asyncio.wait_for(self.notifications.get(), timeout)

    def _parse_json(self, text: str) -> dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"invalid JSON from device: {text}") from exc

    def _decrypt_envelope(self, envelope: dict[str, Any]) -> dict[str, Any]:
        if self.session is None:
            raise ProtocolError("secure session is not ready")
        for key in ("nonce", "ct", "tag"):
            if key not in envelope:
                raise ProtocolError(f"missing secure envelope field: {key}")
        nonce_counter = int(envelope["nonce"])
        if nonce_counter <= self.session.rx_counter:
            raise ProtocolError(f"replay detected: rx_counter={self.session.rx_counter}, incoming={nonce_counter}")
        nonce = self.session.rx_nonce_base + _u32be(nonce_counter)
        try:
            ct = base64.b64decode(str(envelope["ct"]).strip())
            tag = base64.b64decode(str(envelope["tag"]).strip())
        except (binascii.Error, ValueError) as exc:
            raise ProtocolError("invalid base64 in secure envelope ct/tag") from exc
        aes = AESCCM(self.session.session_key, tag_length=CCM_TAG_LEN)
        plain = aes.decrypt(nonce, ct + tag, None)
        self.session.rx_counter = nonce_counter
        return self._parse_json(plain.decode("utf-8"))

    def _encrypt_envelope(self, plaintext_json: dict[str, Any]) -> dict[str, Any]:
        if self.session is None:
            raise ProtocolError("secure session is not ready")
        plain = _json_dumps(plaintext_json).encode("utf-8")
        nonce = self.session.tx_nonce_base + _u32be(self.session.tx_counter)
        aes = AESCCM(self.session.session_key, tag_length=CCM_TAG_LEN)
        blob = aes.encrypt(nonce, plain, None)
        ct = blob[:-CCM_TAG_LEN]
        tag = blob[-CCM_TAG_LEN:]
        envelope = {
            "nonce": self.session.tx_counter,
            "ct": base64.b64encode(ct).decode("ascii"),
            "tag": base64.b64encode(tag).decode("ascii"),
        }
        self.session.tx_counter += 1
        return envelope

    async def wait_for_event(self, event_name: str, timeout: float = 10.0, allow_encrypted: bool = True) -> dict[str, Any]:
        while True:
            raw = await self._wait_raw_notification(timeout)
            doc = self._parse_json(raw)
            if allow_encrypted and {"nonce", "ct", "tag"}.issubset(doc.keys()):
                doc = self._decrypt_envelope(doc)
            # 固件对解密/信封错误用 event "secure"，与业务 cmd（如 model）不一致；否则会被 continue 丢掉导致超时
            if doc.get("event") == "secure" and not doc.get("ok", True):
                return doc
            if doc.get("event") != event_name:
                continue
            return doc

    async def get_protocol_version(self) -> tuple[str, int]:
        self._drain_notifications()
        await self._write_json({"cmd": "ble-crypto-ver"})
        response = await self.wait_for_event("ble-crypto-ver", allow_encrypted=False)
        if not response.get("ok", False):
            raise ProtocolError(f"ble-crypto-ver failed: {response.get('msg', '')}")
        data = response.get("d") or {}
        version = str(data.get("ver") or PROTOCOL_VERSION_FALLBACK)
        step = int(data.get("step", 0))
        return version, step

    async def reset_handshake(self) -> dict[str, Any]:
        """Plaintext ble-crypto-reset (only valid at step 0 or 1)."""
        self._drain_notifications()
        await self._write_json({"cmd": "ble-crypto-reset"})
        return await self.wait_for_event("ble-crypto-reset", allow_encrypted=False)

    async def _send_round1(self, client_nonce_hex: str, client_round1_b64: str) -> tuple[str, str]:
        if len(client_round1_b64) <= ROUND1_CHUNK_LEN:
            self._drain_notifications()
            await self._write_json(
                {
                    "cmd": "ble-crypto-jpake-round1",
                    "client_nonce": client_nonce_hex,
                    "client_round1": client_round1_b64,
                }
            )
        else:
            parts = [
                client_round1_b64[i : i + ROUND1_CHUNK_LEN]
                for i in range(0, len(client_round1_b64), ROUND1_CHUNK_LEN)
            ]
            total = len(parts)
            self._drain_notifications()
            for idx, part in enumerate(parts):
                await self._write_json(
                    {
                        "cmd": "ble-crypto-jpake-round1",
                        "client_nonce": client_nonce_hex,
                        "part_idx": idx,
                        "part_total": total,
                        "client_round1_part": part,
                    }
                )
                if idx + 1 < total:
                    response = await self.wait_for_event("ble-crypto-jpake-round1", allow_encrypted=False)
                    if not response.get("ok", False):
                        raise ProtocolError(f"round1 upload failed: {response.get('msg', '')}")
                    data = response.get("d") or {}
                    if data.get("status") != "continue":
                        raise ProtocolError(f"unexpected round1 chunk ack: {response}")

        first = await self.wait_for_event("ble-crypto-jpake-round1", allow_encrypted=False)
        if not first.get("ok", False):
            raise ProtocolError(f"round1 failed: {first.get('msg', '')}")
        data = first.get("d") or {}
        device_nonce = str(data.get("device_nonce") or "")
        if not device_nonce:
            raise ProtocolError("device_nonce missing in round1 response")
        if "server_round1" in data:
            return device_nonce, str(data["server_round1"])

        if "server_round1_part" not in data:
            raise ProtocolError(f"unexpected round1 response: {first}")

        parts: dict[int, str] = {}
        part_idx = int(data.get("part_idx", 0))
        parts[part_idx] = str(data["server_round1_part"])
        total = int(data.get("part_total", 0))
        if total <= 0:
            raise ProtocolError("invalid round1 total chunk count")

        done = bool(data.get("done", False))
        while len(parts) < total:
            await self._write_json(
                {
                    "cmd": "ble-crypto-jpake-round1",
                    "client_nonce": client_nonce_hex,
                    "fetch_next": True,
                }
            )
            chunk = await self.wait_for_event("ble-crypto-jpake-round1", allow_encrypted=False)
            if not chunk.get("ok", False):
                raise ProtocolError(f"round1 chunk receive failed: {chunk.get('msg', '')}")
            data = chunk.get("d") or {}
            if str(data.get("device_nonce") or "") != device_nonce:
                raise ProtocolError("device_nonce changed across round1 chunks")
            part_idx = int(data.get("part_idx", -1))
            if part_idx < 0 or "server_round1_part" not in data:
                raise ProtocolError(f"invalid round1 chunk: {chunk}")
            chunk_total = int(data.get("part_total", total))
            if chunk_total != total:
                raise ProtocolError(f"round1 total chunk count changed: expected {total}, got {chunk_total}")
            parts[part_idx] = str(data["server_round1_part"])
            done = bool(data.get("done", False))
            if done and len(parts) >= total:
                break
        missing = [idx for idx in range(total) if idx not in parts]
        if missing:
            raise ProtocolError(f"round1 chunks missing: {missing}")
        assembled = "".join(parts[idx] for idx in range(total))
        return device_nonce, assembled

    async def full_handshake(self, pin: str, protocol_version: str) -> SessionState:
        pin_key = derive_pin_key(pin, self.sn, protocol_version)
        jpake = EcJpakeClient(pin_key)
        client_nonce = secrets.token_bytes(SESSION_NONCE_LEN)
        client_round1_b64 = base64.b64encode(jpake.write_round1()).decode("ascii")

        device_nonce_hex, server_round1_b64 = await self._send_round1(client_nonce.hex(), client_round1_b64)
        jpake.read_round1(base64.b64decode(server_round1_b64))

        client_round2_b64 = base64.b64encode(jpake.write_round2()).decode("ascii")
        self._drain_notifications()
        await self._write_json({"cmd": "ble-crypto-jpake-round2", "client_round2": client_round2_b64})
        response = await self.wait_for_event("ble-crypto-jpake-round2", allow_encrypted=False)
        if not response.get("ok", False):
            raise ProtocolError(f"round2 failed: {response.get('msg', '')}")
        server_round2_b64 = str((response.get("d") or {}).get("server_round2") or "")
        if not server_round2_b64:
            raise ProtocolError("server_round2 missing")
        jpake.read_round2(base64.b64decode(server_round2_b64))

        device_nonce = _bytes_from_hex(device_nonce_hex)
        shared_key = jpake.derive_shared_key()
        ltk = derive_ltk(shared_key, device_nonce, client_nonce, self.sn, protocol_version)
        session_key = derive_session_key(ltk, device_nonce, client_nonce, self.sn, protocol_version)
        broadcast_key = derive_broadcast_key(ltk, device_nonce, client_nonce, self.sn, protocol_version)
        tx_nonce_base = derive_nonce_base(client_nonce, device_nonce, "ccm-rx-nonce")
        rx_nonce_base = derive_nonce_base(device_nonce, client_nonce, "ccm-tx-nonce")

        state = SessionState(
            protocol_version=protocol_version,
            sn=self.sn,
            client_nonce=client_nonce,
            device_nonce=device_nonce,
            ltk=ltk,
            session_key=session_key,
            tx_nonce_base=tx_nonce_base,
            rx_nonce_base=rx_nonce_base,
            broadcast_key=broadcast_key,
        )
        self.session = state
        self.cache.save_device(self.sn, protocol_version, ltk, self.client.address, broadcast_key)
        return state

    async def resume_from_ltk(self, protocol_version: str, ltk: bytes) -> SessionState:
        client_nonce = secrets.token_bytes(SESSION_NONCE_LEN)
        self._drain_notifications()
        await self._write_json({"cmd": "ble-crypto-session-nonce", "client_nonce": client_nonce.hex()})
        response = await self.wait_for_event("ble-crypto-session-nonce", allow_encrypted=False)
        if not response.get("ok", False):
            raise ProtocolError(f"session resume failed: {response.get('msg', '')}")
        device_nonce_hex = str((response.get("d") or {}).get("device_nonce") or "")
        if not device_nonce_hex:
            raise ProtocolError("device_nonce missing in session resume")
        device_nonce = _bytes_from_hex(device_nonce_hex)
        session_key = derive_session_key(ltk, device_nonce, client_nonce, self.sn, protocol_version)
        tx_nonce_base = derive_nonce_base(client_nonce, device_nonce, "ccm-rx-nonce")
        rx_nonce_base = derive_nonce_base(device_nonce, client_nonce, "ccm-tx-nonce")
        cached = self.cache.load_device(self.sn) or {}
        bkey: Optional[bytes] = None
        bh = str(cached.get("broadcast_key_hex") or "")
        if len(bh) == SESSION_KEY_LEN * 2:
            try:
                bkey = bytes.fromhex(bh)
            except ValueError:
                bkey = None
        state = SessionState(
            protocol_version=protocol_version,
            sn=self.sn,
            client_nonce=client_nonce,
            device_nonce=device_nonce,
            ltk=ltk,
            session_key=session_key,
            tx_nonce_base=tx_nonce_base,
            rx_nonce_base=rx_nonce_base,
            broadcast_key=bkey,
        )
        self.session = state
        return state

    async def open_secure_channel(self, pin: Optional[str], ltk_hex_arg: Optional[str] = None) -> SessionState:
        protocol_version, step = await self.get_protocol_version()
        if step == 0:
            if not pin:
                raise ProtocolError("device requires full J-PAKE handshake, but --pin was not provided")
            return await self.full_handshake(pin, protocol_version)
        if step == 2:
            if ltk_hex_arg:
                ltk = parse_ltk_hex(ltk_hex_arg)
                return await self.resume_from_ltk(protocol_version, ltk)
            cached = self.cache.load_device(self.sn)
            if not cached:
                raise ProtocolError(
                    f"device is waiting for session resume (step=2), but no cached LTK for SN {self.sn}. "
                    "Pass --ltk <64_hex_chars> or use --cache-file with a saved device entry."
                )
            ltk_hex = str(cached.get("ltk_hex") or "")
            if len(ltk_hex) != SESSION_KEY_LEN * 2:
                raise ProtocolError("cached LTK length is invalid")
            return await self.resume_from_ltk(protocol_version, _bytes_from_hex(ltk_hex))
        if step == 1:
            raise ProtocolError("device is mid-handshake; send ble-crypto-reset or reconnect")
        if step == 3:
            if self.session is not None:
                return self.session
            raise ProtocolError(
                "device is already step=3 on this GATT link, but this client has no session keys; "
                "disconnect and reconnect instead of repeating handshake"
            )
        raise ProtocolError(f"unsupported protocol step: {step}")

    async def send_secure_command(
        self,
        payload: dict[str, Any],
        expected_event: Optional[str] = None,
        timeout: float = 20.0,
        *,
        raise_on_fail: bool = False,
    ) -> dict[str, Any]:
        if self.session is None:
            raise ProtocolError("secure session is not ready (handshake first)")
        self._drain_notifications()
        self._log(f"[TX secure plain] {_json_dumps(payload)}")
        envelope = self._encrypt_envelope(payload)
        await self._write_json(envelope)
        try:
            response = await self.wait_for_event(
                expected_event or str(payload.get("cmd") or "secure"),
                timeout=timeout,
            )
        except Exception as exc:
            self._log(f"等待加密应答超时/失败: {exc}")
            return {"ok": False, "msg": "timeout", "event": expected_event or payload.get("cmd")}
        if raise_on_fail and not response.get("ok", False):
            raise ProtocolError(f"secure command failed: {response.get('msg', '')}")
        return response

    async def read_secure_snapshot(self) -> dict[str, Any]:
        raw = await self.client.read_gatt_char(READ_CHARACTERISTIC_UUID)
        text = bytes(raw).decode("utf-8")
        doc = self._parse_json(text)
        if {"nonce", "ct", "tag"}.issubset(doc.keys()):
            doc = self._decrypt_envelope(doc)
        if not doc.get("ok", True) and doc.get("event") == "read":
            raise ProtocolError(f"secure read failed: {doc.get('msg', '')}")
        return doc

    async def send_wifi_encrypted(
        self,
        ssid: str,
        password: str,
        *,
        enable_ble: Optional[bool] = None,
        enable_https: Optional[bool] = None,
    ) -> dict[str, Any]:
        """加密通道下发送 cmd=wifi（可选 enableble / enablehttps）。"""
        payload: dict[str, Any] = {"cmd": "wifi", "ssid": ssid, "pass": password}
        if enable_ble is not None:
            payload["enableble"] = bool(enable_ble)
        if enable_https is not None:
            payload["enablehttps"] = bool(enable_https)
        return await self.send_secure_command(payload, "wifi", timeout=30.0)

    async def poll_read_until_connected(
        self,
        *,
        total_timeout_s: float = 60.0,
        interval_s: float = 1.0,
        log: Any = print,
    ) -> tuple[dict[str, Any], str, Optional[str]]:
        """
        每秒 read GATT 0xC314，直到 IP 为有效 IPv4（非 0.0.0.0）或超时。
        返回 (last_doc, state, ip)  state: connected | timeout | ...
        """
        deadline = time.monotonic() + total_timeout_s
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = await self.read_secure_snapshot()
            log(f"[READ {time.strftime('%H:%M:%S')}] {json.dumps(last, ensure_ascii=False)}")
            ip_raw = extract_ip_field_from_read_doc(last)
            st, ip, raw = classify_ble_read_ip_field(ip_raw)
            log(f"[READ] 解析 IP 字段: state={st} ip={ip} raw={raw!r}")
            if st == "connected" and ip:
                return last, st, ip
            await asyncio.sleep(interval_s)
        st, ip, _ = classify_ble_read_ip_field(extract_ip_field_from_read_doc(last))
        return last, "timeout", ip


def infer_sn(explicit_sn: Optional[str], device_name: Optional[str]) -> str:
    """从显式参数或广播名 MODEL-SN 推断 12 位 hex SN。"""
    if explicit_sn:
        return explicit_sn.strip()
    pulse = sn_from_pulse_sn_name(device_name)
    if pulse:
        return pulse
    if device_name and "-" in device_name:
        return device_name.split("-", 1)[1].strip()
    raise ProtocolError("SN is required. Pass SN, or use a device name like MODEL-SN")


def parse_ltk_hex(value: str) -> bytes:
    """Parse 16-byte LTK from hex (32 hex chars, optional 0x prefix)."""
    s = "".join(value.split()).lower()
    if s.startswith("0x"):
        s = s[2:]
    if len(s) != SESSION_KEY_LEN * 2:
        raise ProtocolError(
            f"LTK hex must be exactly {SESSION_KEY_LEN * 2} characters ({SESSION_KEY_LEN} bytes), got {len(s)}"
        )
    try:
        out = bytes.fromhex(s)
    except ValueError as exc:
        raise ProtocolError("LTK is not valid hexadecimal") from exc
    if len(out) != SESSION_KEY_LEN:
        raise ProtocolError("LTK length mismatch after decode")
    return out


def default_cache_path() -> Path:
    return Path(__file__).resolve().parent / "ble_crypto_client_cache.json"

