"""Constants for the MIPC Camera integration."""

from datetime import timedelta

DOMAIN = "mipc_camera"
PLATFORMS = ("camera", "button", "sensor", "binary_sensor")
SCAN_INTERVAL = timedelta(seconds=60)

CONF_ENABLE_PTZ = "enable_ptz"
CONF_ENABLE_STREAM = "enable_stream"
CONF_STREAM_TOKEN = "stream_token"
CONF_ALLOW_REMOTE_STREAM = "allow_remote_stream"
CONF_PTZ_STEP = "ptz_step"
CONF_PAN_SPEED = "pan_speed"
CONF_TILT_SPEED = "tilt_speed"

DEFAULT_OPTIONS = {
    CONF_ENABLE_PTZ: True,
    CONF_ENABLE_STREAM: True,
    CONF_STREAM_TOKEN: "p0",
    CONF_ALLOW_REMOTE_STREAM: False,
    CONF_PTZ_STEP: 30,
    CONF_PAN_SPEED: 48,
    CONF_TILT_SPEED: 16,
}
