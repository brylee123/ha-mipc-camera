"""Speaker discovery, real audio decoding, media-source playback and cleanup."""

import asyncio
import threading
import wave
from fractions import Fraction
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import av
import pytest
from homeassistant.components.media_player import MediaPlayerState
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.mipc_camera.audio import MAX_MEDIA_BYTES, decode_audio
from custom_components.mipc_camera.media_player import MipcSpeaker
from tests.test_integration import setup


def wav(seconds=0.1, rate=16000):
    output = BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(bytes(int(seconds * rate) * 2))
    return output.getvalue()


def speaker(hass, config):
    entity_id = next(
        e.entity_id
        for e in er.async_get(hass).entities.values()
        if e.config_entry_id == config.entry_id and e.domain == "media_player"
    )
    from homeassistant.components.media_player.const import DATA_COMPONENT

    return hass.data[DATA_COMPONENT].get_entity(entity_id)


@pytest.fixture
def real_executor(hass, monkeypatch):
    monkeypatch.setattr(
        hass,
        "async_add_executor_job",
        lambda function, *args: hass.loop.run_in_executor(None, function, *args),
    )


@pytest.fixture(autouse=True)
def consume_pcm(hub):
    hub.send_audio.side_effect = lambda chunks, stop: b"".join(chunks)


async def test_speaker_is_enabled_by_default_and_shares_verified_volume(hass, hub):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    registration = er.async_get(hass).async_get(entity.entity_id)
    assert registration.disabled_by is None
    assert entity.name == "Speaker"
    assert entity.volume_level == 0.4
    await entity.async_set_volume_level(0.23)
    assert entity.volume_level == 0.23
    assert hub.settings["speaker"]["level"] == 23
    assert hass.states.get(entity.entity_id).state == MediaPlayerState.IDLE
    for value in [float("nan"), float("inf"), -1, 2, True]:
        with pytest.raises(ServiceValidationError):
            await entity.async_set_volume_level(value)


async def test_no_speaker_is_invented_when_camera_does_not_report_one(hass, hub):
    hub.settings.pop("speaker")
    config = await setup(hass, hub)
    assert not any(
        e.domain == "media_player" and e.config_entry_id == config.entry_id
        for e in er.async_get(hass).entities.values()
    )


async def test_real_wav_download_decodes_and_uploads_locally(hass, hub, aioclient_mock):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    aioclient_mock.get("http://media.test/clip.wav", content=wav())
    await entity.async_play_media(
        "audio/wav", "http://media.test/clip.wav", announce=True
    )
    # HA starts background tasks eagerly; a tiny mocked clip can already finish
    # before this call returns. Active-state behavior is checked with a blocked
    # upload below.
    await entity._playback_task
    pcm, stop = hub.send_audio.call_args.args
    assert isinstance(stop, threading.Event)
    assert entity.state == MediaPlayerState.IDLE
    assert not entity.extra_state_attributes
    hub.set_value.assert_not_called()


async def test_tts_media_source_is_resolved_for_this_player(hass, hub, aioclient_mock):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    uri = "media-source://tts/provider?message=private"
    resolve = AsyncMock(
        return_value=SimpleNamespace(
            url="http://media.test/tts.wav", mime_type="audio/wav"
        )
    )
    aioclient_mock.get("http://media.test/tts.wav", content=wav())
    with patch(
        "custom_components.mipc_camera.media_player.media_source.async_resolve_media",
        resolve,
    ):
        await entity.async_play_media("music", uri)
        await entity._playback_task
    resolve.assert_awaited_once_with(hass, uri, entity.entity_id)
    hub.send_audio.assert_called_once()


@pytest.mark.parametrize(
    "url",
    [
        "file:///config/secrets.yaml",
        "ftp://example.test/a",
        "http://u:p@example.test/a",
        "http://example.test:bad/a",
        "",
        "http:///a",
    ],
)
async def test_unsupported_urls_never_fetch_or_publish(hass, hub, url):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    with pytest.raises(ServiceValidationError):
        await entity.async_play_media("music", url)
    hub.send_audio.assert_not_called()


@pytest.mark.parametrize(
    "kind,options", [("video/mp4", {}), ("music", {"enqueue": "add"})]
)
async def test_no_video_or_queued_playback(hass, hub, kind, options):
    config = await setup(hass, hub)
    with pytest.raises(ServiceValidationError):
        await speaker(hass, config).async_play_media(
            kind, "http://media.test/file", **options
        )


@pytest.mark.parametrize(
    "status,body",
    [
        (302, b""),
        (404, b""),
        (200, b"#EXTM3U\nfile:///config/secrets.yaml"),
        (200, bytes(MAX_MEDIA_BYTES + 1)),
    ],
)
async def test_bad_downloads_are_reported_without_publishing(
    hass, hub, aioclient_mock, status, body
):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    aioclient_mock.get("http://media.test/fail", status=status, content=body)
    await entity.async_play_media("music", "http://media.test/fail")
    await entity._playback_task
    assert entity.extra_state_attributes == {"playback_error": "Could not play audio"}
    assert entity.state == MediaPlayerState.IDLE
    if status != 200 or len(body) > MAX_MEDIA_BYTES:
        hub.send_audio.assert_not_called()


async def test_stop_joins_upload_and_leaves_settings_connection_open(
    hass, hub, aioclient_mock, real_executor
):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    started = threading.Event()

    def upload(pcm, stop):
        started.set()
        assert stop.wait(3)

    hub.send_audio.side_effect = upload
    aioclient_mock.get("http://media.test/a.wav", content=wav())
    await entity.async_play_media("music", "http://media.test/a.wav")
    async with asyncio.timeout(5):
        while not started.is_set():
            await asyncio.sleep(0)
        assert entity.state == MediaPlayerState.PLAYING
        await entity.async_media_stop()
    assert entity._playback_task is None
    assert entity.state == MediaPlayerState.IDLE
    hub.close.assert_not_called()


async def test_unload_joins_upload(hass, hub, aioclient_mock, real_executor):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    started = threading.Event()

    def upload(pcm, stop):
        started.set()
        stop.wait(3)

    hub.send_audio.side_effect = upload
    aioclient_mock.get("http://media.test/a.wav", content=wav())
    await entity.async_play_media("music", "http://media.test/a.wav")
    async with asyncio.timeout(5):
        while not started.is_set():
            await asyncio.sleep(0)
        assert await hass.config_entries.async_unload(config.entry_id)
    assert entity._playback_task is None


async def test_stop_cancels_pending_download_without_opening_talk(hass, hub):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    started = asyncio.Event()

    async def download(*args):
        started.set()
        await asyncio.Event().wait()

    with patch.object(entity, "_async_download", side_effect=download):
        await entity.async_play_media("music", "http://media.test/slow")
        await started.wait()
        await entity.async_media_stop()
    assert entity._playback_task is None
    assert entity.state == MediaPlayerState.IDLE
    hub.send_audio.assert_not_called()


def test_wav_resamples_to_16khz_and_rejects_long_audio():
    assert len(decode_audio(wav(rate=44100), threading.Event())) == 3200
    assert len(decode_audio(wav(seconds=31), threading.Event())) == 31 * 32000
    with pytest.raises(ValueError):
        decode_audio(b"", threading.Event())
    with pytest.raises(ValueError):
        decode_audio(bytes(MAX_MEDIA_BYTES + 1), threading.Event())
    stop = threading.Event()
    stop.set()
    assert decode_audio(wav(), stop) == b""


async def test_browse_filters_audio(hass, hub):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    with patch(
        "custom_components.mipc_camera.media_player.media_source.async_browse_media",
        new_callable=AsyncMock,
    ) as browse:
        await entity.async_browse_media()
    filter_fn = browse.call_args.kwargs["content_filter"]
    assert filter_fn(SimpleNamespace(media_content_type="audio/mpeg"))
    assert not filter_fn(SimpleNamespace(media_content_type="video/mp4"))


async def test_cancelled_executor_is_joined_before_cleanup(hass, hub, real_executor):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    stop = threading.Event()
    started = threading.Event()
    finished = threading.Event()

    def work():
        started.set()
        stop.wait(3)
        finished.set()

    task = asyncio.create_task(entity._async_worker(stop, work))
    while not started.is_set():
        await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished.is_set()


def test_url_check_rejects_non_http_sources():
    assert MipcSpeaker._valid_url("https://media.test/audio.mp3")
    assert not MipcSpeaker._valid_url("http://media.test:0/a")


@pytest.mark.parametrize(
    "container_format,codec,rate",
    [
        ("mp3", "libmp3lame", 16000),
        ("flac", "flac", 16000),
        ("ogg", "libopus", 48000),
        ("ipod", "aac", 16000),
    ],
)
def test_real_supported_audio_formats_decode_without_external_inputs(
    container_format, codec, rate
):
    buffer = BytesIO()
    with av.open(buffer, mode="w", format=container_format) as output:
        stream = output.add_stream(codec, rate=rate)
        stream.layout = "mono"
        resampler = av.AudioResampler(
            format=stream.codec_context.codec.audio_formats[0].name,
            layout="mono",
            rate=rate,
        )
        frame = av.AudioFrame(format="s16", layout="mono", samples=rate // 5)
        frame.sample_rate = rate
        frame.time_base = Fraction(1, rate)
        frame.pts = 0
        frame.planes[0].update(bytes(frame.planes[0].buffer_size))
        for converted in resampler.resample(frame):
            for packet in stream.encode(converted):
                output.mux(packet)
        for packet in stream.encode(None):
            output.mux(packet)
    assert len(decode_audio(buffer.getvalue(), threading.Event())) > 1000


def test_media_with_video_only_cannot_be_sent_to_speaker():
    buffer = BytesIO()
    with av.open(buffer, mode="w", format="mp4") as output:
        stream = output.add_stream("mpeg4", rate=1)
        stream.width = stream.height = 16
        frame = av.VideoFrame(16, 16, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes(plane.buffer_size))
        for packet in stream.encode(frame):
            output.mux(packet)
        for packet in stream.encode(None):
            output.mux(packet)
    with pytest.raises(ValueError, match="no audio"):
        decode_audio(buffer.getvalue(), threading.Event())


@pytest.mark.parametrize(
    "mime,url",
    [("video/mp4", "http://media.test/a"), ("audio/wav", "file:///etc/passwd")],
)
async def test_unusable_media_source_never_fetches_or_uploads(hass, hub, mime, url):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    with patch(
        "custom_components.mipc_camera.media_player.media_source.async_resolve_media",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(mime_type=mime, url=url),
    ):
        await entity.async_play_media("music", "media-source://test/a")
        await entity._playback_task
    assert entity.extra_state_attributes["playback_error"]
    hub.send_audio.assert_not_called()


@pytest.mark.parametrize("stage", ["download"])
async def test_stop_between_preparation_steps_never_uploads(hass, hub, stage):
    config = await setup(hass, hub)
    entity = speaker(hass, config)

    async def download(url, stop):
        if stage == "download":
            stop.set()
        return wav()

    def decode(data, stop):
        stop.set()
        return bytes(3200)

    with (
        patch.object(entity, "_async_download", side_effect=download),
        patch(
            "custom_components.mipc_camera.media_player.iter_audio",
            side_effect=decode,
        ),
    ):
        await entity.async_play_media("music", "http://media.test/a")
        await entity._playback_task
    hub.send_audio.assert_not_called()
    assert entity.state == MediaPlayerState.IDLE


async def test_oversized_advertised_download_is_rejected_early(
    hass, hub, aioclient_mock
):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    aioclient_mock.get(
        "http://media.test/big", headers={"Content-Length": str(MAX_MEDIA_BYTES + 1)}
    )
    await entity.async_play_media("music", "http://media.test/big")
    await entity._playback_task
    hub.send_audio.assert_not_called()
    assert entity.extra_state_attributes["playback_error"]


async def test_cancelled_download_does_not_buffer_remaining_data(
    hass, hub, aioclient_mock
):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    aioclient_mock.get("http://media.test/data", content=wav())
    stop = threading.Event()
    stop.set()
    assert await entity._async_download("http://media.test/data", stop) == b""


async def test_upload_failure_is_private_and_returns_to_idle(
    hass, hub, aioclient_mock, caplog
):
    config = await setup(hass, hub)
    entity = speaker(hass, config)
    aioclient_mock.get("http://media.test/a", content=wav())
    hub.send_audio.side_effect = OSError("private-signed-url-and-tts-text")
    await entity.async_play_media("music", "http://media.test/a")
    await entity._playback_task
    assert entity.state == MediaPlayerState.IDLE
    assert entity.extra_state_attributes["playback_error"]
    assert "private-signed-url-and-tts-text" not in caplog.text


@pytest.mark.parametrize("fail", [False, True])
def test_adapter_always_closes_its_separate_audio_session(fail):
    from unittest.mock import Mock

    from custom_components.mipc_camera.api import MipcHub

    hub = MipcHub("192.0.2.10", "test", "test")
    client = Mock()
    hub.create_event_client = Mock(return_value=client)
    if fail:
        client.send_audio.side_effect = OSError("transport")
        with pytest.raises(OSError):
            hub.send_audio(bytes(320), threading.Event())
    else:
        assert (
            hub.send_audio(bytes(320), threading.Event())
            == client.send_audio.return_value
        )
    client.logout.assert_called_once()
    client.close.assert_called_once()
