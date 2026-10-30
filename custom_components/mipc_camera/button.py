"""Relative pan/tilt buttons; available only when enabled."""

from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MipcError
from .const import (
    CONF_ENABLE_PTZ,
    CONF_PAN_SPEED,
    CONF_PTZ_STEP,
    CONF_TILT_SPEED,
    DEFAULT_OPTIONS,
    DOMAIN,
)
from .coordinator import MipcConfigEntry
from .entity import MipcEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class MipcButtonDescription(ButtonEntityDescription):
    x: int
    y: int


DESCRIPTIONS = (
    MipcButtonDescription(key="pan_left", translation_key="pan_left", x=-1, y=0),
    MipcButtonDescription(key="pan_right", translation_key="pan_right", x=1, y=0),
    MipcButtonDescription(key="tilt_up", translation_key="tilt_up", x=0, y=1),
    MipcButtonDescription(key="tilt_down", translation_key="tilt_down", x=0, y=-1),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: MipcConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    options = {**DEFAULT_OPTIONS, **entry.options}
    entities = [MipcRestartButton(entry.runtime_data, entry)]
    if options[CONF_ENABLE_PTZ]:
        entities.extend(
            MipcPtzButton(entry.runtime_data, entry, desc, options)
            for desc in DESCRIPTIONS
        )
    async_add_entities(entities)


class MipcPtzButton(MipcEntity, ButtonEntity):
    def __init__(self, coordinator, entry, description, options) -> None:
        super().__init__(coordinator, entry)
        self.entity_description = description
        self._options = options
        self._attr_unique_id = f"{self._id}_{description.key}"

    async def async_press(self) -> None:
        desc = self.entity_description
        try:
            await self.hass.async_add_executor_job(
                self._hub.move,
                desc.x * self._options[CONF_PTZ_STEP],
                desc.y * self._options[CONF_PTZ_STEP],
                self._options[CONF_PAN_SPEED],
                self._options[CONF_TILT_SPEED],
            )
        except (MipcError, OSError, ValueError) as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="movement_failed",
                translation_placeholders={"error": type(err).__name__},
            ) from err


class MipcRestartButton(MipcEntity, ButtonEntity):
    _attr_translation_key = "restart"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._id}_restart"

    async def async_press(self):
        await self.coordinator.async_restart()
