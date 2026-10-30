"""Advertised stream choices and safe persisted profile selection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.camera import get_camera_from_entity_id
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.mipc_camera.api import MipcProtocolError
from tests.test_integration import setup


def quality_id(hass, config):
    return next(
        e.entity_id
        for e in er.async_get(hass).entities.values()
        if e.config_entry_id == config.entry_id
        and e.unique_id.endswith("_video_quality")
    )


async def quality_setup(hass, hub, options=None):
    hub.discover_stream_profiles.return_value = [
        {
            "token": p["n"],
            "name": p["v"],
            "width": 1920 if p["n"] == "p0" else 640,
            "height": 1080 if p["n"] == "p0" else 360,
        }
        for p in hub.info["p"]
    ]
    return await setup(hass, hub, options)


async def test_quality_selection_negotiates_and_reloads_stream_with_same_identity(
    hass, hub
):
    hub.info["p"] = [
        {"n": "p0", "v": "HD1080p"},
        {"n": "p1", "v": "D1"},
        {"n": "p2", "v": "CIF"},
    ]
    config = await quality_setup(
        hass, hub, {"enable_ptz": True, "motion_events": False}
    )
    entity = quality_id(hass, config)
    state = hass.states.get(entity)
    assert state.state == "1920 × 1080"
    assert state.attributes["options"] == ["1920 × 1080", "640 × 360"]
    camera_id = next(
        e.entity_id
        for e in er.async_get(hass).entities.values()
        if e.config_entry_id == config.entry_id and e.domain == "camera"
    )
    original = get_camera_from_entity_id(hass, camera_id)
    previous_stream = MagicMock()
    previous_stream.stop = AsyncMock()
    original.stream = previous_stream
    with patch("custom_components.mipc_camera.MipcHub", return_value=hub):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity, "option": "640 × 360"},
            blocking=True,
        )
        await hass.async_block_till_done()
    assert (
        config.options["stream_token"] == "p1" and config.options["enable_ptz"] is True
    )
    assert hass.states.get(entity).state == "640 × 360"
    replacement = get_camera_from_entity_id(hass, camera_id)
    hub.check_stream_profile.assert_called_once_with("p1", 640, 360)
    assert replacement is not original
    hub.discover_stream_profiles.assert_called_once_with()
    previous_stream.stop.assert_awaited_once()
    assert previous_stream.dynamic_stream_settings.preload_stream is False
    assert await replacement.stream_source() == "rtmp://192.0.2.10/live"
    hub.stream_url.assert_called_with("p1")
    hub.stream_url.reset_mock()
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity, "option": "640 × 360"},
        blocking=True,
    )
    hub.stream_url.assert_not_called()


async def test_quality_failure_preserves_previous_profile_and_options(hass, hub):
    hub.info["p"] = [{"n": "p0", "v": "HD1080p"}, {"n": "p1", "v": "D1"}]
    config = await quality_setup(hass, hub)
    entity = quality_id(hass, config)
    hub.check_stream_profile.side_effect = MipcProtocolError("ccm_play")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": entity, "option": "640 × 360"},
            blocking=True,
        )
    assert "stream_token" not in config.options
    assert hass.states.get(entity).state == "1920 × 1080"


async def test_quality_capability_removed_is_unavailable_and_rejects_old_option(
    hass, hub
):
    hub.info["p"] = [{"n": "p0", "v": "HD1080p"}, {"n": "p1", "v": "D1"}]
    config = await quality_setup(hass, hub)
    entity = quality_id(hass, config)
    hub.info["p"] = []
    config.runtime_data.async_update_listeners()
    assert hass.states.get(entity).state == "unavailable"
    from custom_components.mipc_camera.select import MipcVideoQuality

    selection = MipcVideoQuality(config.runtime_data, config)
    with pytest.raises(HomeAssistantError):
        await selection.async_select_option("640 × 360")
    assert "stream_token" not in config.options


async def test_failed_optional_resolution_discovery_keeps_camera_controls_available(
    hass, hub
):
    from custom_components.mipc_camera.api import MipcTransportError

    hub.info["p"] = [{"n": "p0", "v": "HD1080p"}, {"n": "p1", "v": "D1"}]
    hub.discover_stream_profiles.side_effect = MipcTransportError("ccm_play", "timeout")
    config = await setup(hass, hub)
    assert config.runtime_data.last_update_success
    assert config.data["profile_signature"] is None
    assert not any(
        e.unique_id.endswith("_video_quality")
        for e in er.async_get(hass).entities.values()
    )
