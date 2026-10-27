# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Custom Home Assistant integration for the Midea QS2476-90 water softener (9L Grey). Installed via HACS. Talks to the softener over the LAN (port 6444) when the entry has `host`, `token` and `key`, with Midea's MSmartHome cloud API as the fallback. Without those three keys it is cloud only.

Device type: `0xED`. Query body type: `0x09`. Protocol file: `T_0000_ED_10008619_2024092001.lua`.

## Architecture

```
custom_components/midea_water_softener/
├── __init__.py          # async_setup_entry / async_unload_entry
├── manifest.json
├── const.py             # all shared constants and attribute key names
├── security.py          # MSmartSecurity: AES, HMAC, password hashing
├── cloud.py             # MSmartHomeCloud: login, list_appliances, get_keys, send_command
├── local.py             # LocalTransport: LAN handshake + one frame per connection
├── message.py           # build_query, build_set_*, parse_response, DeviceStatus
├── device.py            # WaterSoftenerDevice: local first, cloud fallback, + message protocol
├── coordinator.py       # WaterSoftenerCoordinator (DataUpdateCoordinator)
├── config_flow.py       # step_user (credentials) → step_device (selection) → step_local (IP); reconfigure (IP)
├── diagnostics.py       # redacts credentials, ids, token and key
├── sensor.py
├── switch.py
├── number.py
├── time.py
└── button.py
```

**Data flow:** `coordinator` polls `device.refresh_status()` → `device._request(build_query())` → `local.send()` if configured, else (or on local failure) `cloud.send_command()` → response bytes decoded by `parse_response()` → dict of attributes keyed by `ATTR_*` constants from `const.py` → entities read from `coordinator.data`.

**Write flow:** entity calls `device.set_*(...)` → `device._request(build_set_*(...), write=True)` (same path as reads) → `coordinator.async_request_refresh()`.

**Fallback rules (`device._request`):**
- `LocalNotSent` (refused, timeout before sending, handshake error) → the cloud handles that request, reads and writes alike.
- `LocalNoReply` (frame sent, no reply) → reads fall back to the cloud; writes raise `HomeAssistantError` and are NOT resent, because the softener may already have acted.
- One INFO log line per mode change (local → cloud, cloud → local), never per request.
- Before a cloud fallback, `cloud.ensure_logged_in()` logs in if setup skipped it (cloud down at startup with local configured).
- Both paths failing: polls raise `UpdateFailed`, commands raise `HomeAssistantError`, as in cloud-only mode.

**Setup (`__init__.py`):** builds a `LocalTransport` only when `host`, `token` and `key` are all in `entry.data`. If the cloud login raises `CannotConnect` and local is configured, setup carries on; `InvalidAuth` still raises `ConfigEntryAuthFailed`.

## Protocol (message.py)

Byte indices below are Lua 1-indexed converted to Python 0-indexed (`byteN → body[N-10]`). `body[0]` is the response body type (`0x09`). `parse_response` rejects bodies shorter than 21 bytes.

| Field | Body offset | Formula |
|---|---|---|
| `flow_rate` | body[2] | byte12, L/min |
| `soft_water_remaining` | body[3:5] | body[3] + (body[4]<<8), L; replaced by the 32-bit value at body[21:25] when the body has 25+ bytes |
| `water_consumption_raw` | body[5:7] | body[5] + (body[6]<<8), 100 L units (not in the coordinator data) |
| `salt_remaining` | body[7] | byte17 (%) |
| `leak_threshold` | body[8] | body[8] * 10, L (Lua unit is 10 L) |
| `water_hardness` | body[11:13] | body[11] + (body[12]<<8), ppm |
| `regen_interval` | body[13] | days |
| `regen_hour/min` | body[14], body[15] | |
| `regen_seconds_remaining` | body[16:18] | body[16] + (body[17]<<8) |
| `use_days` | body[18:20] | body[18] + (body[19]<<8) |
| `soft_water_remaining` (32-bit) | body[21:25] | 32-bit LE, in L |
| `water_consumption_total` | body[25:29] | 32-bit LE, in L |
| `flags` | body[51] | bit0=soften, bit2=anti_leakage, bit3=leak_detected, bit4=inlet, bit5=standby, bit7=regenerating |
| `error` | body[52] | raw code; the Lua has no table of meanings |

Set commands use `SET_BODY_TYPE = 0x15` with the EDNewSetParamPack format:
`[param_low, param_high, value, addition_low, addition_high]` prefixed by `[0x01, 0x01]`.

| Control | SetParam | value | addition |
|---|---|---|---|
| soften | 0x0108 | 1/0 | 0 |
| inlet | 0x0200 | 1/0 | 0 |
| anti_leakage | 0x010A | 1/0 | 0 |
| hardness | 0x0100 | 0 | ppm |
| regen_interval | 0x0101 | 0 | days |
| regen_time | 0x0102 | 0 | hour \| (min<<8) |
| regen_now | 0x0103 | 1 | 0 |

In the Lua, the `addition` of `anti_leakage` (0x010A) carries the leak volume, and `value` is the on/off state. The Anti-Leakage Limit number sends litres divided by `LEAK_LIMIT_SET_UNIT_L` (10, unconfirmed) in `addition` and the CURRENT on/off state in `value`; never send `value` 0 just to set a volume. The Lua gives no range or step (min 10 L, max 2550 L (one status byte of 10 L units), step 10 L are our own). The Anti-Leakage Reminder switch still sends `addition` 0.

## Cloud API (cloud.py / security.py)

- **App:** MSmartHome, `APP_ID="1010"`, `APP_KEY="ac21b9f9cbfe4ca5a88562ef25e2b768"`
- **Login flow:** `_re_route()` → `_get_login_id()` → `POST /mj/user/login`
- **Transparent send:** `POST /v1/appliance/transparent/send`
  - Payload bytes → `_bytes_to_dec_string` (comma-separated signed decimals) → AES encrypt (session key/IV) → hex → `order` field
  - Reply: reverse the process
- **Session key setup (`set_aes_keys`):** Login response contains `accessToken` and `randomData` fields that are AES-CBC encrypted. They are decrypted using a temporary key derived as `SHA256(APP_KEY).hexdigest()[:16]` (first 16 hex chars as ASCII bytes) with iv = chars 16-32. The decrypted values become `_aes_key` and `_aes_iv`.
- **Request signing:** `HMAC-SHA256(iot_key + payload_json + random, hmac_key)` where `random = str(int(time.time()))` (seconds). Headers: `"authorization"` (lowercase), `"accesstoken"` (lowercase), `"secretVersion": "1"`.
- **Response parsing:** Success = `int(body["code"]) == 0`, data is in `body["data"]`.
- **`_make_general_data()`:** All requests include `appVersion`, `src`, `format`, `stamp`, `platformId`, `deviceId`, `reqId`, `uid`, `clientType`, `appId`.
- **Fixed key/IV** (integers `13101328926877700970` / `16429062708050928556`): only used for Lua file decryption, NOT for login or device commands.

## Local API (local.py)

- **Library:** `midea-local>=12.2.0` in the manifest, `==12.2.0` in `requirements_test.txt`. 12.2.0 is the version Home Assistant's own Midea integration pins. hassfest rejects both a different version and an exact pin of a package HA depends on, so the manifest gives a minimum and follows HA. Tests stay on the exact version.
- **Safe import:** `local.py` imports midea-local on first use (`_midea_local()`), never at module load; `cloud.py` gets `get_udp_id` through `local.udp_id()`. A failed import, or an `AttributeError`/`TypeError`/`NameError`/`ImportError` while using it (changed API), raises `LocalUnavailable`. Setup checks `unavailable_reason()` in an executor and, if set, logs one WARNING and runs cloud only. At runtime the device sets `_local = None` with one WARNING; a write already sent is still not repeated. The config flow shows `local_unavailable`. Uses its `LocalSecurity` (8370 encode/decode, `tcp_key`) and `PacketBuilder` (the 0x5A5A wrapper). No crypto of our own.
- **Per request:** connect `host:6444` → send `encode_8370(token, 0)` → `tcp_key(reply[8:72], key)` → send `encode_8370(PacketBuilder(device_id, frame).finalize(), 6)` → read until a reply → close. 10 s limit on the whole request. A lock on the transport stops a poll and a command opening two sessions at once (many Midea devices accept only one).
- **Reply:** `decode_8370` the stream, skip heartbeat payload types `0x0001`/`0x1001` and packets of 56 bytes or less, `aes_decrypt(packet[40:-16])` gives the `0xAA` frame. Frames with message type `0x04` (unrequested status report) are skipped; the first other frame is returned.
- **Errors:** every failure (timeout, socket error, midea-local error, malformed packet) maps to `LocalNotSent` before the frame left, `LocalNoReply` after. Messages never contain the token or key.
- **Token and key (`cloud.get_keys`):** `POST /v1/iot/secure/getToken` with `udpid = CloudSecurity.get_udp_id(device_id, method)` for methods 1 and 2, plus `applianceCodes = str(device_id)` (MSmartHome returns 3004 without it). Keep `tokenlist` entries whose `udpId` matches, lowercased. The config flow tests each pair with a status query and saves the first that parses. Unverified against the live cloud: the request uses our own `_make_general_data()`, not midea-local's field set.
- **Config entry keys:** `host`, `token`, `key` (`CONF_HOST`, `CONF_TOKEN`, `CONF_KEY` in `const.py`). A blank IP in the `local` or `reconfigure` step means cloud only; reconfigure with a blank IP removes all three. The IP field uses `suggested_value`, not `default`: the frontend drops a cleared optional field, and a default would put the old IP back.
- **Tests:** `tests/test_local.py` runs a fake softener on 127.0.0.1 using midea-local's own crypto. It needs the `socket_enabled` fixture because the HA test plugin blocks sockets.

## Working Style

- Ask clarifying questions before starting any large task.
- Batch related file changes together.
- Be concise — no commentary after completing a task unless something important needs flagging.
- No placeholder or example code — only real, working code.

## Testing

For new features and bug fixes, use the test-driven-development skill: write the failing test first, and show it failing before writing code.

## Skills

- For Python code and tests, use python-patterns and python-testing. The test-first rule still applies. Don't add a coverage target unless I ask.
