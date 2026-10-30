"""JPEG snapshot and optional RTMP streaming camera."""

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_ALLOW_REMOTE_STREAM, CONF_ENABLE_STREAM, CONF_STREAM_TOKEN, DEFAULT_OPTIONS,
)
from .entity import MipcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([MipcCamera(entry.runtime_data, entry)])


class MipcCamera(MipcEntity, Camera):
    """A Home Assistant camera backed by the MIPC local RPC interface."""

    def __init__(self, coordinator, entry) -> None:
        MipcEntity.__init__(self, coordinator, entry)
        Camera.__init__(self)
        options = {**DEFAULT_OPTIONS, **entry.options}
        self._options = options
        self._attr_unique_id = f"{self._id}_camera"
        self._attr_name = None
        self._attr_supported_features = (
            CameraEntityFeature.STREAM if options[CONF_ENABLE_STREAM]
            else CameraEntityFeature(0)
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        try:
            return await self.hass.async_add_executor_job(self._hub.snapshot)
        except Exception as err:
            raise HomeAssistantError(
                f"MIPC snapshot failed ({type(err).__name__})"
            ) from err

    async def stream_source(self) -> str | None:
        if not self._options[CONF_ENABLE_STREAM]:
            return None
        try:
            return await self.hass.async_add_executor_job(
                self._hub.stream_url,
                self._options[CONF_STREAM_TOKEN],
                self._options[CONF_ALLOW_REMOTE_STREAM],
            )
        except Exception as err:
            raise HomeAssistantError(
                f"MIPC RTMP stream unavailable ({type(err).__name__}): {err}"
            ) from err
