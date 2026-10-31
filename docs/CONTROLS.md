# Camera controls and behavior

[Back to the README](../README.md)

Detailed behavior, limits and action examples for supported cameras. Entity availability depends on the fields returned by your camera.

## Live view switch

The **Live view** switch controls viewing through this integration. Turning it
off stops the active Home Assistant video session and replaces snapshots and the
MJPEG feed with a locally generated **Camera Off** screen. The camera entity stays
available for that placeholder, even if camera polling subsequently fails. No
camera snapshot or stream negotiation is requested while off. Automatic video
profile probing is also skipped while off; changing quality only saves the choice
from previously verified profiles. Turning Live view on resumes camera media.

The preference is saved across integration reloads and Home Assistant restarts,
and uses the same setting as **Live view** in integration options. Switching it
does not reload the integration or interrupt motion events and other controls.

This is a Home Assistant viewing gate, **not a physical privacy mode or power
switch**. It does not stop SD recording, mute the camera, block cloud access or
prevent other apps from viewing it. Previously delivered frames and buffered
video cannot be recalled. The off screen uses Home Assistant's still-image/MJPEG
path, rather than a replacement HLS video; an already-open HLS-only player may
need to be reopened to show it. Motion events and device polling continue.

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
long-duration operation still need separate validation. The initial motion test disabled IO, snapshot and recording
actions temporarily. The later events-only configuration kept those outputs
disabled by explicit user choice; installing the integration does not apply that configuration.

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
- **Motion alerts** enables motion-triggered alarm actions. **Alarm master** controls
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

## Speaker media player

A **Speaker** `media_player` entity is enabled by default on cameras returning
readable speaker volume configuration. Existing user-disabled entity preferences
are respected. Use it with **Play media**, media-source browsing, **Stop**,
**Volume**, or `tts.speak` from an installed TTS provider.

```yaml
action: media_player.play_media
target:
  entity_id: media_player.YOUR_CAMERA_SPEAKER
data:
  media_content_id: media-source://media_source/local/announcement.wav
  media_content_type: audio/wav
```

The player accepts WAV, MP3, FLAC, Ogg and M4A audio, including resolved
Home Assistant TTS media sources. Home Assistant downloads and decodes the audio,
then sends AAC over RTMP directly to the camera on a separate authenticated
session. The camera does not download the media URL or need internet access.
The selected TTS provider or remote media source may require internet access from
Home Assistant; local media and a local TTS provider keep that part local too.

There is **no fixed playback duration cap**: decoding and upload run incrementally
and Stop interrupts the sender. Source downloads retain a **5 MiB** size guard. Queues, playlists,
radio streams, seek/pause and live browser microphone capture are not supported.
New playback replaces the previous clip. Stop signals the uploader and waits for
its bounded network operation, encoder cleanup and a one-second camera release interval; a short buffered tail can
remain audible. Download redirects and input file/network references inside
media files are rejected. Playback errors return the player to idle and expose a
generic `playback_error` attribute; private URLs and TTS text are not logged.

Volume uses the camera's existing speaker-volume setting. The redundant speaker
volume number entity is removed automatically on reload, including if renamed.
Automations that used it should use `media_player.volume_set` with a level from
0.0 to 1.0 instead of `number.set_value` with 0 to 100. Playback does not
unmute the camera microphone, change alarm settings or turn Live view on. Live
view controls camera viewing independently of this speaker entity. A readable
volume field is not proof every firmware accepts talk audio: unsupported devices
report a playback failure rather than receiving guessed fallback commands. AAC
16 kHz mono has been acoustically verified on the f300; see the library's
[Android/audio evidence](https://github.com/brylee123/mipc-camera-client-python/blob/main/docs/ANDROID.md).

## Alarm controls

**Alarm master** is the global gate for all configured alarm triggers, including
motion and IO-input alarms. **Motion alerts** enables only the motion trigger.

| Alarm master | Motion alerts | Result |
| --- | --- | --- |
| Off | Either | Configured alarm triggers are disarmed. |
| On | Off | Motion alerts are disabled; other enabled alarm triggers can still run. |
| On | On | Motion alerts can run, along with any other enabled alarm triggers. |

For an events-only setup with IO-input alarms disabled, Alarm master mainly acts
as an overall on/off switch for motion. **Both switches must be on** for the
camera to generate motion events. The Motion event entity reports received
pulses; enabling that entity alone does not arm the camera.

Neither switch changes sensitivity or chooses whether an alarm takes snapshots,
records video or activates an IO output. Those are separate action settings,
which these switches preserve. An events-only setup requires those motion
outputs to be disabled separately. **Day motion sensitivity** and **Night motion
sensitivity** adjust the detector thresholds; they do not arm it.

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
