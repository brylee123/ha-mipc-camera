from copy import deepcopy
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

DATA = {
    "device": {"sn": "synthetic-camera", "model": "f300", "img_ver": "test-firmware"},
    "video_sources": [{"token": "vs0"}],
    "imaging": {
        "brightness": 50,
        "contrast": 50,
        "color_saturation": 50,
        "sharpness": 50,
        "mode": "auto",
    },
    "microphones": [
        {"token": "mic0", "entity": {"token": "mic0"}, "silent": 0, "level": 60}
    ],
    "speaker": {"token": "ao0", "level": 40},
    "misc": {"flip": 0},
    "osd": {
        "text": "Camera",
        "text_enable": 1,
        "date": {"date_enable": 1, "time_enable": 1},
    },
    "alerts": {"motion_level": 50, "motion_level_night": 50},
    "recording": {"task": {"sch": {"enable": 1}}, "sd_ready": 1},
    "disks": [{"token": "sd", "stat": "normal", "size": 100, "used_size": 25}],
}


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def hub():
    instance = MagicMock()
    instance.info = {
        "sn": "synthetic-camera",
        "model": "f300",
        "img_ver": "test-firmware",
        "nick": "Test camera",
    }
    instance.host = "192.0.2.10"
    instance.model, instance.firmware, instance.serial_number = (
        "f300",
        "test-firmware",
        "synthetic-camera",
    )
    instance.last_seen = datetime.now(timezone.utc)
    instance.settings, instance.errors = deepcopy(DATA), {}
    instance.connect.return_value = instance.info
    instance.refresh.side_effect = lambda: {
        "settings": deepcopy(instance.settings),
        "errors": deepcopy(instance.errors),
    }
    instance.snapshot.return_value = b"\xff\xd8synthetic-jpeg\xff\xd9"
    instance.stream_url.return_value = "rtmp://192.0.2.10/live"

    def apply_setting(spec, value):
        current = instance.settings
        for key in spec.path[:-1]:
            current = (
                next(item for item in current if item["token"] == key)
                if isinstance(current, list)
                else current[key]
            )
        current[spec.path[-1]] = value

    instance.set_value.side_effect = apply_setting
    return instance
