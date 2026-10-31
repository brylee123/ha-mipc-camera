"""Firmware-supported day/night selection."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ._vendor.mipc_camera_client.profiles import stream_profiles
from .api import MipcError
from .capabilities import Setting, settings_for
from .const import CONF_ENABLE_STREAM, CONF_STREAM_TOKEN, DEFAULT_OPTIONS, DOMAIN
from .coordinator import MipcConfigEntry, MipcCoordinator
from .entity import MipcEntity, MipcSettingEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant, entry: MipcConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entities = [
        MipcSelect(entry.runtime_data, entry, spec)
        for spec in settings_for(entry.runtime_data.data["settings"], "select")
    ]
    if len(MipcVideoQuality(entry.runtime_data, entry).options) > 1:
        entities.append(MipcVideoQuality(entry.runtime_data, entry))
    async_add_entities(entities)


class MipcSelect(MipcSettingEntity, SelectEntity):
    def __init__(
        self, coordinator: MipcCoordinator, entry: MipcConfigEntry, spec: Setting
    ) -> None:
        super().__init__(coordinator, entry, spec)
        self._attr_options = list(spec.options)

    @property
    def current_option(self):
        return self.current_value

    async def async_select_option(self, option: str) -> None:
        if option not in self.options:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_setting"
            )
        await self.coordinator.async_set_value(self.spec, option)


class MipcVideoQuality(MipcEntity, SelectEntity):
    """Persist a supported playback profile and reconnect the camera stream."""

    _attr_translation_key = "video_quality"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: MipcCoordinator, entry: MipcConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{self._id}_video_quality"

    @property
    def _verified(self):
        advertised = {p.token for p in stream_profiles(self._hub.info)}
        return [
            p
            for p in self._entry.data.get("stream_profiles", [])
            if isinstance(p, dict)
            and p.get("token") in advertised
            and all(
                type(p.get(k)) is int and 1 <= p[k] <= 16384
                for k in ("width", "height")
            )
        ]

    @staticmethod
    def _label(profile):
        token = profile["token"]
        names = {"p1": "Standard", "p2": "Smooth"}
        name = names.get(token, profile.get("name") or token)
        return f"{name} ({profile['width']} × {profile['height']})"

    @property
    def _profiles(self):
        return {self._label(p): p["token"] for p in self._verified}

    @property
    def options(self):
        return list(self._profiles)

    @property
    def current_option(self):
        token = self._entry.options.get(
            CONF_STREAM_TOKEN, DEFAULT_OPTIONS[CONF_STREAM_TOKEN]
        )
        return next(
            (self._label(p) for p in self._verified if p["token"] == token), None
        )

    @property
    def available(self):
        return super().available and len(self.options) > 1

    async def async_select_option(self, option: str) -> None:
        token = self._profiles.get(option)
        if token is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_setting"
            )
        if option == self.current_option:
            return
        profile = next(p for p in self._verified if p["token"] == token)
        try:
            # Decode before persisting; credentials/URLs stay private.
            if self._entry.options.get(CONF_ENABLE_STREAM, True):
                await self.hass.async_add_executor_job(
                    self._hub.check_stream_profile,
                    token,
                    profile["width"],
                    profile["height"],
                )
        except (MipcError, OSError, ValueError) as error:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="stream_failed",
                translation_placeholders={"error": type(error).__name__},
            ) from error
        self.hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, CONF_STREAM_TOKEN: token}
        )
        self.async_write_ha_state()
