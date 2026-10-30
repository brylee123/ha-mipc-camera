"""Read-only local motion pulses on a dedicated, reconnecting event session."""

import asyncio
import logging
import time
from collections import deque
from contextlib import suppress
from functools import partial
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ._vendor.mipc_camera_client.events import MotionEvent
from .api import MipcError, MipcUnsupportedError

if TYPE_CHECKING:
    from .coordinator import MipcCoordinator

_LOGGER = logging.getLogger(__name__)


def close_event_client(client) -> None:
    """Release the authenticated session even after a queue failure."""
    try:
        client.logout()
    except (MipcError, OSError):
        pass
    finally:
        client.close()


def motion_supported(settings: dict) -> bool:
    """Require the detector/action schema actually returned by this firmware."""
    actions = settings.get("alert_actions", {}).get("actions")
    return isinstance(actions, list) and any(
        isinstance(a, dict)
        and a.get("name") == "motion_alert"
        and a.get("srcs") == [{"devs": ["motion"]}]
        and a.get("enable") in (0, 1)
        for a in actions
    )


def motion_armed(settings: dict) -> bool:
    if not motion_supported(settings):
        return False
    document = settings["alert_actions"]
    return document.get("enable") == 1 and any(
        a.get("name") == "motion_alert"
        and a.get("enable") == 1
        and a.get("srcs") == [{"devs": ["motion"]}]
        for a in document["actions"]
        if isinstance(a, dict)
    )


class MipcMotionCoordinator(DataUpdateCoordinator[MotionEvent | None]):
    """Queue health is separate from the camera's normal settings connection."""

    def __init__(self, parent: MipcCoordinator) -> None:
        super().__init__(
            parent.hass, _LOGGER, name="MIPC motion", config_entry=parent.config_entry
        )
        self.parent = parent
        self.data = None
        self.last_update_success = False
        self._stop = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._seen: deque[tuple[int, int]] = deque(maxlen=256)

    def start(self) -> None:
        self._task = self.config_entry.async_create_background_task(
            self.hass, self._run(), "MIPC local motion listener"
        )

    async def async_stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            except Exception:
                _LOGGER.exception("MIPC motion listener stopped unexpectedly")

    @callback
    def process(self, items: list[dict]) -> None:
        """Publish distinct fresh pulses for this camera without inventing a clear state."""
        self.async_set_updated_data(self.data)
        for item in items:
            event = MotionEvent.from_message(item)
            if event is None or event.serial_number != self.parent.hub.serial_number:
                continue
            key = (event.message_id, event.timestamp)
            if key in self._seen or abs(time.time() - event.timestamp) > 120:
                continue
            self._seen.append(key)
            self.async_set_updated_data(event)

    async def _job(self, function, *args, cleanup_result=None):
        """Join the bounded executor operation before closing on cancellation."""
        future = self.hass.async_add_executor_job(function, *args)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            result = await future
            if cleanup_result:
                await self.hass.async_add_executor_job(cleanup_result, result)
            raise

    async def _run(self) -> None:
        delay = 1
        try:
            while not self._stop.is_set():
                client = queue = None
                unsupported = False
                try:
                    client = await self._job(
                        self.parent.hub.create_event_client,
                        cleanup_result=close_event_client,
                    )
                    queue = await self._job(
                        partial(client.event_queue, lifetime=300),
                        cleanup_result=lambda queue: queue.close(),
                    )
                    while not self._stop.is_set():
                        items = await self._job(queue.poll, 3)
                        delay = 1
                        self.process(items)
                except (MipcError, OSError) as error:
                    self.data = None
                    self.async_set_update_error(error)
                    unsupported = isinstance(error, MipcUnsupportedError)
                finally:
                    if queue is not None:
                        with suppress(MipcError, OSError):
                            await self._job(queue.close)
                    if client is not None:
                        await self._job(close_event_client, client)
                if unsupported:
                    return
                if not self._stop.is_set():
                    with suppress(TimeoutError):
                        await asyncio.wait_for(self._stop.wait(), timeout=delay)
                    delay = min(delay * 2, 60)
        finally:
            self.last_update_success = False
            self.async_update_listeners()
