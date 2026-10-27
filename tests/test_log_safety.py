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


async def test_unparseable_status_log_uses_the_device_name(
    make_session, make_cloud, caplog
):
    from custom_components.midea_water_softener.device import WaterSoftenerDevice

    from .conftest import send_reply

    cloud = make_cloud(make_session({SEND: [send_reply(b"\x01\x02")]}))
    await cloud.login()
    device = WaterSoftenerDevice(cloud, 987654, "Test softener")

    with caplog.at_level(logging.WARNING):
        assert await device.refresh_status() is None

    line = next(r.getMessage() for r in caplog.records if "parse" in r.getMessage())
    assert line.startswith("[Test softener]")
