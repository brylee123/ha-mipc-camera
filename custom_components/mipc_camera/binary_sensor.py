"""Online status derived from an actual recurring camera RPC."""

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import MipcEntity


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    async_add_entities([MipcOnlineSensor(entry.runtime_data, entry)])


class MipcOnlineSensor(MipcEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "online"

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._id}_online"

    @property
    def available(self) -> bool:
        # An offline diagnostic must stay visible when the coordinator fails.
        return True

    @property
    def is_on(self) -> bool:
        return self.coordinator.last_update_success
