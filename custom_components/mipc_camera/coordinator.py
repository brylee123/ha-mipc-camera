"""Poll camera availability and information."""

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MipcHub
from .const import DOMAIN, SCAN_INTERVAL


class MipcCoordinator(DataUpdateCoordinator[dict]):
    """Data coordinator for an individual camera."""

    def __init__(self, hass, hub: MipcHub) -> None:
        super().__init__(
            hass, logger=__import__("logging").getLogger(__name__),
            name=DOMAIN, update_interval=SCAN_INTERVAL,
        )
        self.hub = hub

    async def _async_update_data(self) -> dict:
        try:
            return await self.hass.async_add_executor_job(self.hub.refresh)
        except Exception as err:
            raise UpdateFailed(f"MIPC camera check failed ({type(err).__name__})") from err
