from copy import deepcopy
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mipc_camera.api import (
    MipcAuthenticationError,
    MipcTransportError,
)
from custom_components.mipc_camera.capabilities import settings_for
from custom_components.mipc_camera.const import DOMAIN
from custom_components.mipc_camera.diagnostics import async_get_config_entry_diagnostics
from tests.conftest import DATA


def entry(options=None):
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="sn:synthetic-camera",
        title="Test camera",
        data={"host": "192.0.2.10", "username": "", "password": "never-export-this"},
        options=options or {},
    )


async def setup(hass, hub, options=None):
    config = entry(options)
    config.add_to_hass(hass)
    with patch("custom_components.mipc_camera.MipcHub", return_value=hub):
        assert await hass.config_entries.async_setup(config.entry_id)
        await hass.async_block_till_done()
    return config


async def test_config_flow_autodetects_device_username(hass, hub):
    with (
        patch(
            "custom_components.mipc_camera.config_flow.MipcHub", return_value=hub
        ) as factory,
        patch("custom_components.mipc_camera.async_setup_entry", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.0.2.10", "password": "device-secret"}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["username"] == ""
    assert result["result"].unique_id == "sn:synthetic-camera"
    assert factory.call_args.args[1] == ""
    hub.close.assert_called()


@pytest.mark.parametrize(
    "error,expected",
    [
        (MipcAuthenticationError("login"), "invalid_auth"),
        (MipcTransportError("read"), "cannot_connect"),
    ],
)
async def test_connection_errors_remain_user_facing(hass, hub, error, expected):
    hub.connect.side_effect = error
    with patch("custom_components.mipc_camera.config_flow.MipcHub", return_value=hub):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.0.2.10", "password": "secret"}
        )
    assert result["errors"] == {"base": expected}
    hub.close.assert_called()


async def test_entities_setup_and_unload_without_blocking_io(hass, hub):
    config = await setup(hass, hub)
    assert config.state is ConfigEntryState.LOADED
    states = hass.states.async_all()
    assert any(s.domain == "camera" for s in states)
    assert sum(s.domain == "number" for s in states) == 8
    assert sum(s.domain == "switch" for s in states) == 6
    assert not any(s.domain == "button" for s in states)
    assert await hass.config_entries.async_unload(config.entry_id)
    hub.close.assert_called()


async def test_ptz_is_explicit_and_options_enable_buttons(hass, hub):
    config = await setup(hass, hub, {"enable_ptz": True})
    buttons = [s.entity_id for s in hass.states.async_all() if s.domain == "button"]
    assert len(buttons) == 4
    await hass.services.async_call(
        DOMAIN,
        "move",
        {"config_entry_id": config.entry_id, "x": 5, "y": 0},
        blocking=True,
    )
    hub.move.assert_called_once_with(5, 0, 16, 16)


async def test_ptz_service_rejects_unverified_motors(hass, hub):
    config = await setup(hass, hub)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN,
            "move",
            {"config_entry_id": config.entry_id, "x": 5, "y": 0},
            blocking=True,
        )
    hub.move.assert_not_called()


async def test_optional_capability_errors_do_not_create_controls(hass, hub):
    hub.settings.pop("speaker")
    hub.errors["speaker"] = "MipcUnsupportedError"
    await setup(hass, hub)
    assert not any("speaker" in s.entity_id for s in hass.states.async_all())


async def test_setting_service_routes_write_and_refresh(hass, hub):
    await setup(hass, hub)
    brightness = next(
        s.entity_id
        for s in hass.states.async_all()
        if s.domain == "number" and "brightness" in s.entity_id
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": brightness, "value": 55}, blocking=True
    )
    assert hub.set_value.call_args.args[1] == 55
    assert hub.set_value.call_args.args[0].key == "brightness"
    assert hub.refresh.call_count >= 2


async def test_diagnostics_omit_credentials_and_raw_network_data(hass, hub):
    config = await setup(hass, hub)
    data = await async_get_config_entry_diagnostics(hass, config)
    text = str(data)
    assert "never-export-this" not in text
    assert "192.0.2.10" not in text
    assert "synthetic-camera" not in text
    assert "rtmp" not in text


def test_capabilities_use_types_not_truthy_missing_fields():
    data = deepcopy(DATA)
    data["imaging"]["brightness"] = "50"
    data["misc"]["flip"] = 2
    assert "brightness" not in {s.key for s in settings_for(data, "number")}
    assert "flip" not in {s.key for s in settings_for(data, "switch")}


def test_microphones_are_stable_by_token():
    data = deepcopy(DATA)
    data["microphones"].append({"token": "mic1", "level": 30, "silent": 1})
    specs = settings_for(data, "number")
    assert {s.path[1] for s in specs if s.path[0] == "microphones"} == {"mic0", "mic1"}


async def test_consecutive_writes_wait_for_fresh_camera_state(hass, hub):
    def update(spec, value):
        hub.settings["imaging"]["brightness"] = value

    hub.set_value.side_effect = update
    await setup(hass, hub)
    brightness = next(
        s.entity_id
        for s in hass.states.async_all()
        if s.domain == "number" and "brightness" in s.entity_id
    )
    for value in (55, 56):
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": brightness, "value": value},
            blocking=True,
        )
        assert float(hass.states.get(brightness).state) == value
    assert hub.refresh.call_count == 3


async def test_empty_card_slot_has_no_usage_percentage(hass, hub):
    hub.settings["disks"][0].update(stat="empty", size=0, used_size=0)
    await setup(hass, hub)
    sensors = [s for s in hass.states.async_all() if s.domain == "sensor"]
    assert any("storage_status" in s.entity_id and s.state == "empty" for s in sensors)
    assert not any("storage_used" in s.entity_id for s in sensors)
