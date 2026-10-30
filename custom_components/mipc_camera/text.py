"""On-screen text label, preserving all other OSD configuration."""

from homeassistant.components.text import TextEntity, TextMode

from .capabilities import settings_for
from .entity import MipcSettingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        MipcText(entry.runtime_data, entry, spec)
        for spec in settings_for(entry.runtime_data.data["settings"], "text")
    )


class MipcText(MipcSettingEntity, TextEntity):
    _attr_native_min = 0
    _attr_native_max = 128
    _attr_mode = TextMode.TEXT

    @property
    def native_value(self):
        return self.current_value

    async def async_set_value(self, value):
        if not isinstance(value, str) or len(value) > 128:
            raise ValueError("OSD text is limited to 128 characters")
        await self.coordinator.async_set_value(self.spec, value)
