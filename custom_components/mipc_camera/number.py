"""Image levels, microphone/speaker volume and motion sensitivity."""

from homeassistant.components.number import NumberEntity, NumberMode

from .capabilities import settings_for
from .entity import MipcSettingEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        MipcNumber(entry.runtime_data, entry, spec)
        for spec in settings_for(entry.runtime_data.data["settings"], "number")
    )


class MipcNumber(MipcSettingEntity, NumberEntity):
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, entry, spec):
        super().__init__(coordinator, entry, spec)
        self._attr_native_min_value, self._attr_native_max_value = (
            spec.minimum,
            spec.maximum,
        )

    @property
    def native_value(self):
        return self.current_value

    async def async_set_native_value(self, value):
        if (
            not float(value).is_integer()
            or not self.spec.minimum <= value <= self.spec.maximum
        ):
            raise ValueError("Invalid setting value")
        await self.coordinator.async_set_value(self.spec, int(value))
