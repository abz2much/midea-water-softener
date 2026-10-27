# Midea Water Softener — Home Assistant Integration

Custom Home Assistant integration for the **Midea QS2476-90** water softener (9 L Grey). Communicates exclusively via the MSmartHome cloud API — no local LAN access is required.

## Features

### Sensors

| Entity | Unit | Description |
|---|---|---|
| Remaining Soft Water | L | Soft water available before the next regeneration |
| Flow Rate | L/min | Current water flow through the device |
| Remaining Salt | % | Estimated salt level remaining in the brine tank |
| Device Status | — | Current state: `normal`, `standby`, or `regenerating` |
| Total Water Consumption | L | Cumulative water processed (total increasing) |
| Days in Use | days | Days the softener has been in use |
| Regeneration Time Remaining | s | Time left in the current regeneration |
| Anti-Leakage Threshold | L | Leak limit set on the softener (read-only) |

### Binary sensors

| Entity | Description |
|---|---|
| Leak Detected | On when the softener reports a leak |

### Controls

| Entity | Type | Description |
|---|---|---|
| Soft Water | Switch | Enable or disable the softening process |
| Inlet | Switch | Open or close the water inlet valve |
| Anti-Leakage Reminder | Switch | Enable or disable the leakage alert feature |
| Hardness Setting | Number (0–2000 ppm, step 5) | Set target water hardness |
| Anti-Leakage Limit | Number (10–2550 L, step 10) | Set the leak volume. Shown under Configuration |
| Regeneration Interval | Number (1–99 days) | Days between scheduled regeneration cycles |
| Regeneration Time | Time | Daily time at which scheduled regeneration runs |
| Regenerate Now | Button | Trigger an immediate regeneration cycle |

## Requirements

- Home Assistant 2025.8 or newer
- A **MSmartHome** account with the water softener already added in the app
- The `pycryptodome` Python package (installed automatically)

## Installation

### Via HACS (recommended)

1. Open HACS → **Integrations** → three-dot menu → **Custom repositories**.
2. Add `https://github.com/abz2much/midea-water-softener` as an **Integration**.
3. Search for **Midea Water Softener** and install it.
4. Restart Home Assistant.

### Manual

1. Download or clone this repository.
2. Copy the `custom_components/midea_water_softener/` folder into your Home Assistant `config/custom_components/` directory.
3. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **Midea Water Softener**.
3. Enter your MSmartHome credentials (email and password).
4. Select the server region (default: MSmartHome Global).
5. Choose your device from the list of discovered appliances.
6. Optionally adjust the poll interval (10–300 seconds, default 30 s).

To change the poll interval later, open the integration and choose **Configure**. If your Midea password changes, Home Assistant asks for the new one. Enter it there; you do not need to set up the integration again.

## Notes

- The integration polls the MSmartHome cloud. A stable internet connection is required; local LAN communication is not supported.
- All write operations (switches, numbers, time, button) send commands through the cloud and trigger an immediate poll to refresh state. If a command fails, Home Assistant shows an error and does not poll.
- The session is established once at startup and reused across poll cycles. If the cloud says the session has expired, the integration logs in again once and retries that request once. If that also fails, the request fails with an error and the next poll tries again. A wrong password or an unreachable cloud at startup stops setup with a clear error.

## Credits

The cloud login and message protocol in this integration are based on:

- [sususweet/midea_auto_cloud](https://github.com/sususweet/midea_auto_cloud) (Apache-2.0)
- [georgezhao2010/midea_ac_lan](https://github.com/georgezhao2010/midea_ac_lan) (MIT)

This is an unofficial integration. It is not affiliated with, endorsed by or supported by Midea.
