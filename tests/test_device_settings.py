"""Settings, guarded maintenance and credential-free network views."""

from copy import deepcopy
from unittest.mock import patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.mipc_camera.api import MipcHub, MipcProtocolError
from custom_components.mipc_camera.capabilities import Setting, settings_for
from custom_components.mipc_camera.diagnostics import async_get_config_entry_diagnostics
from tests.test_adapter import client
from tests.test_integration import setup

EXTRA = {
    "misc": {"flip": 0, "power_freq": 1},
    "osd": {
        "text": "Camera",
        "text_enable": 1,
        "week": 1,
        "date": {
            "date_enable": 1,
            "time_enable": 1,
            "enable_12h": 0,
            "format": "YYYY-MM-DD",
        },
    },
    "alert_actions": {"enable": 0, "actions": [{"token": "motion_alert", "enable": 1}]},
    "ntp": {"timezone": "London"},
    "recording": {"task": {"sch": {"enable": 0, "full_time": 0}}, "sd_ready": 0},
    "controls": {
        "power_frequency": "50_hz",
        "time_format": "24_hour",
        "recording_mode": "off",
    },
    "network": [
        {
            "token": "eth0",
            "connection": "ethernet",
            "link_status": "ok",
            "ip_address": "192.0.2.10",
            "mac_address": "02:00:00:00:00:01",
        }
    ],
}


def entity_id(hass, config, suffix):
    return next(
        e.entity_id
        for e in er.async_get(hass).entities.values()
        if e.config_entry_id == config.entry_id and e.unique_id.endswith("_" + suffix)
    )


async def test_new_settings_use_readback_and_preserve_existing_unique_ids(hass, hub):
    hub.settings.update(deepcopy(EXTRA))
    config = await setup(hass, hub)
    for key, option in [
        ("osd_date_format", "MM-DD-YYYY"),
        ("osd_time_format", "12_hour"),
        ("recording_mode", "continuous"),
        ("power_frequency", "60_hz"),
    ]:
        target = entity_id(hass, config, key)
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": target, "option": option},
            blocking=True,
        )
        assert hass.states.get(target).state == option
    mode = hass.states.get(entity_id(hass, config, "recording_mode"))
    assert mode.attributes["options"] == ["off", "continuous"]
    for key in ("osd_weekday", "motion_detection", "osd_date", "osd_time"):
        target = entity_id(hass, config, key)
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": target}, blocking=True
        )
        assert hass.states.get(target).state == "off"
    # Motion action edits never implicitly toggle the separate global arming flag.
    assert hass.states.get(entity_id(hass, config, "alarm_armed")).state == "off"
    assert (
        er.async_get(hass).async_get(entity_id(hass, config, "osd_date")).unique_id
        == "sn:synthetic-camera_osd_date"
    )
    assert (
        hass.states.get(entity_id(hass, config, "reported_timezone")).state == "London"
    )
    assert not any(
        e.domain == "select" and e.unique_id.endswith("_timezone")
        for e in er.async_get(hass).entities.values()
    )
    hub.set_value.side_effect = None
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": entity_id(hass, config, "osd_date_format"),
                "option": "YYYY-MM-DD",
            },
            blocking=True,
        )


@pytest.mark.parametrize(
    "key,value,method,args,kwargs",
    [
        ("osd_weekday", False, "update_osd", (), {"week": 0}),
        (
            "osd_date_format",
            "MM-DD-YYYY",
            "update_osd",
            (),
            {"date": {"format": "MM-DD-YYYY"}},
        ),
        ("osd_time_format", "12_hour", "update_osd", (), {"date": {"enable_12h": 1}}),
        ("power_frequency", "60_hz", "set_power_frequency", (60,), {}),
        ("recording_mode", "continuous", "set_recording_mode", ("continuous",), {}),
        ("motion_detection", False, "set_motion_alarm_enabled", (False,), {}),
        ("alarm_armed", True, "set_alarm_armed", (True,), {}),
    ],
)
def test_adapter_routes_new_controls_without_touching_other_settings(
    key, value, method, args, kwargs
):
    c = client()
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "secret")
        hub.connect()
        hub.settings.update(deepcopy(EXTRA))
        spec = next(
            s
            for platform in ("select", "switch")
            for s in settings_for(hub.settings, platform)
            if s.key == key
        )
        hub.set_value(spec, value)
        getattr(c, method).assert_called_once_with(*args, **kwargs)
        hub.close()


def test_adapter_derives_labels_from_verified_flags_and_sanitizes_network():
    from custom_components.mipc_camera._vendor.mipc_camera_client.device_settings import (
        NetworkInterface,
    )

    c = client()
    c.get_misc.return_value = EXTRA["misc"]
    c.get_osd.return_value = EXTRA["osd"]
    c.get_recording.return_value = EXTRA["recording"]
    c.get_ntp.return_value = EXTRA["ntp"]
    c.get_network_interfaces.return_value = (
        NetworkInterface(
            "eth0", "ethernet", True, "ok", "02:00:00:00:00:01", "192.0.2.10"
        ),
    )
    with patch("custom_components.mipc_camera.api.MipcCameraClient", return_value=c):
        hub = MipcHub("192.0.2.10", "", "secret")
        hub.connect()
        settings = hub.refresh()["settings"]
        assert settings["controls"] == EXTRA["controls"]
        assert settings["network"][0]["connection"] == "ethernet"
        hub.refresh()
        hub.reboot()
        c.reboot.assert_called_once_with()
        hub.factory_reset()
        c.restore.assert_called_once_with(keep_configuration=False)
        hub.settings["controls"]["unknown"] = "old"
        with pytest.raises(ValueError):
            hub.set_value(
                Setting("invalid", "Invalid", "select", ("controls", "unknown")), "bad"
            )
        hub.close()


async def test_network_entities_are_optional_and_diagnostics_remain_redacted(hass, hub):
    from custom_components.mipc_camera.sensor import MipcNetworkSensor

    hub.settings.update(deepcopy(EXTRA))
    with patch.object(MipcNetworkSensor, "_attr_entity_registry_enabled_default", True):
        config = await setup(hass, hub)
    for field in ("connection", "link_status", "mac_address", "ip_address"):
        target = entity_id(hass, config, "network_eth0_" + field)
        assert hass.states.get(target).state == EXTRA["network"][0][field]
    diagnostics = str(await async_get_config_entry_diagnostics(hass, config))
    assert "02:00:00:00:00:01" not in diagnostics and "192.0.2.10" not in diagnostics
    hub.settings["network"] = []
    await config.runtime_data.async_refresh()
    assert (
        hass.states.get(entity_id(hass, config, "network_eth0_connection")).state
        == "unavailable"
    )


async def test_restart_and_network_are_disabled_by_default(hass, hub):
    hub.settings.update(deepcopy(EXTRA))
    config = await setup(hass, hub)
    for suffix in ("restart", "network_eth0_ip_address", "network_eth0_mac_address"):
        registered = er.async_get(hass).async_get(entity_id(hass, config, suffix))
        assert registered.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_restart_button_reports_failures_without_retry(hass, hub):
    from custom_components.mipc_camera.button import MipcRestartButton

    with patch.object(MipcRestartButton, "_attr_entity_registry_enabled_default", True):
        config = await setup(hass, hub)
    target = entity_id(hass, config, "restart")
    await hass.services.async_call(
        "button", "press", {"entity_id": target}, blocking=True
    )
    hub.reboot.assert_called_once_with()
    hub.reboot.side_effect = MipcProtocolError("ccm_reboot")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "button", "press", {"entity_id": target}, blocking=True
        )
    assert hub.reboot.call_count == 2


async def test_factory_reset_requires_confirmation_and_loaded_target(hass, hub):
    config = await setup(hass, hub)
    for data in (
        {"config_entry_id": config.entry_id, "confirm": False},
        {"config_entry_id": "missing", "confirm": True},
        {"config_entry_id": config.entry_id},
    ):
        with pytest.raises((HomeAssistantError, __import__("voluptuous").Invalid)):
            await hass.services.async_call(
                "mipc_camera", "factory_reset", data, blocking=True
            )
    hub.factory_reset.assert_not_called()
    await hass.services.async_call(
        "mipc_camera",
        "factory_reset",
        {"config_entry_id": config.entry_id, "confirm": True},
        blocking=True,
    )
    hub.factory_reset.assert_called_once_with()
    hub.factory_reset.side_effect = MipcProtocolError("ccm_restore")
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "mipc_camera",
            "factory_reset",
            {"config_entry_id": config.entry_id, "confirm": True},
            blocking=True,
        )
    assert hub.factory_reset.call_count == 2
