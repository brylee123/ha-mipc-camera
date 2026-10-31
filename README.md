<p align="center">
  <img src="https://raw.githubusercontent.com/brylee123/ha-mipc-camera/main/custom_components/mipc_camera/brand/icon%402x.png" alt="MIPC logo" width="112" height="112">
</p>

# MIPC Camera for Home Assistant

View compatible MIPC cameras, adjust settings, move their motors, receive motion events and play speaker announcements through a direct connection from Home Assistant to your camera.

[![Validation](https://github.com/brylee123/ha-mipc-camera/actions/workflows/validate.yml/badge.svg?branch=main)](https://github.com/brylee123/ha-mipc-camera/actions/workflows/validate.yml)
[![HACS custom integration](https://img.shields.io/badge/HACS-Custom-41BDF5)](https://www.hacs.xyz/docs/faq/custom_repositories/)
[![Home Assistant minimum version](https://img.shields.io/badge/Home%20Assistant-2026.10%2B-18BCF2)](https://www.home-assistant.io/)
[![License: BSD 3-Clause](https://img.shields.io/badge/License-BSD%203--Clause-blue.svg)](LICENSE)

**Beta · Local connection · UI setup · No MIPC cloud account required**

An independent community integration for [MIPC](https://play.google.com/store/apps/details?id=com.mining.app.mipca), available as a **HACS custom repository**. Features depend on camera firmware. This is not an official Home Assistant integration.

[Install](#installation) · [Configure](#configuration) · [Features](#supported-features) · [Motion](#motion-and-alarms) · [Security](#privacy-and-network-security) · [Help](#troubleshooting)

## Compatibility and requirements

| Requirement | Details |
| --- | --- |
| Home Assistant | **2026.10.0 or newer** |
| Camera | A compatible MIPC camera with a reachable local control interface |
| Credentials | Camera **Device/Admin password**, not your MIPC account password |
| Network | Direct access from Home Assistant to the camera; reserve its LAN address |
| Installation | HACS or manual installation; initial dependency downloads need internet access |

**Hardware tested:** f300, firmware `v5.1.10.1811061306`. Snapshots, local video, both motors, supported settings, native motion events and AAC speaker playback were verified. Other models and firmware are not yet confirmed. Unsupported controls stay absent.

SD recording settings were checked, but footage was not tested because no usable SD card was present. Factory reset has automated test coverage only. Motion was triggered by camera movement; person movement and long-duration reliability need further validation.

## Installation

### HACS (recommended)

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=brylee123&repository=ha-mipc-camera&category=integration)

1. Open **HACS** in Home Assistant.
2. Open the menu → **Custom repositories**.
3. Add `https://github.com/brylee123/ha-mipc-camera` with type **Integration**.
4. Find **MIPC Camera** in HACS and download it.
5. Restart Home Assistant, then continue with [Configuration](#configuration).

The button opens this repository in HACS. Use the steps above if the link does not work in your browser.

### Manual installation

1. Download this repository: **Code → Download ZIP**.
2. Extract it and copy **only** `custom_components/mipc_camera` into your Home Assistant configuration directory:

   ```text
   config/
   └── custom_components/
       └── mipc_camera/
           ├── __init__.py
           ├── manifest.json
           └── …
   ```

3. Restart Home Assistant, then continue below.

## Configuration

[![Add MIPC Camera to Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=mipc_camera)

1. Open **Settings → Devices & services → Add integration**.
2. Search for **MIPC Camera**.
3. Enter the connection details and submit.

| Field | What to enter |
| --- | --- |
| Camera address | Local IP or hostname, optionally with a port, such as `192.168.1.50:80`. No `http://` or path. |
| Device username | Optional. Leave blank to use the camera's device serial automatically. |
| Device/Admin PW | The device password configured for the camera. The MIPC cloud account password will not work. |

Repeat setup for each camera. No `configuration.yaml` entry is needed. Use **Reconfigure** in the integration menu after an address change. Invalid credentials prompt reauthentication. A saved address that points to a different camera is rejected.

### Options

Open the integration's **Configure** dialog to change these options.

| Option | Default | Purpose |
| --- | --- | --- |
| Enable pan/tilt motors | Off | Adds movement buttons and enables the movement action. Enable only for a camera with motors. |
| Live view | On | Enables Home Assistant viewing; off displays a local **Camera Off** screen. |
| Stream quality token | `p0` | Camera stream profile; supported profiles depend on firmware. |
| Movement per press | 5 | Relative movement units, from 1 to 30. |
| Pan / tilt speed | 16 each | Device speed settings, from 1 to 100. |
| Enable local motion events | Off | Adds the Motion event entity where supported. Does not arm the camera. |

Changing options reloads this integration. Entity IDs and customizations are retained. Most camera settings are entities on the device page, rather than options in this dialog.

## Supported features

| Feature | Controls and information |
| --- | --- |
| Camera | JPEG snapshots and local RTMP video through Home Assistant |
| Speaker | Media playback, TTS, volume, Stop and media browsing; enabled by default where supported |
| Motion | Native Motion event entity; separate day and night sensitivity |
| Alarms | Alarm master and Motion alerts switches |
| Image | Brightness, contrast, saturation, sharpness, flip, Auto/Day/Night mode and 50/60 Hz power frequency |
| Video quality | Verified profiles labeled with measured resolution |
| On-screen display (OSD) | Text, calendar date, clock time, weekday, date format and 12/24-hour format |
| Microphone | Volume and mute where reported |
| Recording | SD recording enabled, Off/Continuous mode, Scheduled where existing schedule windows are present |
| Movement | Pan left/right and tilt up/down buttons; relative movement action |
| Maintenance | Optional Restart button and confirmation-required factory-reset action |
| Diagnostics | Connection, recording media readiness, storage status/usage, firmware, last seen, reported timezone, per-interface IP/MAC/type/link |

Firmware, last-seen and network diagnostic entities are disabled by default, as is Restart. Enable them under **Settings → Devices & services → Entities** when needed.

Settings are polled every **60 seconds**. Changes are read back before success is reported; failed writes are not automatically replayed. Expired sessions renew automatically for reads and media requests, with one retry. A renewed session discards cached video URLs on the next successful poll. Motion uses a separate local event connection. See [detailed controls and behavior](docs/CONTROLS.md) for capability rules and firmware details.

### Live view and video quality

**Live view off** stops viewing through this integration and displays a local **Camera Off** still/MJPEG screen. Motion events and other controls continue. The preference survives restarts. An already-open HLS player may need to be reopened to show the placeholder.

**This does not turn off the camera**, stop SD recording, mute audio, block the vendor cloud or prevent another app from viewing it.

The **Video quality** selector uses measured resolutions. On the tested f300:

| Profile | Measured resolution |
| --- | --- |
| HD1080p | 1920 × 1080 |
| Standard | 640 × 360 |
| Smooth | 640 × 360 |

Standard and Smooth remain separate because bitrate or frame rate may differ. No working automatic quality mode was found. Discovery can add several seconds to setup; changing quality briefly reconnects video and motion. It does not change recording or encoder settings.

### Speaker announcements

Use the **Speaker** media player with **Play media**, **Stop**, **Volume**, or an installed [TTS provider](https://www.home-assistant.io/integrations/tts/). WAV, MP3, FLAC, Ogg and M4A audio is decoded and converted to the camera's AAC format automatically.

Home Assistant sends audio directly to the camera; the camera does not fetch the media URL. Remote media and cloud TTS may still require internet access from Home Assistant. Use local media and a local TTS provider to keep the entire path local.

There is no fixed duration limit, but source downloads are limited to **5 MiB**. New playback replaces the previous clip. Stop interrupts playback, although a short buffered tail may remain. Playlists, radio streams, pause/seek and live browser microphone talk are unsupported.

**Upgrading from an earlier beta:** the separate speaker-volume number entity is removed. Change its automations to `media_player.volume_set` with **0.0–1.0**, replacing `number.set_value` with **0–100**.

### Motion and alarms

1. Enable **Local motion events** in the integration options.
2. Review the camera's configured alarm outputs before arming it; existing actions may take snapshots, record or activate IO.
3. Turn on **Alarm master** and **Motion alerts** on the device page.
4. In an automation, choose the Motion entity's **Event received** trigger and the `motion` event type.

| Alarm master | Motion alerts | Behavior |
| --- | --- | --- |
| Off | Either | All configured alarm triggers are disarmed. |
| On | Off | Motion alerts are disabled; other enabled triggers, such as IO-input alarms, can still run. |
| On | On | Motion alerts and any other enabled alarm triggers can run. |

**Alarm master** is the global gate; **Motion alerts** enables only the motion trigger. Neither changes sensitivity or configured outputs. For events-only operation, disable those outputs separately in the camera's alarm settings before arming. Installation does not change them for you.

Motion is an **event**, not an occupancy sensor: its state is the last event timestamp and stays unknown until the first event. No ten-second clear timer is added. Keep the camera clock correct; stale, duplicate and unknown events are filtered. Reconnects can lose events, so this is not a guaranteed security-alarm delivery system.

## Actions and examples

Use **Developer tools → Actions** to select the target entities or camera. Replace example entity IDs with those from your installation.

<details>
<summary>Play a local announcement</summary>

```yaml
action: media_player.play_media
target:
  entity_id: media_player.your_camera_speaker
data:
  media_content_id: media-source://media_source/local/announcement.wav
  media_content_type: audio/wav
```

Place the file in Home Assistant's local media directory first.

</details>

<details>
<summary>Set speaker volume to 25%</summary>

```yaml
action: media_player.volume_set
target:
  entity_id: media_player.your_camera_speaker
data:
  volume_level: 0.25
```

</details>

For pan/tilt, use the four buttons or **MIPC Camera: Move camera** (`mipc_camera.move`). The action's camera picker supplies the configuration entry ID. Movement uses relative device units, not degrees; start small. See the [movement example](docs/CONTROLS.md#movement-action).

**Factory reset camera** (`mipc_camera.factory_reset`) requires a camera selection and explicit `confirm: true`. It erases camera settings, credentials and networking, and may require physical access afterward. A timeout does not prove failure; check the camera before retrying. Disk formatting, credential/network changes and firmware updates are not exposed.

## Privacy and network security

The integration uses local HTTP control and local media sessions, with **no MIPC cloud fallback**. This does not stop camera firmware from contacting vendor services independently.

For better privacy, reserve the camera's IP and block its **outbound internet/WAN access** at the router or firewall, for IPv4 and IPv6 where enabled. Keep Home Assistant-to-camera access allowed. Cover both Ethernet and Wi-Fi if connected, and remove camera port forwards or UPnP mappings. Blocking only DNS is insufficient.

The camera uses legacy LAN authentication. Limit access to trusted devices, ideally on a separate camera/IoT network. See the [network isolation guide](docs/SECURITY.md) for steps, time synchronization and verification. Operation with WAN access blocked has not yet been hardware-validated; verify your model after applying restrictions.

## Known limitations

- **Firmware support varies.** Missing or unsupported settings are omitted. Reload to discover capability changes; unreadable settings become unavailable.
- **Timezone is read-only.** Tested firmware can acknowledge a change while shifting its clock incorrectly.
- **Recording modes control camera SD storage.** External MIPC recording boxes are not configured here. Storage usage is a ratio; unverified raw units are not presented as bytes.
- **Speaker playback is not live two-way talk.** Browser microphone capture and full two-way WebRTC talk are not implemented.
- **This beta bundles the updated Python library.** It does not use the older PyPI release. See [dependency details](docs/DEVELOPMENT.md#temporary-library-bundle).

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| Missing from Add integration | Confirm the folder path, restart Home Assistant and refresh your browser. |
| Cannot connect | Verify the local address, port and Home Assistant-to-camera firewall access. |
| Invalid credentials | Use the Device/Admin password. Leave username blank unless your camera needs an explicit one. |
| Address belongs to another camera | Restore the original camera's address and use Reconfigure. Do not edit identifiers in Home Assistant storage. |
| No live video | Turn Live view on, try `p0`, and check local RTMP reachability. |
| No motion events | Enable local events, Alarm master and Motion alerts. Check camera time and event-connection diagnostics. A healthy but disarmed camera produces no alerts. |
| Missing control | The camera may not report a supported field. Reload after a firmware or capability change. |
| Setting read-back error | The write may have reached the camera. Check its current state and connection before retrying. |
| Speaker playback fails | Try a small local WAV/MP3 file. Check `playback_error`; readable volume alone does not prove audio-upload support. |
| No storage percentage | Check for a usable SD card. An empty slot or invalid capacity has no percentage. |

For help, [open an issue](https://github.com/brylee123/ha-mipc-camera/issues/new) with your Home Assistant/integration versions, camera model/firmware, reproduction steps and relevant logs. Download diagnostics from the integration menu. Diagnostics exclude credentials, identifiers, raw payloads and private media URLs. Review logs before sharing; do not attach passwords, camera images or recordings.

## Updating and removing

**Update:** back up Home Assistant, download the update through HACS and restart. For manual installations, replace the integration folder and restart. Review release notes and migration notes first.

**Remove:** delete each camera entry under **Settings → Devices & services**, then remove MIPC Camera through HACS and restart. For manual installations, remove only `custom_components/mipc_camera`. Removal does not reset the camera or erase its SD card.

## Development and credits

[Development guide](docs/DEVELOPMENT.md) · [Engineering review](docs/QUALITY.md) · [Detailed controls](docs/CONTROLS.md) · [Python library](https://github.com/brylee123/mipc-camera-client-python)

Built on [Pan Maruda's original MIPC Python client](https://github.com/pan-maruda/mipc-camera-client-python). Thanks to **Pan Maruda** for the original client and protocol work.

Maintained by **brylee123**, a programmer by trade, with AI assistance and review/testing against a real camera. Source code uses the [BSD 3-Clause license](LICENSE). MIPC names and artwork belong to their respective owners; see [logo provenance](custom_components/mipc_camera/brand/README.md). This project is not affiliated with or endorsed by MIPC or Home Assistant.
