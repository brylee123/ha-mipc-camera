"""Firmware-supported day/night selection."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import Setting, settings_for
from .const import DOMAIN
from .coordinator import MipcConfigEntry, MipcCoordinator
from .entity import MipcSettingEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: MipcConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        MipcSelect(entry.runtime_data, entry, spec)
        for spec in settings_for(entry.runtime_data.data["settings"], "select")
    )


class MipcSelect(MipcSettingEntity, SelectEntity):
    def __init__(
        self, coordinator: MipcCoordinator, entry: MipcConfigEntry, spec: Setting
    ) -> None:
        super().__init__(coordinator, entry, spec)
        self._attr_options = list(spec.options)

    @property
    def current_option(self):
        return self.current_value

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_setting"
            )
        await self.coordinator.async_set_value(self.spec, option)
