from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.camera import get_camera_from_entity_id

from custom_components.mipc_camera.api import (
    MipcAuthenticationError,
    MipcError,
    MipcHub,
    MipcProtocolError,
    MipcTransportError,
)
from tests.test_adapter import client
from tests.test_integration import setup


@pytest.mark.parametrize("operation", ["snapshot", "stream", "profiles", "quality"])
def test_media_read_renews_once_and_uses_new_client(operation):
    old, new = client(), client()
    method = {
        "snapshot": "get_image",
        "stream": "get_stream_url",
        "profiles": "probe_stream_profiles",
        "quality": "get_stream_url",
    }[operation]
    getattr(old, method).side_effect = MipcAuthenticationError("read", "Receiver")
    new.get_image.return_value = b"fresh-jpeg"
    new.get_stream_url.return_value = "rtmp://192.0.2.10/fresh-session"
    new.probe_stream_profiles.return_value = []
    with patch(
        "custom_components.mipc_camera.api.MipcCameraClient", side_effect=[old, new]
    ) as factory:
        hub = MipcHub("192.0.2.10", "", "secret")
        hub.connect()
        if operation == "snapshot":
            assert hub.snapshot() == b"fresh-jpeg"
        elif operation == "stream":
            assert hub.stream_url("p2").endswith("fresh-session")
            new.get_stream_url.assert_called_once_with("p2")
        elif operation == "profiles":
            assert hub.discover_stream_profiles() == []
        else:
            with patch.object(
                hub, "_decode_stream_dimensions", return_value=(640, 360)
            ):
                hub.check_stream_profile("p2", 640, 360)
        assert factory.call_count == 2
        assert getattr(old, method).call_count == 1
        assert getattr(new, method).call_count == 1
        assert hub.session_generation == 2
        old.close.assert_called_once()
        hub.close()


def test_failed_renewal_is_bounded_and_next_poll_can_reconnect():
    old, failed, recovered = client(), client(), client()
    old.get_misc.side_effect = MipcAuthenticationError("ccm_misc_get")
    failed.login.side_effect = MipcTransportError("login", "timeout")
    with patch(
        "custom_components.mipc_camera.api.MipcCameraClient",
        side_effect=[old, failed, recovered],
    ) as factory:
        hub = MipcHub("192.0.2.10", "", "secret")
        hub.connect()
        with pytest.raises(MipcTransportError):
            hub.refresh()
        assert factory.call_count == 2
        assert hub.refresh()["settings"]["imaging"]["brightness"] == 50
        assert factory.call_count == 3
        failed.close.assert_called_once()
        hub.close()


def test_rejected_second_attempt_does_not_loop():
    old, new = client(), client()
    for c in (old, new):
        c.get_image.side_effect = MipcAuthenticationError("ccm_pic_get")
    with patch(
        "custom_components.mipc_camera.api.MipcCameraClient", side_effect=[old, new]
    ) as factory:
        hub = MipcHub("192.0.2.10", "", "secret")
        hub.connect()
        with pytest.raises(MipcAuthenticationError):
            hub.snapshot()
        assert factory.call_count == 2
        assert old.get_image.call_count == new.get_image.call_count == 1
        hub.close()


def test_all_authenticated_reads_failing_does_not_advance_last_success():
    c = client()
    methods = [
        "get_device_info",
        "get_video_sources",
        "get_microphones",
        "get_speaker",
        "get_imaging",
        "get_misc",
        "get_osd",
        "get_alert_config",
        "get_alert_actions",
        "get_recording",
        "get_disks",
        "get_ntp",
        "get_network_interfaces",
    ]
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "secret")
        hub.connect()
        previous = hub.refresh()
        seen = hub.last_seen
        for method in methods:
            getattr(c, method).side_effect = MipcError(method, "Receiver")
        with pytest.raises(MipcProtocolError):
            hub.refresh()
        assert hub.last_seen == seen
        assert hub.settings == previous["settings"]
        hub.close()


async def test_poll_renewal_discards_cached_stream_and_retains_options(hass, hub):
    hub.session_generation = 1
    config = await setup(hass, hub, {"stream_token": "p2"})
    camera_id = next(
        s.entity_id for s in hass.states.async_all() if s.domain == "camera"
    )
    camera = get_camera_from_entity_id(hass, camera_id)
    stream = MagicMock()
    stream.stop = AsyncMock()
    camera.stream = stream
    hub.session_generation = 2
    await config.runtime_data.async_refresh()
    stream.stop.assert_awaited_once()
    assert camera.stream is None
    assert config.options["stream_token"] == "p2"
    assert await camera.stream_source() == hub.stream_url.return_value
    hub.stream_url.assert_called_with("p2")
    await config.runtime_data.async_refresh()
    stream.stop.assert_awaited_once()


async def test_total_authenticated_failure_disconnects_then_recovers(hass, hub):
    config = await setup(hass, hub)
    connected = next(
        s.entity_id
        for s in hass.states.async_all()
        if s.domain == "binary_sensor" and s.entity_id.endswith("connection")
    )
    hub.refresh.side_effect = MipcProtocolError("authenticated_reads_failed")
    await config.runtime_data.async_refresh()
    assert hass.states.get(connected).state == "off"
    hub.refresh.side_effect = lambda: {"settings": hub.settings, "errors": {}}
    await config.runtime_data.async_refresh()
    assert hass.states.get(connected).state == "on"
