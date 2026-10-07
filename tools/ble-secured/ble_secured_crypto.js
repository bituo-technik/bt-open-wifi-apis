/**
 * BLE Secured channel crypto (Lite/Pro) — aligned with ble_crypto_core.py / Crypto API V2.
 * Uses @noble/curves + @noble/hashes + @noble/ciphers (CDN ES modules).
 */
import { p256 } from "./vendor/curves/esm/p256.js";
import { sha256 } from "./vendor/hashes/esm/sha256.js";
import { pbkdf2 } from "./vendor/hashes/esm/pbkdf2.js";
import { hkdf } from "./vendor/hashes/esm/hkdf.js";
import { ccmEncrypt, ccmDecrypt } from "./vendor/aes_ccm.js";

export const PBKDF2_ITERATIONS = 10000;
export const PIN_DERIVED_LEN = 32;
export const SESSION_KEY_LEN = 16;
export const SESSION_NONCE_LEN = 8;
export const CCM_TAG_LEN = 8;
export const ROUND1_CHUNK_LEN = 220;
export const PROTOCOL_VERSION_FALLBACK = "BT_Crypto_V1";
export const GROUP_TLS_NAMED_CURVE_SECP256R1 = new Uint8Array([0x03, 0x00, 0x17]);
export const ADV_CCM_TAG_LEN = 4;
export const ADV_PLAIN_LEN = 15;
export const ADV_MFG_PAYLOAD_LEN = 26;
export const ADV_COMPANY_ID = 0xffff;

const Point = p256.ProjectivePoint;
const ORDER = p256.CURVE.n;
const G = Point.BASE;

export class ProtocolError extends Error {
  constructor(msg) {
    super(msg);
    this.name = "ProtocolError";
  }
}

function te(s) {
  return new TextEncoder().encode(s);
}
function td(u8) {
  return new TextDecoder().decode(u8);
}

export function bytesToHex(u8) {
  return [...u8].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function hexToBytes(hex) {
  const s = hex.replace(/\s+/g, "").toLowerCase().replace(/^0x/, "");
  if (s.length % 2) throw new ProtocolError("odd hex length");
  const out = new Uint8Array(s.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(s.slice(i * 2, i * 2 + 2), 16);
  return out;
}

export function b64encode(u8) {
  let bin = "";
  for (const b of u8) bin += String.fromCharCode(b);
  return btoa(bin);
}

export function b64decode(s) {
  const bin = atob(String(s).trim());
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function concatBytes(...parts) {
  const n = parts.reduce((a, p) => a + p.length, 0);
  const out = new Uint8Array(n);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out;
}

function u32be(n) {
  const b = new Uint8Array(4);
  new DataView(b.buffer).setUint32(0, n >>> 0, false);
  return b;
}

function randomBytes(n) {
  const b = new Uint8Array(n);
  crypto.getRandomValues(b);
  return b;
}

function randomScalar() {
  // 1 .. ORDER-1
  for (let i = 0; i < 64; i++) {
    const raw = randomBytes(32);
    let x = BigInt("0x" + bytesToHex(raw)) % ORDER;
    if (x !== 0n) return x;
  }
  throw new ProtocolError("failed to sample scalar");
}

function minimalIntBytes(value) {
  if (value === 0n) return new Uint8Array([0]);
  let hex = value.toString(16);
  if (hex.length % 2) hex = "0" + hex;
  return hexToBytes(hex);
}

function pointToRaw(P) {
  if (P.equals(Point.ZERO)) throw new ProtocolError("point at infinity");
  const aff = P.toAffine();
  const xb = hexToBytes(aff.x.toString(16).padStart(64, "0"));
  const yb = hexToBytes(aff.y.toString(16).padStart(64, "0"));
  return concatBytes(new Uint8Array([0x04]), xb, yb);
}

function tlsWritePoint(P) {
  const raw = pointToRaw(P);
  if (raw.length > 255) throw new ProtocolError("unexpected point length");
  return concatBytes(new Uint8Array([raw.length]), raw);
}

function readExact(buf, offset, length) {
  const end = offset + length;
  if (end > buf.length) throw new ProtocolError("buffer too short");
  return [buf.slice(offset, end), end];
}

function tlsReadPoint(buf, offset) {
  let pointLenBytes;
  [pointLenBytes, offset] = readExact(buf, offset, 1);
  const pointLen = pointLenBytes[0];
  let raw;
  [raw, offset] = readExact(buf, offset, pointLen);
  if (raw.length !== 65 || raw[0] !== 0x04) throw new ProtocolError("invalid EC point encoding");
  const x = BigInt("0x" + bytesToHex(raw.slice(1, 33)));
  const y = BigInt("0x" + bytesToHex(raw.slice(33, 65)));
  const P = Point.fromAffine({ x, y });
  return [P, offset];
}

function pointMul(scalar, P) {
  const s = ((scalar % ORDER) + ORDER) % ORDER;
  if (s === 0n) return Point.ZERO;
  return P.multiply(s);
}

function pointAdd(...pts) {
  let acc = Point.ZERO;
  for (const p of pts) {
    if (!p || p.equals(Point.ZERO)) continue;
    acc = acc.add(p);
  }
  return acc;
}

function pointNeg(P) {
  if (P.equals(Point.ZERO)) return P;
  const a = P.toAffine();
  const p = p256.CURVE.p;
  return Point.fromAffine({ x: a.x, y: (p - (a.y % p)) % p });
}

function pointSub(left, right) {
  return pointAdd(left, pointNeg(right));
}

function pointEqual(a, b) {
  return a.equals(b);
}

function ecjpakeHash(Gpt, V, X, identity, secretInt) {
  const gRaw = pointToRaw(Gpt);
  const vRaw = pointToRaw(V);
  const xRaw = pointToRaw(X);
  const ident = te(identity);
  let payload = concatBytes(
    u32be(gRaw.length),
    gRaw,
    u32be(vRaw.length),
    vRaw,
    u32be(xRaw.length),
    xRaw,
    u32be(ident.length),
    ident
  );
  if (secretInt !== null && secretInt !== undefined && secretInt !== 0n) {
    const sb = minimalIntBytes(secretInt);
    payload = concatBytes(payload, u32be(sb.length), sb);
  }
  const digest = sha256(payload);
  return BigInt("0x" + bytesToHex(digest)) % ORDER;
}

function zkpWrite(Gpt, secretScalar, publicPoint, identity, secretInt) {
  for (let i = 0; i < 8; i++) {
    const v = randomScalar();
    const V = pointMul(v, Gpt);
    const h = ecjpakeHash(Gpt, V, publicPoint, identity, secretInt);
    const r = (((v - ((secretScalar * h) % ORDER)) % ORDER) + ORDER) % ORDER;
    const rBytes = minimalIntBytes(r);
    if (rBytes.length <= 255) {
      return concatBytes(tlsWritePoint(V), new Uint8Array([rBytes.length]), rBytes);
    }
  }
  throw new ProtocolError("failed to generate Schnorr proof");
}

function zkpRead(Gpt, publicPoint, identity, buf, offset, secretInt) {
  let V;
  [V, offset] = tlsReadPoint(buf, offset);
  let rLenRaw;
  [rLenRaw, offset] = readExact(buf, offset, 1);
  const rLen = rLenRaw[0];
  if (rLen === 0) throw new ProtocolError("invalid Schnorr proof length");
  let rBytes;
  [rBytes, offset] = readExact(buf, offset, rLen);
  const r = BigInt("0x" + bytesToHex(rBytes));
  const h = ecjpakeHash(Gpt, V, publicPoint, identity, secretInt);
  const vv = pointAdd(pointMul(h, publicPoint), pointMul(r, Gpt));
  if (!pointEqual(vv, V)) throw new ProtocolError("Schnorr proof verification failed");
  return offset;
}

function kkpWrite(Gpt, secretScalar, publicPoint, identity, secretInt) {
  return concatBytes(tlsWritePoint(publicPoint), zkpWrite(Gpt, secretScalar, publicPoint, identity, secretInt));
}

function kkpRead(Gpt, identity, buf, offset, secretInt) {
  let publicPoint;
  [publicPoint, offset] = tlsReadPoint(buf, offset);
  if (publicPoint.equals(Point.ZERO)) throw new ProtocolError("peer public point is infinity");
  offset = zkpRead(Gpt, publicPoint, identity, buf, offset, secretInt);
  return [publicPoint, offset];
}

export class EcJpakeClient {
  constructor(secretMaterial) {
    this._secretInt = BigInt("0x" + bytesToHex(secretMaterial));
    this._x1 = null;
    this._x2 = null;
    this._X1 = null;
    this._X2 = null;
    this._X3 = null;
    this._X4 = null;
    this._Xs = null;
  }

  writeRound1() {
    this._x1 = randomScalar();
    this._x2 = randomScalar();
    this._X1 = pointMul(this._x1, G);
    this._X2 = pointMul(this._x2, G);
    return concatBytes(
      kkpWrite(G, this._x1, this._X1, "client", this._secretInt),
      kkpWrite(G, this._x2, this._X2, "client", this._secretInt)
    );
  }

  readRound1(payload) {
    let offset = 0;
    [this._X3, offset] = kkpRead(G, "server", payload, offset, this._secretInt);
    [this._X4, offset] = kkpRead(G, "server", payload, offset, this._secretInt);
    if (offset !== payload.length) throw new ProtocolError("extra bytes found in round1 payload");
  }

  writeRound2() {
    if ([this._x1, this._x2, this._X1, this._X3, this._X4].some((x) => x == null)) {
      throw new ProtocolError("round1 must complete before round2");
    }
    const ga = pointAdd(this._X1, this._X3, this._X4);
    const xc = (this._x2 * this._secretInt) % ORDER;
    const xcPoint = pointMul(xc, ga);
    return kkpWrite(ga, xc, xcPoint, "client", this._secretInt);
  }

  readRound2(payload) {
    if ([this._X1, this._X2, this._X3].some((x) => x == null)) {
      throw new ProtocolError("round1 state is incomplete");
    }
    let offset = 0;
    let groupBytes;
    [groupBytes, offset] = readExact(payload, offset, GROUP_TLS_NAMED_CURVE_SECP256R1.length);
    if (bytesToHex(groupBytes) !== bytesToHex(GROUP_TLS_NAMED_CURVE_SECP256R1)) {
      throw new ProtocolError("unexpected EC group in server round2");
    }
    const gb = pointAdd(this._X1, this._X2, this._X3);
    [this._Xs, offset] = kkpRead(gb, "server", payload, offset, this._secretInt);
    if (offset !== payload.length) throw new ProtocolError("extra bytes found in round2 payload");
  }

  deriveSharedKey() {
    if ([this._x2, this._X4, this._Xs].some((x) => x == null)) {
      throw new ProtocolError("round2 must complete before shared key derivation");
    }
    const x2s = (this._x2 * this._secretInt) % ORDER;
    let kPoint = pointMul(this._x2, pointSub(this._Xs, pointMul(x2s, this._X4)));
    if (kPoint.equals(Point.ZERO)) throw new ProtocolError("derived shared point is infinity");
    const x = kPoint.toAffine().x;
    const xb = hexToBytes(x.toString(16).padStart(64, "0"));
    return sha256(xb);
  }
}

export function derivePinKey(pin, sn, version) {
  if (pin.length !== 8 || !/^\d{8}$/.test(pin)) throw new ProtocolError("PIN must be exactly 8 digits");
  const salt = te(`${sn}${version}PBKDF2`);
  return pbkdf2(sha256, te(pin), salt, { c: PBKDF2_ITERATIONS, dkLen: PIN_DERIVED_LEN });
}

export function hkdfSha256(ikm, length, info, salt = null) {
  // Match cryptography HKDF: salt=None → HashLen (32) zero bytes for SHA-256
  const s = salt == null ? new Uint8Array(32) : salt;
  return hkdf(sha256, ikm, s, info, length);
}

export function deriveLtk(sharedKey, deviceNonce, clientNonce, sn, version) {
  const salt = concatBytes(deviceNonce, clientNonce);
  const info = te(`${sn}${version}LTK`);
  return hkdfSha256(sharedKey, SESSION_KEY_LEN, info, salt);
}

export function deriveSessionKey(ltk, deviceNonce, clientNonce, sn, version) {
  const salt = concatBytes(deviceNonce, clientNonce);
  const info = te(`${sn}${version}session`);
  return hkdfSha256(ltk, SESSION_KEY_LEN, info, salt);
}

export function deriveBroadcastKey(ltk, deviceNonce, clientNonce, sn, version) {
  const salt = concatBytes(deviceNonce, clientNonce);
  const info = te(`${sn}${version}broadcast`);
  return hkdfSha256(ltk, SESSION_KEY_LEN, info, salt);
}

export function deriveNonceBase(first, second, label) {
  // Crypto doc §3.6.2: salt=∅ — cryptography None == 32 zero bytes
  return hkdfSha256(concatBytes(first, second), SESSION_NONCE_LEN, te(label), null);
}

export function inferSn(explicitSn, deviceName) {
  if (explicitSn && String(explicitSn).trim()) return String(explicitSn).trim();
  const name = (deviceName || "").trim();
  const pulse = /^Pulse-([0-9A-Fa-f]{12})$/i.exec(name);
  if (pulse) return pulse[1].toUpperCase();
  if (name.includes("-")) return name.split("-").slice(1).join("-").trim();
  throw new ProtocolError("SN is required (12 hex) or device name MODEL-SN");
}


/** Matter 11-digit manual pairing code → 8-digit setup PIN (Verhoeff-checked). */
export function pinFromManualPairingCode(code11) {
  const s = String(code11 || "").replace(/\D/g, "");
  if (s.length === 8 && /^\d{8}$/.test(s)) return s; // already PIN
  if (!/^\d{11}$/.test(s)) throw new ProtocolError("pairing code must be 11 digits (or 8-digit PIN)");
  const body = s.slice(0, 10);
  const check = s.slice(10);
  if (verhoeffCheckDigit(body) !== check) throw new ProtocolError("pairing code checksum invalid");
  const first = Number(body[0]);
  const middle = Number(body.slice(1, 6));
  const end = Number(body.slice(6, 10));
  const pin = ((end << 14) | (middle & 0x3fff)) >>> 0;
  if (pin < 1 || pin > 99999998) throw new ProtocolError("decoded PIN out of range");
  return String(pin).padStart(8, "0");
}

function verhoeffCheckDigit(num) {
  const d = [
    [0,1,2,3,4,5,6,7,8,9],[1,2,3,4,0,6,7,8,9,5],[2,3,4,0,1,7,8,9,5,6],[3,4,0,1,2,8,9,5,6,7],
    [4,0,1,2,3,9,5,6,7,8],[5,9,8,7,6,0,4,3,2,1],[6,5,9,8,7,1,0,4,3,2],[7,6,5,9,8,2,1,0,4,3],
    [8,7,6,5,9,3,2,1,0,4],[9,8,7,6,5,4,3,2,1,0],
  ];
  const p = [
    [0,1,2,3,4,5,6,7,8,9],[1,5,7,6,2,8,3,0,9,4],[5,8,0,3,7,9,6,1,4,2],[8,9,1,6,0,4,3,5,2,7],
    [9,4,5,3,1,2,6,8,7,0],[4,2,8,6,5,7,3,9,0,1],[2,7,9,3,8,0,6,4,1,5],[7,0,4,6,9,1,3,2,5,8],
  ];
  const inv = [0,4,3,2,1,5,6,7,8,9];
  let c = 0;
  const chars = [...String(num)].reverse();
  for (let i = 0; i < chars.length; i++) c = d[c][p[(i + 1) % 8][Number(chars[i])]];
  return String(inv[c]);
}

export class SessionState {
  constructor({
    protocolVersion,
    sn,
    clientNonce,
    deviceNonce,
    ltk,
    sessionKey,
    txNonceBase,
    rxNonceBase,
    broadcastKey = null,
  }) {
    this.protocolVersion = protocolVersion;
    this.sn = sn;
    this.clientNonce = clientNonce;
    this.deviceNonce = deviceNonce;
    this.ltk = ltk;
    this.sessionKey = sessionKey;
    this.txNonceBase = txNonceBase;
    this.rxNonceBase = rxNonceBase;
    this.broadcastKey = broadcastKey;
    this.txCounter = 1;
    this.rxCounter = 0;
  }
}

export function encryptEnvelope(session, plaintextObj) {
  const plain = te(JSON.stringify(plaintextObj));
  const nonce = concatBytes(session.txNonceBase, u32be(session.txCounter));
  const blob = ccmEncrypt(session.sessionKey, nonce, plain, CCM_TAG_LEN, new Uint8Array(0));
  const ct = blob.slice(0, blob.length - CCM_TAG_LEN);
  const tag = blob.slice(blob.length - CCM_TAG_LEN);
  const envelope = {
    nonce: session.txCounter,
    ct: b64encode(ct),
    tag: b64encode(tag),
  };
  session.txCounter += 1;
  return envelope;
}

export function decryptEnvelope(session, envelope) {
  const nonceCounter = Number(envelope.nonce);
  if (nonceCounter <= session.rxCounter) {
    throw new ProtocolError(`replay detected: rx_counter=${session.rxCounter}, incoming=${nonceCounter}`);
  }
  const nonce = concatBytes(session.rxNonceBase, u32be(nonceCounter));
  const ct = b64decode(envelope.ct);
  const tag = b64decode(envelope.tag);
  const plain = ccmDecrypt(session.sessionKey, nonce, concatBytes(ct, tag), CCM_TAG_LEN, new Uint8Array(0));
  session.rxCounter = nonceCounter;
  return JSON.parse(td(plain));
}

export function randomClientNonce() {
  return randomBytes(SESSION_NONCE_LEN);
}

/** Self-check vs spec/ble-secured-test-vectors.json (made-up PIN 12345678 / SN AABBCCDDEEFF). */
export function selfCheckPinKey() {
  const k = derivePinKey("12345678", "AABBCCDDEEFF", "BT_Crypto_V1");
  const expect = "d129e243e1aa38bcb3a86d0bac57d296f452615f81d26496c27784728a531114";
  if (bytesToHex(k) !== expect) {
    throw new ProtocolError(`PBKDF2 mismatch: got ${bytesToHex(k)}`);
  }
  return true;
}

/** Normalize manufacturer blob to 26-byte long form (FF FF …) or null. */
export function normalizeAdvManufacturer(raw) {
  if (!raw || !(raw instanceof Uint8Array)) return null;
  if (raw.length === ADV_MFG_PAYLOAD_LEN && raw[0] === 0xff && raw[1] === 0xff) return raw;
  if (raw.length === ADV_MFG_PAYLOAD_LEN - 2) {
    const out = new Uint8Array(ADV_MFG_PAYLOAD_LEN);
    out[0] = 0xff; out[1] = 0xff;
    out.set(raw, 2);
    return out;
  }
  return null;
}

/** §9.3 decrypt long advertisement with broadcast_key (tag=4). */
export function decryptLongManufacturer(blob26, broadcastKey) {
  if (!blob26 || blob26.length !== ADV_MFG_PAYLOAD_LEN) throw new ProtocolError("bad adv length");
  const ctr = blob26[3] | (blob26[4] << 8) | (blob26[5] << 16) | (blob26[6] << 24);
  const nonce = new Uint8Array(12);
  nonce[8] = (ctr >>> 24) & 0xff;
  nonce[9] = (ctr >>> 16) & 0xff;
  nonce[10] = (ctr >>> 8) & 0xff;
  nonce[11] = ctr & 0xff;
  const ct = blob26.slice(7, 7 + ADV_PLAIN_LEN);
  const tag = blob26.slice(7 + ADV_PLAIN_LEN, ADV_MFG_PAYLOAD_LEN);
  const plain = ccmDecrypt(broadcastKey, nonce, concatBytes(ct, tag), ADV_CCM_TAG_LEN, new Uint8Array(0));
  return { counter: ctr >>> 0, ctrl: blob26[2], plain };
}

export function parseLongAdvFields(ctrl, plain15) {
  if (!plain15 || plain15.length !== ADV_PLAIN_LEN) throw new ProtocolError("adv plaintext must be 15 bytes");
  const product = ctrl & 0x03;
  const phase = (ctrl >> 2) & 0x03;
  const version = (ctrl >> 4) & 0x07;
  const gattUp = !!(ctrl & 0x80);
  const phaseName = ({ 0: "A/L1", 1: "B/L2", 2: "C" })[phase] || String(phase);
  const productName = ({ 0: "other", 1: "1P", 2: "2ch", 3: "3P" })[product] || String(product);
  const u16 = (o) => plain15[o] | (plain15[o + 1] << 8);
  const u32 = (o) => (plain15[o] | (plain15[o + 1] << 8) | (plain15[o + 2] << 16) | (plain15[o + 3] << 24)) >>> 0;
  let raw24 = plain15[4] | (plain15[5] << 8) | (plain15[6] << 16);
  if (raw24 & 0x800000) raw24 -= 0x1000000;
  return {
    ctrl,
    version,
    gatt_installed: gattUp,
    product: productName,
    phase: phaseName,
    phase_idx: phase,
    V: Math.round(u16(0) / 10 * 10) / 10,
    I: Math.round(u16(2) / 100 * 1000) / 1000,
    P: Math.round(raw24 / 1000 * 1000) / 1000,
    FE: Math.round(u32(7) / 100 * 100) / 100,
    RE: Math.round(u32(11) / 100 * 100) / 100,
    counter: undefined,
  };
}
