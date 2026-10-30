"""Diagnostic sensors backed by verified camera RPC data."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import MipcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities((
        MipcSerialSensor(entry.runtime_data, entry),
        MipcLastSeenSensor(entry.runtime_data, entry),
    ))


class MipcSerialSensor(MipcEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "serial_number"
    _attr_icon = "mdi:identifier"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._id}_serial"

    @property
    def native_value(self):
        return self._hub.serial_number


class MipcLastSeenSensor(MipcEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "last_seen"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._id}_last_seen"

    @property
    def native_value(self):
        return self._hub.last_seen
