"""Snapshots and direct local RTMP streaming through Home Assistant."""

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MipcError
from .const import CONF_ENABLE_STREAM, CONF_STREAM_TOKEN, DEFAULT_OPTIONS, DOMAIN
from .coordinator import MipcConfigEntry, MipcCoordinator
from .entity import MipcEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: MipcConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([MipcCamera(entry.runtime_data, entry)])


class MipcCamera(MipcEntity, Camera):
    def __init__(self, coordinator: MipcCoordinator, entry: MipcConfigEntry) -> None:
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

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        try:
            return await self.hass.async_add_executor_job(self._hub.snapshot)
        except (MipcError, OSError, ValueError) as error:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="snapshot_failed",
                translation_placeholders={"error": type(error).__name__},
            ) from error

    async def stream_source(self) -> str | None:
        if not self._options[CONF_ENABLE_STREAM]:
            return None
        try:
            return await self.hass.async_add_executor_job(
                self._hub.stream_url, self._options[CONF_STREAM_TOKEN]
            )
        except (MipcError, OSError, ValueError) as error:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="stream_failed",
                translation_placeholders={"error": type(error).__name__},
            ) from error
