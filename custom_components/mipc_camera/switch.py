"""Explicit camera configuration toggles."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .capabilities import settings_for
from .const import CONF_ENABLE_STREAM, DEFAULT_OPTIONS
from .coordinator import MipcConfigEntry
from .entity import MipcEntity, MipcSettingEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: MipcConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            MipcLiveViewSwitch(entry.runtime_data, entry),
            *(
                MipcSwitch(entry.runtime_data, entry, spec)
                for spec in settings_for(entry.runtime_data.data["settings"], "switch")
            ),
        ]
    )


class MipcLiveViewSwitch(MipcEntity, SwitchEntity):
    """Local viewing preference, independent of camera recording and arming."""

    _attr_translation_key = "live_view"
    _attr_available = True

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._id}_live_view"

    @property
    def available(self):
        return True

    @property
    def is_on(self):
        return self._entry.options.get(
            CONF_ENABLE_STREAM, DEFAULT_OPTIONS[CONF_ENABLE_STREAM]
        )

    async def _async_set_enabled(self, enabled):
        if self.is_on == enabled:
            return
        # Stop media before acknowledging the switch; the options listener is
        # idempotent and also handles changes made through the options form.
        if self.coordinator.live_view_callback:
            await self.coordinator.live_view_callback(enabled)
        self.hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, CONF_ENABLE_STREAM: enabled}
        )
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs):
        await self._async_set_enabled(True)

    async def async_turn_off(self, **kwargs):
        await self._async_set_enabled(False)


class MipcSwitch(MipcSettingEntity, SwitchEntity):
    @property
    def is_on(self):
        return bool(self.current_value)

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_set_value(self.spec, True)

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_set_value(self.spec, False)
