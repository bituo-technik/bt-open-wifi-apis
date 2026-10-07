// Verifies the JS reference implementation against spec/ble-secured-test-vectors.json.
//   node scripts/check_test_vectors.mjs
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import {
  bytesToHex, hexToBytes, derivePinKey, deriveLtk, deriveSessionKey, deriveBroadcastKey,
  deriveNonceBase, SessionState, encryptEnvelope, decryptEnvelope, pinFromManualPairingCode,
} from "../tools/ble-secured/ble_secured_crypto.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const v = JSON.parse(readFileSync(path.join(here, "..", "spec", "ble-secured-test-vectors.json"), "utf8"));
let failed = 0;
function eq(name, got, want) {
  const ok = got === want;
  if (!ok) failed++;
  console.log(`${ok ? "ok  " : "FAIL"} ${name}${ok ? "" : `\n     got  ${got}\n     want ${want}`}`);
}

const { pin, sn, ver } = v.inputs;
const sharedKey = hexToBytes(v.inputs.shared_key_hex);
const dn = hexToBytes(v.inputs.device_nonce_hex);
const cn = hexToBytes(v.inputs.client_nonce_hex);

eq("pbkdf2", bytesToHex(derivePinKey(pin, sn, ver)), v.pbkdf2.s_hex);
const ltk = deriveLtk(sharedKey, dn, cn, sn, ver);
eq("ltk", bytesToHex(ltk), v.hkdf.ltk.hex);
const sk = deriveSessionKey(ltk, dn, cn, sn, ver);
eq("session_key", bytesToHex(sk), v.hkdf.session_key.hex);
eq("broadcast_key", bytesToHex(deriveBroadcastKey(ltk, dn, cn, sn, ver)), v.hkdf.broadcast_key.hex);
const d2c = deriveNonceBase(dn, cn, "ccm-tx-nonce");
const c2d = deriveNonceBase(cn, dn, "ccm-rx-nonce");
eq("ccm base device->client", bytesToHex(d2c), v.ccm_nonce_base.device_to_client.hex);
eq("ccm base client->device", bytesToHex(c2d), v.ccm_nonce_base.client_to_device.hex);

// Client-side session: tx = client->device, rx = device->client
const mk = () => new SessionState({
  protocolVersion: ver, sn, clientNonce: cn, deviceNonce: dn, ltk, sessionKey: sk,
  txNonceBase: c2d, rxNonceBase: d2c,
});
let s = mk();
let e = encryptEnvelope(s, JSON.parse(v.envelope.client_to_device.plaintext));
eq("envelope c2d #1", JSON.stringify(e), JSON.stringify(v.envelope.client_to_device.envelope));
e = encryptEnvelope(s, JSON.parse(v.envelope.client_to_device_counter_2.plaintext));
eq("envelope c2d #2", JSON.stringify(e), JSON.stringify(v.envelope.client_to_device_counter_2.envelope));
s = mk();
const plain = decryptEnvelope(s, v.envelope.device_to_client.envelope);
eq("envelope d2c decrypt", JSON.stringify(plain), JSON.stringify(JSON.parse(v.envelope.device_to_client.plaintext)));

eq("manual code -> pin", pinFromManualPairingCode(v.manual_pairing_code.code11), v.manual_pairing_code.pin);
let threw = false;
try { pinFromManualPairingCode(v.manual_pairing_code.invalid_example_wrong_check_digit); } catch { threw = true; }
eq("manual code wrong check digit rejected", threw, true);

if (failed) { console.log(`\n${failed} check(s) FAILED`); process.exit(1); }
console.log("\nall checks passed");
