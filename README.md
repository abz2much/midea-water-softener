# Midea Water Softener — Home Assistant Integration

Custom Home Assistant integration for the **Midea QS2476-90** water softener (9 L Grey). Communicates exclusively via the MSmartHome cloud API — no local LAN access is required.

## Features

### Sensors

| Entity | Unit | Description |
|---|---|---|
| Remaining Soft Water | L | Soft water available before the next regeneration |
| Flow Rate | L/min | Current water flow through the device |
| Remaining Salt | % | Estimated salt level remaining in the brine tank |
| Salt Days Remaining | days | Predicted days until salt runs out |
| Device Status | — | Current state: `normal`, `standby`, or `regenerating` |
| Total Water Consumption | L | Cumulative water processed (total increasing) |
| Daily Average Water Consumption | L | Rolling daily average consumption |

### Controls

| Entity | Type | Description |
|---|---|---|
| Soft Water | Switch | Enable or disable the softening process |
| Inlet | Switch | Open or close the water inlet valve |
| Anti-Leakage Reminder | Switch | Enable or disable the leakage alert feature |
| Hardness Setting | Number (0–2000 ppm, step 5) | Set target water hardness |
| Regeneration Interval | Number (1–99 days) | Days between scheduled regeneration cycles |
| Regeneration Time | Time | Daily time at which scheduled regeneration runs |
| Regenerate Now | Button | Trigger an immediate regeneration cycle |

## Requirements

- Home Assistant 2024.1 or newer
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

## Notes

- The integration polls the MSmartHome cloud. A stable internet connection is required; local LAN communication is not supported.
- All write operations (switches, numbers, time, button) send commands through the cloud and trigger an immediate poll to refresh state.
- The session is established once at startup and reused across poll cycles. If the session expires the integration will re-authenticate automatically on the next request failure.
