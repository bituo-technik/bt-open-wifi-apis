#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A fake three-phase meter for developing and testing integrations without hardware (stdlib only).

Serves, on non-privileged ports by default:
    HTTP        :8080   /signin /data /model /status /snapshot /sn /getFunctionMap /count, POST /save-config
    Modbus TCP  :1502   identification 978..999, measurements 1000..1076, control 10001 / 10002
    WebSocket   :8081   welcome + periodic telemetry push, commands (cmd)
    UDP                 sends telemetry to targets added with the `udp` command (or --udp-to)

    python mock_device.py                       # then:  python modbus_poll.py 127.0.0.1 -p 1502
    python mock_device.py --password 123456     # exercise the token flow
    python mock_device.py --udp-to 127.0.0.1:9000 --udp-key 00112233445566778899aabbccddeeff

It follows the documented behavior (unified responses, token rules, 1024-byte limit, one request per
Modbus response), not the full firmware. Do not rely on it to prove that a real device behaves identically.
"""
import argparse
import base64
import hashlib
import json
import math
import socket
import socketserver
import struct
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

SPEC = json.loads((Path(__file__).resolve().parents[2] / "spec" / "modbus-tcp-map.json").read_text(encoding="utf-8"))
MAC = "10304B0D7760"
MODEL = "SDM01_3PN"
FW = "5.1.16"
MCU = "003.00.13"


class Meter:
    def __init__(self, password, udp_key):
        self.password = password
        self.tokens = {}  # token -> last use
        self.post = 0
        self.energy = 1234.5
        self.started = time.time()
        self.udp_targets = {}  # (ip, port) -> True
        self.udp_period = 5.0
        self.ws_period = 1.0
        self.udp_key = udp_key
        self.udp_counter = 0
        self.functionMap = 0x8000 | 0x80 | 0x2000 | 0x800
        self.lock = threading.Lock()

    # ----------------------------------------------------------- values
    def base(self):
        t = time.time() - self.started
        v = [230.0 + 1.5 * math.sin(t / 7 + k) for k in range(3)]
        i = [5.0 + 0.4 * math.sin(t / 5 + k) for k in range(3)]
        p = [v[k] * i[k] * 0.98 / 1000 for k in range(3)]
        return v, i, p

    def telemetry(self):
        with self.lock:
            self.post += 1
            self.energy += 0.01
            post, energy = self.post, self.energy
        v, i, p = self.base()
        d = {"Post": post, "Time": int(time.time()), "IP": "127.0.0.1", "Rssi": -61, "FWVersion": FW,
             "MCUVersion": MCU, "SerialNumber": MAC, "ProductModel": MODEL, "TP": 4}
        for k, x in enumerate("XYZ"):
            d["Voltage" + x] = "%.1f" % v[k]
            d["Current" + x] = "%.3f" % i[k]
            d["ActivePower" + x] = "%.3f" % p[k]
            d["PowerFactor" + x] = "0.98"
        d.update({"TotalCurrent": "%.3f" % sum(i), "TotalActivePower": "%.3f" % sum(p),
                  "OverallPowerFactor": "0.98", "AverageVoltageL_N": "%.1f" % (sum(v) / 3),
                  "AverageLineCurrent": "%.3f" % (sum(i) / 3), "UnbalanceLineCurrents": "0", "Frequency": "50.00",
                  "TotalForwardEnergy": "%.2f" % energy, "TotalReverseEnergy": "0.00", "TotalEnergy": "%.2f" % energy})
        return d

    def registers(self):
        """978..1077 as a list of 100 uint16 following the documented map."""
        regs = [0] * 100

        def put_str(addr, s, nregs):
            b = s.encode("ascii").ljust(nregs * 2, b"\x00")[:nregs * 2]
            for k in range(nregs):
                regs[addr - 978 + k] = (b[2 * k] << 8) | b[2 * k + 1]

        put_str(978, MAC, 6)
        put_str(984, MODEL, 5)
        put_str(989, MCU, 5)
        regs[994 - 978] = 61  # absolute value of RSSI
        now = int(time.time())
        regs[995 - 978], regs[996 - 978] = now >> 16, now & 0xFFFF
        put_str(997, FW, 3)
        v, i, p = self.base()
        for r in SPEC["measurements"]["three-phase"]:
            name, unit = r["en"], r["unit"]
            if unit == "V":
                val = sum(v) / 3 if "Average" in name else v[("ABC".index(name.split()[-1][0])) if name.split()[-1][0] in "ABC" else 0]
            elif unit == "A":
                val = sum(i) if "Total" in name else (sum(i) / 3 if "Average" in name else i["ABC".index(name.split()[-1])])
            elif unit == "kW":
                val = sum(p) if "Total" in name else p["ABC".index(name.split()[-1])]
            elif unit in ("kVAR", "kVA"):
                val = 0.1
            elif unit == "":
                val = 0.98
            elif unit == "Hz":
                val = 50.0
            elif unit == "%":
                val = 0.0
            else:  # kWh
                val = 0.0 if name.lower().startswith(("export", "total export", "phase a export", "phase b export", "phase c export")) else self.energy
            raw = struct.pack(">f", val)
            regs[r["address"] - 978] = struct.unpack(">H", raw[:2])[0]
            regs[r["address"] - 978 + 1] = struct.unpack(">H", raw[2:])[0]
        return regs

    # ----------------------------------------------------------- tokens
    def token_ok(self, tok):
        now = time.time()
        for t in [t for t, ts in self.tokens.items() if now - ts > 300]:
            del self.tokens[t]
        if tok in self.tokens:
            self.tokens[tok] = now
            return True
        return False

    # ----------------------------------------------------------- commands
    def command(self, doc):
        cmd = doc.get("cmd") or doc.get("configType")
        if not cmd:
            return {"ok": False, "msg": "invalid cmd", "event": "cmd", "code": -1}
        ok = lambda msg="", d=None: dict({"ok": True, "msg": msg, "event": cmd}, **({"d": d} if d is not None else {}))
        if cmd == "getFunctionMap":
            return ok("", {"functionMap": self.functionMap})
        if cmd == "location":
            return ok("location received")
        if cmd == "zero":
            self.energy = 0.0
            return ok("zero received")
        if cmd == "setInterval":
            v = doc.get("value", 0)
            if not isinstance(v, int) or v < 100:
                return {"ok": False, "msg": "bad value", "event": cmd, "code": 4}
            self.ws_period = v / 1000.0
            return ok("", {"value": v})
        if cmd == "getInterval":
            return ok("", {"value": int(self.ws_period * 1000)})
        if cmd == "udp":
            ip, port = doc.get("IpAddress"), doc.get("localUdpPort")
            if not ip or not port or len(self.udp_targets) >= 5 and (ip, port) not in self.udp_targets:
                return {"ok": False, "msg": "UDP full", "event": cmd, "code": 24}
            self.udp_targets[(ip, int(port))] = True
            if "Frequency" in doc:
                self.udp_period = max(0.1, float(doc["Frequency"]))
            self.functionMap |= 0x2000
            return ok("UDP successfully")
        if cmd == "deleteudp":
            if self.udp_targets.pop((doc.get("IpAddress"), int(doc.get("localUdpPort", 0))), None) is None:
                return {"ok": False, "msg": "UDP not found", "event": cmd, "code": 25}
            return ok("UDP deleted")
        if cmd == "udpdata":
            return ok("", {"udp_data": [{"ip": a, "port": str(p)} for a, p in self.udp_targets]})
        if cmd == "model":
            return ok("", self.model())
        return {"ok": False, "msg": "unknow cmd", "event": cmd, "code": 15}

    def model(self):
        return {"WN": "MockWiFi", "WPN": "EnergySensor-%s_01-%s" % (MODEL, MAC), "MH": "", "MF": False, "MP": 0,
                "MC": "", "MI": 5000, "MS": False, "LSM": 0, "UI": int(self.udp_period * 1000),
                "WI": int(self.ws_period * 1000), "MAD": "5 / 9600 / N81"}

    def encode_udp(self, text):
        if not self.udp_key:
            return text.encode()
        from cryptography.hazmat.primitives.ciphers.aead import AESCCM
        self.udp_counter += 1
        nonce = b"\x00" * 8 + self.udp_counter.to_bytes(4, "big")
        out = AESCCM(self.udp_key, tag_length=8).encrypt(nonce, text.encode(), None)
        return json.dumps({"ct": base64.b64encode(out[:-8]).decode(), "tag": base64.b64encode(out[-8:]).decode(),
                           "counter": self.udp_counter}).encode()


# ----------------------------------------------------------------------------- HTTP
def make_http(meter):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, *a):
            pass

        def _send(self, obj, status=200):
            body = obj.encode() if isinstance(obj, str) else json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/plain" if isinstance(obj, str) else "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _handle(self, body=None):
            u = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            path = u.path
            if path == "/signin":
                if "password" not in q:
                    return self._send({"ok": True, "msg": "no password"} if not meter.password else
                                      {"ok": False, "msg": "need signin", "code": 2005})
                if not meter.password:
                    return self._send({"ok": True, "msg": "no password set"})
                if q["password"] != meter.password:
                    return self._send({"ok": False, "msg": "wrong password", "code": 2003})
                if "token" in q:
                    meter.tokens[int(q["token"])] = time.time()
                    return self._send({"ok": True, "msg": ""})
                tok = int(time.time())
                meter.tokens[tok] = time.time()
                return self._send({"ok": True, "msg": "", "token": tok})
            if meter.password:
                if "token" not in q:
                    return self._send({"ok": False, "msg": "need token", "code": 2001})
                if not meter.token_ok(int(q["token"])):
                    return self._send({"ok": False, "msg": "invalid token", "code": 2002})
            if path == "/data":
                return self._send(meter.telemetry())
            if path == "/model":
                return self._send(meter.model())
            if path == "/status":
                return self._send({"MQTTStatus": "Off", "UDPStatus": "Online" if meter.udp_targets else "Off",
                                   "WebSocketStatus": "Online", "ModbusTCPStatus": "Online", "wsInterval": int(meter.ws_period * 1000)})
            if path == "/snapshot":
                return self._send({"data": meter.telemetry(), "model": meter.model(), "status": {}})
            if path == "/sn":
                return self._send("%s-%s" % (MODEL, MAC))
            if path == "/getFunctionMap":
                return self._send(meter.command({"cmd": "getFunctionMap"}))
            if path == "/count":
                return self._send({"ok": True, "msg": str(meter.post), "event": "count"})
            if path == "/save-config" and body is not None:
                if len(body) > 1024:
                    return self._send({"ok": False, "msg": "payload too large", "event": "save-config", "code": 2041})
                try:
                    return self._send(meter.command(json.loads(body)))
                except ValueError:
                    return self._send({"ok": False, "msg": "Error!", "event": "save-config", "code": -1})
            return self._send("not found", 404)

        def do_GET(self):
            self._handle()

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            self._handle(self.rfile.read(n))

    return H


# ----------------------------------------------------------------------------- Modbus TCP
def make_modbus(meter):
    class H(socketserver.BaseRequestHandler):
        def handle(self):
            self.request.settimeout(30)
            buf = b""
            try:
                while True:
                    d = self.request.recv(600)
                    if not d:
                        return
                    buf += d
                    last = None
                    while len(buf) >= 7:
                        ln = struct.unpack(">H", buf[4:6])[0]
                        if len(buf) < 6 + ln:
                            break
                        last, buf = buf[:6 + ln], buf[6 + ln:]
                    if last:  # like the firmware, only the newest frame is answered
                        self.request.sendall(self.respond(last))
            except OSError:
                return

        def respond(self, f):
            tid, unit, fc = f[0:2], f[6], f[7]
            if len(f) < 12:
                return self.exc(f, 5)
            addr, val = struct.unpack(">HH", f[8:12])
            if fc in (3, 4):
                if addr < 978 or addr + val > 1078:
                    return self.exc(f, 2)
                regs = meter.registers()[addr - 978:addr - 978 + val]
                data = b"".join(struct.pack(">H", r) for r in regs)
                pdu = bytes([fc, len(data)]) + data
            elif fc == 6:
                if addr == 10001 and val == 0x51AA:
                    meter.energy = 0.0
                elif addr == 10002 and val == 0x5055:
                    print("mock: locate (LED blink)", flush=True)
                elif addr in (10001, 10002):
                    return self.exc(f, 3)
                else:
                    return self.exc(f, 2)
                pdu = f[7:12]
            else:
                return self.exc(f, 1)
            return tid + b"\x00\x00" + struct.pack(">H", len(pdu) + 1) + bytes([unit]) + pdu

        def exc(self, f, code):
            return f[0:2] + b"\x00\x00\x00\x03" + bytes([f[6], f[7] | 0x80, code])

    class S(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    return S, H


# ----------------------------------------------------------------------------- WebSocket
def ws_frame(text):
    b = text.encode()
    n = len(b)
    return bytes([0x81]) + (bytes([n]) if n < 126 else bytes([126]) + struct.pack(">H", n)) + b


def make_ws(meter):
    clients, lock = [], threading.Lock()

    class H(socketserver.BaseRequestHandler):
        def handle(self):
            s = self.request
            head = b""
            while b"\r\n\r\n" not in head:
                c = s.recv(1024)
                if not c:
                    return
                head += c
            key = [l.split(b":", 1)[1].strip() for l in head.split(b"\r\n") if l.lower().startswith(b"sec-websocket-key")][0]
            acc = base64.b64encode(hashlib.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").digest())
            s.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + acc + b"\r\n\r\n")
            with lock:
                if len(clients) >= 2:
                    return
                clients.append(s)
            try:
                s.sendall(ws_frame(json.dumps({"ok": True, "event": "welcome", "msg": "websocket connected"})))
                while True:
                    b0, b1 = self.rd(2)
                    n = b1 & 0x7F
                    if n == 126:
                        n = struct.unpack(">H", self.rd(2))[0]
                    mask = self.rd(4) if b1 & 0x80 else b"\x00" * 4
                    data = bytes(x ^ mask[k % 4] for k, x in enumerate(self.rd(n)))
                    if b0 & 0x0F == 8:
                        return
                    if b0 & 0x0F == 1:
                        if len(data) > 1024 or not data.startswith(b"{"):
                            r = {"ok": False, "event": "error", "msg": "invalid json", "code": 4001}
                        else:
                            try:
                                r = meter.command(json.loads(data))
                            except ValueError:
                                r = {"ok": False, "event": "error", "msg": "json parse error", "code": 4002}
                        s.sendall(ws_frame(json.dumps(r)))
            except (OSError, IndexError):
                pass
            finally:
                with lock:
                    if s in clients:
                        clients.remove(s)

        def rd(self, n):
            b = b""
            while len(b) < n:
                c = self.request.recv(n - len(b))
                if not c:
                    raise OSError
                b += c
            return b

    def pusher():
        while True:
            time.sleep(meter.ws_period)
            with lock:
                cs = list(clients)
            if cs:
                f = ws_frame(json.dumps(meter.telemetry()))
                for c in cs:
                    try:
                        c.sendall(f)
                    except OSError:
                        pass

    class S(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True

    return S, H, pusher


def udp_sender(meter):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        time.sleep(meter.udp_period)
        if not meter.udp_targets:
            continue
        data = meter.encode_udp(json.dumps(meter.telemetry()))
        for tgt in list(meter.udp_targets):
            try:
                s.sendto(data, tgt)
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bind", default="127.0.0.1")
    ap.add_argument("--http-port", type=int, default=8080)
    ap.add_argument("--modbus-port", type=int, default=1502)
    ap.add_argument("--ws-port", type=int, default=8081)
    ap.add_argument("--password", help="Web password (enables the token flow)")
    ap.add_argument("--udp-to", help="ip:port to send UDP reports to from the start")
    ap.add_argument("--udp-key", help="32 hex characters; encrypt UDP datagrams with AES-CCM")
    a = ap.parse_args()

    meter = Meter(a.password, bytes.fromhex(a.udp_key) if a.udp_key else None)
    if a.udp_to:
        ip, port = a.udp_to.rsplit(":", 1)
        meter.udp_targets[(ip, int(port))] = True
        meter.udp_period = 1.0

    http = ThreadingHTTPServer((a.bind, a.http_port), make_http(meter))
    S, H = make_modbus(meter)
    mb = S((a.bind, a.modbus_port), H)
    WS, WH, pusher = make_ws(meter)
    ws = WS((a.bind, a.ws_port), WH)
    for fn in (http.serve_forever, mb.serve_forever, ws.serve_forever, pusher, lambda: udp_sender(meter)):
        threading.Thread(target=fn, daemon=True).start()
    print("mock meter %s %s: http :%d  modbus :%d  ws :%d%s" % (MODEL, MAC, a.http_port, a.modbus_port, a.ws_port,
                                                              "  (password set)" if a.password else ""), flush=True)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    sys.exit(main())
