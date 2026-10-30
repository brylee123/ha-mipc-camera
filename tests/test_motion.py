"""Fresh native motion events, availability, reconnects and lifecycle cleanup."""

import asyncio
import time
from copy import deepcopy
from unittest.mock import MagicMock, create_autospec, patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import entity_registry as er

from custom_components.mipc_camera._vendor.mipc_camera_client import MipcCameraClient
from custom_components.mipc_camera.api import MipcTransportError, MipcUnsupportedError
from custom_components.mipc_camera.motion import (
    MipcMotionCoordinator,
    motion_armed,
    motion_supported,
)
from tests.test_integration import setup

ACTIONS = {
    "enable": 1,
    "actions": [
        {
            "token": "motion",
            "name": "motion_alert",
            "enable": 1,
            "srcs": [{"devs": ["motion"]}],
        }
    ],
}


def pulse(msg_id=1, **patches):
    return {
        "type": "alert",
        "code": "motion_alert",
        "sn": "synthetic-camera",
        "msg_id": msg_id,
        "date": int(time.time()),
        **patches,
    }


@pytest.mark.parametrize(
    "document", [{}, {"actions": []}, {"actions": [{}]}, {"actions": "bad"}]
)
def test_unknown_action_schema_is_not_capability(document):
    assert not motion_supported({"alert_actions": document})
    assert not motion_armed({"alert_actions": document})


async def motion_setup(hass, hub):
    hub.settings["alert_actions"] = deepcopy(ACTIONS)
    hub.create_event_client.return_value = create_autospec(
        MipcCameraClient, instance=True
    )
    with patch.object(MipcMotionCoordinator, "start"):
        config = await setup(hass, hub, {"motion_events": True})
    entity = next(
        e.entity_id
        for e in er.async_get(hass).entities.values()
        if e.config_entry_id == config.entry_id and e.domain == "event"
    )
    return config, config.runtime_data.motion, entity


async def test_event_entity_fires_each_fresh_pulse_without_a_clear_timer(hass, hub):
    config, motion, entity = await motion_setup(hass, hub)
    assert hass.states.get(entity).state == STATE_UNAVAILABLE
    motion.process([])
    assert hass.states.get(entity).state == STATE_UNKNOWN
    first = pulse()
    motion.process(
        [
            first,
            first,
            pulse(code="io_alert"),
            pulse(sn="other"),
            pulse(date=int(time.time()) - 300),
        ]
    )
    state = hass.states.get(entity)
    assert state.attributes["event_type"] == "motion"
    assert state.attributes["message_id"] == 1
    assert state.attributes["event_types"] == ["motion"]
    assert "synthetic-camera" not in str(dict(state.attributes))
    motion.process([first])
    assert hass.states.get(entity).state == state.state
    motion.process([pulse(2)])
    assert hass.states.get(entity).state != state.state
    assert hass.states.get(entity).attributes["message_id"] == 2
    last = hass.states.get(entity).state
    motion.process([])
    assert hass.states.get(entity).state == last
    motion.async_set_update_error(MipcTransportError("mmq_pick", "timeout"))
    assert hass.states.get(entity).state == STATE_UNAVAILABLE
    motion.process([])
    assert hass.states.get(entity).state == last
    config.runtime_data.data["settings"]["alert_actions"]["enable"] = 0
    motion.process([pulse(3)])
    # The actual event is authoritative; settings polling can lag arming changes.
    assert hass.states.get(entity).attributes["message_id"] == 3
    assert await hass.config_entries.async_unload(config.entry_id)


async def test_option_does_not_create_event_for_unsupported_camera(hass, hub):
    config = await setup(hass, hub, {"motion_events": True})
    assert config.runtime_data.motion is None
    assert not any(e.domain == "event" for e in er.async_get(hass).entities.values())


async def test_native_listener_uses_separate_queue_and_closes_on_stop(hass, hub):
    config, motion, _ = await motion_setup(hass, hub)
    client = hub.create_event_client.return_value
    queue = client.event_queue.return_value

    def poll(timeout):
        assert timeout == 3
        motion._stop.set()
        return [pulse()]

    queue.poll.side_effect = poll
    motion.start()
    await motion._task
    await motion.async_stop()
    client.event_queue.assert_called_once_with(lifetime=300)
    queue.close.assert_called_once()
    client.close.assert_called_once()
    assert not motion.last_update_success
    assert motion.data.message_id == 1


async def test_unsupported_subscription_is_not_retried(hass, hub):
    _, motion, _ = await motion_setup(hass, hub)
    client = hub.create_event_client.return_value
    client.event_queue.side_effect = MipcUnsupportedError("ccm_subscribe", 404)
    await motion._run()
    assert hub.create_event_client.call_count == 1
    client.close.assert_called_once()
    assert not motion.last_update_success


async def test_timeout_reopens_queue_without_replaying_writes(hass, hub):
    _, motion, _ = await motion_setup(hass, hub)
    first, second = (create_autospec(MipcCameraClient, instance=True) for _ in range(2))
    first.event_queue.return_value.poll.side_effect = MipcTransportError(
        "mmq_pick", "timeout"
    )

    def poll(_):
        motion._stop.set()
        return [pulse()]

    second.event_queue.return_value.poll.side_effect = poll
    hub.create_event_client.side_effect = [first, second]

    async def immediate_timeout(coro, timeout):
        coro.close()
        raise TimeoutError

    with patch(
        "custom_components.mipc_camera.motion.asyncio.wait_for",
        side_effect=immediate_timeout,
    ):
        await motion._run()
    assert hub.create_event_client.call_count == 2
    first.event_queue.return_value.close.assert_called_once()
    second.event_queue.return_value.close.assert_called_once()
    assert motion.data.message_id == 1
    assert not motion.last_update_success


async def test_deduplication_memory_is_bounded(hass, hub):
    _, motion, _ = await motion_setup(hass, hub)
    motion.process([pulse(i) for i in range(1, 300)])
    assert len(motion._seen) == 256


async def test_cancellation_joins_executor_and_closes_created_resource(hass, hub):
    import threading

    _, motion, _ = await motion_setup(hass, hub)
    entered, release = threading.Event(), threading.Event()
    resource = MagicMock()

    def create():
        entered.set()
        release.wait(timeout=5)
        return resource

    task = hass.async_create_task(
        motion._job(create, cleanup_result=lambda result: result.close())
    )
    await hass.async_add_executor_job(entered.wait, 3)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    resource.close.assert_called_once()


async def test_setup_starts_listener_and_unload_joins_it(hass, hub):
    hub.settings["alert_actions"] = deepcopy(ACTIONS)
    hub.create_event_client.side_effect = MipcUnsupportedError("ccm_subscribe", 404)
    config = await setup(hass, hub, {"motion_events": True})
    motion = config.runtime_data.motion
    await motion._task
    assert await hass.config_entries.async_unload(config.entry_id)
    assert motion._task.done()


async def test_events_seen_while_settings_offline_are_not_replayed_on_recovery(
    hass, hub
):
    config, motion, entity = await motion_setup(hass, hub)
    motion.process([pulse()])
    before = hass.states.get(entity).state
    parent = config.runtime_data
    parent.async_set_update_error(MipcTransportError("ccm_info_get", "timeout"))
    motion.process([pulse(2)])
    assert hass.states.get(entity).state == STATE_UNAVAILABLE
    parent.async_set_updated_data(parent.data)
    assert hass.states.get(entity).state == before
    assert hass.states.get(entity).attributes["message_id"] == 1
    motion.process([pulse(3)])
    assert hass.states.get(entity).attributes["message_id"] == 3


@pytest.mark.parametrize("cancelled", [True, False])
async def test_stop_drains_cancelled_or_failed_worker_without_breaking_unload(
    hass, hub, cancelled
):
    _, motion, _ = await motion_setup(hass, hub)

    async def fail():
        raise RuntimeError("synthetic worker failure")

    if cancelled:
        task = hass.async_create_task(asyncio.Event().wait())
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        task = hass.async_create_task(fail())
        with pytest.raises(RuntimeError):
            await task
    motion._task = task
    await motion.async_stop()
    assert task.done()


async def test_native_event_received_automation_fires_only_for_new_motion(hass, hub):
    from homeassistant.setup import async_setup_component

    _, motion, entity = await motion_setup(hass, hub)
    received = []
    hass.bus.async_listen("mipc_test_motion", lambda event: received.append(event))
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "alias": "MIPC motion test",
                    "triggers": [
                        {
                            "trigger": "event.received",
                            "target": {"entity_id": entity},
                            "options": {"event_type": ["motion"]},
                        }
                    ],
                    "actions": [{"event": "mipc_test_motion"}],
                }
            ]
        },
    )
    await hass.async_block_till_done()
    motion.process([])
    first = pulse()
    motion.process([first])
    await hass.async_block_till_done()
    assert len(received) == 1
    motion.process([first])
    motion.async_set_update_error(MipcTransportError("mmq_pick", "timeout"))
    motion.process([])
    await hass.async_block_till_done()
    assert len(received) == 1
    motion.process([pulse(2)])
    await hass.async_block_till_done()
    assert len(received) == 2
