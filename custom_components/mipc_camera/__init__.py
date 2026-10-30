"""Local MIPC cameras, configured through Home Assistant's UI."""

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .api import MipcAuthenticationError, MipcError, MipcHub
from .const import (
    CONF_ENABLE_PTZ,
    CONF_PAN_SPEED,
    CONF_TILT_SPEED,
    DEFAULT_OPTIONS,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MipcCoordinator

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config):
    async def async_move(call):
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if (
            entry is None
            or entry.domain != DOMAIN
            or getattr(entry, "runtime_data", None) is None
        ):
            raise HomeAssistantError("Unknown or unloaded camera")
        options = {**DEFAULT_OPTIONS, **entry.options}
        if not options[CONF_ENABLE_PTZ]:
            raise HomeAssistantError(
                "Enable PTZ only after verifying this camera has motors"
            )
        try:
            await hass.async_add_executor_job(
                entry.runtime_data.hub.move,
                call.data["x"],
                call.data["y"],
                call.data.get(CONF_PAN_SPEED, options[CONF_PAN_SPEED]),
                call.data.get(CONF_TILT_SPEED, options[CONF_TILT_SPEED]),
            )
        except (MipcError, ValueError, OSError) as error:
            raise HomeAssistantError(
                f"Camera movement failed ({type(error).__name__})"
            ) from error

    hass.services.async_register(
        DOMAIN,
        "move",
        async_move,
        schema=vol.Schema(
            {
                vol.Required("config_entry_id"): cv.string,
                vol.Required("x"): vol.All(
                    vol.Coerce(int), vol.Range(min=-360, max=360)
                ),
                vol.Required("y"): vol.All(
                    vol.Coerce(int), vol.Range(min=-360, max=360)
                ),
                vol.Optional(CONF_PAN_SPEED): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=100)
                ),
                vol.Optional(CONF_TILT_SPEED): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=100)
                ),
            }
        ),
    )
    return True


async def async_setup_entry(hass, entry):
    hub = MipcHub(
        entry.data["host"], entry.data.get("username", ""), entry.data["password"]
    )
    try:
        await hass.async_add_executor_job(hub.connect)
        coordinator = MipcCoordinator(hass, entry, hub)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except MipcAuthenticationError as error:
        await hass.async_add_executor_job(hub.close)
        raise ConfigEntryAuthFailed("Camera device credentials rejected") from error
    except (MipcError, OSError) as error:
        await hass.async_add_executor_job(hub.close)
        raise ConfigEntryNotReady(
            f"Camera unavailable ({type(error).__name__})"
        ) from error
    except Exception:
        await hass.async_add_executor_job(hub.close)
        raise
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await hass.async_add_executor_job(entry.runtime_data.hub.close)
    return True
