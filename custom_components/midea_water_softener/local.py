"""Local (LAN) transport: talks to the softener on port 6444, no cloud.

Each request opens a connection, does the 8370 handshake with the token and
key, sends one frame and closes. The crypto is midea-local's own.

midea-local is imported on first use, not at module load. If it is missing or
its API has changed, local control turns itself off (LocalUnavailable) and the
integration carries on over the cloud.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from types import SimpleNamespace

from .message import MessageType

_LOGGER = logging.getLogger(__name__)

DEFAULT_PORT = 6444
TIMEOUT = 10  # seconds, for the whole request

# The handshake reply: 8 header bytes, then 64 bytes of key material.
_MIN_HANDSHAKE_REPLY = 72
# Heartbeat packets carry no frame (payload types from midea-local device.py).
_HEARTBEAT_TYPES = (0x0001, 0x1001)
# A packet shorter than this has no encrypted frame in it.
_MIN_PACKET_LENGTH = 56
# Errors that mean midea-local's API is not what this code expects.
_API_ERRORS = (AttributeError, TypeError, NameError, ImportError)

_lib: SimpleNamespace | None = None


class LocalError(Exception):
    """Base class for local transport errors."""


class LocalNotSent(LocalError):
    """The frame was not sent: no connection, timeout or a failed handshake."""


class LocalNoReply(LocalError):
    """The frame was sent, but no reply came back."""


class LocalUnavailable(LocalError):
    """midea-local is missing or its API has changed. Local control is off.

    `sent` says whether the frame had already left when it broke.
    """

    def __init__(self, message: str, *, sent: bool = False) -> None:
        super().__init__(message)
        self.sent = sent


def _midea_local() -> SimpleNamespace:
    """Import the parts of midea-local we use, once. Blocking: disk access."""
    global _lib
    if _lib is None:
        try:
            from midealocal.packet_builder import PacketBuilder
            from midealocal.security import (
                MSGTYPE_ENCRYPTED_REQUEST,
                MSGTYPE_HANDSHAKE_REQUEST,
                CloudSecurity,
                LocalSecurity,
            )
        except Exception as exc:  # noqa: BLE001 - any broken install turns local off
            raise LocalUnavailable(
                f"midea-local cannot be imported ({type(exc).__name__}: {exc})"
            ) from None
        _lib = SimpleNamespace(
            PacketBuilder=PacketBuilder,
            CloudSecurity=CloudSecurity,
            LocalSecurity=LocalSecurity,
            MSGTYPE_ENCRYPTED_REQUEST=MSGTYPE_ENCRYPTED_REQUEST,
            MSGTYPE_HANDSHAKE_REQUEST=MSGTYPE_HANDSHAKE_REQUEST,
        )
    return _lib


def unavailable_reason() -> str | None:
    """Why midea-local can't be used, or None if it can. Run in an executor."""
    try:
        _midea_local()
    except LocalUnavailable as exc:
        return str(exc)
    return None


def udp_id(device_id: int, method: int) -> str | None:
    """midea-local's udpid for the cloud getToken call."""
    lib = _midea_local()
    try:
        return lib.CloudSecurity.get_udp_id(device_id, method)
    except _API_ERRORS as exc:
        raise LocalUnavailable(
            f"midea-local API has changed ({type(exc).__name__}: {exc})"
        ) from None


class LocalTransport:
    """One water softener on the local network."""

    def __init__(
        self,
        host: str,
        device_id: int,
        token: str,
        key: str,
        *,
        port: int = DEFAULT_PORT,
        timeout: float = TIMEOUT,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self._device_id = device_id
        self._token = bytes.fromhex(token)
        self._key = bytes.fromhex(key)
        # Many Midea devices accept one LAN session at a time, so a poll and a
        # command take turns rather than opening two connections.
        self._lock = asyncio.Lock()

    async def send(self, frame: bytes) -> bytes:
        """Send one frame and return the device's reply frame.

        Raises LocalNotSent if the frame never left, LocalNoReply if it was
        sent but nothing came back in time, and LocalUnavailable if
        midea-local can't be used.
        """
        async with self._lock:
            return await self._send(frame)

    async def _send(self, frame: bytes) -> bytes:
        lib = _midea_local()
        sent = False
        writer: asyncio.StreamWriter | None = None
        try:
            async with asyncio.timeout(self.timeout):
                reader, writer = await asyncio.open_connection(self.host, self.port)
                security = lib.LocalSecurity()
                writer.write(
                    security.encode_8370(self._token, lib.MSGTYPE_HANDSHAKE_REQUEST)
                )
                await writer.drain()
                response = await reader.read(512)
                if len(response) < _MIN_HANDSHAKE_REPLY:
                    raise LocalNotSent(
                        f"Handshake with {self.host} failed (reply of {len(response)} bytes)"
                    )
                security.tcp_key(response[8:72], self._key)

                packet = lib.PacketBuilder(self._device_id, frame).finalize()
                writer.write(security.encode_8370(packet, lib.MSGTYPE_ENCRYPTED_REQUEST))
                await writer.drain()
                sent = True
                return await self._read_reply(reader, security)
        except LocalError:
            raise
        except _API_ERRORS as exc:
            raise LocalUnavailable(
                f"midea-local API has changed ({type(exc).__name__}: {exc})", sent=sent
            ) from None
        except Exception as exc:  # noqa: BLE001 - every failure maps to one of the two
            # Timeouts, socket errors, midea-local errors and malformed packets
            # alike: what matters to the caller is whether the frame left.
            error = LocalNoReply if sent else LocalNotSent
            stage = "no reply from" if sent else "cannot reach"
            raise error(
                f"Local connection: {stage} {self.host}:{self.port} ({type(exc).__name__})"
            ) from None
        finally:
            if writer is not None:
                writer.close()
                with contextlib.suppress(OSError):
                    await writer.wait_closed()

    async def _read_reply(
        self, reader: asyncio.StreamReader, security
    ) -> bytes:
        """Read until a reply frame arrives. Skip heartbeats and status reports."""
        buffer = b""
        while True:
            chunk = await reader.read(1024)
            if not chunk:
                raise LocalNoReply(f"{self.host} closed the connection without a reply")
            packets, buffer = security.decode_8370(buffer + chunk)
            for packet in packets:
                if packet == b"ERROR":
                    raise LocalNoReply(f"{self.host} replied ERROR")
                payload_type = packet[2] + (packet[3] << 8)
                if payload_type in _HEARTBEAT_TYPES or len(packet) <= _MIN_PACKET_LENGTH:
                    continue
                reply = bytes(security.aes_decrypt(bytes(packet[40:-16])))
                if len(reply) > 9 and reply[9] == MessageType.notify:
                    _LOGGER.debug("Skipping a status report from %s", self.host)
                    continue
                return reply
