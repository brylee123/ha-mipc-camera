"""Camera-reported motion pulses represented by Home Assistant event entities."""

from datetime import datetime, timezone

from homeassistant.components.event import EventDeviceClass, EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MipcConfigEntry, MipcCoordinator
from .entity import MipcEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: MipcConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.runtime_data.motion:
        async_add_entities([MipcMotion(entry.runtime_data, entry)])


class MipcMotion(MipcEntity, EventEntity):
    _attr_translation_key = "motion"
    _attr_device_class = EventDeviceClass.MOTION
    _attr_event_types = ["motion"]

    def __init__(self, coordinator: MipcCoordinator, entry: MipcConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._id}_motion"
        self.motion = coordinator.motion
        self._last_received = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        attributes = self.state_attributes
        self._last_received = (
            attributes.get("message_id"),
            attributes.get("camera_timestamp"),
        )
        self.async_on_remove(
            self.motion.async_add_listener(self._handle_coordinator_update)
        )

    @property
    def available(self):
        return super().available and self.motion.last_update_success

    @callback
    def _handle_coordinator_update(self) -> None:
        event = self.motion.data
        if event is not None:
            timestamp = datetime.fromtimestamp(
                event.timestamp, tz=timezone.utc
            ).isoformat()
            key = (event.message_id, timestamp)
            if key != self._last_received:
                self._last_received = key
                if self.available:
                    self._trigger_event(
                        "motion",
                        {"message_id": event.message_id, "camera_timestamp": timestamp},
                    )
        self.async_write_ha_state()
