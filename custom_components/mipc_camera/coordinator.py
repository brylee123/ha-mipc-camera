"""Coordinate local reads and serialize settings writes with their read-back."""

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MipcAuthenticationError, MipcError, MipcHub
from .capabilities import Setting, supported, value_at
from .const import DOMAIN, SCAN_INTERVAL

type MipcConfigEntry = ConfigEntry[MipcCoordinator]

_LOGGER = logging.getLogger(__name__)


class MipcCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Share a single poll and connection across a camera's entities."""

    config_entry: MipcConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: MipcConfigEntry, hub: MipcHub
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=SCAN_INTERVAL,
        )
        self.hub = hub
        self._write_lock = asyncio.Lock()

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.hass.async_add_executor_job(self.hub.refresh)
        except MipcAuthenticationError as error:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from error
        except (MipcError, OSError) as error:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": type(error).__name__},
            ) from error

    async def async_set_value(self, spec: Setting, value: str | int | bool) -> None:
        """Never replay a write; verify the new state before completing an action."""
        async with self._write_lock:
            try:
                await self.hass.async_add_executor_job(self.hub.set_value, spec, value)
            except (MipcError, ValueError, OSError) as error:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="setting_failed",
                    translation_placeholders={"error": type(error).__name__},
                ) from error
            await self.async_refresh()
            if not self.last_update_success:
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="readback_failed"
                )
            if (
                not supported(spec, self.data["settings"])
                or value_at(self.data["settings"], spec.path) != value
            ):
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="write_not_applied"
                )
