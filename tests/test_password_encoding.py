"""Passwords with non-ASCII characters must not crash login."""
from __future__ import annotations

import pytest

from custom_components.midea_water_softener.cloud import InvalidAuth
from custom_components.midea_water_softener.security import MSmartSecurity

from .conftest import LOGIN, login_ok

PASSWORDS = ["café", "£pound", "päss中文"]


@pytest.mark.parametrize("password", PASSWORDS)
def test_non_ascii_password_hashes_without_error(password):
    security = MSmartSecurity()
    assert len(security.encrypt_password("login-id", password)) == 64
    assert len(security.encrypt_iam_password("login-id", password)) == 64


def test_ascii_password_hash_is_unchanged():
    # Values taken from the code before the change: ASCII passwords hash the same.
    security = MSmartSecurity()
    assert security.encrypt_password("login-id", "fake-password") == (
        "655f93c180f6223c62f73b47226cb88a9d1a1c795684579b06cfc849e2eaf09c"
    )
    assert security.encrypt_iam_password("login-id", "fake-password") == (
        "406e20fc1c425810a403da799ab058da99de2209a0c74bdb2d62552eff68e9c5"
    )


async def test_rejected_non_ascii_login_is_invalid_auth(make_session, make_cloud):
    from custom_components.midea_water_softener.cloud import MSmartHomeCloud

    session = make_session({LOGIN: [{"code": 1, "msg": "invalid password"}]})
    cloud = MSmartHomeCloud(session, "user@example.com", "café")
    with pytest.raises(InvalidAuth):
        await cloud.login()
