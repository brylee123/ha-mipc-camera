"""Connectivity and a camera-reported recording-media ready flag."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.entity import EntityCategory

from .entity import MipcEntity


async def async_setup_entry(hass, entry, async_add_entities):
    entities = [MipcOnline(entry.runtime_data, entry)]
    if entry.runtime_data.data["settings"].get("recording", {}).get("sd_ready") in (
        0,
        1,
    ):
        entities.append(MipcStorageReady(entry.runtime_data, entry))
    async_add_entities(entities)


class MipcOnline(MipcEntity, BinarySensorEntity):
    _attr_name = "Connection"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._id}_online"

    @property
    def available(self):
        return True

    @property
    def is_on(self):
        return self.coordinator.last_update_success


class MipcStorageReady(MipcEntity, BinarySensorEntity):
    _attr_name = "Recording media ready"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._id}_storage_ready"

    @property
    def is_on(self):
        value = self.coordinator.data["settings"].get("recording", {}).get("sd_ready")
        return bool(value) if value in (0, 1) else None
