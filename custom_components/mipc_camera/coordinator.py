"""One bounded poll for a physical camera and verified settings writes."""

import logging

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MipcAuthenticationError, MipcError
from .const import DOMAIN, SCAN_INTERVAL


class MipcCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass, entry, hub):
        super().__init__(
            hass,
            logging.getLogger(__name__),
            name=DOMAIN,
            config_entry=entry,
            update_interval=SCAN_INTERVAL,
        )
        self.hub = hub

    async def _async_update_data(self):
        try:
            return await self.hass.async_add_executor_job(self.hub.refresh)
        except MipcAuthenticationError as error:
            raise ConfigEntryAuthFailed(
                "Camera device credentials were rejected"
            ) from error
        except (MipcError, OSError) as error:
            raise UpdateFailed(
                f"Camera update failed ({type(error).__name__})"
            ) from error

    async def async_set_value(self, spec, value):
        try:
            await self.hass.async_add_executor_job(self.hub.set_value, spec, value)
        except (MipcError, ValueError, OSError) as error:
            raise HomeAssistantError(
                f"Camera setting failed ({type(error).__name__})"
            ) from error
        await self.async_request_refresh()
