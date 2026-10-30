"""Local device setup, credential renewal and connection reconfiguration."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback

from .api import (
    MipcAuthenticationError,
    MipcError,
    MipcHub,
    MipcTransportError,
    valid_host,
)
from .const import DEFAULT_OPTIONS, DOMAIN


def connection_schema(defaults=None, password_only=False):
    defaults = defaults or {}
    schema = {}
    if not password_only:
        schema[vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, ""))] = str
    schema[vol.Optional(CONF_USERNAME, default=defaults.get(CONF_USERNAME, ""))] = str
    schema[vol.Required(CONF_PASSWORD)] = vol.All(str, vol.Length(min=1))
    return vol.Schema(schema)


async def validate(hass, data):
    hub = MipcHub(data[CONF_HOST], data.get(CONF_USERNAME, ""), data[CONF_PASSWORD])
    try:
        await hass.async_add_executor_job(hub.connect)
        return {
            "unique_id": f"sn:{hub.serial_number}",
            "title": hub.info.get("nick") or "MIPC camera",
        }
    finally:
        await hass.async_add_executor_job(hub.close)


class MipcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _check(self, data, errors):
        data[CONF_HOST] = data[CONF_HOST].strip().lower()
        if not valid_host(data[CONF_HOST]):
            errors["base"] = "invalid_host"
            return None
        try:
            return await validate(self.hass, data)
        except MipcAuthenticationError:
            errors["base"] = "invalid_auth"
        except (MipcTransportError, OSError):
            errors["base"] = "cannot_connect"
        except (MipcError, ValueError):
            errors["base"] = "unknown"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors = {}
        if user_input is not None:
            info = await self._check(user_input, errors)
            if info:
                await self.async_set_unique_id(info["unique_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=user_input)
        return self.async_show_form(
            step_id="user", data_schema=connection_schema(user_input), errors=errors
        )

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            info = await self._check(data, errors)
            if info and info["unique_id"] != entry.unique_id:
                errors["base"] = "device_mismatch"
            elif info:
                return self.async_update_reload_and_abort(entry, data_updates=data)
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=connection_schema(entry.data, True),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()
        errors = {}
        if user_input is not None:
            info = await self._check(user_input, errors)
            if info and info["unique_id"] != entry.unique_id:
                errors["base"] = "device_mismatch"
            elif info:
                return self.async_update_reload_and_abort(
                    entry, data_updates=user_input, reason="reconfigure_successful"
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=connection_schema(entry.data),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MipcOptionsFlow()


class MipcOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = {**DEFAULT_OPTIONS, **self.config_entry.options}
        schema = vol.Schema(
            {
                vol.Required("enable_ptz", default=options["enable_ptz"]): bool,
                vol.Required("enable_stream", default=options["enable_stream"]): bool,
                vol.Required("stream_token", default=options["stream_token"]): vol.In(
                    ("p0", "p1", "p2", "p3")
                ),
                vol.Required("ptz_step", default=options["ptz_step"]): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=30)
                ),
                vol.Required("pan_speed", default=options["pan_speed"]): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=100)
                ),
                vol.Required("tilt_speed", default=options["tilt_speed"]): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=100)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
