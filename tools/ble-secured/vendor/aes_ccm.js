/**
 * AES-128-CCM (RFC 3610) using @noble/ciphers unsafe AES block ops.
 * Matches cryptography AESCCM: encrypt → ciphertext || tag.
 */
import { unsafe } from "./ciphers/esm/aes.js";

function xorBlock(a, b) {
  const out = new Uint8Array(16);
  for (let i = 0; i < 16; i++) out[i] = a[i] ^ b[i];
  return out;
}

function encryptBlock(key, block) {
  const ek = unsafe.expandKeyLE(key);
  const b = block.slice();
  unsafe.encryptBlock(ek, b);
  return b;
}

/**
 * @param {Uint8Array} key 16 bytes
 * @param {Uint8Array} nonce 7..13 bytes (we use 12)
 * @param {Uint8Array} plaintext
 * @param {number} tagLength 4..16 even; we use 8
 * @param {Uint8Array} [aad]
 */
export function ccmEncrypt(key, nonce, plaintext, tagLength = 8, aad = new Uint8Array(0)) {
  if (key.length !== 16) throw new Error("AES-CCM: key must be 16 bytes");
  if (nonce.length < 7 || nonce.length > 13) throw new Error("AES-CCM: bad nonce length");
  const L = 15 - nonce.length;
  if (tagLength < 4 || tagLength > 16 || tagLength % 2) throw new Error("AES-CCM: bad tag length");
  const M = (tagLength - 2) / 2; // encoded in flags

  // B0 flags: Adata | (M' << 3) | (L-1)
  const flags = (aad.length > 0 ? 0x40 : 0) | (((tagLength - 2) / 2) << 3) | (L - 1);
  const B0 = new Uint8Array(16);
  B0[0] = flags;
  B0.set(nonce, 1);
  // Q: plaintext length in L bytes, big-endian at end
  let q = plaintext.length;
  for (let i = 15; i >= 16 - L; i--) {
    B0[i] = q & 0xff;
    q >>>= 8;
  }

  // CBC-MAC
  let x = encryptBlock(key, B0);
  if (aad.length > 0) {
    // encode aad length
    let aadEnc;
    if (aad.length < 0xff00) {
      aadEnc = new Uint8Array(2 + aad.length);
      aadEnc[0] = (aad.length >> 8) & 0xff;
      aadEnc[1] = aad.length & 0xff;
      aadEnc.set(aad, 2);
    } else {
      aadEnc = new Uint8Array(6 + aad.length);
      aadEnc[0] = 0xff;
      aadEnc[1] = 0xfe;
      aadEnc[2] = (aad.length >>> 24) & 0xff;
      aadEnc[3] = (aad.length >>> 16) & 0xff;
      aadEnc[4] = (aad.length >>> 8) & 0xff;
      aadEnc[5] = aad.length & 0xff;
      aadEnc.set(aad, 6);
    }
    for (let i = 0; i < aadEnc.length; i += 16) {
      const block = new Uint8Array(16);
      block.set(aadEnc.subarray(i, Math.min(i + 16, aadEnc.length)));
      x = encryptBlock(key, xorBlock(x, block));
    }
  }
  for (let i = 0; i < plaintext.length; i += 16) {
    const block = new Uint8Array(16);
    block.set(plaintext.subarray(i, Math.min(i + 16, plaintext.length)));
    x = encryptBlock(key, xorBlock(x, block));
  }
  const tag = x.slice(0, tagLength);

  // CTR encryption
  const A0 = new Uint8Array(16);
  A0[0] = L - 1;
  A0.set(nonce, 1);
  const S0 = encryptBlock(key, A0);
  const encTag = new Uint8Array(tagLength);
  for (let i = 0; i < tagLength; i++) encTag[i] = tag[i] ^ S0[i];

  const ciphertext = new Uint8Array(plaintext.length);
  let counter = 1;
  for (let i = 0; i < plaintext.length; i += 16) {
    const Ai = new Uint8Array(16);
    Ai[0] = L - 1;
    Ai.set(nonce, 1);
    let c = counter++;
    for (let j = 15; j >= 16 - L; j--) {
      Ai[j] = c & 0xff;
      c >>>= 8;
    }
    const Si = encryptBlock(key, Ai);
    const n = Math.min(16, plaintext.length - i);
    for (let j = 0; j < n; j++) ciphertext[i + j] = plaintext[i + j] ^ Si[j];
  }
  const out = new Uint8Array(ciphertext.length + tagLength);
  out.set(ciphertext);
  out.set(encTag, ciphertext.length);
  return out;
}

export function ccmDecrypt(key, nonce, ciphertextAndTag, tagLength = 8, aad = new Uint8Array(0)) {
  if (ciphertextAndTag.length < tagLength) throw new Error("AES-CCM: ciphertext too short");
  const ct = ciphertextAndTag.slice(0, ciphertextAndTag.length - tagLength);
  const encTag = ciphertextAndTag.slice(ciphertextAndTag.length - tagLength);
  const L = 15 - nonce.length;

  const A0 = new Uint8Array(16);
  A0[0] = L - 1;
  A0.set(nonce, 1);
  const S0 = encryptBlock(key, A0);
  const tag = new Uint8Array(tagLength);
  for (let i = 0; i < tagLength; i++) tag[i] = encTag[i] ^ S0[i];

  const plaintext = new Uint8Array(ct.length);
  let counter = 1;
  for (let i = 0; i < ct.length; i += 16) {
    const Ai = new Uint8Array(16);
    Ai[0] = L - 1;
    Ai.set(nonce, 1);
    let c = counter++;
    for (let j = 15; j >= 16 - L; j--) {
      Ai[j] = c & 0xff;
      c >>>= 8;
    }
    const Si = encryptBlock(key, Ai);
    const n = Math.min(16, ct.length - i);
    for (let j = 0; j < n; j++) plaintext[i + j] = ct[i + j] ^ Si[j];
  }

  // Verify tag via CBC-MAC
  const flags = (aad.length > 0 ? 0x40 : 0) | (((tagLength - 2) / 2) << 3) | (L - 1);
  const B0 = new Uint8Array(16);
  B0[0] = flags;
  B0.set(nonce, 1);
  let q = plaintext.length;
  for (let i = 15; i >= 16 - L; i--) {
    B0[i] = q & 0xff;
    q >>>= 8;
  }
  let x = encryptBlock(key, B0);
  if (aad.length > 0) {
    let aadEnc;
    if (aad.length < 0xff00) {
      aadEnc = new Uint8Array(2 + aad.length);
      aadEnc[0] = (aad.length >> 8) & 0xff;
      aadEnc[1] = aad.length & 0xff;
      aadEnc.set(aad, 2);
    } else {
      aadEnc = new Uint8Array(6 + aad.length);
      aadEnc[0] = 0xff;
      aadEnc[1] = 0xfe;
      aadEnc[2] = (aad.length >>> 24) & 0xff;
      aadEnc[3] = (aad.length >>> 16) & 0xff;
      aadEnc[4] = (aad.length >>> 8) & 0xff;
      aadEnc[5] = aad.length & 0xff;
      aadEnc.set(aad, 6);
    }
    for (let i = 0; i < aadEnc.length; i += 16) {
      const block = new Uint8Array(16);
      block.set(aadEnc.subarray(i, Math.min(i + 16, aadEnc.length)));
      x = encryptBlock(key, xorBlock(x, block));
    }
  }
  for (let i = 0; i < plaintext.length; i += 16) {
    const block = new Uint8Array(16);
    block.set(plaintext.subarray(i, Math.min(i + 16, plaintext.length)));
    x = encryptBlock(key, xorBlock(x, block));
  }
  for (let i = 0; i < tagLength; i++) {
    if (x[i] !== tag[i]) throw new Error("AES-CCM: authentication failed");
  }
  return plaintext;
}
