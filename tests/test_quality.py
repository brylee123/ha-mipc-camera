"""Lifecycle, translations and failure/recovery behavior against Home Assistant."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.components.camera import get_camera_from_entity_id
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.mipc_camera.api import (
    MipcAuthenticationError,
    MipcProtocolError,
    MipcTransportError,
)
from custom_components.mipc_camera.const import DOMAIN
from tests.test_integration import entry, setup


def entity_id(hass, config, key):
    return next(
        e.entity_id
        for e in er.async_get(hass).entities.values()
        if e.config_entry_id == config.entry_id
        and e.unique_id == f"{config.unique_id}_{key}"
    )


@pytest.mark.parametrize("source", ["reauth", "reconfigure"])
@pytest.mark.parametrize("matching", [True, False])
async def test_existing_entry_flows_preserve_identity(hass, hub, source, matching):
    config = entry()
    config.add_to_hass(hass)
    if not matching:
        hub.serial_number = "different-camera"
    data = {"username": "", "password": "new-device-password"}
    if source == "reconfigure":
        data["host"] = "192.0.2.11"
    with (
        patch("custom_components.mipc_camera.config_flow.MipcHub", return_value=hub),
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": source,
                "entry_id": config.entry_id,
                "unique_id": config.unique_id,
            },
            data=dict(config.data) if source == "reauth" else None,
        )
        assert result["type"] is FlowResultType.FORM
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
        await hass.async_block_till_done()
    if matching:
        assert result["type"] is FlowResultType.ABORT
        assert result["reason"] == source + "_successful"
        assert config.data["password"] == data["password"]
        assert config.unique_id == "sn:synthetic-camera"
    else:
        assert result["errors"] == {"base": "device_mismatch"}
        assert config.data["password"] == "never-export-this"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    hub.close.assert_called()


async def test_duplicate_camera_is_rejected(hass, hub):
    config = entry()
    config.add_to_hass(hass)
    with patch("custom_components.mipc_camera.config_flow.MipcHub", return_value=hub):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={"host": "192.0.2.11", "password": "secret"},
        )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize(
    "host", ["https://camera", "user:secret@camera", "camera/path"]
)
async def test_invalid_address_never_opens_connection(hass, hub, host):
    with patch(
        "custom_components.mipc_camera.config_flow.MipcHub", return_value=hub
    ) as factory:
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={"host": host, "password": "secret"},
        )
    assert result["errors"] == {"base": "invalid_host"}
    factory.assert_not_called()


@pytest.mark.parametrize(
    "error", [MipcProtocolError("info"), ValueError("invalid response")]
)
async def test_protocol_failure_is_reported_without_raw_details(hass, hub, error):
    hub.connect.side_effect = error
    with patch("custom_components.mipc_camera.config_flow.MipcHub", return_value=hub):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
            data={"host": "192.0.2.11", "password": "secret"},
        )
    assert result["errors"] == {"base": "unknown"}
    hub.close.assert_called_once()


async def test_options_reload_the_existing_entry(hass, hub):
    config = await setup(hass, hub)
    with patch.object(hass.config_entries, "async_reload", return_value=True) as reload:
        result = await hass.config_entries.options.async_init(config.entry_id)
        assert result["type"] is FlowResultType.FORM
        options = {
            "motion_events": False,
            "enable_ptz": True,
            "enable_stream": False,
            "stream_token": "p1",
            "ptz_step": 4,
            "pan_speed": 16,
            "tilt_speed": 16,
        }
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], options
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config.options == options
    reload.assert_awaited_once_with(config.entry_id)


@pytest.mark.parametrize(
    "error,expected",
    [
        (MipcAuthenticationError("login"), ConfigEntryState.SETUP_ERROR),
        (MipcTransportError("info"), ConfigEntryState.SETUP_RETRY),
        (RuntimeError("unexpected"), ConfigEntryState.SETUP_ERROR),
    ],
)
async def test_failed_setup_closes_connection(hass, hub, error, expected):
    config = entry()
    config.add_to_hass(hass)
    hub.connect.side_effect = error
    with patch("custom_components.mipc_camera.MipcHub", return_value=hub):
        assert not await hass.config_entries.async_setup(config.entry_id)
        await hass.async_block_till_done()
    assert config.state is expected
    hub.close.assert_called_once()
    await hass.config_entries.async_unload(config.entry_id)


async def test_reused_ip_never_attaches_another_camera(hass, hub):
    config = entry()
    config.add_to_hass(hass)
    hub.serial_number = "different-camera"
    with patch("custom_components.mipc_camera.MipcHub", return_value=hub):
        assert not await hass.config_entries.async_setup(config.entry_id)
    hub.refresh.assert_not_called()
    hub.close.assert_called_once()
    assert not hass.states.async_all("camera")


async def test_move_rejects_unloaded_entry(hass, hub):
    config = await setup(hass, hub, {"enable_ptz": True})
    await hass.config_entries.async_unload(config.entry_id)
    with pytest.raises(HomeAssistantError) as result:
        await hass.services.async_call(
            DOMAIN,
            "move",
            {"config_entry_id": config.entry_id, "x": 1, "y": 0},
            blocking=True,
        )
    assert result.value.translation_key == "entry_unavailable"
    hub.move.assert_not_called()


async def test_action_failure_has_a_translated_sanitized_message(hass, hub):
    config = await setup(hass, hub, {"enable_ptz": True})
    hub.move.side_effect = MipcTransportError("ccm_ptz_ctl")
    for domain, name, data in [
        (DOMAIN, "move", {"config_entry_id": config.entry_id, "x": 1, "y": 0}),
        ("button", "press", {"entity_id": entity_id(hass, config, "pan_right")}),
    ]:
        with pytest.raises(HomeAssistantError) as result:
            await hass.services.async_call(domain, name, data, blocking=True)
        assert result.value.translation_key == "movement_failed"
        assert "never-export-this" not in str(result.value)


@pytest.mark.parametrize("streaming", [True, False])
async def test_camera_delegates_media_and_wraps_known_failures(hass, hub, streaming):
    config = await setup(hass, hub, {"enable_stream": streaming})
    camera = get_camera_from_entity_id(hass, entity_id(hass, config, "camera"))
    assert await camera.async_camera_image() == hub.snapshot.return_value
    assert await camera.stream_source() == (
        hub.stream_url.return_value if streaming else None
    )
    hub.snapshot.side_effect = MipcTransportError("ccm_pic_get")
    with pytest.raises(HomeAssistantError) as result:
        await camera.async_camera_image()
    assert result.value.translation_key == "snapshot_failed"
    if streaming:
        hub.stream_url.side_effect = MipcTransportError("ccm_play")
        with pytest.raises(HomeAssistantError) as result:
            await camera.stream_source()
        assert result.value.translation_key == "stream_failed"


@pytest.mark.parametrize(
    "key,domain,service,value",
    [
        ("flip", "switch", "turn_on", True),
        ("flip", "switch", "turn_off", False),
        ("day_night", "select", "select_option", "night"),
        ("osd_text", "text", "set_value", "Test label"),
        ("microphone_mic0_volume", "number", "set_value", 42),
    ],
)
async def test_settings_actions_verify_real_readback(
    hass, hub, key, domain, service, value
):
    config = await setup(hass, hub)
    data = {"entity_id": entity_id(hass, config, key)}
    if domain == "select":
        data["option"] = value
    elif domain != "switch":
        data["value"] = value
    await hass.services.async_call(domain, service, data, blocking=True)
    state = hass.states.get(data["entity_id"]).state
    assert (
        state == ("on" if value else "off")
        if domain == "switch"
        else state == str(value)
    )


@pytest.mark.parametrize(
    "failure,expected",
    [
        ("write", "setting_failed"),
        ("read", "readback_failed"),
        ("unchanged", "write_not_applied"),
    ],
)
async def test_failed_writes_and_reads_do_not_report_false_success(
    hass, hub, failure, expected
):
    config = await setup(hass, hub)
    if failure == "write":
        hub.set_value.side_effect = MipcTransportError("ccm_img_set")
    elif failure == "read":
        hub.refresh.side_effect = MipcTransportError("ccm_img_get")
    else:
        hub.set_value.side_effect = None
    with pytest.raises(HomeAssistantError) as result:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id(hass, config, "brightness"), "value": 51},
            blocking=True,
        )
    assert result.value.translation_key == expected
    hub.set_value.assert_called_once()


async def test_optional_read_failure_and_poll_recovery_update_availability(hass, hub):
    config = await setup(hass, hub)
    hub.settings.pop("recording")
    hub.settings.pop("disks")
    await config.runtime_data.async_refresh()
    assert (
        hass.states.get(entity_id(hass, config, "storage_status")).state
        == "unavailable"
    )
    assert (
        hass.states.get(entity_id(hass, config, "storage_used")).state == "unavailable"
    )
    assert (
        hass.states.get(entity_id(hass, config, "storage_ready")).state == "unavailable"
    )
    hub.refresh.side_effect = MipcTransportError("info")
    await config.runtime_data.async_refresh()
    assert hass.states.get(entity_id(hass, config, "online")).state == "off"
    assert hass.states.get(entity_id(hass, config, "brightness")).state == "unavailable"
    hub.refresh.side_effect = lambda: {"settings": hub.settings, "errors": {}}
    await config.runtime_data.async_refresh()
    assert hass.states.get(entity_id(hass, config, "online")).state == "on"


async def test_poll_authentication_failure_starts_reauthentication(hass, hub):
    config = await setup(hass, hub)
    hub.refresh.side_effect = MipcAuthenticationError("ccm_img_get")
    with patch.object(config, "async_start_reauth") as reauth:
        await config.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert not config.runtime_data.last_update_success
    reauth.assert_called_once()


async def test_translations_and_diagnostic_defaults_keep_stable_ids(hass, hub):
    config = await setup(hass, hub)
    registry = er.async_get(hass)
    for key in ("firmware", "last_seen"):
        registered = registry.async_get(entity_id(hass, config, key))
        assert registered.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert (
        hass.states.get(entity_id(hass, config, "microphone_mic0_volume")).attributes[
            "friendly_name"
        ]
        == "Test camera Microphone volume"
    )
    assert (
        hass.states.get(entity_id(hass, config, "day_night")).attributes[
            "friendly_name"
        ]
        == "Test camera Day/night mode"
    )


async def test_cancelled_setup_still_closes_its_connection(hass, hub):
    import asyncio
    from unittest.mock import call

    from custom_components.mipc_camera import async_setup_entry

    with (
        patch("custom_components.mipc_camera.MipcHub", return_value=hub),
        patch.object(
            hass,
            "async_add_executor_job",
            new=AsyncMock(side_effect=[asyncio.CancelledError(), None]),
        ) as executor,
    ):
        with pytest.raises(asyncio.CancelledError):
            await async_setup_entry(hass, entry())
        assert executor.await_args_list == [call(hub.connect), call(hub.close)]


@pytest.mark.parametrize("source", ["reauth", "reconfigure"])
async def test_existing_entry_retry_does_not_save_invalid_credentials(
    hass, hub, source
):
    config = entry()
    config.add_to_hass(hass)
    data = {"username": "", "password": "replacement-device-password"}
    if source == "reconfigure":
        data["host"] = "192.0.2.11"
    hub.connect.side_effect = MipcAuthenticationError("login")
    with (
        patch("custom_components.mipc_camera.config_flow.MipcHub", return_value=hub),
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": source,
                "entry_id": config.entry_id,
                "unique_id": config.unique_id,
            },
            data=dict(config.data) if source == "reauth" else None,
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
        assert result["errors"] == {"base": "invalid_auth"}
        assert config.data["password"] == "never-export-this"
        hub.connect.side_effect = None
        result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == source + "_successful"
    assert config.data["password"] == data["password"]
