# MIPC Camera for Home Assistant

Local control of compatible MIPC cameras, packaged as a separate HACS custom integration. Requires Home Assistant **2026.10.0 or newer**. This is a beta; camera firmware determines which controls appear.

## Features

| Platform | Supported capabilities |
| --- | --- |
| Camera | JPEG snapshots and local RTMP streaming through Home Assistant |
| Event | Local camera-reported motion pulses (opt-in; requires a returned motion action and local queue support) |
| Number | Brightness, contrast, saturation, sharpness, speaker/microphone volume, day/night motion sensitivity |
| Switch | Image flip, microphone mute, OSD text/date/time/weekday, SD recording enabled, motion action and global arming |
| Select | Auto/day/night image mode, verified video profiles, OSD formats, power frequency, SD recording mode |
| Text | OSD text content |
| Button | Pan left/right and tilt up/down (opt-in), restart (disabled by default) |
| Sensor | Firmware and last successful read (disabled by default), storage status/usage, reported timezone, per-interface IP/MAC/type/link (disabled by default) |
| Binary sensor | Connection health and recording media readiness |

Settings entities are created only when the camera reports an appropriately typed field. Entity names, modes, errors and icons use Home Assistant translation resources. Entity and device IDs remain stable when you rename the camera or change its address. Missing fields and unsupported calls do not become invented capabilities. Polling runs every 60 seconds; settings actions wait for a fresh read-back and report an error if the camera does not confirm the requested value. Requests are serialized, and a saved address that points to another camera is rejected during setup. The first hardware test model is an **f300**, firmware `v5.1.10.1811061306`. Both physical motors were verified with small moves and inverse moves.

## Install

1. Add `https://github.com/brylee123/ha-mipc-camera` as a HACS custom repository, category **Integration**, then download MIPC Camera. Unreleased review branches can be tested with manual installation.
2. Alternatively, copy **only** `custom_components/mipc_camera` into your Home Assistant configuration directory's `custom_components` folder.
3. Restart Home Assistant.
4. Open **Settings > Devices & services > Add integration > MIPC Camera**.
5. Enter the camera's local hostname/IP (optional port), and its **Device/Admin password**. Your MIPC cloud account password is a different credential. Leave username blank to use the device serial automatically.
6. Open the integration options to enable PTZ after confirming the camera has motors. Streaming can be disabled or changed between camera profile tokens `p0`-`p3`.

Home Assistant must be able to reach the camera directly. Reserve its LAN address. No MIPC cloud account is used and there is no cloud fallback. Dependency installation initially needs internet access. The camera's own vendor-cloud behavior is outside this integration's control. The camera protocol uses HTTP on the LAN; keep it on a trusted network and do not expose its port to the internet.

## Security: keep camera traffic local

For better privacy, block the camera's internet access at your router or firewall
while allowing Home Assistant to reach it locally. Using this integration does
not stop the camera firmware from contacting vendor services on its own. Network
restrictions reduce that exposure; they do not make the camera firmware trusted.

1. Reserve the camera's LAN address in your router's DHCP settings.
2. Create an **internet-only block** for the camera: deny outbound traffic to the
   internet (WAN), across all protocols and ports, for **both IPv4 and IPv6** if
   enabled. Blocking DNS or a list of vendor domains alone is insufficient.
3. Allow Home Assistant to reach the camera's local control and media services,
   including return traffic. If using a separate camera/IoT network, add the
   required firewall rules between that network and Home Assistant. Guest-network
   isolation or a router's generic **Block device** option may also block local
   access; check what the option actually does.
4. Cover every connected camera interface. Ethernet and Wi-Fi can be active at
   the same time with different addresses; restrict both or disconnect the unused
   interface. Do not forward camera ports from the internet, and remove any
   existing camera port forwards or UPnP mappings.
5. Verify that the router enforces the WAN block, then restart the camera and
   check snapshots, live video, PTZ, settings and motion events where supported.

MIPC cloud viewing, cloud notifications, vendor updates and internet time
synchronization may stop working. If the camera needs time synchronization, use
a trusted local time server where the firmware supports it and allow only the
necessary local access. A correct camera clock matters for motion-event filtering.
Home Assistant can retain its own internet access for installation and updates;
the restriction targets the camera.

Local control and streaming have been tested, but operation with the camera's WAN
access blocked has **not yet been hardware-validated**. Verify your model after
applying the rule. The camera uses HTTP and legacy authentication on the LAN;
keep access limited to trusted devices, ideally on a separate camera/IoT network.

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

This beta includes the updated [Python library fork](https://github.com/brylee123/mipc-camera-client-python) inside `_vendor/mipc_camera_client`, version `0.2.0.dev0`, commit `7b4a1beff5c031b6ca4313ebb38d03fb12c16901`. **It does not install the older PyPI release.** The only adaptation is the resource package lookup in `catalog.py` so the RPC catalogue resolves inside the integration namespace. The original BSD license is retained in `_vendor/LICENSE`. This bundle can be replaced with a pinned published dependency when the updated library is released.

## Limits and diagnostics

- No two-way talk audio pipeline or microphone streaming is implemented. Microphone/speaker settings are available where supported.
- Motion sensitivity remains a setting. Enable **Local motion events** in integration options to add a native Home Assistant motion event entity on supported cameras.
- Factory reset is an explicit confirmation-guarded action. Disk format, credential/network changes, and automatic firmware updates are not exposed.
- Storage usage is a ratio; raw camera storage units have not been assumed to be bytes.
- Unsupported settings stay absent. A failed later read makes that setting unavailable. Reload the integration to discover newly enabled capabilities.
- The integration can reconnect an expired session for polling, but does not automatically replay writes.
- Download diagnostics from the integration menu. Diagnostics whitelist model, firmware, capability names, error classes and options, excluding device IDs, credentials, raw payloads and media URLs.

## Configuration and options

The connection form requires a local camera address and Device/Admin password. Username is optional and defaults to the camera's serial. Use **Reconfigure** from the integration menu after an address change; a camera with a different serial is rejected. If the camera rejects credentials, Home Assistant offers reauthentication. Changing integration options reloads only this integration.

| Option | Default | Meaning |
| --- | --- | --- |
| Enable pan/tilt | Off | Exposes four motor buttons and allows the movement action after hardware verification |
| Enable live video | On | Offers Home Assistant streaming in addition to snapshots |
| Stream quality token | `p0` | Camera profile token; other profiles depend on camera firmware |
| Movement per press | 5 | Relative units, allowed range 1–30 |
| Pan speed | 16 | Device speed setting, allowed range 1–100 |
| Tilt speed | 16 | Device speed setting, allowed range 1–100 |

Image levels, sensitivity, OSD, audio and recording configuration are entities on the camera's device page. Firmware and last-seen diagnostics are disabled by default to avoid redundant history; enable them in **Settings → Devices & services → Entities** if useful. Existing entity preferences are retained.

## Examples

To nudge a supported camera when a dashboard button is pressed, use the movement action above, or add the pan/tilt button entities to your dashboard. To change image brightness, use the camera's brightness number entity with `number.set_value` and a whole-number value from 0 to 100. Select the entity from your installation; names and entity IDs may have been customized.

## Troubleshooting and removal

- **Cannot connect:** check the camera's reserved LAN address, port and network reachability from Home Assistant. No cloud fallback is attempted.
- **Invalid credentials:** use the Device/Admin password, not the MIPC account password. Leave username blank unless the device requires an explicit username.
- **Different camera at the saved address:** restore the original camera address and use Reconfigure. Do not replace device identifiers in Home Assistant storage files.
- **A setting is absent:** the corresponding camera field was missing or unsupported at discovery. Reload after a firmware or capability change. A field that stops being readable becomes unavailable.
- **A setting action reports a read-back error:** the command may have been sent, but the new state is not confirmed. Check the current state and connectivity before retrying. Writes are never replayed automatically.
- **No storage percentage:** an empty slot or invalid capacity has no usable percentage. The storage status sensor still reports the device's status.
- **No live video:** try the default `p0` profile and confirm the local RTMP connection can be reached from Home Assistant. Two-way talk is not implemented.

Remove the camera entry in **Settings → Devices & services → MIPC Camera → Delete**. For multiple cameras, remove each entry. Remove the integration through HACS, or remove only `custom_components/mipc_camera` for a manual installation, and restart Home Assistant. Removal closes the local client; it does not reset the camera or erase its SD card. Keep a Home Assistant backup before uninstalling custom integrations if you want to retain entity customizations.

See [the engineering review](docs/QUALITY.md) for the applied Home Assistant guidance and the explicit temporary library-packaging exception. The official MIPC logo is used to identify the compatible product; see [asset provenance](custom_components/mipc_camera/brand/README.md).

## Development

```sh
pip install -r requirements_test.txt
pytest -q --cov=custom_components.mipc_camera --cov-report=term-missing
ruff check .
ruff format --check .
```

Tests use synthetic camera data, block network access and cover initial setup, duplicate entries, failed and cancelled setup, reauthentication, reconfiguration, options reload, entity discovery, verified writes, unavailable/recovery transitions, optional capabilities, PTZ, camera media, unload and diagnostics. CI enforces at least 95% coverage of the integration, including branches; the bundled library is excluded because it has its own test suite. Live acceptance tests are separate and must use local private credentials; never commit credentials or camera images.

## Credits

Built on [Pan Maruda's original mipc-camera-client-python](https://github.com/pan-maruda/mipc-camera-client-python). Thank you to **Pan Maruda** for the original client and protocol work. The expanded fork is maintained by [brylee123](https://github.com/brylee123/mipc-camera-client-python).

This integration and library expansion were developed by brylee123, a programmer by trade, with AI assistance and reviewed/tested against a real camera. This project is an independent community integration and is not affiliated with MIPC or Home Assistant.

## Local motion events

Enable **Local motion events** in the integration options. On firmware returning
an observed `motion_alert` action, an `event` entity named **Motion** is added.
Its state is the last event's reception timestamp, with `event_type: motion`,
`message_id`, and the camera's `camera_timestamp` as attributes. It stays unknown
before its first event and retains the last event afterward; no motion-clear or
ten-second occupancy state is invented. Use Home Assistant's **Event received**
automation trigger for this entity, selecting the `motion` event type.

This feature only subscribes and reads. The camera's motion alarm must be armed
to generate alerts; the integration never changes arming, IO outputs, recording,
snapshots or publication filters automatically. Diagnostics include the reported
arming and event-connection status. An idle/disarmed camera can have a healthy
event connection without producing alerts. The event entity becomes unavailable
when the settings connection or its separate queue connection fails.

A dedicated local session keeps long polls from blocking controls or video.
Transient queue failures reconnect with bounded backoff. Unknown event codes,
other-camera messages, duplicates and events more than two minutes from the
Home Assistant clock are ignored. Keep the camera clock correct. Duplicate
suppression is bounded to 256 events per runtime, and the entity also checks its
restored last event to avoid firing that event again after a reload. Missed
notifications are not backfilled from history, and queue reconnects can lose
alerts; this is not a security alarm delivery guarantee.

Verified on an f300: native local `alert` / `motion_alert` delivery while pan
movement changed its view. Physical movement, other models and continuous
long-duration operation still need separate validation. IO, snapshot and recording
actions were disabled for testing, with original settings restored afterward.

## Video quality

The **Video quality** dropdown shows verified playback profiles using the Windows
client names, with measured dimensions: e.g. **HD1080p (1920 × 1080)**,
**Standard (640 × 360)**, **Smooth (640 × 360)** on the tested f300. Standard and
Smooth remain separate because equal dimensions do not prove equal frame rate or
bitrate. D1/CIF are never translated into assumed sizes. The extracted Auto handler
only changes its label; no automatic camera mode was found, so none is invented.

Discovery decodes a frame from each advertised local profile and can add seconds
to setup. Failed probes are not shown as working choices. Results are cached;
firmware/profile changes invalidate them. With fewer than two verified profiles,
discovery retries on reload. Selecting a quality verifies a fresh frame before
saving and reloads the integration, closing the previous stream. Video and motion
briefly reconnect. Existing entity IDs, other options, snapshots and encoder /
recording configuration are preserved.

## Device settings and maintenance

Controls appear only for correctly typed fields returned by the camera:

- **OSD calendar date**, **OSD clock time**, and **OSD weekday** are independent.
  The existing date/time switches retain their unique IDs. Live snapshots confirmed
  the field mapping. Date format supports YYYY-MM-DD / MM-DD-YYYY; clock format is
  12-hour / 24-hour.
- **Timezone (reported)** is a read-only diagnostic. The f300 can acknowledge a
  timezone change while shifting its clock incorrectly, so no timezone-writing
  control is exposed. The SDK reports advertised UTC offsets, matching Windows UI
  option values; city names/file paths are not assumed to be setter IDs.
- **Power frequency** follows the MIPC client mapping (0 = 60 Hz, 1 = 50 Hz).
  An OEM UI in the extracted bundle reverses labels; other OEM firmware needs
  hardware validation.
- **Motion alarm action** toggles the motion action alone. **Alarm armed** controls
  global arming. Both must be enabled to generate motion alerts. Global arming can
  activate existing IO outputs, snapshots and recording, as configured on the
  camera. The integration never arms them automatically or rewrites those actions.
- **SD recording enabled** preserves the existing task mode. **SD recording mode**
  explicitly selects Off / Continuous; Scheduled appears only with existing time
  windows. Continuous is all-day recording to camera storage; Scheduled uses the
  configured time windows. An external MIPC **recording box** is different hardware
  and is not configured by these controls. No usable SD card was present during
  validation, so settings readback was verified, but actual footage was not.
- Per-interface **Local IP address**, **MAC address**, **Connection type**, and
  **Link status** diagnostic sensors are disabled by default; enable them in the
  entity list. Ethernet and Wi-Fi are reported separately. Both may be connected;
  link status does not identify a default route. Wi-Fi passwords, SSIDs and nearby
  AP lists are excluded from coordinator data. Diagnostics still redact addresses.
- **Restart** is a configuration button, disabled by default. Enable it in the
  entity list when needed. It temporarily disconnects the camera. Recovery waits
  for known controls to return, then reloads the integration to create a fresh
  media session. Recovery is bounded and never repeats the reboot command.
- **Factory reset camera** is an explicit action `mipc_camera.factory_reset`,
  requiring a configuration entry ID and `confirm: true`. It erases settings,
  credentials and networking, and can require physical access afterward. It is
  tested with mocks only; the live camera was never factory-reset.

Settings writes are serialized, never retried automatically, and read back before
reporting success. Reboot/reset cannot be verified through the normal settings
readback while the camera disconnects; a transport timeout may leave their outcome
unknown. Check the camera before retrying either maintenance action.
