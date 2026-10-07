#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read a meter over Modbus TCP (no third-party packages).

Examples
    python modbus_poll.py 192.168.1.50                # identification + one reading
    python modbus_poll.py 192.168.1.50 -i 2           # poll every 2 s
    python modbus_poll.py 192.168.1.50 --json         # machine-readable output
    python modbus_poll.py 192.168.1.50 --locate       # blink the LED (register 10002)
    python modbus_poll.py 192.168.1.50 --reset-energy --yes   # IRREVERSIBLE

The register map comes from spec/modbus-tcp-map.json, the same file the docs are
checked against (docs/modbus-tcp/modbus-tcp-api.*.md).
"""
import argparse
import json
import socket
import ssl
import struct
import sys
import time
from pathlib import Path

SPEC = Path(__file__).resolve().parents[2] / "spec" / "modbus-tcp-map.json"
EXC = {1: "illegal function", 2: "illegal data address", 3: "illegal data value", 5: "short frame"}


class ModbusError(Exception):
    pass


class Client:
    def __init__(self, host, port=502, unit=1, timeout=3.0, tls=False):
        self.unit = unit
        self.tid = 0
        raw = socket.create_connection((host, port), timeout=timeout)
        if tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE  # device certificates are usually self-signed
            raw = ctx.wrap_socket(raw, server_hostname=host)
        self.sock = raw

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass

    def _recv(self, n):
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ModbusError("connection closed by device")
            buf += chunk
        return buf

    def _call(self, pdu):
        self.tid = (self.tid + 1) & 0xFFFF
        self.sock.sendall(struct.pack(">HHHB", self.tid, 0, len(pdu) + 1, self.unit) + pdu)
        tid, pid, length, _unit = struct.unpack(">HHHB", self._recv(7))
        body = self._recv(length - 1)
        if tid != self.tid:
            raise ModbusError("transaction id mismatch")
        if body[0] & 0x80:
            code = body[1]
            raise ModbusError("exception %d (%s)" % (code, EXC.get(code, "?")))
        return body

    def read(self, start, count, fc=3):
        body = self._call(struct.pack(">BHH", fc, start, count))
        data = body[2:2 + body[1]]
        if len(data) != count * 2:
            raise ModbusError("short response")
        return data

    def write_single(self, address, value):
        self._call(struct.pack(">BHH", 6, address, value))


def text(data):
    return data.decode("ascii", "replace").rstrip("\x00").strip()


def model_type(model):
    if "SDM02" in model:
        return "split-phase"
    if "1PN" in model or "SPM01" in model:
        return "single-phase"
    return "three-phase"


def identification(cli):
    d = cli.read(978, 22)
    rssi = struct.unpack(">H", d[32:34])[0]
    return {
        "mac": text(d[0:12]),
        "model": text(d[12:22]),
        "mcuVersion": text(d[22:32]),
        "rssiDbm": -rssi,  # register holds the absolute value
        "time": struct.unpack(">I", d[34:38])[0],
        "wifiFirmware": text(d[38:44]),
    }


def measurements(cli, table):
    last = max(r["address"] for r in table) + 2
    data = cli.read(1000, last - 1000)
    out = {}
    for r in table:
        off = (r["address"] - 1000) * 2
        out[r["en"]] = (round(struct.unpack(">f", data[off:off + 4])[0], 3), r["unit"])
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("-p", "--port", type=int, default=502)
    ap.add_argument("-u", "--unit", type=int, default=1)
    ap.add_argument("-i", "--interval", type=float, default=0, help="poll period in seconds (0 = once)")
    ap.add_argument("-n", "--count", type=int, default=0, help="stop after N polls (0 = forever)")
    ap.add_argument("--type", choices=["auto", "single-phase", "split-phase", "three-phase"], default="auto")
    ap.add_argument("--tls", action="store_true", help="Modbus TCP over TLS (certificate is not verified)")
    ap.add_argument("--json", action="store_true", help="one JSON object per poll")
    ap.add_argument("--locate", action="store_true", help="write 0x5055 to 10002 (blink the LED)")
    ap.add_argument("--reset-energy", action="store_true", help="write 0x51AA to 10001 (IRREVERSIBLE)")
    ap.add_argument("--yes", action="store_true", help="confirm --reset-energy")
    a = ap.parse_args()

    spec = json.loads(SPEC.read_text(encoding="utf-8"))
    try:
        cli = Client(a.host, a.port, a.unit, tls=a.tls)
    except (OSError, ssl.SSLError) as e:
        print("error: cannot connect to %s:%d (%s). Is function bit 15 on? See docs/modbus-tcp section 7." % (a.host, a.port, e), file=sys.stderr)
        return 1
    try:
        if a.locate:
            cli.write_single(10002, 0x5055)
            print("locate sent")
            return 0
        if a.reset_energy:
            if not a.yes:
                print("refusing: --reset-energy erases the energy counters, add --yes", file=sys.stderr)
                return 2
            cli.write_single(10001, 0x51AA)
            print("reset energy sent")
            return 0

        ident = identification(cli)
        kind = a.type if a.type != "auto" else model_type(ident["model"])
        table = spec["measurements"][kind]
        if not a.json:
            print("device:", ident)
            print("map   :", kind)
        n = 0
        while True:
            vals = measurements(cli, table)
            if a.json:
                print(json.dumps({"time": int(time.time()), "identification": ident,
                                  "values": {k: v[0] for k, v in vals.items()}}, ensure_ascii=False), flush=True)
            else:
                print("---", time.strftime("%H:%M:%S"))
                for k, (v, u) in vals.items():
                    print("%-42s %14.3f %s" % (k, v, u))
            n += 1
            if not a.interval or (a.count and n >= a.count):
                return 0
            time.sleep(max(a.interval, 0.15))
    except (ModbusError, OSError) as e:
        print("error:", e, file=sys.stderr)
        return 1
    finally:
        cli.close()


if __name__ == "__main__":
    sys.exit(main())
