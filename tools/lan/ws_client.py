#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Minimal WebSocket client for the meter (stdlib only, port 81).

Prints every pushed telemetry frame, optionally sends commands, and reconnects
automatically (the device allows only 1-2 clients and may drop idle connections).

Examples
    python ws_client.py 192.168.1.50
    python ws_client.py 192.168.1.50 --interval 1000          # setInterval 1000 ms
    python ws_client.py 192.168.1.50 --cmd '{"cmd":"getFunctionMap"}' -n 3
    python ws_client.py 192.168.1.50 --tls                    # wss, falls back to ws when refused

Notes: the device does not accept fragmented frames or frames above 1024 bytes
(600 on WSS); this client always sends one masked text frame. Doc: docs/websocket/websocket-api.*.md
"""
import argparse
import base64
import json
import os
import socket
import ssl
import struct
import sys
import time

from cmdarg import dumps, parse_cmd


class Closed(Exception):
    pass


class WS:
    def __init__(self, host, port=81, tls=False, timeout=10.0):
        raw = socket.create_connection((host, port), timeout=timeout)
        if tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            raw = ctx.wrap_socket(raw, server_hostname=host)
        self.s = raw
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET / HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
               "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n" % (host, port, key))
        self.s.sendall(req.encode())
        head = b""
        while b"\r\n\r\n" not in head:
            c = self.s.recv(1)
            if not c:
                raise Closed("closed during handshake")
            head += c
        if b" 101 " not in head.split(b"\r\n", 1)[0]:
            raise Closed("handshake refused: " + head.split(b"\r\n", 1)[0].decode(errors="replace"))

    def _read(self, n):
        buf = b""
        while len(buf) < n:
            c = self.s.recv(n - len(buf))
            if not c:
                raise Closed("connection closed")
            buf += c
        return buf

    def send(self, text, opcode=1):
        data = text.encode("utf-8") if isinstance(text, str) else text
        hdr = bytes([0x80 | opcode])
        n = len(data)
        hdr += bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n)
        mask = os.urandom(4)
        self.s.sendall(hdr + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        """Return one text message; answers Ping, raises Closed on Close."""
        while True:
            b0, b1 = self._read(2)
            op, n = b0 & 0x0F, b1 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            data = self._read(n)
            if op == 9:
                self.send(data, opcode=10)
            elif op == 8:
                raise Closed("server closed")
            elif op in (1, 2):
                return data.decode("utf-8", "replace")

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("-p", "--port", type=int, default=81)
    ap.add_argument("--tls", action="store_true")
    ap.add_argument("--cmd", action="append", default=[], help="command JSON to send after connecting (repeatable)")
    ap.add_argument("--interval", type=int, help="shortcut for setInterval, milliseconds (100..86400000)")
    ap.add_argument("-n", "--count", type=int, default=0, help="stop after N received frames")
    ap.add_argument("--no-reconnect", action="store_true")
    a = ap.parse_args()

    cmds = [dumps(parse_cmd(c)) for c in a.cmd]
    if a.interval:
        cmds.append(dumps({"cmd": "setInterval", "value": a.interval}))
    tls = a.tls
    seen, delay = 0, 1.0
    while True:
        try:
            ws = WS(a.host, a.port, tls)
            print("connected (%s)" % ("wss" if tls else "ws"), flush=True)
            delay = 1.0
            for c in cmds:
                ws.send(c)
            while True:
                msg = ws.recv()
                try:
                    j = json.loads(msg)
                except ValueError:
                    j = None
                kind = "push" if isinstance(j, dict) and "event" not in j else "event:%s" % (j.get("event") if isinstance(j, dict) else "?")
                print(time.strftime("%H:%M:%S"), kind, msg, flush=True)
                seen += 1
                if a.count and seen >= a.count:
                    ws.close()
                    return 0
        except (Closed, OSError, ssl.SSLError) as e:
            print("disconnected:", e, file=sys.stderr, flush=True)
            if tls:  # no TLS slot -> device falls back to plain ws on the same port
                print("retrying as plain ws", file=sys.stderr)
                tls = False
            if a.no_reconnect:
                return 1
            time.sleep(delay)
            delay = min(delay * 2, 30)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
