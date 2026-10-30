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
