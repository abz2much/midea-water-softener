"""Local (LAN) transport: handshake and one frame, against a fake softener."""
from __future__ import annotations

import asyncio
import os
import socket
from hashlib import sha256

import pytest
from Crypto.Util.strxor import strxor
from midealocal.packet_builder import PacketBuilder
from midealocal.security import (
    MSGTYPE_ENCRYPTED_RESPONSE,
    MSGTYPE_HANDSHAKE_RESPONSE,
    LocalSecurity,
)

from custom_components.midea_water_softener import local
from custom_components.midea_water_softener.local import (
    LocalNoReply,
    LocalNotSent,
    LocalTransport,
)
from custom_components.midea_water_softener.message import build_query

from .conftest import status_packet

# The fake softener listens on 127.0.0.1, the only host the HA test plugin allows.
pytestmark = pytest.mark.usefixtures("socket_enabled")

DEVICE = 123456
TOKEN = "ab" * 64
KEY = "cd" * 32


class FakeSoftener:
    """A TCP server that answers like the softener on port 6444.

    `mode` picks how it behaves: "ok", "bad_handshake", "silent" (never answers
    the handshake), "no_reply" (handshake works, the frame gets no reply) or
    "malformed" (the reply is too short to read).
    `extra` frames are sent before the reply, as the device may do.
    """

    def __init__(self, reply: bytes, mode: str = "ok", extra: list[bytes] | None = None):
        self.reply = reply
        self.mode = mode
        self.extra = extra or []
        self.received: list[bytes] = []
        self.port = 0
        self._server: asyncio.Server | None = None
        self._tasks: set[asyncio.Task] = set()
        self.open_now = 0  # connections being handled right now
        self.most_open = 0

    async def __aenter__(self) -> FakeSoftener:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc) -> None:
        # Stop handlers still waiting (silent, no_reply) so no task lingers.
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, reader, writer) -> None:
        self._tasks.add(asyncio.current_task())
        self.open_now += 1
        self.most_open = max(self.most_open, self.open_now)
        security = LocalSecurity()
        try:
            await reader.read(512)  # handshake request carrying the token
            if self.mode == "silent":
                await asyncio.sleep(5)
                return
            key = bytes.fromhex(KEY)
            plain = os.urandom(32)
            sign = sha256(plain).digest()
            if self.mode == "bad_handshake":
                sign = bytes(32)
            payload = security.aes_cbc_encrypt(plain, key) + sign
            writer.write(security.encode_8370(payload, MSGTYPE_HANDSHAKE_RESPONSE))
            await writer.drain()
            security._tcp_key = strxor(plain, key)

            request = await reader.read(1024)
            packets, _ = security.decode_8370(request)
            self.received.extend(
                security.aes_decrypt(bytes(p[40:-16])) for p in packets
            )
            if self.mode == "no_reply":
                await asyncio.sleep(5)
                return
            if self.mode == "malformed":
                # Too short to hold a payload type: reading it raises IndexError.
                writer.write(security.encode_8370(b"\x01", MSGTYPE_ENCRYPTED_RESPONSE))
                await writer.drain()
                await asyncio.sleep(0.1)
                return
            for frame in [*self.extra, self.reply]:
                packet = PacketBuilder(DEVICE, frame).finalize()
                writer.write(security.encode_8370(packet, MSGTYPE_ENCRYPTED_RESPONSE))
            await writer.drain()
            await reader.read()  # hold the connection until the client closes it
        finally:
            self.open_now -= 1
            writer.close()


def _transport(port: int, timeout: float = 2.0) -> LocalTransport:
    return LocalTransport("127.0.0.1", DEVICE, TOKEN, KEY, port=port, timeout=timeout)


def _free_port() -> int:
    """A port with nothing listening on it."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_defaults_are_port_6444_and_10_seconds():
    assert local.DEFAULT_PORT == 6444
    assert local.TIMEOUT == 10
    transport = LocalTransport("10.0.0.1", DEVICE, TOKEN, KEY)
    assert transport.port == 6444
    assert transport.timeout == 10


async def test_success_sends_the_frame_and_returns_the_reply():
    reply = status_packet({7: 80})
    async with FakeSoftener(reply) as softener:
        result = await _transport(softener.port).send(build_query())
    assert result == reply
    assert softener.received == [build_query()]


async def test_an_unrequested_status_report_is_skipped():
    reply = status_packet({7: 80})
    notify = bytearray(status_packet({7: 1}))
    notify[9] = 0x04  # notify message type
    async with FakeSoftener(reply, extra=[bytes(notify)]) as softener:
        result = await _transport(softener.port).send(build_query())
    assert result == reply


async def test_refused_raises_not_sent():
    with pytest.raises(LocalNotSent):
        await _transport(_free_port()).send(build_query())


async def test_timeout_in_handshake_raises_not_sent():
    async with FakeSoftener(b"", mode="silent") as softener:
        with pytest.raises(LocalNotSent):
            await _transport(softener.port, timeout=0.3).send(build_query())


async def test_bad_handshake_raises_not_sent():
    async with FakeSoftener(b"", mode="bad_handshake") as softener:
        with pytest.raises(LocalNotSent):
            await _transport(softener.port).send(build_query())
    assert softener.received == []


async def test_no_reply_after_sending_raises_no_reply():
    async with FakeSoftener(b"", mode="no_reply") as softener:
        with pytest.raises(LocalNoReply):
            await _transport(softener.port, timeout=0.3).send(build_query())
    assert softener.received == [build_query()]


async def test_errors_never_contain_the_token_or_key():
    async with FakeSoftener(b"", mode="bad_handshake") as softener:
        with pytest.raises(LocalNotSent) as err:
            await _transport(softener.port).send(build_query())
    assert TOKEN not in str(err.value)
    assert KEY not in str(err.value)


async def test_a_malformed_reply_raises_no_reply():
    """Any unexpected error after sending still maps to LocalNoReply."""
    async with FakeSoftener(b"", mode="malformed") as softener:
        with pytest.raises(LocalNoReply):
            await _transport(softener.port).send(build_query())


async def test_requests_to_one_softener_do_not_overlap():
    """Many Midea devices accept only one LAN session at a time."""
    reply = status_packet({7: 80})
    async with FakeSoftener(reply) as softener:
        transport = _transport(softener.port)
        softener.open_now = 0
        softener.most_open = 0
        await asyncio.gather(*(transport.send(build_query()) for _ in range(3)))
    assert softener.most_open == 1
