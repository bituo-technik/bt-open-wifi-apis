#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Poll the meter HTTP API and send configuration commands (stdlib only).

Handles the optional Web password: signs in once, keeps the token, and signs in
again when the device says the token is missing / expired (codes 2001, 2002).

Examples
    python http_poll.py 192.168.1.50                       # one /snapshot
    python http_poll.py 192.168.1.50 -i 5                  # every 5 s
    python http_poll.py 192.168.1.50 -e data --password 123456
    python http_poll.py 192.168.1.50 --cmd '{"cmd":"getFunctionMap"}'
    python http_poll.py 192.168.1.50 --https               # Pro, port 443, certificate not verified

Doc: docs/http/http-api.*.md
"""
import argparse
import json
import random
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from cmdarg import dumps, parse_cmd


class Device:
    def __init__(self, host, port=None, https=False, password=None, timeout=5.0):
        self.base = "%s://%s%s" % ("https" if https else "http", host, (":%d" % port) if port else "")
        self.password = password
        self.token = None
        self.timeout = timeout
        self.ctx = None
        if https:
            self.ctx = ssl.create_default_context()
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def _open(self, path, params=None, body=None):
        q = dict(params or {})
        if self.token is not None and not path.startswith("/signin"):
            q["token"] = self.token
        url = self.base + path + (("?" + urllib.parse.urlencode(q)) if q else "")
        req = urllib.request.Request(url, data=body, method="POST" if body is not None else "GET")
        if body is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ctx) as r:
                return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:  # 403 / 404 carry a body too
            return e.code, e.read().decode("utf-8", "replace")

    def signin(self):
        if not self.password:
            return
        self.token = random.randint(1, 2**32 - 1)  # bring our own token, device keeps up to 5
        _, txt = self._open("/signin", {"password": self.password, "token": self.token})
        j = json.loads(txt)
        if not j.get("ok"):
            raise RuntimeError("sign-in failed: %s (code %s)" % (j.get("msg"), j.get("code")))
        if "token" in j:  # device generated one instead
            self.token = j["token"]

    def request(self, path, params=None, body=None):
        for attempt in (0, 1):
            status, txt = self._open(path, params, body)
            try:
                j = json.loads(txt)
            except ValueError:
                return status, txt
            if isinstance(j, dict) and j.get("ok") is False and j.get("code") in (2001, 2002, 2005) and attempt == 0:
                if not self.password:
                    raise RuntimeError("device needs a Web password: use --password")
                self.signin()
                continue
            return status, j
        return status, j


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("host")
    ap.add_argument("-p", "--port", type=int)
    ap.add_argument("--https", action="store_true")
    ap.add_argument("--password")
    ap.add_argument("-e", "--endpoint", default="snapshot", help="data, model, status, snapshot, sn, ... (default snapshot)")
    ap.add_argument("-i", "--interval", type=float, default=0, help="poll period in seconds (0 = once)")
    ap.add_argument("-n", "--count", type=int, default=0)
    ap.add_argument("--cmd", help='business command JSON, sent with POST /save-config, e.g. \'{"cmd":"location"}\'')
    a = ap.parse_args()

    dev = Device(a.host, a.port, a.https, a.password)
    try:
        # a first call tells whether the device is protected
        if a.password:
            dev.signin()
        if a.cmd:
            body = dumps(parse_cmd(a.cmd)).encode("utf-8")  # fails early on bad input
            status, res = dev.request("/save-config", body=body)
            print(status, json.dumps(res, ensure_ascii=False) if not isinstance(res, str) else res)
            return 0 if isinstance(res, dict) and res.get("ok") else 1
        n = 0
        while True:
            status, res = dev.request("/" + a.endpoint.lstrip("/"))
            print(time.strftime("%H:%M:%S"), status, res if isinstance(res, str) else json.dumps(res, ensure_ascii=False), flush=True)
            n += 1
            if not a.interval or (a.count and n >= a.count):
                return 0
            time.sleep(a.interval)
    except (RuntimeError, OSError, ValueError) as e:
        print("error:", e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
