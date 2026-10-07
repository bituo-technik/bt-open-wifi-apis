# -*- coding: utf-8 -*-
"""Verify the Python reference implementation against spec/ble-secured-test-vectors.json.

    py -3 scripts/check_test_vectors.py
"""
import base64, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools" / "ble-secured"))
import ble_crypto_core as c  # noqa: E402
from cryptography.hazmat.primitives.ciphers.aead import AESCCM  # noqa: E402

v = json.loads((ROOT / "spec" / "ble-secured-test-vectors.json").read_text(encoding="utf-8"))
failed = 0


def eq(name, got, want):
    global failed
    ok = got == want
    failed += 0 if ok else 1
    print(("ok   " if ok else "FAIL ") + name + ("" if ok else f"\n     got  {got}\n     want {want}"))


i = v["inputs"]
pin, sn, ver = i["pin"], i["sn"], i["ver"]
shared = bytes.fromhex(i["shared_key_hex"])
dn, cn = bytes.fromhex(i["device_nonce_hex"]), bytes.fromhex(i["client_nonce_hex"])

eq("pbkdf2", c.derive_pin_key(pin, sn, ver).hex(), v["pbkdf2"]["s_hex"])
ltk = c.derive_ltk(shared, dn, cn, sn, ver)
eq("ltk", ltk.hex(), v["hkdf"]["ltk"]["hex"])
sk = c.derive_session_key(ltk, dn, cn, sn, ver)
eq("session_key", sk.hex(), v["hkdf"]["session_key"]["hex"])
eq("broadcast_key", c.derive_broadcast_key(ltk, dn, cn, sn, ver).hex(), v["hkdf"]["broadcast_key"]["hex"])
d2c = c.derive_nonce_base(dn, cn, "ccm-tx-nonce")
c2d = c.derive_nonce_base(cn, dn, "ccm-rx-nonce")
eq("ccm base device->client", d2c.hex(), v["ccm_nonce_base"]["device_to_client"]["hex"])
eq("ccm base client->device", c2d.hex(), v["ccm_nonce_base"]["client_to_device"]["hex"])

for name, base in (("client_to_device", c2d), ("client_to_device_counter_2", c2d), ("device_to_client", d2c)):
    item = v["envelope"][name]
    env = item["envelope"]
    nonce = base + int(env["nonce"]).to_bytes(4, "big")
    blob = base64.b64decode(env["ct"]) + base64.b64decode(env["tag"])
    plain = AESCCM(sk, tag_length=8).decrypt(nonce, blob, None).decode("utf-8")
    eq("envelope " + name, plain, item["plaintext"])

m = v["manual_pairing_code"]
eq("manual code -> pin", c.pin_from_manual_pairing_code(m["code11"]), m["pin"])
try:
    c.pin_from_manual_pairing_code(m["invalid_example_wrong_check_digit"])
    eq("manual code wrong check digit rejected", False, True)
except Exception:
    eq("manual code wrong check digit rejected", True, True)

if failed:
    print(f"\n{failed} check(s) FAILED")
    sys.exit(1)
print("\nall checks passed")
