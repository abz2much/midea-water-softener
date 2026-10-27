"""A failed transparent/send logs the error code and message, not the body."""
from __future__ import annotations

import logging

from .conftest import SEND


async def test_failed_send_logs_only_code_and_message(make_session, make_cloud, caplog):
    body = {
        "code": 9999,
        "msg": "bad request",
        "data": {"accessToken": "sample-secret-token", "uid": "sample-uid"},
    }
    cloud = make_cloud(make_session({SEND: [body]}))
    await cloud.login()

    with caplog.at_level(logging.DEBUG):
        assert await cloud.send_command(123456, b"\x01") is None

    assert "9999" in caplog.text
    assert "bad request" in caplog.text
    assert "sample-secret-token" not in caplog.text
    assert "sample-uid" not in caplog.text
