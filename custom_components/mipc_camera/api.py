"""Synchronous, serialized adapter for the temporarily bundled local client."""

import threading
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from ._vendor.mipc_camera_client import (
    MipcAuthenticationError,
    MipcCameraClient,
    MipcError,
    MipcProtocolError,
    MipcTransportError,
    MipcUnsupportedError,
)
from .capabilities import Setting, value_at


class MipcHub:
    def __init__(self, host: str, username: str, password: str) -> None:
        self.host, self.username, self._password = host, username, password
        self._lock = threading.RLock()
        self._client: MipcCameraClient | None = None
        self._serial_number: str | None = None
        self.info: dict[str, Any] = {}
        self.settings: dict[str, Any] = {}
        self.errors: dict[str, str] = {}
        self.last_seen: datetime | None = None
        self.video_token = "vs0"

    @property
    def serial_number(self) -> str | None:
        return self._serial_number

    @property
    def model(self) -> str:
        model = self.info.get("model")
        if isinstance(model, str) and model:
            return model
        properties = self.info.get("p")
        if isinstance(properties, list):
            for item in properties:
                if (
                    isinstance(item, dict)
                    and item.get("n") == "model"
                    and isinstance(item.get("v"), str)
                ):
                    return item["v"]
        return "IP camera"

    @property
    def firmware(self) -> str | None:
        firmware = self.info.get("img_ver") or self.info.get("ver")
        return firmware if isinstance(firmware, str) else None

    def _get_client(self) -> MipcCameraClient:
        if self._client is None:
            raise MipcProtocolError("connection")
        return self._client

    def connect(self) -> dict[str, Any]:
        with self._lock:
            self.close()
            client = MipcCameraClient(self.host, timeout=8)
            try:
                basic = client.get_info()
                serial = basic.get("sn")
                if not isinstance(serial, str) or not serial:
                    raise MipcProtocolError("ccm_info_get")
                if self.serial_number and self.serial_number != serial:
                    raise MipcProtocolError("identity_changed")
                client.login(self.username or serial, self._password)
                self._client = client
                self._serial_number = serial
                self.info = basic
                try:
                    self.info.update(client.get_device_info())
                except MipcAuthenticationError:
                    raise
                except (MipcUnsupportedError, MipcProtocolError):
                    pass
                self.info["sn"] = serial
                return self.info
            except Exception:
                client.close()
                self._client = None
                raise

    def refresh(self) -> dict[str, Any]:
        with self._lock:
            try:
                return self._refresh_once()
            except MipcAuthenticationError:
                # Session renewal retries reads only, never a settings write.
                self.connect()
                return self._refresh_once()

    def _refresh_once(self) -> dict[str, Any]:
        client = self._get_client()
        basic = client.get_info()
        if basic.get("sn") != self.serial_number:
            raise MipcProtocolError("identity_changed")
        self.info.update(basic)
        settings, errors = {}, {}
        reads = {
            "device": client.get_device_info,
            "video_sources": client.get_video_sources,
            "microphones": client.get_microphones,
            "speaker": client.get_speaker,
            "imaging": lambda: client.get_imaging(self.video_token),
            "misc": client.get_misc,
            "osd": client.get_osd,
            "alerts": client.get_alert_config,
            "alert_actions": client.get_alert_actions,
            "recording": client.get_recording,
            "disks": client.get_disks,
        }
        for section, read in reads.items():
            try:
                settings[section] = read()
                if section == "video_sources" and settings[section]:
                    token = settings[section][0].get("token")
                    if isinstance(token, str) and token:
                        self.video_token = token
            except MipcAuthenticationError:
                raise
            except MipcTransportError as error:
                if not error.code.startswith("http_"):
                    raise
                errors[section] = type(error).__name__
            except MipcError as error:
                errors[section] = type(error).__name__
        self.info.update(settings.get("device", {}))
        self.info["sn"] = self.serial_number
        self.settings, self.errors = settings, errors
        self.last_seen = datetime.now(timezone.utc)
        return {"settings": settings, "errors": errors}

    def create_event_client(self) -> MipcCameraClient:
        """Open a separate identity-checked session; long polls never lock controls."""
        client = MipcCameraClient(self.host, timeout=6)
        try:
            if client.get_device_sn() != self.serial_number:
                raise MipcProtocolError("identity_changed")
            client.login(self.username or self.serial_number, self._password)
            return client
        except BaseException:
            client.close()
            raise

    def discover_stream_profiles(self) -> list[dict]:
        """Decode local frames once; advertised names do not prove resolutions."""

        def decode(url):
            import av

            with (
                av.logging.Capture(local=True),
                av.open(
                    url, mode="r", timeout=(8, 8), options={"rtmp_live": "live"}
                ) as container,
            ):
                frame = next(container.decode(video=0))
                return frame.width, frame.height

        with self._lock:
            return [
                {"token": p.token, "name": p.name, "width": p.width, "height": p.height}
                for p in self._get_client().probe_stream_profiles(decode)
            ]

    def snapshot(self) -> bytes:
        with self._lock:
            return self._get_client().get_image()

    def stream_url(self, token: str) -> str:
        with self._lock:
            # The library rejects media hosts other than the configured camera.
            return self._get_client().get_stream_url(token)

    def move(self, x: int, y: int, speed_x: int, speed_y: int) -> None:
        with self._lock:
            self._get_client().control_ptz(x, y, speed_x, speed_y)

    def set_value(self, spec: Setting, value: str | int | bool) -> None:
        with self._lock:
            client = self._get_client()
            if value_at(self.settings, spec.path) is None:
                raise MipcProtocolError("setting_unavailable")
            section, *tail = spec.path
            field = tail[-1]
            if section == "imaging":
                client.set_imaging(field, value, self.video_token)
            elif section == "speaker":
                client.set_speaker_level(
                    value, self.settings[section].get("token", "ao0")
                )
            elif section == "microphones":
                client.update_microphone(tail[0], **{field: value})
            elif section == "misc":
                client.set_flip(value)
            elif section == "osd":
                patch = {field: int(value) if spec.platform == "switch" else value}
                client.update_osd(**({"date": patch} if len(tail) == 2 else patch))
            elif section == "alerts":
                client.update_alert_config(**{field: value})
            elif section == "recording":
                client.set_recording_enabled(value)
            else:
                raise ValueError("Unsupported setting")

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                client, self._client = self._client, None
                try:
                    client.logout()
                except MipcError:
                    pass
                finally:
                    client.close()


def valid_host(host: str) -> bool:
    if (
        not isinstance(host, str)
        or not host
        or any(c.isspace() for c in host)
        or "\\" in host
    ):
        return False
    try:
        parsed = urlsplit("http://" + host)
        return (
            bool(parsed.hostname)
            and not (
                parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or host.endswith(":")
            )
            and parsed.port != 0
        )
    except ValueError:
        return False
