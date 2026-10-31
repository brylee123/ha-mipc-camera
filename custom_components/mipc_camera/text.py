"""On-screen text label, preserving all other OSD configuration."""

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import settings_for
from .const import DOMAIN
from .coordinator import MipcConfigEntry
from .entity import MipcSettingEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: MipcConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
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

    async def async_set_value(self, value: str) -> None:
        if not isinstance(value, str) or len(value) > 128:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_setting"
            )
        await self.coordinator.async_set_value(self.spec, value)
