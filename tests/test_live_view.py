"""Local viewing gate, real placeholder responses and stream teardown."""

import asyncio
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.camera import (
    CameraEntityFeature,
    get_camera_from_entity_id,
)
from homeassistant.helpers import entity_registry as er
from PIL import Image

from custom_components.mipc_camera.api import MipcTransportError
from tests.test_integration import setup


def entities(hass, config):
    entries = [
        e
        for e in er.async_get(hass).entities.values()
        if e.config_entry_id == config.entry_id
    ]
    camera_id = next(e.entity_id for e in entries if e.domain == "camera")
    switch_id = next(e.entity_id for e in entries if e.unique_id.endswith("_live_view"))
    return get_camera_from_entity_id(hass, camera_id), switch_id


async def toggle(hass, switch_id, enabled):
    await hass.services.async_call(
        "switch",
        "turn_on" if enabled else "turn_off",
        {"entity_id": switch_id},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_switch_stops_stream_without_reloading_and_restores_media(hass, hub):
    config = await setup(hass, hub, {"enable_ptz": True, "stream_token": "p1"})
    camera, switch_id = entities(hass, config)
    stream = MagicMock()
    stream.stop = AsyncMock()
    camera.stream = stream
    with patch("custom_components.mipc_camera.MipcHub") as factory:
        await toggle(hass, switch_id, False)
        factory.assert_not_called()
    stream.stop.assert_awaited_once()
    assert stream.dynamic_stream_settings.preload_stream is False
    assert camera.stream is None
    assert camera.available and camera.is_on
    assert camera.supported_features == 0
    assert hass.states.get(switch_id).state == "off"
    assert config.options == {
        "enable_stream": False,
        "enable_ptz": True,
        "stream_token": "p1",
    }
    hub.snapshot.reset_mock()
    hub.stream_url.reset_mock()
    image = await camera.async_camera_image()
    with Image.open(BytesIO(image)) as decoded:
        assert decoded.format == "JPEG" and decoded.size == (1280, 720)
    assert await camera.stream_source() is None
    assert await camera.async_create_stream() is None
    hub.snapshot.assert_not_called()
    hub.stream_url.assert_not_called()
    await toggle(hass, switch_id, False)
    stream.stop.assert_awaited_once()
    await toggle(hass, switch_id, True)
    assert camera.supported_features == CameraEntityFeature.STREAM
    assert await camera.async_camera_image() == hub.snapshot.return_value
    assert await camera.stream_source() == hub.stream_url.return_value
    hub.stream_url.assert_called_once_with("p1")
    hub.set_value.assert_not_called()


async def test_off_survives_reload_and_remains_viewable_when_camera_offline(hass, hub):
    config = await setup(hass, hub, {"enable_stream": False})
    camera, switch_id = entities(hass, config)
    config.runtime_data.async_set_update_error(OSError("offline"))
    assert camera.available
    assert hass.states.get(switch_id).state == "off"
    assert await camera.async_camera_image()
    hub.snapshot.assert_not_called()
    with patch("custom_components.mipc_camera.MipcHub", return_value=hub):
        await hass.config_entries.async_reload(config.entry_id)
        await hass.async_block_till_done()
    replacement, same_switch = entities(hass, config)
    assert replacement is not camera and same_switch == switch_id
    assert hass.states.get(switch_id).state == "off"
    assert await replacement.async_camera_image() == await camera.async_camera_image()


async def test_options_form_uses_same_gate_without_reloading(hass, hub):
    config = await setup(hass, hub)
    camera, switch_id = entities(hass, config)
    hass.config_entries.async_update_entry(config, options={"enable_stream": False})
    await hass.async_block_till_done()
    assert entities(hass, config)[0] is camera
    assert hass.states.get(switch_id).state == "off"
    assert camera.supported_features == 0


async def test_off_startup_does_not_probe_advertised_video(hass, hub):
    hub.info["p"] = [{"n": "p0", "v": "HD1080p"}, {"n": "p1", "v": "D1"}]
    config = await setup(hass, hub, {"enable_stream": False})
    camera, _ = entities(hass, config)
    assert await camera.async_camera_image() == camera._off_image
    hub.discover_stream_profiles.assert_not_called()
    hub.snapshot.assert_not_called()
    hub.stream_url.assert_not_called()


async def test_off_image_and_mjpeg_endpoints_return_placeholder(hass, hub, hass_client):
    config = await setup(hass, hub, {"enable_stream": False})
    camera, _ = entities(hass, config)
    client = await hass_client()
    response = await client.get(f"/api/camera_proxy/{camera.entity_id}")
    assert response.status == 200
    assert response.content_type == "image/jpeg"
    assert await response.read() == await camera.async_camera_image()
    response = await client.get(f"/api/camera_proxy_stream/{camera.entity_id}")
    assert response.status == 200
    assert response.content_type == "multipart/x-mixed-replace"
    async with asyncio.timeout(5):
        chunk = await response.content.read(32768)
    assert b"Content-Type: image/jpeg" in chunk
    assert b"\xff\xd8" in chunk
    response.close()
    hub.snapshot.assert_not_called()
    hub.stream_url.assert_not_called()


@pytest.mark.parametrize(
    "operation", ["async_camera_image", "stream_source", "async_create_stream"]
)
@pytest.mark.parametrize("failed", [False, True])
async def test_inflight_media_cannot_return_live_content_after_off(
    hass, hub, operation, failed
):
    config = await setup(hass, hub)
    camera, switch_id = entities(hass, config)
    started, release = asyncio.Event(), asyncio.Event()

    async def delayed_snapshot(*args):
        started.set()
        await release.wait()
        if failed:
            raise MipcTransportError("ccm_pic_get")
        return b"private-live-frame"

    with patch.object(hass, "async_add_executor_job", side_effect=delayed_snapshot):
        task = asyncio.create_task(getattr(camera, operation)())
        await started.wait()
        toggle_task = asyncio.create_task(toggle(hass, switch_id, False))
        # A source lookup owns HA's creation lock. Off must close the gate
        # immediately, then wait for that lookup before acknowledging completion.
        while camera._options["enable_stream"]:
            await asyncio.sleep(0)
        release.set()
        assert await task == (
            camera._off_image if operation == "async_camera_image" else None
        )
        await toggle_task
        assert camera.stream is None
