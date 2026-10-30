"""Relative pan/tilt buttons; available only when enabled."""

from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_ENABLE_PTZ, CONF_PAN_SPEED, CONF_PTZ_STEP, CONF_TILT_SPEED,
    DEFAULT_OPTIONS,
)
from .entity import MipcEntity


@dataclass(frozen=True, kw_only=True)
class MipcButtonDescription(ButtonEntityDescription):
    x: int
    y: int


DESCRIPTIONS = (
    MipcButtonDescription(key="pan_left", translation_key="pan_left", icon="mdi:arrow-left", x=-1, y=0),
    MipcButtonDescription(key="pan_right", translation_key="pan_right", icon="mdi:arrow-right", x=1, y=0),
    MipcButtonDescription(key="tilt_up", translation_key="tilt_up", icon="mdi:arrow-up", x=0, y=1),
    MipcButtonDescription(key="tilt_down", translation_key="tilt_down", icon="mdi:arrow-down", x=0, y=-1),
)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    options = {**DEFAULT_OPTIONS, **entry.options}
    if not options[CONF_ENABLE_PTZ]:
        return
    async_add_entities(
        MipcPtzButton(entry.runtime_data, entry, desc, options)
        for desc in DESCRIPTIONS
    )


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
        except Exception as err:
            raise HomeAssistantError(
                f"MIPC PTZ action failed ({type(err).__name__})"
            ) from err
