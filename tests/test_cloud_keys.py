"""cloud.get_keys: fetch the local token and key the way midea-local does."""
from __future__ import annotations

import aiohttp
import pytest

from custom_components.midea_water_softener.cloud import CannotConnect

from .test_config_flow_local import (
    DEVICE,
    GET_TOKEN,
    KEY_1,
    KEY_2,
    NO_TOKENS,
    TOKEN_1,
    TOKEN_2,
    TOKEN_ERROR,
    token_reply,
)


async def _cloud(make_session, make_cloud, replies):
    session = make_session({GET_TOKEN: replies})
    cloud = make_cloud(session)
    await cloud.login()
    return cloud, session


async def test_returns_the_pair_for_each_udpid_method(make_session, make_cloud):
    cloud, session = await _cloud(
        make_session,
        make_cloud,
        [token_reply(1, TOKEN_1, KEY_1), token_reply(2, TOKEN_2, KEY_2)],
    )
    keys = await cloud.get_keys(DEVICE)
    assert keys == [
        {"token": TOKEN_1, "key": KEY_1},
        {"token": TOKEN_2, "key": KEY_2},
    ]
    assert session.count(GET_TOKEN) == 2


async def test_a_pair_for_another_udpid_is_ignored(make_session, make_cloud):
    # Method 2's reply carries method 1's udpid, so it does not match.
    cloud, _ = await _cloud(
        make_session,
        make_cloud,
        [NO_TOKENS, token_reply(1, TOKEN_1, KEY_1)],
    )
    assert await cloud.get_keys(DEVICE) == []


async def test_an_api_error_returns_no_keys(make_session, make_cloud):
    cloud, _ = await _cloud(make_session, make_cloud, [TOKEN_ERROR, TOKEN_ERROR])
    assert await cloud.get_keys(DEVICE) == []


async def test_cloud_down_raises_cannot_connect(make_session, make_cloud):
    cloud, _ = await _cloud(
        make_session, make_cloud, [aiohttp.ClientConnectionError("down")]
    )
    with pytest.raises(CannotConnect):
        await cloud.get_keys(DEVICE)
