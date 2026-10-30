"""Synchronous MIPC client adapter; run all public calls in an executor.

The upstream 0.1.3 client uses requests without a timeout and a mutable
session counter. This adapter bounds requests and serializes access.
"""

from datetime import datetime, timezone
from functools import partial
import ipaddress
import threading
from urllib.parse import urlsplit

from mipc_camera_client import MipcCameraClient
from requests.exceptions import RequestException

class MipcAuthenticationError(Exception):
    """Authentication rejected by the camera."""

class MipcCommunicationError(Exception):
    """Unexpected camera response or unsupported protocol."""

class MipcHub:
    """Own one MIPC session for one physical camera."""

    def __init__(self, host: str, username: str, password: str) -> None:
        self.host = host
        self.username = username
        self._password = password
        self._lock = threading.RLock()
        self._client: MipcCameraClient | None = None
        self.info: dict = {}
        self.last_seen: datetime | None = None
        self.last_error: str | None = None

    @property
    def serial_number(self) -> str | None:
        sn = self.info.get("sn")
        return str(sn) if sn else None

    @property
    def model(self) -> str:
        return str(self.info.get("model") or self.info.get("product") or "IP camera")

    def _get_client(self) -> MipcCameraClient:
        if self._client is None:
            raise MipcCommunicationError("Camera session not initialized")
        return self._client

    def connect(self) -> dict:
        """Authenticate and fetch identity (blocking)."""
        with self._lock:
            client = MipcCameraClient(self.host)
            # Upstream requests.Session.request has no timeout. This is a
            # per-instance bound method wrapper; do not monkeypatch requests globally.
            client._r.request = partial(client._r.request, timeout=10)
            try:
                client.login(self.username, self._password)
            except RequestException:
                raise
            except Exception as err:
                raise MipcAuthenticationError("Camera login was rejected") from err
            self._client = client
            return self.refresh()

    def refresh(self) -> dict:
        """Check live network connectivity, not the client's cached serial."""
        with self._lock:
            try:
                result = self._get_client().run_rpc("ccm_info_get", {})
                data = result.get("data") if isinstance(result, dict) else None
                if not isinstance(data, dict) or not data.get("sn"):
                    raise MipcCommunicationError("No device identity in camera reply")
                self.info = data
                self.last_seen = datetime.now(timezone.utc)
                self.last_error = None
                return data
            except Exception as err:
                self.last_error = type(err).__name__
                raise

    def snapshot(self) -> bytes:
        with self._lock:
            image = self._get_client().get_image()
            if not isinstance(image, bytes) or not image.startswith(b"\xff\xd8"):
                raise MipcCommunicationError("Camera returned non-JPEG data")
            return image

    @staticmethod
    def _is_local_endpoint(stream_host: str, camera_host: str) -> bool:
        if stream_host.lower() == camera_host.lower():
            return True
        if stream_host.lower().endswith((".local", ".lan", ".home.arpa")):
            return True
        try:
            address = ipaddress.ip_address(stream_host)
            return address.is_private or address.is_loopback or address.is_link_local
        except ValueError:
            return False

    def stream_url(self, token: str, allow_remote: bool) -> str:
        """Return URL suitable for FFmpeg; reject cloud hosts by default."""
        with self._lock:
            url = self._get_client().get_rtmp_stream(token=token)
        if not isinstance(url, str):
            raise MipcCommunicationError("Camera did not return a stream URL")
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in ("rtmp", "rtmps") or not parsed.hostname:
            raise MipcCommunicationError("Camera did not return an RTMP URL")
        if not allow_remote and not self._is_local_endpoint(parsed.hostname, self.host):
            raise MipcCommunicationError(
                "Stream points outside the LAN; enable remote streaming explicitly"
            )
        return url

    def move(self, x: int, y: int, speed_x: int, speed_y: int) -> None:
        with self._lock:
            self._get_client().control_ptz(
                tilt_x=x, tilt_y=y, speed_x=speed_x, speed_y=speed_y
            )

    def close(self) -> None:
        with self._lock:
            if self._client is not None:
                self._client._r.close()
                self._client = None
