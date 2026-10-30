"""Snapshots and direct local RTMP streaming through Home Assistant."""

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.exceptions import HomeAssistantError

from .const import CONF_ENABLE_STREAM, CONF_STREAM_TOKEN, DEFAULT_OPTIONS
from .entity import MipcEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([MipcCamera(entry.runtime_data, entry)])


class MipcCamera(MipcEntity, Camera):
    def __init__(self, coordinator, entry):
        Camera.__init__(self)
        MipcEntity.__init__(self, coordinator, entry)
        self._options = {**DEFAULT_OPTIONS, **entry.options}
        self._attr_unique_id = f"{self._id}_camera"
        self._attr_name = None
        self._attr_supported_features = (
            CameraEntityFeature.STREAM
            if self._options[CONF_ENABLE_STREAM]
            else CameraEntityFeature(0)
        )

    async def async_camera_image(self, width=None, height=None):
        try:
            return await self.hass.async_add_executor_job(self._hub.snapshot)
        except Exception as error:
            raise HomeAssistantError(
                f"Snapshot unavailable ({type(error).__name__})"
            ) from error

    async def stream_source(self):
        if not self._options[CONF_ENABLE_STREAM]:
            return None
        try:
            return await self.hass.async_add_executor_job(
                self._hub.stream_url, self._options[CONF_STREAM_TOKEN]
            )
        except Exception as error:
            raise HomeAssistantError(
                f"Local stream unavailable ({type(error).__name__})"
            ) from error
