#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Watch a meter's MQTT topics and send commands to it.

    pip install paho-mqtt

Examples
    python mqtt_monitor.py --broker 192.168.1.10 --model SDM01_3PN --sn 10304B0D7760
    python mqtt_monitor.py --broker broker.example.com --port 8883 --tls --user u --password p \
           --model SPM02 --sn AABBCCDDEEFF --cmd '{"cmd":"location"}'

Topics default to {model}/{sn}/{data|cmd|cdata|mdata}. If the device uses other topics, read them with the
business command `mqttdata` (TP / TC / TR / TM) and pass --topic-data / --topic-cmd / --topic-resp / --topic-meta.
Doc: docs/mqtt/mqtt-api.*.md
"""
import argparse
import json
import ssl
import sys
import threading
import time

from cmdarg import dumps, parse_cmd

try:
    import paho.mqtt.client as mqtt
except ImportError:
    sys.exit("paho-mqtt is required:  pip install paho-mqtt")


def make_client(client_id):
    try:  # paho-mqtt >= 2.0
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    except AttributeError:
        return mqtt.Client(client_id=client_id)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--broker", required=True)
    ap.add_argument("--port", type=int, default=1883)
    ap.add_argument("--tls", action="store_true", help="MQTTS (certificate is verified with the system store unless --insecure)")
    ap.add_argument("--insecure", action="store_true", help="do not verify the broker certificate")
    ap.add_argument("--user")
    ap.add_argument("--password")
    ap.add_argument("--model", help="model part of the topic, e.g. SDM01_3PN")
    ap.add_argument("--sn", help="12 hex characters serial number")
    ap.add_argument("--topic-data")
    ap.add_argument("--topic-cmd")
    ap.add_argument("--topic-resp")
    ap.add_argument("--topic-meta")
    ap.add_argument("--cmd", help="command JSON to publish to the cmd topic, waits for the response")
    ap.add_argument("--timeout", type=float, default=10.0, help="seconds to wait for a response")
    ap.add_argument("-n", "--count", type=int, default=0, help="stop after N /data messages")
    a = ap.parse_args()

    base = "%s/%s" % (a.model, a.sn) if a.model and a.sn else None
    t_data = a.topic_data or (base and base + "/data")
    t_cmd = a.topic_cmd or (base and base + "/cmd")
    t_resp = a.topic_resp or (base and base + "/cdata")
    t_meta = a.topic_meta or (base and base + "/mdata")
    if not (t_data and t_cmd and t_resp and t_meta):
        sys.exit("give --model and --sn, or all four --topic-* options")

    got_resp = threading.Event()
    state = {"data": 0, "want": None, "rc": 0}

    c = make_client("api-monitor-%d" % int(time.time()))
    if a.user:
        c.username_pw_set(a.user, a.password)
    if a.tls:
        c.tls_set(cert_reqs=ssl.CERT_NONE if a.insecure else ssl.CERT_REQUIRED)
        if a.insecure:
            c.tls_insecure_set(True)

    def on_connect(client, userdata, flags, rc, *rest):
        if getattr(rc, "is_failure", False) or (isinstance(rc, int) and rc != 0):
            print("connect failed:", rc, file=sys.stderr)
            return
        for t in (t_data, t_resp, t_meta):
            client.subscribe(t)
        print("connected, subscribed to", t_data, t_resp, t_meta, flush=True)
        if a.cmd:
            doc = parse_cmd(a.cmd)
            state["want"] = doc.get("cmd")
            client.publish(t_cmd, dumps(doc))
            print(">>", dumps(doc), flush=True)

    def on_message(client, userdata, msg):
        text = msg.payload.decode("utf-8", "replace")
        tag = {t_data: "data", t_resp: "resp", t_meta: "meta"}.get(msg.topic, msg.topic)
        print(time.strftime("%H:%M:%S"), tag, text, flush=True)
        if msg.topic == t_resp and a.cmd:
            try:
                ev = json.loads(text).get("event")
            except ValueError:
                ev = None
            if ev == state["want"]:
                got_resp.set()
        if msg.topic == t_data:
            state["data"] += 1
            if a.count and state["data"] >= a.count:
                got_resp.set()

    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(a.broker, a.port, keepalive=60)
    c.loop_start()
    try:
        if a.cmd or a.count:
            if not got_resp.wait(a.timeout if a.cmd else 3600):
                print("timeout: no response (commands over 1024 bytes or invalid JSON get none)", file=sys.stderr)
                state["rc"] = 1
        else:
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        c.loop_stop()
        c.disconnect()
    return state["rc"]


if __name__ == "__main__":
    sys.exit(main())
