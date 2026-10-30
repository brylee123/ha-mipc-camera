"""Image levels, microphone/speaker volume and motion sensitivity."""

from homeassistant.components.number import NumberEntity, NumberMode
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
        MipcNumber(entry.runtime_data, entry, spec)
        for spec in settings_for(entry.runtime_data.data["settings"], "number")
    )


class MipcNumber(MipcSettingEntity, NumberEntity):
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(
        self, coordinator: MipcCoordinator, entry: MipcConfigEntry, spec: Setting
    ) -> None:
        super().__init__(coordinator, entry, spec)
        self._attr_native_min_value, self._attr_native_max_value = (
            spec.minimum,
            spec.maximum,
        )

    @property
    def native_value(self):
        return self.current_value

    async def async_set_native_value(self, value: float) -> None:
        if (
            not float(value).is_integer()
            or not self.spec.minimum <= value <= self.spec.maximum
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_setting"
            )
        await self.coordinator.async_set_value(self.spec, int(value))
