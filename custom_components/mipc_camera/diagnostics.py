"""Sanitized diagnostics; never export authentication material or stream URLs."""

from importlib.metadata import version

from homeassistant.helpers.redact import async_redact_data

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass, entry) -> dict:
    coordinator = entry.runtime_data
    hub = coordinator.hub
    return {
        "integration": DOMAIN,
        "library_version": version("mipc-camera-client"),
        "connected": coordinator.last_update_success,
        "last_seen": hub.last_seen.isoformat() if hub.last_seen else None,
        "last_error_type": hub.last_error,
        "camera": async_redact_data(
            {
                "host": hub.host,
                "serial_number": hub.serial_number,
                "model": hub.model,
            },
            {"host", "serial_number"},
        ),
        "options": dict(entry.options),
        "api_features": ["jpeg_snapshot", "rtmp_stream", "relative_ptz", "device_info"],
    }
