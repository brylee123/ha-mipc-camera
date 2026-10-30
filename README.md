# MIPC Camera for Home Assistant

Local control of compatible MIPC cameras, packaged as a separate HACS custom integration. Requires Home Assistant **2026.10.0 or newer**. This is a beta; camera firmware determines which controls appear.

## Features

| Platform | Supported capabilities |
| --- | --- |
| Camera | JPEG snapshots and local RTMP streaming through Home Assistant |
| Number | Brightness, contrast, saturation, sharpness, speaker/microphone volume, day/night motion sensitivity |
| Switch | Image flip, microphone mute, OSD text/date/time, recording schedule enabled |
| Select | Auto/day/night image mode |
| Text | OSD text content |
| Button | Pan left/right and tilt up/down, explicitly enabled in options |
| Sensor | Firmware, last successful read, storage status and percentage used |
| Binary sensor | Connection health and recording media readiness |

Settings entities are created only when the camera reports an appropriately typed field. Missing fields and unsupported calls do not become invented capabilities. Polling runs every 60 seconds; successful writes refresh state immediately. The first hardware test model is an **f300**, firmware `v5.1.10.1811061306`. Both physical motors were verified with small moves and inverse moves.

## Install

1. Add `https://github.com/brylee123/ha-mipc-camera` as a HACS custom repository, category **Integration**, then download MIPC Camera. Until the beta is merged/released, use the review branch or manual installation.
2. Alternatively, copy **only** `custom_components/mipc_camera` into your Home Assistant configuration directory's `custom_components` folder.
3. Restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → MIPC Camera**.
5. Enter the camera's local hostname/IP (optional port), and its **Device/Admin password**. Your MIPC cloud account password is a different credential. Leave username blank to use the device serial automatically.
6. Open the integration options to enable PTZ after confirming the camera has motors. Streaming can be disabled or changed between camera profile tokens `p0`–`p3`.

Home Assistant must be able to reach the camera directly. Reserve its LAN address. No MIPC cloud account is used and there is no cloud fallback. Dependency installation initially needs internet access. The camera's own vendor-cloud behavior is outside this integration's control. The camera protocol uses HTTP on the LAN; keep it on a trusted network and do not expose its port to the internet.

## Movement action

The four buttons use the step and speed configured in options. Automations can also call:

```yaml
action: mipc_camera.move
data:
  config_entry_id: YOUR_MIPC_CONFIG_ENTRY_ID
  x: 5
  y: 0
  pan_speed: 16
  tilt_speed: 16
```

Positive X pans right; positive Y tilts up according to the device protocol. These are relative device units, not calibrated physical degrees. Start with small values. PTZ is disabled by default and the action rejects calls until enabled.

## Temporary library bundle

This beta includes the updated [Python library fork](https://github.com/brylee123/mipc-camera-client-python) inside `_vendor/mipc_camera_client`, version `0.2.0.dev0`, commit `1a6e1cf6a7648247481d270105ae753df527ca31`. **It does not install the older PyPI release.** The only adaptation is the resource package lookup in `catalog.py` so the RPC catalogue resolves inside the integration namespace. The original BSD license is retained in `_vendor/LICENSE`. This bundle can be replaced with a pinned published dependency when the updated library is released.

## Limits and diagnostics

- No two-way talk audio pipeline or microphone streaming is implemented. Microphone/speaker settings are available where supported.
- Motion sensitivity is a setting, not a motion-event sensor. Actual motion event reporting has not been established.
- No factory reset, disk format, credential/network changes, or automatic firmware updates are exposed.
- Storage usage is a ratio; raw camera storage units have not been assumed to be bytes.
- Unsupported settings stay absent. A failed later read makes that setting unavailable. Reload the integration to discover newly enabled capabilities.
- The integration can reconnect an expired session for polling, but does not automatically replay writes.
- Download diagnostics from the integration menu. Diagnostics whitelist model, firmware, capability names, error classes and options, excluding device IDs, credentials, raw payloads and media URLs.

## Development

```sh
pip install -r requirements_test.txt
pytest -q
ruff check .
ruff format --check .
```

Tests use synthetic camera data, block network access and cover config flow, entity discovery, writes, optional capabilities, PTZ, unload and diagnostics. Live acceptance tests are separate and must use local private credentials; never commit credentials or camera images.

## Credits

Built on [Pan Maruda's original mipc-camera-client-python](https://github.com/pan-maruda/mipc-camera-client-python). Thank you to **Pan Maruda** for the original client and protocol work. The expanded fork is maintained by [brylee123](https://github.com/brylee123/mipc-camera-client-python).

This integration and library expansion were developed by brylee123, a programmer by trade, with AI assistance and reviewed/tested against a real camera. This project is an independent community integration and is not affiliated with MIPC or Home Assistant.
