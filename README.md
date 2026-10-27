# Midea Water Softener — Home Assistant Integration

Custom Home Assistant integration for the **Midea QS2476-90** water softener (9 L Grey). It talks to the softener over your home network (local control) when you give it the softener's IP address, and uses the MSmartHome cloud as the fallback. Without an IP address it uses the cloud only.

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
- The `pycryptodome` and `midea-local` Python packages (installed automatically)

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
7. Enter the softener's IP address for local control, or leave it blank to use the cloud only. See [Local control](#local-control).

To change the poll interval later, open the integration and choose **Configure**. If your Midea password changes, Home Assistant asks for the new one. Enter it there; you do not need to set up the integration again.

## Local control

With local control, Home Assistant talks to the softener directly over your home network on port 6444, instead of going through Midea's cloud. It is faster and keeps working when the cloud is down.

- **Setup:** enter the softener's IP address at the last step. The integration gets the softener's local key from your Midea account, tests a connection, and saves it. If either step fails, the form shows an error; fix the address or leave it blank to carry on with the cloud only.
- **Give the softener a fixed IP address** in your router, so the address doesn't change.
- **The cloud is the fallback.** Every request goes local first. If the softener can't be reached (refused, timeout, failed handshake or no reply), that request goes through the cloud instead. The log shows one line when the integration switches to the cloud and one when local works again.
- **Commands are never sent twice.** If a command was sent locally but no reply came back, the softener may already have acted on it, so it is not repeated through the cloud. Home Assistant shows an error instead. Status polls always fall back.
- **Cloud down at startup:** with local control set up, the integration still starts if the cloud can't be reached. It logs in to the cloud later, when it first needs it.
- **If the `midea-local` library can't be used** (missing, or changed by an update), local control turns itself off with one warning in the log, and the integration carries on using the cloud only.

### Add local control to an existing setup

1. Go to **Settings → Devices & Services → Midea Water Softener**.
2. Open the three-dot menu on the entry and choose **Reconfigure**.
3. Enter the softener's IP address and submit. The integration uses the account and password it already has to get the local key, tests the connection, saves it and reloads.

To go back to the cloud only, reconfigure again and leave the IP address blank.

## Notes

- Without local control, the integration polls the MSmartHome cloud, so a stable internet connection is required.
- All write operations (switches, numbers, time, button) use the same path as polls (local first, then the cloud) and trigger an immediate poll to refresh state. If a command fails, Home Assistant shows an error and does not poll.
- The cloud session is established once at startup and reused across poll cycles. If the cloud says the session has expired, the integration logs in again once and retries that request once. If that also fails, the request fails with an error and the next poll tries again. A wrong password stops setup with a clear error. An unreachable cloud at startup also does, unless local control is set up.
- Diagnostics never include the local token or key.

## Credits

The cloud login and message protocol in this integration are based on:

- [sususweet/midea_auto_cloud](https://github.com/sususweet/midea_auto_cloud) (Apache-2.0)
- [georgezhao2010/midea_ac_lan](https://github.com/georgezhao2010/midea_ac_lan) (MIT)

Local control uses [midea-lan/midea-local](https://github.com/midea-lan/midea-local) (MIT) for the LAN handshake and encryption.

This is an unofficial integration. It is not affiliated with, endorsed by or supported by Midea.
