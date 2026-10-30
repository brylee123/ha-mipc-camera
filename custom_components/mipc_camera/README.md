# MIPC Camera custom integration

This integration communicates over the local MIPC camera RPC interface using
[mipc-camera-client 0.1.3](https://pypi.org/project/mipc-camera-client/).
See the repository root README section "Home Assistant integration".

**Alpha / hardware testing needed.** The upstream client exposes snapshots,
RTMP, serial number and relative PTZ. It does not expose motion events,
IR mode, recording switches, or Tapo-style camera settings.

The device must support the upstream RPC endpoints. The stream may require
FFmpeg and not all returned RTMP URLs are local or playable.
