"""Firmware-supported day/night selection."""

from homeassistant.components.select import SelectEntity

from .capabilities import settings_for
from .entity import MipcSettingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        MipcSelect(entry.runtime_data, entry, spec)
        for spec in settings_for(entry.runtime_data.data["settings"], "select")
    )


class MipcSelect(MipcSettingEntity, SelectEntity):
    def __init__(self, coordinator, entry, spec):
        super().__init__(coordinator, entry, spec)
        self._attr_options = list(spec.options)

    @property
    def current_option(self):
        return self.current_value

    async def async_select_option(self, option):
        if option not in self.options:
            raise ValueError("Unknown camera mode")
        await self.coordinator.async_set_value(self.spec, option)
