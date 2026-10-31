"""Explicit whitelist: no raw device documents, credentials, IDs or media URLs."""

from ._vendor import LIBRARY_COMMIT, LIBRARY_VERSION
from .const import DEFAULT_OPTIONS
from .motion import motion_armed


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "library_version": LIBRARY_VERSION,
        "library_commit": LIBRARY_COMMIT,
        "connected": coordinator.last_update_success,
        "motion_listener_connected": bool(
            coordinator.motion and coordinator.motion.last_update_success
        ),
        "motion_alarm_armed": motion_armed(coordinator.data.get("settings", {})),
        "model": coordinator.hub.model,
        "firmware": coordinator.hub.firmware,
        "readable_sections": sorted(coordinator.data.get("settings", {})),
        "section_errors": dict(coordinator.data.get("errors", {})),
        "options": {
            key: entry.options.get(key, value) for key, value in DEFAULT_OPTIONS.items()
        },
    }
