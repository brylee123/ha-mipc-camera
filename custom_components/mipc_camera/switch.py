"""Explicit camera configuration toggles."""

from homeassistant.components.switch import SwitchEntity

from .capabilities import settings_for
from .entity import MipcSettingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        MipcSwitch(entry.runtime_data, entry, spec)
        for spec in settings_for(entry.runtime_data.data["settings"], "switch")
    )


class MipcSwitch(MipcSettingEntity, SwitchEntity):
    @property
    def is_on(self):
        return bool(self.current_value)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_value(self.spec, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_value(self.spec, False)
