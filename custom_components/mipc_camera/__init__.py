"""Local MIPC cameras, configured through Home Assistant's UI."""

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryError,
    ConfigEntryNotReady,
    HomeAssistantError,
    ServiceValidationError,
)
from homeassistant.helpers import config_validation as cv

from ._vendor.mipc_camera_client.profiles import stream_profiles
from .api import MipcAuthenticationError, MipcError, MipcHub
from .const import (
    CONF_ENABLE_PTZ,
    CONF_ENABLE_STREAM,
    CONF_MOTION_EVENTS,
    CONF_PAN_SPEED,
    CONF_TILT_SPEED,
    DEFAULT_OPTIONS,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import MipcConfigEntry, MipcCoordinator
from .motion import MipcMotionCoordinator, motion_supported

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config):
    async def async_move(call: ServiceCall) -> None:
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
            or getattr(entry, "runtime_data", None) is None
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_unavailable"
            )
        options = {**DEFAULT_OPTIONS, **entry.options}
        if not options[CONF_ENABLE_PTZ]:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="ptz_disabled"
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
                translation_domain=DOMAIN,
                translation_key="movement_failed",
                translation_placeholders={"error": type(error).__name__},
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

    async def async_factory_reset(call: ServiceCall) -> None:
        entry = hass.config_entries.async_get_entry(call.data["config_entry_id"])
        if not call.data["confirm"]:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="reset_confirmation_required"
            )
        if (
            entry is None
            or entry.domain != DOMAIN
            or entry.state is not ConfigEntryState.LOADED
            or getattr(entry, "runtime_data", None) is None
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="entry_unavailable"
            )
        async with entry.runtime_data._write_lock:
            try:
                await hass.async_add_executor_job(entry.runtime_data.hub.factory_reset)
            except (MipcError, ValueError, OSError) as error:
                raise HomeAssistantError(
                    translation_domain=DOMAIN,
                    translation_key="setting_failed",
                    translation_placeholders={"error": type(error).__name__},
                ) from error

    hass.services.async_register(
        DOMAIN,
        "factory_reset",
        async_factory_reset,
        schema=vol.Schema(
            {
                vol.Required("config_entry_id"): cv.string,
                vol.Required("confirm"): vol.Boolean(),
            }
        ),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: MipcConfigEntry) -> bool:
    hub = MipcHub(
        entry.data["host"], entry.data.get("username", ""), entry.data["password"]
    )
    try:
        await hass.async_add_executor_job(hub.connect)
        if entry.unique_id is not None and entry.unique_id != f"sn:{hub.serial_number}":
            raise ConfigEntryError(
                translation_domain=DOMAIN, translation_key="identity_changed"
            )
        coordinator = MipcCoordinator(hass, entry, hub)
        await coordinator.async_config_entry_first_refresh()
        advertised = stream_profiles(hub.info)
        signature = [hub.firmware, [[p.token, p.name] for p in advertised]]
        if (
            entry.options.get(CONF_ENABLE_STREAM, DEFAULT_OPTIONS[CONF_ENABLE_STREAM])
            and len(advertised) > 1
            and entry.data.get("profile_signature") != signature
        ):
            try:
                profiles = await hass.async_add_executor_job(
                    hub.discover_stream_profiles
                )
            except MipcAuthenticationError:
                raise
            except (MipcError, OSError):
                profiles = []
            hass.config_entries.async_update_entry(
                entry,
                data={
                    **entry.data,
                    "profile_signature": signature
                    if len([p for p in profiles if p.get("width") and p.get("height")])
                    > 1
                    else None,
                    "stream_profiles": profiles,
                },
            )
        entry.runtime_data = coordinator
        if entry.options.get(CONF_MOTION_EVENTS, False) and motion_supported(
            coordinator.data["settings"]
        ):
            coordinator.motion = MipcMotionCoordinator(coordinator)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        if coordinator.motion:
            coordinator.motion.start()
    except MipcAuthenticationError as error:
        await hass.async_add_executor_job(hub.close)
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN, translation_key="invalid_auth"
        ) from error
    except (MipcError, OSError) as error:
        await hass.async_add_executor_job(hub.close)
        raise ConfigEntryNotReady(
            translation_domain=DOMAIN,
            translation_key="update_failed",
            translation_placeholders={"error": type(error).__name__},
        ) from error
    except BaseException:
        await hass.async_add_executor_job(hub.close)
        raise
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: MipcConfigEntry) -> None:
    coordinator = entry.runtime_data
    previous = {**DEFAULT_OPTIONS, **coordinator.media_options}
    current = {**DEFAULT_OPTIONS, **entry.options}
    changed = {key for key in current if current[key] != previous.get(key)}
    if changed <= {CONF_ENABLE_STREAM} and coordinator.live_view_callback:
        await coordinator.live_view_callback(current[CONF_ENABLE_STREAM])
        coordinator.media_options = dict(entry.options)
        coordinator.async_update_listeners()
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MipcConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    if entry.runtime_data.motion:
        await entry.runtime_data.motion.async_stop()
    await hass.async_add_executor_job(entry.runtime_data.hub.close)
    return True
