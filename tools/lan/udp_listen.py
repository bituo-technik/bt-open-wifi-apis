#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Receive the meter's UDP report; decrypts AES-CCM datagrams when a key is given.

First tell the meter where to send (any channel, e.g. HTTP):
    python http_poll.py <meter> --cmd "udp IpAddress=<this PC> localUdpPort=9000 Frequency=5"

Then
    python udp_listen.py                       # port 9000, plaintext
    python udp_listen.py --key 00112233445566778899aabbccddeeff
    python udp_listen.py --cache ../ble-secured/ble_crypto_client_cache.json --sn AABBCCDDEEFF

Datagrams: plaintext telemetry JSON, or {"ct","tag","counter"} (AES-128-CCM, 8-byte tag,
nonce = 8 zero bytes + counter big-endian, no AAD). Doc: docs/udp/udp-api.*.md
Decryption needs:  pip install cryptography
"""
import argparse
import base64
import json
import socket
import sys
import time
from pathlib import Path


def decrypt(env, key):
    from cryptography.hazmat.primitives.ciphers.aead import AESCCM
    ct = base64.b64decode(env["ct"])
    tag = base64.b64decode(env["tag"])
    nonce = b"\x00" * 8 + int(env["counter"]).to_bytes(4, "big")
    return json.loads(AESCCM(key, tag_length=8).decrypt(nonce, ct + tag, None))


def key_from_cache(path, sn):
    devs = json.loads(Path(path).read_text(encoding="utf-8")).get("devices", {})
    if sn not in devs:
        raise SystemExit("serial number %s not in cache (known: %s)" % (sn, ", ".join(devs) or "none"))
    h = devs[sn].get("broadcast_key_hex")
    if not h:
        raise SystemExit("cache entry has no broadcast_key_hex; run a full secured provisioning first")
    return bytes.fromhex(h)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-p", "--port", type=int, default=9000)
    ap.add_argument("--bind", default="0.0.0.0")
    ap.add_argument("--key", help="16-byte broadcast key as 32 hex characters")
    ap.add_argument("--cache", help="ble_crypto_client_cache.json written by the secured BLE tools")
    ap.add_argument("--sn", help="serial number to look up in --cache")
    ap.add_argument("-n", "--count", type=int, default=0, help="stop after N datagrams")
    ap.add_argument("--fields", help="comma separated fields to print, default whole packet")
    a = ap.parse_args()

    key = None
    if a.key:
        key = bytes.fromhex(a.key)
        if len(key) != 16:
            raise SystemExit("--key must be 32 hex characters")
    elif a.cache:
        if not a.sn:
            raise SystemExit("--cache needs --sn")
        key = key_from_cache(a.cache, a.sn)
    fields = [f.strip() for f in a.fields.split(",")] if a.fields else None

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind((a.bind, a.port))
    print("listening on %s:%d%s" % (a.bind, a.port, " (decrypting)" if key else ""), flush=True)
    last = {}  # serial -> last Post, to flag loss / duplicates
    n = 0
    while True:
        data, addr = s.recvfrom(4096)
        if not data:  # device without broadcast key sends an empty datagram
            continue
        try:
            doc = json.loads(data.decode("utf-8"))
        except ValueError:
            print("%s not JSON (%d bytes)" % (addr[0], len(data)))
            continue
        enc = False
        if isinstance(doc, dict) and "ct" in doc and "tag" in doc:
            enc = True
            if key is None:
                print("%s encrypted datagram counter=%s (give --key or --cache to decrypt)" % (addr[0], doc.get("counter")))
                n += 1
                if a.count and n >= a.count:
                    return 0
                continue
            try:
                doc = decrypt(doc, key)
            except Exception as e:  # tag mismatch, bad base64 ...
                print("%s decrypt failed: %s" % (addr[0], type(e).__name__))
                continue
        sn = doc.get("SerialNumber", addr[0])
        post = doc.get("Post")
        note = ""
        if isinstance(post, int) and sn in last:
            if post == last[sn]:
                note = " (duplicate)"
            elif post > last[sn] + 1:
                note = " (lost %d)" % (post - last[sn] - 1)
        if isinstance(post, int):
            last[sn] = post
        shown = {k: doc.get(k) for k in fields} if fields else doc
        print("%s %s%s %s%s" % (time.strftime("%H:%M:%S"), addr[0], " [enc]" if enc else "", json.dumps(shown, ensure_ascii=False), note), flush=True)
        n += 1
        if a.count and n >= a.count:
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        pass
