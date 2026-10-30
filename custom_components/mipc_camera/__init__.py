"""Home Assistant integration for MIPC-compatible cameras."""

import logging

import requests
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .api import MipcAuthenticationError, MipcHub
from .const import (
    CONF_PAN_SPEED, CONF_TILT_SPEED, DEFAULT_OPTIONS, DOMAIN, PLATFORMS,
)
from .coordinator import MipcCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register an automation action for relative pan/tilt movement."""

    async def async_move(call) -> None:
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if entry is None or entry.domain != DOMAIN or entry.runtime_data is None:
            raise HomeAssistantError("Unknown or unloaded MIPC config entry")
        coordinator: MipcCoordinator = entry.runtime_data
        opts = {**DEFAULT_OPTIONS, **entry.options}
        if not opts["enable_ptz"]:
            raise HomeAssistantError("PTZ is disabled for this camera")
        try:
            await hass.async_add_executor_job(
                coordinator.hub.move,
                call.data["x"], call.data["y"],
                call.data.get(CONF_PAN_SPEED, opts[CONF_PAN_SPEED]),
                call.data.get(CONF_TILT_SPEED, opts[CONF_TILT_SPEED]),
            )
        except Exception as err:
            raise HomeAssistantError(
                f"MIPC PTZ command failed ({type(err).__name__})"
            ) from err

    hass.services.async_register(
        DOMAIN,
        "move",
        async_move,
        schema=vol.Schema({
            vol.Required("config_entry_id"): cv.string,
            vol.Required("x"): vol.All(vol.Coerce(int), vol.Range(min=-360, max=360)),
            vol.Required("y"): vol.All(vol.Coerce(int), vol.Range(min=-360, max=360)),
            vol.Optional(CONF_PAN_SPEED): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
            vol.Optional(CONF_TILT_SPEED): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
        }),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Authenticate, connect, and set up supported platforms."""
    hub = MipcHub(
        entry.data[CONF_HOST], entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    try:
        await hass.async_add_executor_job(hub.connect)
    except MipcAuthenticationError as err:
        raise ConfigEntryAuthFailed("MIPC camera credentials rejected") from err
    except (requests.exceptions.RequestException, OSError) as err:
        raise ConfigEntryNotReady("MIPC camera is unreachable") from err
    except Exception as err:
        raise ConfigEntryNotReady(f"MIPC initialization failed ({type(err).__name__})") from err

    coordinator = MipcCoordinator(hass, hub)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Stop entities and close the HTTP session."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await hass.async_add_executor_job(entry.runtime_data.hub.close)
    return True
