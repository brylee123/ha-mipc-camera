"""Coordinate local reads and serialize settings writes with their read-back."""

import asyncio
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MipcAuthenticationError, MipcError, MipcHub
from .capabilities import Setting, settings_for, supported, value_at
from .const import DOMAIN, SCAN_INTERVAL
from .motion import MipcMotionCoordinator

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
        self.motion: MipcMotionCoordinator | None = None
        self._write_lock = asyncio.Lock()
        self._restart_task: asyncio.Task | None = None

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

    async def async_restart(self) -> None:
        """Send once, then wait for controls before rebuilding the media session."""
        async with self._write_lock:
            if self._restart_task and not self._restart_task.done():
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="restart_in_progress"
                )
            expected = {
                s.key
                for platform in ("switch", "number", "select", "text")
                for s in settings_for(self.data["settings"], platform)
            }
            sections = set(self.data["settings"])
            try:
                await self.hass.async_add_executor_job(self.hub.reboot)
            except (MipcError, ValueError, OSError) as error:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="setting_failed",
                    translation_placeholders={"error": type(error).__name__},
                ) from error
            self._restart_task = self.config_entry.async_create_background_task(
                self.hass,
                self._async_finish_restart(expected, sections),
                "MIPC restart recovery",
            )

    async def _async_finish_restart(
        self, expected: set[str], sections: set[str]
    ) -> None:
        for _ in range(12):
            await asyncio.sleep(5)
            await self.async_refresh()
            if not self.last_update_success:
                continue
            present = {
                s.key
                for platform in ("switch", "number", "select", "text")
                for s in settings_for(self.data["settings"], platform)
            }
            if sections <= self.data["settings"].keys() and expected <= present:
                break
        # This discards the old stream URL/session. HA handles setup retry if the
        # camera still cannot connect; the reboot command is never replayed.
        self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
