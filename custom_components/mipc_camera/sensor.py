"""Diagnostic sensors without guessed storage units."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MipcConfigEntry, MipcCoordinator
from .entity import MipcEntity

PARALLEL_UPDATES = 0


def disk(settings):
    disks = settings.get("disks", [])
    if not isinstance(disks, list):
        return {}
    return next(
        (d for d in disks if isinstance(d, dict) and d.get("token") == "sd"),
        disks[0] if len(disks) == 1 and isinstance(disks[0], dict) else {},
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: MipcConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
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
    entities = [MipcSensor(entry.runtime_data, entry, key) for key in keys]
    for interface in entry.runtime_data.data["settings"].get("network", []):
        if not isinstance(interface, dict) or not isinstance(
            interface.get("token"), str
        ):
            continue
        for field in ("mac_address", "ip_address", "connection", "link_status"):
            if isinstance(interface.get(field), str):
                entities.append(
                    MipcNetworkSensor(
                        entry.runtime_data, entry, interface["token"], field
                    )
                )
    async_add_entities(entities)


class MipcSensor(MipcEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: MipcCoordinator, entry: MipcConfigEntry, key: str
    ) -> None:
        super().__init__(coordinator, entry)
        self.key = key
        self._attr_translation_key = key
        self._attr_entity_registry_enabled_default = key not in (
            "firmware",
            "last_seen",
        )
        self._attr_unique_id = f"{self._id}_{key}"
        if key == "last_seen":
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        if key == "storage_used":
            self._attr_native_unit_of_measurement = "%"
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def available(self):
        if not super().available:
            return False
        if self.key == "firmware":
            return isinstance(self._hub.firmware, str)
        if self.key == "last_seen":
            return self._hub.last_seen is not None
        if self.key == "storage_status":
            return isinstance(disk(self.coordinator.data["settings"]).get("stat"), str)
        return self.native_value is not None

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


class MipcNetworkSensor(MipcEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry, token, field):
        super().__init__(coordinator, entry)
        self._token, self._field = token, field
        self._attr_unique_id = f"{self._id}_network_{token}_{field}"
        self._attr_translation_key = f"network_{field}"
        self._attr_translation_placeholders = {"interface": token}

    @property
    def native_value(self):
        values = [
            i
            for i in self.coordinator.data["settings"].get("network", [])
            if isinstance(i, dict) and i.get("token") == self._token
        ]
        return values[0].get(self._field) if len(values) == 1 else None

    @property
    def available(self):
        return super().available and isinstance(self.native_value, str)
