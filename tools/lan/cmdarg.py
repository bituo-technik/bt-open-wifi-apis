# -*- coding: utf-8 -*-
"""Parse a command given on the command line.

Windows PowerShell 5.1 removes the double quotes inside an argument, so
    --cmd '{"cmd":"location"}'
arrives as  {cmd:location}.  This helper accepts both forms:
    {"cmd":"udp","IpAddress":"192.168.1.9","localUdpPort":9000}     (real JSON)
    {cmd:udp,IpAddress:192.168.1.9,localUdpPort:9000}              (quotes lost)
    udp IpAddress=192.168.1.9 localUdpPort=9000                    (short form)
Numbers, true, false and null are converted; everything else stays a string.
Values that contain commas or spaces need real JSON (use --cmd-file or escape the quotes).
"""
import json


def _convert(v):
    if v in ("true", "false", "null"):
        return json.loads(v)
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        return v


def parse_cmd(text):
    text = text.strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass
    if text.startswith("{") and text.endswith("}"):
        pairs = [p for p in text[1:-1].split(",") if p.strip()]
        out = {}
        for p in pairs:
            if ":" not in p:
                raise ValueError("cannot parse command: %r" % text)
            k, v = p.split(":", 1)
            out[k.strip().strip('"')] = _convert(v.strip().strip('"'))
        return out
    words = text.split()
    if not words:
        raise ValueError("empty command")
    out = {"cmd": words[0]}
    for w in words[1:]:
        if "=" not in w:
            raise ValueError("expected key=value, got %r" % w)
        k, v = w.split("=", 1)
        out[k] = _convert(v)
    return out


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
