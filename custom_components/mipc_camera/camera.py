"""Snapshots and direct local RTMP streaming through Home Assistant."""

import asyncio
from pathlib import Path

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
    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._off_image = await self.hass.async_add_executor_job(
            Path(__file__).with_name("camera_off.jpg").read_bytes
        )
        self.coordinator.live_view_callback = self.async_set_live_view

    @property
    def available(self):
        return not self._options[CONF_ENABLE_STREAM] or super().available

    async def async_set_live_view(self, enabled: bool) -> None:
        """Replace camera media with a local still/MJPEG placeholder when off."""
        async with self._media_lock:
            if self._options[CONF_ENABLE_STREAM] == enabled:
                return
            self._options[CONF_ENABLE_STREAM] = enabled
            self._attr_supported_features = (
                CameraEntityFeature.STREAM if enabled else CameraEntityFeature(0)
            )
            # Serialize with HA stream creation, so an in-flight source request
            # cannot install a live stream after it has been switched off.
            if not self._create_stream_lock:
                self._create_stream_lock = asyncio.Lock()
            async with self._create_stream_lock:
                if self.stream is not None:
                    self.stream.dynamic_stream_settings.preload_stream = False
                    await self.stream.stop()
                    self.stream = None
            self.async_write_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Invalidate the previous stream when switching quality or unloading."""
        if self.stream is not None:
            self.stream.dynamic_stream_settings.preload_stream = False
            await self.stream.stop()
        self.coordinator.live_view_callback = None
        await super().async_will_remove_from_hass()

    def __init__(self, coordinator: MipcCoordinator, entry: MipcConfigEntry) -> None:
        Camera.__init__(self)
        MipcEntity.__init__(self, coordinator, entry)
        self._options = {**DEFAULT_OPTIONS, **entry.options}
        self._media_lock = asyncio.Lock()
        self._off_image = b""
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
        if not self._options[CONF_ENABLE_STREAM]:
            return self._off_image
        try:
            image = await self.hass.async_add_executor_job(self._hub.snapshot)
            return image if self._options[CONF_ENABLE_STREAM] else self._off_image
        except (MipcError, OSError, ValueError) as error:
            if not self._options[CONF_ENABLE_STREAM]:
                return self._off_image
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="snapshot_failed",
                translation_placeholders={"error": type(error).__name__},
            ) from error

    async def stream_source(self) -> str | None:
        if not self._options[CONF_ENABLE_STREAM]:
            return None
        try:
            source = await self.hass.async_add_executor_job(
                self._hub.stream_url, self._options[CONF_STREAM_TOKEN]
            )
            return source if self._options[CONF_ENABLE_STREAM] else None
        except (MipcError, OSError, ValueError) as error:
            if not self._options[CONF_ENABLE_STREAM]:
                return None
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="stream_failed",
                translation_placeholders={"error": type(error).__name__},
            ) from error
