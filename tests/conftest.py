"""Shared fakes: a scripted aiohttp session and canned Midea cloud responses."""
from __future__ import annotations

import json
from collections import deque
from hashlib import sha256

import pytest
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from custom_components.midea_water_softener.cloud import MSmartHomeCloud
from custom_components.midea_water_softener.message import MessageType, _build_message
from custom_components.midea_water_softener.security import MSmartSecurity

ROUTER = "/v1/unitcenter/router/user/name"
LOGIN_ID = "/v1/user/login/id/get"
LOGIN = "/mj/user/login"
SEND = "/v1/appliance/transparent/send"

SESSION_KEY = "k" * 16
SESSION_IV = "i" * 16


def _login_encrypt(text: str) -> str:
    """Encrypt a value the way the cloud does for the login response."""
    digest = sha256(MSmartSecurity.APP_KEY.encode("ascii")).hexdigest()
    cipher = AES.new(
        digest[:16].encode("ascii"), AES.MODE_CBC, iv=digest[16:32].encode("ascii")
    )
    return cipher.encrypt(pad(text.encode("ascii"), 16)).hex()


def login_ok(token: str = "fake-token") -> dict:
    return {
        "code": 0,
        "data": {
            "uid": "1000",
            "mdata": {"accessToken": token},
            "accessToken": _login_encrypt(SESSION_KEY),
            "randomData": _login_encrypt(SESSION_IV),
        },
    }


def login_prelude() -> dict:
    """Responses for the two calls before /mj/user/login (enough for 3 logins)."""
    return {
        ROUTER: [{"code": 0, "data": {}}] * 3,
        LOGIN_ID: [{"code": 0, "data": {"loginId": "fake-login-id"}}] * 3,
    }


def send_reply(payload: bytes = b"\x01\x02\x03") -> dict:
    """A good transparent/send response whose reply decrypts to `payload`."""
    dec = ",".join(str(b if b < 128 else b - 256) for b in payload)
    cipher = AES.new(
        SESSION_KEY.encode("ascii"), AES.MODE_CBC, iv=SESSION_IV.encode("ascii")
    )
    return {"code": 0, "data": {"reply": cipher.encrypt(pad(dec.encode(), 16)).hex()}}


EXPIRED = {"code": 40002, "msg": "user token not exist"}


class _FakeResponse:
    def __init__(self, item):
        self._item = item

    async def read(self) -> bytes:
        return json.dumps(self._item).encode()


class _FakeContext:
    def __init__(self, item):
        self._item = item

    async def __aenter__(self):
        if isinstance(self._item, Exception):
            raise self._item
        return _FakeResponse(self._item)

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """Stands in for aiohttp.ClientSession. Each endpoint has a queue of replies.

    A reply is a dict (the JSON body) or an Exception (raised on connect).
    A call with no queued reply fails the test.
    """

    def __init__(self, routes: dict[str, list]) -> None:
        self._routes = {k: deque(v) for k, v in routes.items()}
        self.calls: list[str] = []

    def count(self, endpoint: str) -> int:
        return self.calls.count(endpoint)

    def post(self, url, data=None, headers=None, timeout=None):
        endpoint = url.split("alias=", 1)[1]
        self.calls.append(endpoint)
        queue = self._routes.get(endpoint)
        if not queue:
            raise AssertionError(f"Unexpected call to {endpoint}")
        return _FakeContext(queue.popleft())


@pytest.fixture
def make_session():
    def _make(overrides: dict | None = None) -> FakeSession:
        routes = login_prelude()
        routes[LOGIN] = [login_ok()]
        routes[SEND] = []
        routes.update(overrides or {})
        return FakeSession(routes)

    return _make


@pytest.fixture
def make_cloud():
    def _make(session: FakeSession) -> MSmartHomeCloud:
        return MSmartHomeCloud(session, "user@example.com", "fake-password")

    return _make


def status_packet(set_bytes: dict[int, int] | None = None, body_len: int = 53) -> bytes:
    """A device status packet (query response) with `body_len` body bytes.

    `set_bytes` maps a body index to a value; every other body byte is 0.
    The body starts with the 0x09 response body type, as the device sends it.
    """
    body = bytearray(body_len)
    body[0] = 0x09
    for index, value in (set_bytes or {}).items():
        body[index] = value
    return _build_message(MessageType.query, None, body)
