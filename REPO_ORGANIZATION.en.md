[中文](REPO_ORGANIZATION.zh-CN.md)

# bt-open-wifi-apis: repository layout and conventions

> Notes for people, and working rules for AI.  
> Published entry point: [SPM/SDM Open Wi-Fi API Overview](https://docs.bituo-technik.com/device-api/spm-sdm-open-wi-fi-api-overview)  
> Document version: 2026-10. Status: first complete pass. Plaintext and secured BLE are in place, and so are the Wi-Fi overview, mDNS, Modbus TCP, HTTP, WebSocket, MQTT, UDP, telemetry format, and error codes. They were checked against firmware source; differences are listed under "Open points" in the [CHANGELOG](CHANGELOG.en.md).

---

## 0. One-minute answers

| Question | Answer |
|----------|--------|
| One repository per API? | **No.** One repository, one directory per channel. |
| Public or private? | **Private** (`bituo-technik/bt-open-wifi-apis`). Partners get access when invited. It is not open to everyone. |
| What goes in? | Integrator-facing API docs (Chinese and English), demo tools, and machine-readable `spec/`. |
| What stays out? | ESP32 **firmware source**, production keys, and any real device's PIN / LTK / client cache file. |
| Both BLE channels share one business JSON. How do we maintain that? | **One shared document** in `docs/ble-common/`. Each channel document describes only its own transport. See §3. |
| How does this relate to Gitbook? | This repo is the source of truth. Gitbook is the publishing surface: paste a generated page from `dist/`, or sync from `docs/SUMMARY.md`. |
| How are firmware branches represented? | As a matrix (Basic / Basic+ / Lite / Pro). Do not split the repo by branch. |
| How is language handled on entry pages? | The filename people look for (`README.md` and the others) is a language choice. The body lives in `*.zh-CN.md` and `*.en.md`. A page does not mix the two languages. |

---

## 1. Product facts (from the overview)

Capabilities follow the **firmware branch**:

| Branch | Hardware lean | BLE | Wi-Fi / TLS | Lifecycle when the docs were written |
|--------|---------------|-----|-------------|--------------------------------------|
| Basic | SPM/SDM (8685) | Plaintext `A002` | Plaintext HTTP and similar; no HTTPS | NRND |
| Basic+ | SDM01 (8685) | Plaintext `A002` | About **1** TLS slot at most | NRND |
| Lite | SPM/SDM (8685) | Secured `A003` | MQTT TLS on the Wi-Fi side; HTTP / Modbus / WS have no TLS | Active |
| Pro | SDM01 Gen2 (C6) | Secured `A003` | About **2** TLS slots at most; HTTPS exists | Active |

Docs and tools must say whether a branch supports a feature. Do not assume every device has every API.

### Boundary with the firmware repository

```text
[private] ESP firmware repo     ← implementation, NVS, build, production
            ↑ compare locally in a second window; no submodule, no copied source
[private] bt-open-wifi-apis    ← protocol docs + demo tools + spec
            ↓ copy / sync
[published] docs.bituo-technik.com
```

---

## 2. Directory layout

```text
bt-open-wifi-apis/
├── README.md                      language choice (GitHub home page)
├── README.zh-CN.md / README.en.md home-page body
├── AGENTS.md                      AI entry and hard rules (Chinese source of truth; tools load this filename)
├── AGENTS.en.md                   English body of the same rules; if they disagree, AGENTS.md wins
├── REPO_ORGANIZATION.md           language choice
├── REPO_ORGANIZATION.zh-CN.md     Chinese body
├── REPO_ORGANIZATION.en.md        this file
├── CHANGELOG.md                   language choice
├── CHANGELOG.zh-CN.md / .en.md    doc and tool changes, with the firmware version they were checked against
│
├── docs/
│   ├── README.md                  language choice
│   ├── README.zh-CN.md / .en.md   reading paths
│   ├── SUMMARY.md                 Gitbook contents (Chinese tree and English tree)
│   ├── overview/                  Wi-Fi overview: branches, capability matrix, TLS slots, how to choose
│   ├── mdns/ modbus-tcp/ http/    each Wi-Fi channel: connection, framing, limits, examples, troubleshooting
│   │   websocket/ mqtt/ udp/
│   ├── reference/                 telemetry format and error codes (shared, one document each)
│   ├── ble-common/                business commands shared by every channel (zh-CN / en)
│   ├── ble-plaintext/             plaintext BLE transport (Basic / Basic+, A002)
│   └── ble-secured/               secured BLE transport (Lite / Pro, A003) + protocol reference
│
├── tools/
│   ├── README.md                  language choice; body in README.zh-CN.md / README.en.md
│   ├── lan/                       Wi-Fi channel CLIs + fake meter (README split the same way)
│   ├── ble-plaintext/             Web Bluetooth page + Windows tool
│   └── ble-secured/               same, plus the offline single-file page and the bundle script
│
├── spec/                          machine-readable: command list, Modbus map, HTTP / MQTT / WS / UDP / mDNS manifests, error codes, test vectors
├── scripts/                       bundle generation, link checks, test-vector checks
└── dist/                          generated output (not committed)
```

### 2.1 What each directory is for

| Path | For people | For AI / programs |
|------|------------|-------------------|
| `docs/**` | Reading, and the Gitbook body | The primary source for implementing a client |
| `tools/<channel>/` | Manual tests, demos, on-site provisioning | Behavior samples; the protocol still comes from docs |
| `spec/ble-plain-api.json` | Usually unread | Command table; **must match `docs/ble-common`** |
| `spec/ble-secured-test-vectors.json` | Self-test while implementing the secured channel | Known-answer vectors (PBKDF2 / HKDF / AES-CCM / 11-digit pairing code) |
| `spec/modbus-tcp-map.json` | Usually unread | Register map (three phase layouts); **`check_docs.py` compares every address with both documents** |
| `spec/{http-endpoints,mqtt-api,websocket-api,udp-api,mdns-discovery,capabilities}.json` | Usually unread | Ports, paths, limits, and naming rules per channel. The docs are authoritative; the manifests are for programs |
| `spec/error-codes.json` | Usually unread | Subcodes and fixed codes; `check_docs.py` checks that both documents contain them |
| `spec/udp-aes-test-vector.json` | Self-test while implementing UDP decryption | AES-CCM vector generated from the documented parameters, not from a device capture |
| `dist/` | Paste into Gitbook, or hand to an AI | One file containing the transport layer plus the business layer |

---

## 3. How the shared business JSON is maintained (the most important rule in this repo)

After the transport layer is unwrapped, the business JSON of the plaintext channel and the secured channel is **identical**: the same `wifi` / `model` / `mqtt` / `modbus` / `udp` commands, the same snapshot fields, the same error codes. Copying that table into both channel documents drifts (A gets updated, B does not). So:

| Content | Where | How many copies |
|---------|-------|-----------------|
| Business commands, fields, responses, snapshot keys, business error codes, appendices (functionMap bits / model short keys / infrequent error codes) | `docs/ble-common/ble-business-api.*.md` | **One** (a Chinese file and an English file) |
| UUIDs, the gate (`pass` or the handshake), envelope, reconnect, MTU, platform notes, channel-specific errors | `docs/ble-plaintext/` or `docs/ble-secured/` | Each channel writes its own |
| J-PAKE / ZKP binary layout, advertising manufacturer data | `docs/ble-secured/crypto-protocol.*.md` | Provided by the firmware team. **If there is a conflict, this document wins** |

Rules:

1. A business-command change goes only into `ble-common`. Channel documents **do not** copy the command table; they link to it.
2. Channel differences may appear only in the §1.2 difference table of `ble-common`, and only when they are real transport differences (for example whether `read` carries `continue`).
3. A new command updates `ble-common` §3, the §4 index, `spec/ble-plain-api.json`, and both tools' `command_help` when they need it.
4. A channel document still has to be enough when someone hands **that one document** to an AI. `scripts/build_bundles.py` therefore concatenates **the channel document + the shared document (+ the crypto protocol reference)** into one file under `dist/`.

> A full copy inside every channel document means every edit is done four times, and a missed edit is invisible.
> A single document where each channel page only lists differences fails the reader who received only one file. The `dist/` bundle covers that case without hand-maintaining two full channel documents.

---

## 4. How to write a single-channel document (template)

1. Quick start (smallest closed loop, plus a runnable example or pseudocode)  
2. Prompt for an AI (copy the whole block)  
3. Scope (which firmware branches)  
4. Session / authentication / discovery (UUIDs, unlock or handshake, reconnect)  
5. Command or resource reference (real request / response examples)  
6. Error codes  
7. Implementation checklist + acceptance checks  
8. Where the demo tool is  
9. Security notes  

Conventions:

- Command names, field names, and device `msg` strings **stay in English**.  
- One Chinese file and one English file: `*.zh-CN.md` / `*.en.md`, with matching section numbers. Do not mix the two languages on one page.  
- Filenames people open directly (`README.md`, `docs/README.md`, `tools/**/README.md`, `CHANGELOG.md`, and `REPO_ORGANIZATION.md` for this document) contain only the language choice. The body is the `.zh-CN.md` and `.en.md` next to them.  
- `AGENTS.md` is the exception. Coding tools load that filename automatically, so the root `AGENTS.md` must stay a complete Chinese document. It must not shrink to two links. The English body is `AGENTS.en.md`. If the two disagree, `AGENTS.md` wins.  
- Do not state an uncertain fact as certain. Check it with a firmware colleague, or record it under "Open points" in the CHANGELOG.  
- PIN / SN / LTK values in examples are fictional. Do not paste data from a real device.

---

## 5. Where tools live

| Channel | Form | Notes |
|---------|------|-------|
| Plaintext BLE | Chrome Web Bluetooth + Windows PyQt6 / bleak | UI switches between Chinese and English |
| Secured BLE | Same, plus an offline single-file page | Developers use the split files; customers use the `*.offline.html` single file |
| Wi-Fi channels | `tools/lan/` CLI scripts (mostly the Python standard library) + the fake meter `mock_device.py` | A browser talking to the device hits CORS and mixed-content limits, so these are command-line tools. The fake meter follows the documented behavior only |

Tools must match the documented protocol. The UI may be Chinese or English. On-device JSON and `msg` are not translated. Each tool directory's `README.md` is a language-choice page as well.

---

## 6. Private repository and access

- Default branch `main`. Partners get **read-only** access as a GitHub Team member or outside collaborator. Do not grant write access.  
- Local caches such as `tools/ble-secured/ble_crypto_client_cache.json` are in `.gitignore` and **must not be committed**.  
- Do not paste the repository URL into a public issue or forum. External delivery is a single file from `dist/`, or a Gitbook page.  
- Before any future public release, walk through the checklist in §7, especially whether the secured protocol reference is allowed to be public.

---

## 7. Maintainer checklist

- [ ] The repo contains no firmware source, keys, real-device PIN / LTK, or cache files  
- [ ] `docs/ble-common` and `spec/ble-plain-api.json` list the same commands  
- [ ] Chinese and English documents match in outline and content (`scripts/check_docs.py` checks heading counts and links)  
- [ ] Entry pages (READMEs, this document, CHANGELOG, AGENTS) are updated in both languages  
- [ ] `scripts/check_test_vectors.py` and `node scripts/check_test_vectors.mjs` both pass  
- [ ] After a web-console change, `*.offline.html` is regenerated  
- [ ] Both CHANGELOG languages name the firmware version the change was checked against  

### Comparing with local firmware (optional)

To check protocol behavior: search the firmware repo for the `cmd` string or the UUID, then write the conclusion back into the API docs. Do not generate firmware from the docs, and do not copy firmware source into this repo.

---

## 8. Suggested order of work

1. ~~Plaintext BLE~~ and ~~secured BLE~~ are migrated  
2. ~~MQTT, HTTP, mDNS, Modbus TCP, WebSocket, UDP, overview, telemetry format, and error codes~~ have a first version written from firmware source  
3. Confirm the CHANGELOG "Open points" on a real device (locate register, Modbus connection behavior, which branches get UDP AES, and the rest), then update the docs  
4. When needed, turn on Gitbook Git Sync (project directory `docs/`, contents from `docs/SUMMARY.md`) and point the old published pages at this repo's version  
5. When the relay (SRS) product line is added, open `docs/srs/` and matching `spec/` entries. Do not mix them into the existing meter pages  

---

## 9. Terms

| Term | Meaning |
|------|---------|
| Open Wi-Fi | The SPM / SDM ESP product-family position: local and cloud protocols opened to integrators |
| Firmware branch | Basic / Basic+ / Lite / Pro |
| Channel | One of BLE / HTTP / MQTT / WS / UDP / Modbus TCP / mDNS |
| Plaintext BLE | Service `A002`, UTF-8 JSON, no application-layer encryption |
| Secured BLE | Service `A003`, EC J-PAKE handshake + AES-128-CCM envelope |
| Business JSON | Commands and responses after the transport (unlock / envelope) is removed. The same on both BLE channels |
| Source of truth | `docs/` in this repo, not a verbal description and not a Gitbook page edited only online |
