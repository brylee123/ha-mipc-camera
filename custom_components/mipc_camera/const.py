"""Constants and user options."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "mipc_camera"
PLATFORMS = [
    Platform.CAMERA,
    Platform.MEDIA_PLAYER,
    Platform.EVENT,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.TEXT,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]
SCAN_INTERVAL = timedelta(seconds=60)
CONF_MOTION_EVENTS = "motion_events"
CONF_ENABLE_PTZ = "enable_ptz"
CONF_ENABLE_STREAM = "enable_stream"
CONF_STREAM_TOKEN = "stream_token"
CONF_PTZ_STEP = "ptz_step"
CONF_PAN_SPEED = "pan_speed"
CONF_TILT_SPEED = "tilt_speed"
DEFAULT_OPTIONS = {
    CONF_MOTION_EVENTS: False,
    CONF_ENABLE_PTZ: False,
    CONF_ENABLE_STREAM: True,
    CONF_STREAM_TOKEN: "p0",
    CONF_PTZ_STEP: 5,
    CONF_PAN_SPEED: 16,
    CONF_TILT_SPEED: 16,
}
