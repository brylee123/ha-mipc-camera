"""Retire only the redundant speaker number without disturbing entity identity."""

from unittest.mock import patch

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mipc_camera.const import DOMAIN
from tests.test_integration import setup


async def test_renamed_old_speaker_number_removed_and_other_entities_preserved(
    hass, hub
):
    config = await setup(hass, hub)
    registry = er.async_get(hass)
    before = {
        e.unique_id: e.entity_id
        for e in registry.entities.values()
        if e.config_entry_id == config.entry_id
    }
    day_id = next(
        entity_id
        for unique_id, entity_id in before.items()
        if unique_id.endswith("_motion_sensitivity")
    )
    registry.async_update_entity(day_id, name="My sensitivity")
    retired = registry.async_get_or_create(
        "number",
        DOMAIN,
        f"{config.unique_id}_speaker_volume",
        config_entry=config,
        suggested_object_id="custom_loudspeaker_volume",
    )
    registry.async_update_entity(retired.entity_id, name="Custom volume")
    with patch("custom_components.mipc_camera.MipcHub", return_value=hub):
        assert await hass.config_entries.async_reload(config.entry_id)
        await hass.async_block_till_done()
    assert registry.async_get(retired.entity_id) is None
    assert hass.states.get(retired.entity_id) is None
    after = {
        e.unique_id: e.entity_id
        for e in registry.entities.values()
        if e.config_entry_id == config.entry_id
    }
    assert after == before
    assert registry.async_get(day_id).name == "My sensitivity"
    speaker_id = next(
        entity_id
        for unique_id, entity_id in after.items()
        if unique_id.endswith("_speaker")
    )
    await hass.services.async_call(
        "media_player",
        "volume_set",
        {"entity_id": speaker_id, "volume_level": 0.3},
        blocking=True,
    )
    assert hub.settings["speaker"]["level"] == 30


async def test_retirement_does_not_remove_another_entries_entity(hass, hub):
    config = await setup(hass, hub)
    other = MockConfigEntry(domain=DOMAIN, unique_id="sn:another-device", data={})
    other.add_to_hass(hass)
    registry = er.async_get(hass)
    protected = registry.async_get_or_create(
        "number",
        DOMAIN,
        f"{config.unique_id}_speaker_volume",
        config_entry=other,
    )
    with patch("custom_components.mipc_camera.MipcHub", return_value=hub):
        assert await hass.config_entries.async_reload(config.entry_id)
        await hass.async_block_till_done()
    assert registry.async_get(protected.entity_id).config_entry_id == other.entry_id
