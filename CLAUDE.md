# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Custom Home Assistant integration for the Midea QS2476-90 water softener (9L Grey). Installed via HACS. Communicates exclusively via Midea's cloud API (no LAN) using MSmartHome credentials.

Device type: `0xED`. Query body type: `0x09`. Protocol file: `T_0000_ED_10008619_2024092001.lua`.

## Architecture

```
custom_components/midea_water_softener/
├── __init__.py          # async_setup_entry / async_unload_entry
├── manifest.json
├── const.py             # all shared constants and attribute key names
├── security.py          # MSmartSecurity: AES, HMAC, password hashing
├── cloud.py             # MSmartHomeCloud: login, list_appliances, send_command
├── message.py           # build_query, build_set_*, parse_response, DeviceStatus
├── device.py            # WaterSoftenerDevice: wraps cloud + message protocol
├── coordinator.py       # WaterSoftenerCoordinator (DataUpdateCoordinator)
├── config_flow.py       # step_user (credentials) → step_device (selection)
├── sensor.py
├── switch.py
├── number.py
├── time.py
└── button.py
```

**Data flow:** `coordinator` polls `device.refresh_status()` → `device` calls `cloud.send_command(build_query())` → response bytes decoded by `parse_response()` → dict of attributes keyed by `ATTR_*` constants from `const.py` → entities read from `coordinator.data`.

**Write flow:** entity calls `device.set_*(...)` → `device` calls `cloud.send_command(build_set_*(...))` → `coordinator.async_request_refresh()`.

## Protocol (message.py)

Byte indices below are Lua 1-indexed converted to Python 0-indexed (`byteN → body[N-1]`):

| Field | Body offset | Formula |
|---|---|---|
| `flow_rate` | body[11] | byte12 |
| `soft_water_remaining` | body[12:14] | (body[13]<<8)+body[12] |
| `water_consumption_raw` | body[14:16] | (body[15]<<8)+body[14], units unconfirmed |
| `salt_remaining` | body[16] | byte17 (%) |
| `salt_days_remaining` | body[18:20] | (body[19]<<8)+body[18] |
| `water_hardness` | body[20:22] | (body[21]<<8)+body[20], ppm |
| `regen_interval` | body[22] | days |
| `regen_hour/min` | body[23], body[24] | |
| `regen_seconds_remaining` | body[25:27] | |
| `water_consumption_total` | body[30:34] | 32-bit LE, in L |
| `water_consumption_daily_avg` | body[42:44] | |
| `flags` | body[60] | bit0=soften, bit2=anti_leakage, bit3=leak, bit4=inlet, bit5=standby, bit7=regenerating |
| `error` | body[61] | |

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

## Working Style

- Ask clarifying questions before starting any large task.
- Batch related file changes together.
- Be concise — no commentary after completing a task unless something important needs flagging.
- No placeholder or example code — only real, working code.
