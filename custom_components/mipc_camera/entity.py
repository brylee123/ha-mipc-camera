"""Shared MIPC device metadata."""

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MipcCoordinator


class MipcEntity(CoordinatorEntity[MipcCoordinator]):
    """Base for entities belonging to a single camera."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MipcCoordinator, entry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._hub = coordinator.hub
        self._id = entry.unique_id or entry.entry_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._id)},
            name=entry.title,
            manufacturer="MIPC-compatible",
            model=self._hub.model,
            serial_number=self._hub.serial_number,
            configuration_url=f"http://{self._hub.host}",
        )
