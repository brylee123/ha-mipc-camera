from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

from custom_components.mipc_camera.api import (
    MipcAuthenticationError,
    MipcHub,
    MipcProtocolError,
    MipcUnsupportedError,
    valid_host,
)
from custom_components.mipc_camera.capabilities import SETTINGS
from tests.conftest import DATA


def client():
    c = MagicMock()
    c.get_info.return_value = {"sn": "test-device"}
    for section, method in [
        ("device", "get_device_info"),
        ("video_sources", "get_video_sources"),
        ("microphones", "get_microphones"),
        ("speaker", "get_speaker"),
        ("imaging", "get_imaging"),
        ("misc", "get_misc"),
        ("osd", "get_osd"),
        ("alerts", "get_alert_config"),
        ("recording", "get_recording"),
        ("disks", "get_disks"),
    ]:
        getattr(c, method).return_value = deepcopy(DATA[section])
    c.get_device_info.return_value = {"sn": "test-device", "model": "f300"}
    return c


def test_adapter_login_capabilities_and_optional_failure():
    c = client()
    c.get_speaker.side_effect = MipcUnsupportedError("ccm_speaker_get", 404)
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "private")
        hub.connect()
        result = hub.refresh()
        c.login.assert_called_once_with("test-device", "private")
        assert "speaker" not in result["settings"]
        assert result["errors"] == {"speaker": "MipcUnsupportedError"}
        hub.close()
    c.logout.assert_called_once()
    c.close.assert_called_once()


def test_reconnect_retries_reads_but_never_writes():
    first, second = client(), client()
    first.get_imaging.side_effect = MipcAuthenticationError("ccm_img_get")
    with patch(
        "custom_components.mipc_camera.api.MipcCameraClient",
        side_effect=[first, second],
    ):
        hub = MipcHub("192.0.2.10", "", "private")
        hub.connect()
        hub.refresh()
        assert hub.settings["imaging"]["brightness"] == 50
        second.set_imaging.side_effect = MipcAuthenticationError("ccm_img_set")
        spec = next(s for s in SETTINGS if s.key == "brightness")
        with pytest.raises(MipcAuthenticationError):
            hub.set_value(spec, 51)
        second.set_imaging.assert_called_once_with("brightness", 51, "vs0")
        assert second.login.call_count == 1
        hub.close()


def test_address_reuse_rejects_different_device():
    c = client()
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "private")
        hub.connect()
        c.get_info.return_value = {"sn": "another-device"}
        with pytest.raises(MipcProtocolError):
            hub.refresh()
        c.get_imaging.assert_not_called()
        hub.close()


@pytest.mark.parametrize(
    "host, expected",
    [
        ("192.0.2.10:80", True),
        ("camera.local", True),
        ("[::1]:80", True),
        ("http://camera", False),
        ("camera/path", False),
        ("user:password@camera", False),
        ("camera:0", False),
        ("camera?query", False),
        ("camera#fragment", False),
        ("camera\\path", False),
    ],
)
def test_host_validation(host, expected):
    assert valid_host(host) is expected


@pytest.mark.parametrize(
    "key,value,method,args,kwargs",
    [
        ("brightness", 51, "set_imaging", ("brightness", 51, "vs0"), {}),
        ("speaker_volume", 20, "set_speaker_level", (20, "ao0"), {}),
        (
            "microphone_mic0_mute",
            True,
            "update_microphone",
            ("mic0",),
            {"silent": True},
        ),
        ("flip", True, "set_flip", (True,), {}),
        ("osd_date", False, "update_osd", (), {"date": {"date_enable": 0}}),
        ("osd_text", "Label", "update_osd", (), {"text": "Label"}),
        ("motion_sensitivity", 30, "update_alert_config", (), {"motion_level": 30}),
        ("recording", True, "set_recording_enabled", (True,), {}),
    ],
)
def test_setting_adapter_uses_the_correct_typed_client_method(
    key, value, method, args, kwargs
):
    from custom_components.mipc_camera.capabilities import settings_for

    c = client()
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "private")
        hub.connect()
        hub.refresh()
        spec = next(
            s
            for platform in ("number", "switch", "text")
            for s in settings_for(hub.settings, platform)
            if s.key == key
        )
        hub.set_value(spec, value)
        getattr(c, method).assert_called_once_with(*args, **kwargs)
        hub.close()


@pytest.mark.parametrize(
    "error", [MipcProtocolError("info"), MipcAuthenticationError("login")]
)
def test_failed_handshake_closes_client(error):
    c = client()
    c.login.side_effect = error
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "private")
        with pytest.raises(type(error)):
            hub.connect()
    c.close.assert_called_once()
    with pytest.raises(MipcProtocolError):
        hub.snapshot()


@pytest.mark.parametrize("info", [{}, {"sn": ""}, {"sn": 42}])
def test_handshake_requires_a_real_serial(info):
    c = client()
    c.get_info.return_value = info
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "private")
        with pytest.raises(MipcProtocolError):
            hub.connect()
    c.login.assert_not_called()
    c.close.assert_called_once()


def test_reconnect_cannot_switch_device_and_cleanup_survives_logout_error():
    c = client()
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "private")
        hub.connect()
        c.logout.side_effect = MipcProtocolError("logout")
        c.get_info.return_value = {"sn": "different-device"}
        with pytest.raises(MipcProtocolError):
            hub.connect()
        assert c.login.call_count == 1
        assert c.close.call_count == 2


def test_optional_metadata_and_missing_settings_do_not_become_capabilities():
    from custom_components.mipc_camera.capabilities import Setting

    c = client()
    c.get_device_info.side_effect = MipcUnsupportedError("ccm_dev_info_get", 404)
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "private")
        hub.connect()
        hub.refresh()
        assert hub.model == "IP camera"
        assert hub.firmware is None
        assert hub.errors["device"] == "MipcUnsupportedError"
        with pytest.raises(MipcProtocolError):
            hub.set_value(
                Setting("missing", "Missing", "number", ("imaging", "missing")), 42
            )
        hub.settings["other"] = {"field": 1}
        with pytest.raises(ValueError):
            hub.set_value(
                Setting("unsupported", "Unsupported", "number", ("other", "field")), 2
            )
        hub.close()


@pytest.mark.parametrize("code,raises", [("http_500", False), ("timeout", True)])
def test_optional_http_errors_and_transport_failures_have_different_recovery(
    code, raises
):
    from custom_components.mipc_camera.api import MipcTransportError

    c = client()
    c.get_speaker.side_effect = MipcTransportError("speaker", code)
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "private")
        hub.connect()
        if raises:
            with pytest.raises(MipcTransportError):
                hub.refresh()
        else:
            assert hub.refresh()["errors"]["speaker"] == "MipcTransportError"
        hub.close()


def test_media_and_motion_share_the_authenticated_client():
    c = client()
    c.get_image.return_value = b"jpeg"
    c.get_stream_url.return_value = "rtmp://192.0.2.10/live"
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "private")
        hub.connect()
        assert hub.snapshot() == b"jpeg"
        assert hub.stream_url("p0") == "rtmp://192.0.2.10/live"
        hub.move(1, -1, 16, 16)
        c.control_ptz.assert_called_once_with(1, -1, 16, 16)
        hub.close()


def test_optional_metadata_cannot_replace_camera_identity():
    c = client()
    c.get_device_info.return_value = {"sn": "metadata-id", "p": None}
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "private")
        hub.connect()
        hub.refresh()
        assert hub.serial_number == "test-device"
        assert hub.info["sn"] == "test-device"
        assert hub.model == "IP camera"
        hub.info["p"] = [None, {"n": "model", "v": "f300"}]
        assert hub.model == "f300"
        hub.info["ver"] = "fallback-version"
        assert hub.firmware == "fallback-version"
        hub.close()
