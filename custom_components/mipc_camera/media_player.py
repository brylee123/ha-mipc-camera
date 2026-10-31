"""Local speaker playback for short media and Home Assistant TTS."""

import asyncio
import logging
import math
from threading import Event
from urllib.parse import urlsplit

import aiohttp
from homeassistant.components import media_source
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .audio import MAX_MEDIA_BYTES, iter_audio
from .capabilities import settings_for
from .const import DOMAIN
from .entity import MipcSettingEntity

PARALLEL_UPDATES = 0
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    specs = settings_for(entry.runtime_data.data["settings"], "number")
    async_add_entities(
        MipcSpeaker(entry.runtime_data, entry, spec)
        for spec in specs
        if spec.key == "speaker_volume"
    )


class MipcSpeaker(MipcSettingEntity, MediaPlayerEntity):
    """A speaker is available by default only when its configuration is readable."""

    _attr_translation_key = "speaker"
    _attr_entity_category = None
    _attr_entity_registry_enabled_default = True
    _attr_state = MediaPlayerState.IDLE
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.MEDIA_ANNOUNCE
    )

    def __init__(self, coordinator, entry, spec):
        super().__init__(coordinator, entry, spec)
        self._attr_translation_key = "speaker"
        self._attr_unique_id = f"{self._id}_speaker"
        self._playback_task = None
        self._stop_event = Event()
        self._command_lock = asyncio.Lock()

    @property
    def volume_level(self):
        value = self.current_value
        return value / 100 if type(value) in (int, float) else None

    async def async_set_volume_level(self, volume):
        if (
            type(volume) not in (int, float)
            or not math.isfinite(volume)
            or not 0 <= volume <= 1
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_setting"
            )
        await self.coordinator.async_set_value(self.spec, round(volume * 100))

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )

    async def async_play_media(self, media_type, media_id, **kwargs):
        if (
            not isinstance(media_id, str)
            or not media_id
            or not (
                media_source.is_media_source_id(media_id)
                or media_type in (MediaType.MUSIC, MediaType.URL)
                or str(media_type).startswith("audio/")
            )
            or kwargs.get("enqueue") not in (None, "replace")
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_audio"
            )
        if not media_source.is_media_source_id(media_id) and not self._valid_url(
            media_id
        ):
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="invalid_audio"
            )
        async with self._command_lock:
            await self._async_stop_playback()
            self._stop_event = Event()
            self._attr_state = MediaPlayerState.BUFFERING
            self._attr_extra_state_attributes = {}
            self.async_write_ha_state()
            self._playback_task = self._entry.async_create_background_task(
                self.hass,
                self._async_play(media_id, self._stop_event),
                "MIPC speaker playback",
            )

    @staticmethod
    def _valid_url(url):
        try:
            parsed = urlsplit(url)
            return (
                parsed.scheme in ("http", "https")
                and parsed.hostname is not None
                and parsed.username is None
                and parsed.password is None
                and (parsed.port is None or 0 < parsed.port <= 65535)
            )
        except ValueError:
            return False

    async def _async_download(self, url, stop):
        result = bytearray()
        session = async_get_clientsession(self.hass)
        async with session.get(
            url, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=False
        ) as response:
            length = response.headers.get("Content-Length")
            if response.status != 200 or (
                length is not None and int(length) > MAX_MEDIA_BYTES
            ):
                raise ValueError("Audio download failed or exceeds size limit")
            async for chunk in response.content.iter_chunked(65536):
                if stop.is_set():
                    return b""
                result.extend(chunk)
                if len(result) > MAX_MEDIA_BYTES:
                    raise ValueError("Audio exceeds size limit")
        return bytes(result)

    async def _async_worker(self, stop, function, *args):
        future = self.hass.async_add_executor_job(function, *args)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            stop.set()
            await future
            raise

    async def _async_play(self, media_id, stop):
        try:
            if media_source.is_media_source_id(media_id):
                media = await media_source.async_resolve_media(
                    self.hass, media_id, self.entity_id
                )
                if not media.mime_type.startswith("audio/"):
                    raise ValueError("Media source is not audio")
                media_id = media.url
            url = async_process_play_media_url(self.hass, media_id)
            if not self._valid_url(url):
                raise ValueError("Unsupported media URL")
            data = await self._async_download(url, stop)
            if stop.is_set():
                return
            pcm = iter_audio(data, stop)
            self._attr_state = MediaPlayerState.PLAYING
            self.async_write_ha_state()
            await self._async_worker(stop, self._hub.send_audio, pcm, stop)
        except asyncio.CancelledError:
            stop.set()
            raise
        except Exception as error:
            self._attr_extra_state_attributes = {
                "playback_error": "Could not play audio"
            }
            _LOGGER.warning("MIPC speaker playback failed (%s)", type(error).__name__)
        finally:
            self._attr_state = MediaPlayerState.IDLE
            self.async_write_ha_state()

    async def _async_stop_playback(self):
        self._stop_event.set()
        if self._playback_task:
            if self.state == MediaPlayerState.BUFFERING:
                self._playback_task.cancel()
            try:
                await asyncio.shield(self._playback_task)
            except asyncio.CancelledError:
                if not self._playback_task.cancelled():
                    raise
            self._playback_task = None

    async def async_media_stop(self):
        async with self._command_lock:
            await self._async_stop_playback()

    async def async_will_remove_from_hass(self):
        await self.async_media_stop()
        await super().async_will_remove_from_hass()
