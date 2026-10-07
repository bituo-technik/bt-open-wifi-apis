#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find meters on the local network through mDNS (service _http._tcp.local.).

    python discover_mdns.py                 # list devices named EnergySensor-*
    python discover_mdns.py --all           # every _http._tcp service
    python discover_mdns.py --json

Uses the `zeroconf` package when installed (pip install zeroconf); otherwise falls back to a
small built-in mDNS query that needs nothing. Doc: docs/mdns/mdns-discovery.*.md
"""
import argparse
import json
import re
import select
import socket
import struct
import sys
import time

SERVICE = "_http._tcp.local."
NAME_RE = re.compile(r"^EnergySensor-(?P<model>[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*?)(?:_(?P<variant>0[0-9]))?-(?P<mac>[0-9A-F]{12})$")


# ------------------------------------------------------------------ built-in resolver
def _qname(name):
    return b"".join(bytes([len(p)]) + p.encode() for p in name.rstrip(".").split(".")) + b"\x00"


def _query(questions):
    out = struct.pack(">HHHHHH", 0, 0, len(questions), 0, 0, 0)
    for name, qtype in questions:
        out += _qname(name) + struct.pack(">HH", qtype, 1)
    return out


def _read_name(buf, off):
    parts, jumped, end = [], False, off
    while True:
        n = buf[off]
        if n == 0:
            off += 1
            break
        if n & 0xC0 == 0xC0:
            ptr = ((n & 0x3F) << 8) | buf[off + 1]
            if not jumped:
                end = off + 2
            jumped, off = True, ptr
            continue
        parts.append(buf[off + 1:off + 1 + n].decode("utf-8", "replace"))
        off += 1 + n
    return ".".join(parts) + ".", (end if jumped else off)


def _parse(buf, ptr, srv, addr):
    qd, an, ns, ar = struct.unpack(">4H", buf[4:12])
    off = 12
    for _ in range(qd):
        _, off = _read_name(buf, off)
        off += 4
    for _ in range(an + ns + ar):
        name, off = _read_name(buf, off)
        rtype, _cls, _ttl, rdlen = struct.unpack(">HHIH", buf[off:off + 10])
        off += 10
        rd = off
        if rtype == 12 and name.lower() == SERVICE:
            inst, _ = _read_name(buf, rd)
            ptr.add(inst)
        elif rtype == 33:
            port = struct.unpack(">H", buf[rd + 4:rd + 6])[0]
            host, _ = _read_name(buf, rd + 6)
            srv[name] = (host, port)
        elif rtype == 1:
            addr.setdefault(name.lower(), set()).add(socket.inet_ntoa(buf[rd:rd + 4]))
        off += rdlen


def _local_ipv4():
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except OSError:
        pass
    return ips


def discover_builtin(timeout):
    # One socket per local IPv4 address: with several adapters (VPN, virtual switches) the default
    # multicast interface is often the wrong one. A non-5353 source port makes responders answer directly.
    socks = []
    for ip in _local_ipv4() or [""]:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        try:
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
            if ip:
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip))
            s.bind((ip, 0))
            socks.append(s)
        except OSError:
            s.close()
    ptr, srv, addr = set(), {}, {}
    dest = ("224.0.0.251", 5353)

    def send(questions):
        q = _query(questions)
        for s in socks:
            try:
                s.sendto(q, dest)
            except OSError:
                pass

    def pump(seconds):
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select(socks, [], [], max(0.05, end - time.time()))
            for s in ready:
                try:
                    data, _ = s.recvfrom(9000)
                    _parse(data, ptr, srv, addr)
                except (IndexError, struct.error, OSError):
                    pass

    send([(SERVICE, 12)])
    pump(timeout * 0.5)
    missing = [i for i in ptr if i not in srv]
    if missing:
        send([(i, 33) for i in missing])
        pump(timeout * 0.25)
    hosts = [h for h, _ in srv.values() if h.lower() not in addr]
    if hosts:
        send([(h, 1) for h in hosts])
        pump(timeout * 0.25)
    for s in socks:
        s.close()
    out = []
    for inst in sorted(ptr):
        host, port = srv.get(inst, (None, None))
        ips = sorted(addr.get((host or "").lower(), []))
        out.append({"instance": inst[:-len(SERVICE) - 1] if inst.endswith("." + SERVICE) else inst, "host": host, "port": port, "ip": ips})
    return out


# ------------------------------------------------------------------ zeroconf
def discover_zeroconf(timeout):
    from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

    found = {}

    class L(ServiceListener):
        def add_service(self, zc, type_, name):
            info = zc.get_service_info(type_, name, 3000)
            if info:
                found[name] = {"instance": name[:-len(type_) - 1], "host": info.server, "port": info.port,
                               "ip": sorted(info.parsed_addresses())}

        update_service = add_service

        def remove_service(self, zc, type_, name):
            pass

    zc = Zeroconf()
    ServiceBrowser(zc, SERVICE, L())
    time.sleep(timeout)
    zc.close()
    return list(found.values())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-t", "--timeout", type=float, default=4.0)
    ap.add_argument("--all", action="store_true", help="show every _http._tcp service, not only EnergySensor-*")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--builtin", action="store_true", help="force the built-in resolver")
    a = ap.parse_args()

    try:
        if a.builtin:
            raise ImportError
        res = discover_zeroconf(a.timeout)
    except ImportError:
        res = discover_builtin(a.timeout)

    out = []
    for r in res:
        m = NAME_RE.match(r["instance"])
        r["model"], r["variant"], r["mac"] = (m.group("model"), m.group("variant"), m.group("mac")) if m else (None, None, None)
        if m or a.all:
            out.append(r)
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    elif not out:
        print("no device found (different subnet / multicast blocked / not connected to Wi-Fi?)", file=sys.stderr)
    else:
        for r in out:
            print("%-48s %-16s port %-5s model=%s variant=%s mac=%s" % (
                r["instance"], ",".join(r["ip"]) or "?", r["port"], r["model"], r["variant"] or "-", r["mac"]))
    return 0 if out else 1


if __name__ == "__main__":
    sys.exit(main())
