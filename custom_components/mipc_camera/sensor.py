"""Diagnostic sensors without guessed storage units."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import EntityCategory

from .entity import MipcEntity


def disk(settings):
    disks = settings.get("disks", [])
    if not isinstance(disks, list):
        return {}
    return next(
        (d for d in disks if isinstance(d, dict) and d.get("token") == "sd"),
        disks[0] if len(disks) == 1 and isinstance(disks[0], dict) else {},
    )


async def async_setup_entry(hass, entry, async_add_entities):
    keys = ["firmware", "last_seen"]
    data = disk(entry.runtime_data.data["settings"])
    if isinstance(data.get("stat"), str):
        keys.append("storage_status")
    if (
        type(data.get("size")) is int
        and type(data.get("used_size")) is int
        and data["size"] > 0
        and 0 <= data["used_size"] <= data["size"]
    ):
        keys.append("storage_used")
    async_add_entities(MipcSensor(entry.runtime_data, entry, key) for key in keys)


class MipcSensor(MipcEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator, entry)
        self.key = key
        self._attr_name = {
            "firmware": "Firmware",
            "last_seen": "Last seen",
            "storage_status": "Storage status",
            "storage_used": "Storage used",
        }[key]
        self._attr_unique_id = f"{self._id}_{key}"
        if key == "last_seen":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        if key == "storage_used":
            self._attr_native_unit_of_measurement = "%"

    @property
    def native_value(self):
        if self.key == "firmware":
            return self._hub.firmware
        if self.key == "last_seen":
            return self._hub.last_seen
        current = disk(self.coordinator.data["settings"])
        if self.key == "storage_status":
            return current.get("stat")
        size, used = current.get("size"), current.get("used_size")
        if type(size) is int and type(used) is int and size > 0 and 0 <= used <= size:
            return round(100 * used / size, 1)
        return None
