"""Connectivity and a camera-reported recording-media ready flag."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MipcConfigEntry, MipcCoordinator
from .entity import MipcEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: MipcConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities = [MipcOnline(entry.runtime_data, entry)]
    if entry.runtime_data.data["settings"].get("recording", {}).get("sd_ready") in (
        0,
        1,
    ):
        entities.append(MipcStorageReady(entry.runtime_data, entry))
    async_add_entities(entities)


class MipcOnline(MipcEntity, BinarySensorEntity):
    _attr_translation_key = "connection"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: MipcCoordinator, entry: MipcConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._id}_online"

    @property
    def available(self):
        return True

    @property
    def is_on(self):
        return self.coordinator.last_update_success


class MipcStorageReady(MipcEntity, BinarySensorEntity):
    _attr_translation_key = "recording_media_ready"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: MipcCoordinator, entry: MipcConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._id}_storage_ready"

    @property
    def available(self):
        value = self.coordinator.data["settings"].get("recording", {}).get("sd_ready")
        return super().available and type(value) in (int, bool) and value in (0, 1)

    @property
    def is_on(self):
        value = self.coordinator.data["settings"].get("recording", {}).get("sd_ready")
        return bool(value) if value in (0, 1) else None
