# Error Code Reference

> Status: first release | Applies to: all branches, all channels | Based on the firmware source `userApiErrorCodes.h` and the configuration subcode table

## 1. How to read `code`

When a JSON response on any channel **fails**, an integer `code` is added next to `msg` and `event`. A **successful response has no `code`**, so check `ok` (or `result` in the legacy format) first to decide success.

| code | Meaning |
|------|---------|
| absent | Success |
| `-1` | The firmware gave this failure no specific number; judge from `ok` and `msg` |
| 1000 to 1999 | BLE channel |
| 2000 to 2999 | HTTP / HTTPS channel |
| 3000 to 3999 | MQTT channel |
| 4000 to 4999 | WebSocket channel |

Failures without any `code` exist too: for example an MQTT command above 1024 bytes or with a JSON parse error is simply dropped and nothing is sent back.

**Always read `msg` and `event` together with `code`.** Configuration errors are "channel base + subcode", and fixed codes live in the same ranges, so numbers collide (see [Section 6](#6-collisions-and-how-to-tell-them-apart)). `msg` is the English original from the device, and matching on it is the most reliable.

## 2. Configuration subcodes

When a business command (`wifi`, `mqtt`, `udp`, ...) fails, its English `msg` maps to a subcode `s`, and `code = channel base + s`: BLE `1000 + s`, HTTP `2000 + s`, MQTT `3000 + s`, WebSocket `4000 + s`.

| s | msg | Description |
|---|-----|-------------|
| 1 | (empty `msg`) | Unclassified failure |
| 2 | `Error password length!` | New password too long |
| 3 | `auth error` | Auth string wrong or wrong length |
| 4 | `bad value` | Invalid numeric parameter (for example report interval) |
| 5 | `unsupported` | Command not supported by this model or branch |
| 6 | `null` | No data for this model (for example no schedule) |
| 7 | `lorawan unsupported` | This model has no LoRaWAN |
| 8 | `lorawan rejoin failed` | LoRaWAN rejoin failed |
| 9 | `lorawan upload failed` | LoRaWAN upload queue failed |
| 10 | `lorawan region password failed` | Region change password wrong |
| 11 | `lorawan region failed` | Region update failed |
| 12 | `lorawan config disabled` | LoRaWAN configuration disabled |
| 13 | `lorawan config save failed` | LoRaWAN configuration save failed |
| 14 | `functionMap error` | Channel combination invalid or over the limit |
| 15 | `unknow cmd` | Unknown command (spelled like this in the firmware) |
| 16 | `Timer not found` | Timer does not exist |
| 17 | `Invalid timer` | Invalid timer parameters |
| 18 | `Error wifi ssid/pass required!` | SSID or password missing |
| 19 | `Error wifi length!` | Wi-Fi parameter length invalid |
| 20 | `Error wifi reset in progress` | Wi-Fi is reconnecting; try again later |
| 21 | `Error mqtt data empty!` | A required MQTT field is empty |
| 22 | `Error length!` | MQTT or other field length error |
| 23 | `cafile error` | Root certificate write flow error |
| 24 | `UDP full` | UDP target list full (5), or IP / port invalid |
| 25 | `UDP not found` | The UDP target to delete does not exist |
| 26 | `Old Password Error` | Old password wrong |
| 27 | `Error name length!` | Name too long |
| 28 | `mda format error` | Register extension data format error |
| 29 | `mda failed` | Register extension processing failed |
| 30 | `minvert data format error` | Inversion configuration format error |
| 31 | `minvert save failed` | Inversion configuration save failed |
| 32 | `minvert data length error` | Inversion configuration length error |
| 33 | `minvert data error` | Inversion configuration data error |
| 34 | `minvert missing data` | Inversion configuration data missing |
| 35 | `bleota no data` | BLE OTA received no data |
| 36 | `bleota err param` | BLE OTA invalid parameters |
| 37 | `bleota err state` | BLE OTA state error (not started or already done) |
| 38 | `bleota err seq` | BLE OTA packet sequence broken; transfer aborted |
| 39 | `bleota err crc` | BLE OTA CRC check failed |
| 40 | `bleota err write` | BLE OTA partition write failed |
| 41 | `bleota err size` | BLE OTA firmware size over the limit |
| 42 | `bleota err unknown` | BLE OTA unknown error |
| 43 | `scan busy` | Wi-Fi scan in progress; cannot trigger again |
| 44 | `scan not ready` | Wi-Fi scan result not ready |
| 45 | `ota mem insufficient` | Not enough memory to upgrade |
| 46 | `Error enablehttps!` | Invalid `enablehttps` parameter (Pro only) |

An English `msg` not in this table that is not an error text usually means success or a neutral hint and has no `code`.

SRS relay products also have switch-extension subcodes 51 (`illegal cmd`), 52 (`Error name!`), 53 (`Error name length!`) with the same formula. SRS products are not covered by this repository.

## 3. BLE fixed error codes (1000s)

| code | msg | Description |
|------|-----|-------------|
| 1000 | `auth error` | Phone auth string does not match the device |
| 1001 | `not authenticated` | Authentication not completed |
| 1002 | `Please unlock` | Unlock first; `event` is `pas` on the write characteristic notification and `read` on the read characteristic |
| 1003 | `Password Error` | BLE password wrong |
| 1004 | `No cmd` | `cmd` missing |
| 1005 | `No data received` | Switch-extension configuration missing parameters |
| 1010 | `secure channel required` | Establish the secured channel first |
| 1011 | `cipher envelope required` | A ciphertext envelope is required |
| 1012 | `decrypt failed` | Decryption failed |
| 1013 | `payload too large` | Decrypted or secured payload too long |
| 1014 | `plain json invalid` | JSON invalid after decryption |
| 1015 | `missing cmd` / `cipher envelope required` | Command missing, or envelope incomplete |
| 1020 | `version failed` | Secured protocol version negotiation failed |
| 1021 | `invalid step` | Reset flow step mismatch |
| 1022 | — | J-PAKE not active when resetting the session |
| 1030 | `no pending round1 response` | No pending Round1 response to fetch |
| 1031 | `client nonce mismatch` | Client nonce mismatch |
| 1032 | `round1 response unavailable` | Round1 response unavailable |
| 1033 | `invalid step` | J-PAKE Round1 step error |
| 1034 | `invalid round1 chunk` | Invalid chunk parameters |
| 1035 | `round1 chunk out of order` | Chunk order error |
| 1036 | `jpake round1 failed` | J-PAKE Round1 failed |
| 1037 | `round1 response prepare failed` | Preparing Round1 response chunks failed |
| 1040 | `invalid step` | J-PAKE Round2 step error |
| 1041 | `jpake round2 failed` | J-PAKE Round2 failed |
| 1045 | `invalid step` | Session nonce phase step error |
| 1046 | `session nonce failed` | Session nonce exchange failed |
| 1047 | `cipher envelope required` / `secure channel required` | Envelope or channel missing in the session state |
| 1050 | `payload too large` | Plaintext write too long |
| 1051 | `invalid secure json` | JSON invalid in secured mode |
| 1060 | `secure encrypt failed` | Encrypting the read characteristic response failed |
| 1061 | `secure auth required` | Read characteristic requires secured authentication first |
| 1080 and up | dynamic English | Specific errors from the lower security module; use what the device returns |

## 4. HTTP / HTTPS fixed error codes (2000s)

| code | msg | Description |
|------|-----|-------------|
| 2000 | `use_https` | Policy requires HTTPS (port 80 returns 403) |
| 2001 | `need token` | A session token is required |
| 2002 | `invalid token` | Token invalid or expired |
| 2003 | `wrong password` | Sign-in password wrong |
| 2004 | `password too long` | Sign-in password too long (limit 16) |
| 2005 | `need signin` | Sign in first |
| 2006 | `no password` | No Web password set (status hint) |
| 2007 | `no password set` | No Web password set (sign-in case) |
| 2008 | `missing newpass` | New password parameter missing |
| 2009 | `bad newpass length` | New password length invalid (1 to 16) |
| 2010 | `old password wrong` | Old password wrong |
| 2011 | `nvs save failed` | Saving the Web password failed |
| 2012 | log file not found (Chinese msg) | Log file does not exist |
| 2020 | `wifi not available!` | No Wi-Fi; cannot download the remote page |
| 2021 | `Error on HTTP request!` | Remote HTTP request failed |
| 2022 | `Error!` | Opening or writing the local page file failed, or another update error |
| 2023 | `download error!` | Remote page download interrupted |
| 2030 | `No text received.` | Certificate upload received no body |
| 2040 | `No data received` | `/save-config` received no body |
| 2041 | `payload too large` | `/save-config` body too long |
| 2050 | `No data received` | `/schedule` received no body (relay) |
| 2051 | `payload too large` | `/schedule` body too long (relay) |
| 2060 | `No data received` | `/switch-config` received no body |
| 2061 | `payload too large` | `/switch-config` body too long |
| 2062 | `No data received` | `/switch-config` lacks `configType` / `cmd` |
| 2070 | `bad json` | `/save-config` JSON cannot be parsed |
| 2071 | `bad json` | `/schedule` JSON cannot be parsed |
| 2072 | `bad json` | `/switch-config` JSON cannot be parsed |
| 2080 | `use HTTP :80 multipart POST /upload` | Upload endpoint misused on HTTPS |
| 2081 | `file open failed` | Opening the certificate file failed |
| 2090 | `path not on HTTPS API` | Path or method does not exist on HTTPS |
| 2091 | `html not found` | No web assets on the device |
| 2095 | `Unknown status!` | OTA status not recognized |
| 2100 | `Error password length!` | BLE password too long |
| 2101 | `Old password error!` | BLE old password wrong |
| 2102 | `Error name length!` | Device name too long |
| 2110 | `Product update failure!` | Online upgrade verify or write failed |
| 2111 | `HTTP get failed!` | Online upgrade download failed |

## 5. MQTT and WebSocket fixed error codes

MQTT fixed codes (3000s; only in the legacy response `{"result":"failed",...}`; failures in the unified format use "3000 + s" from Section 2):

| code | event | Description |
|------|-------|-------------|
| 3001 | `rdata` | Publishing the data report failed |
| 3002 | `wint` | Writing the report interval failed |
| 3010 | `switch-config` | Switch-extension configuration missing type (relay) |
| 3011 | `wifi` | Wi-Fi configuration failed |

WebSocket (4000s, `event` is `error`):

| code | msg | Description |
|------|-----|-------------|
| 4000 | `payload too large` | A single frame is over the length limit |
| 4001 | `invalid json` | The message is not a JSON object |
| 4002 | `json parse error` | JSON syntax error |
| 4003 | `invalid cmd` | Command field missing or empty |

Business commands that go through the unified parser get `code` as "4000 + s" from Section 2.

## 6. Collisions and how to tell them apart

Configuration subcodes run from 1 to 53, and the fixed codes in each channel range reuse those numbers. The same `code` can therefore mean two things, for example:

| code | Meaning A (fixed error) | Meaning B (configuration subcode) |
|------|-------------------------|-----------------------------------|
| 1014 | BLE secured `plain json invalid` | `functionMap error` |
| 1015 | BLE secured `missing cmd` | `unknow cmd` |
| 1020 | BLE `version failed` | `Error wifi reset in progress` |
| 1021 | BLE `invalid step` (reset) | `Error mqtt data empty!` |
| 2002 | HTTP `invalid token` | `Error password length!` |
| 2003 | HTTP `wrong password` | `auth error` |
| 2040 | HTTP `/save-config` has no body | `bleota err write` |
| 2051 | HTTP `/schedule` body too long | SRS `illegal cmd` |

What to do:

1. Use `event` to know which command or endpoint the response belongs to.
2. Match the English `msg`; do not rely on `code` alone.
3. Different channels use different `code` ranges, so they never collide with each other.

## 7. Related pages

- The commands and their success responses are in the [Business Command Reference](../ble-common/ble-business-api.en.md); its Section 6 lists only the common business errors.
- How each channel returns errors: [HTTP](../http/http-api.en.md), [MQTT](../mqtt/mqtt-api.en.md), [WebSocket](../websocket/websocket-api.en.md).
- English `msg` values added by newer firmware: use what the device returns.
