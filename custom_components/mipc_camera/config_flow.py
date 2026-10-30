"""UI-first setup for MIPC cameras."""

from typing import Any
import re

import requests
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback

from .api import MipcAuthenticationError, MipcHub
from .const import (
    CONF_ALLOW_REMOTE_STREAM, CONF_ENABLE_PTZ, CONF_ENABLE_STREAM,
    CONF_PAN_SPEED, CONF_PTZ_STEP, CONF_STREAM_TOKEN, CONF_TILT_SPEED,
    DEFAULT_OPTIONS, DOMAIN,
)

_HOST_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")

class MipcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Configure a single MIPC camera."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip().lower()
            if not _HOST_RE.fullmatch(host):
                errors["base"] = "invalid_host"
            else:
                user_input[CONF_HOST] = host
                hub = MipcHub(
                    host, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
                try:
                    await self.hass.async_add_executor_job(hub.connect)
                except MipcAuthenticationError:
                    errors["base"] = "invalid_auth"
                except (requests.exceptions.RequestException, OSError):
                    errors["base"] = "cannot_connect"
                except Exception:
                    errors["base"] = "unknown"
                else:
                    unique_id = (
                        f"sn:{hub.serial_number}"
                        if hub.serial_number else f"host:{host}"
                    )
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"MIPC {hub.serial_number or host}", data=user_input
                    )
                finally:
                    await self.hass.async_add_executor_job(hub.close)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> MipcOptionsFlow:
        return MipcOptionsFlow()


class MipcOptionsFlow(OptionsFlowWithReload):
    """Enable only supported options; reload when they change."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = {**DEFAULT_OPTIONS, **self.config_entry.options}
        schema = vol.Schema({
            vol.Required(CONF_ENABLE_PTZ, default=options[CONF_ENABLE_PTZ]): bool,
            vol.Required(CONF_ENABLE_STREAM, default=options[CONF_ENABLE_STREAM]): bool,
            vol.Required(CONF_STREAM_TOKEN, default=options[CONF_STREAM_TOKEN]):
                vol.In(("p0", "p1", "p2", "p3")),
            vol.Required(
                CONF_ALLOW_REMOTE_STREAM, default=options[CONF_ALLOW_REMOTE_STREAM]
            ): bool,
            vol.Required(CONF_PTZ_STEP, default=options[CONF_PTZ_STEP]):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=360)),
            vol.Required(CONF_PAN_SPEED, default=options[CONF_PAN_SPEED]):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
            vol.Required(CONF_TILT_SPEED, default=options[CONF_TILT_SPEED]):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
