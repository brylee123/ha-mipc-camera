"""Shared metadata and per-setting availability."""

from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .capabilities import Setting, supported, value_at
from .const import DOMAIN
from .coordinator import MipcConfigEntry, MipcCoordinator


class MipcEntity(CoordinatorEntity[MipcCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: MipcCoordinator, entry: MipcConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry, self._hub = entry, coordinator.hub
        self._id = entry.unique_id or entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._id)},
            name=entry.title,
            manufacturer=self._hub.info.get("mfc") or "MIPC",
            model=self._hub.model,
            sw_version=self._hub.firmware,
            serial_number=self._hub.serial_number,
            configuration_url=f"http://{self._hub.host}",
        )


class MipcSettingEntity(MipcEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: MipcCoordinator, entry: MipcConfigEntry, spec: Setting
    ) -> None:
        super().__init__(coordinator, entry)
        self.spec = spec
        self._attr_translation_key = spec.translation_key or spec.key
        self._attr_translation_placeholders = spec.translation_placeholders or {}
        self._attr_unique_id = f"{self._id}_{spec.key}"

    @property
    def available(self):
        return super().available and supported(
            self.spec, self.coordinator.data["settings"]
        )

    @property
    def current_value(self):
        return value_at(self.coordinator.data["settings"], self.spec.path)
