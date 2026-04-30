"""
MSmartHome cloud client.
Authentication and request pattern mirrors midea_auto_cloud (sususweet/midea_auto_cloud, Apache-2.0).
"""
from __future__ import annotations

import base64
import datetime
import json
import logging
import time
from secrets import token_hex

import aiohttp

from .security import MSmartSecurity

_LOGGER = logging.getLogger(__name__)

_DEFAULT_API_URL = "https://mp-prod.appsmb.com/mas/v5/app/proxy?alias="


def _bytes_to_dec_string(data: bytes | bytearray) -> bytearray:
    """Convert raw bytes to the comma-separated signed-decimal string the cloud API expects."""
    parts = []
    for b in data:
        signed = b if b < 128 else b - 256
        parts.append(str(signed))
    return bytearray(",".join(parts), "utf-8")


def _dec_string_to_bytes(s: str) -> bytearray:
    result = bytearray()
    for part in s.split(","):
        try:
            result.append(int(part.strip()) & 0xFF)
        except ValueError:
            result.append(0)
    return result


class MSmartHomeCloud:
    APP_ID = "1010"
    APP_VERSION = "3.0.2"
    SRC = "10"

    def __init__(
        self,
        session: aiohttp.ClientSession,
        account: str,
        password: str,
        api_url: str = _DEFAULT_API_URL,
    ) -> None:
        self._session = session
        self._account = account
        self._password = password
        self._api_url = api_url
        self._security = MSmartSecurity()
        self._device_id = MSmartSecurity.get_device_id(account)
        self._uid: str = ""
        self._access_token: str | None = None
        self._auth_base = base64.b64encode(
            f"{MSmartSecurity.APP_KEY}:{self._security._iot_key}".encode("ascii")
        ).decode("ascii")

    @property
    def is_logged_in(self) -> bool:
        """True if both session AES key/IV and the access token are set."""
        return (
            self._security._aes_key is not None
            and self._security._aes_iv is not None
            and self._access_token is not None
        )

    # ------------------------------------------------------------------
    # Request helpers
    # ------------------------------------------------------------------

    def _make_general_data(self) -> dict:
        return {
            "appVersion": self.APP_VERSION,
            "src": self.SRC,
            "format": "2",
            "stamp": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
            "platformId": "1",
            "deviceId": self._device_id,
            "reqId": token_hex(16),
            "uid": self._uid,
            "clientType": "1",
            "appId": self.APP_ID,
        }

    async def _request(self, endpoint: str, data: dict) -> dict | None:
        if not data.get("reqId"):
            data["reqId"] = token_hex(16)
        if not data.get("stamp"):
            data["stamp"] = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

        random = str(int(time.time()))  # seconds, not milliseconds
        payload = json.dumps(data)
        sign = self._security.sign(payload, random)

        headers: dict = {
            "content-type": "application/json; charset=utf-8",
            "secretVersion": "1",
            "sign": sign,
            "random": random,
            "x-recipe-app": self.APP_ID,
            "authorization": f"Basic {self._auth_base}",
        }
        if self._uid:
            headers["uid"] = self._uid
        if self._access_token:
            headers["accesstoken"] = self._access_token

        url = self._api_url + endpoint
        try:
            async with self._session.post(
                url, data=payload, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                raw = await resp.read()
                body = json.loads(raw)
        except Exception as exc:
            _LOGGER.debug("Request to %s failed: %s", endpoint, exc)
            return None

        try:
            code = int(body.get("code", -1))
        except (TypeError, ValueError):
            code = -1

        if code == 0:
            if "/transparent/send" in endpoint:
                _LOGGER.debug("transparent/send success, data=%s", body.get("data"))
            return body.get("data")

        if "/transparent/send" in endpoint:
            _LOGGER.warning("transparent/send error: code=%s full_response=%s", body.get("code"), body)
        else:
            _LOGGER.debug("API error from %s: code=%s msg=%s", endpoint, body.get("code"), body.get("msg"))
        return None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def _re_route(self) -> None:
        """Resolve the account's home server URL before login."""
        data = self._make_general_data()
        data.update({
            "userName": self._account,
            "platformId": "1",
            "userType": "0",
        })
        resp = await self._request("/v1/unitcenter/router/user/name", data)
        if resp and resp.get("masUrl"):
            self._api_url = resp["masUrl"]
            _LOGGER.debug("Re-routed to %s", self._api_url)

    async def _get_login_id(self) -> str | None:
        data = self._make_general_data()
        data.update({
            "loginAccount": self._account,
            "type": "1",
        })
        resp = await self._request("/v1/user/login/id/get", data)
        if resp:
            return resp.get("loginId")
        return None

    async def login(self) -> bool:
        """Authenticate with the MSmartHome cloud. Returns True on success."""
        await self._re_route()

        login_id = await self._get_login_id()
        if not login_id:
            _LOGGER.error("Failed to obtain MSmartHome login ID")
            return False

        stamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        iot_data = self._make_general_data()
        iot_data.pop("uid", None)
        iot_data.update({
            "iampwd": self._security.encrypt_iam_password(login_id, self._password),
            "loginAccount": self._account,
            "password": self._security.encrypt_password(login_id, self._password),
            "stamp": stamp,
        })
        payload = {
            "iotData": iot_data,
            "data": {
                "appKey": MSmartSecurity.APP_KEY,
                "deviceId": self._device_id,
                "platform": "2",
            },
            "stamp": stamp,
        }
        resp = await self._request("/mj/user/login", payload)
        if not resp:
            _LOGGER.error("MSmartHome login request failed")
            return False

        self._uid = resp.get("uid", "")
        mdata = resp.get("mdata") or {}
        self._access_token = mdata.get("accessToken")
        if not self._access_token:
            _LOGGER.error("No accessToken in login response: %s", resp)
            return False

        # 'accessToken' and 'randomData' are both CBC-encrypted with SHA256(APP_KEY).
        # Decrypted ASCII strings become the session key and IV for device command encryption.
        encrypted_key = resp.get("accessToken")
        encrypted_iv = resp.get("randomData")
        if encrypted_key and encrypted_iv:
            try:
                self._security.set_aes_keys(encrypted_key, encrypted_iv)
                _LOGGER.debug("Session AES keys set successfully")
            except Exception as exc:
                _LOGGER.warning("Could not set session AES keys: %s", exc)
        else:
            _LOGGER.warning(
                "Login response missing 'accessToken' or 'randomData' — transparent send will fail. Keys present: %s",
                list(resp.keys()),
            )

        _LOGGER.debug("MSmartHome login successful, uid=%s", self._uid)
        return True

    # ------------------------------------------------------------------
    # Device discovery
    # ------------------------------------------------------------------

    async def list_appliances(self) -> list[dict]:
        """Return all appliances registered to the account."""
        data = self._make_general_data()
        resp = await self._request("/v1/appliance/user/list/get", data)
        if not resp:
            return []

        appliances = []
        for item in resp.get("list") or []:
            try:
                appliances.append({
                    "device_id": int(item["id"]),  # field is "id", not "applianceCode"
                    "name": item.get("name", "Water Softener"),
                    "type": int(item.get("type", "0"), 16),
                    "model": item.get("productModel", ""),
                    "online": item.get("onlineStatus") == "1",
                    "sn": item.get("sn", ""),
                })
            except (KeyError, ValueError):
                continue
        return appliances

    # ------------------------------------------------------------------
    # Device communication
    # ------------------------------------------------------------------

    async def send_command(self, device_id: int, message: bytes) -> bytearray | None:
        """
        Send a raw protocol message via the transparent-send endpoint.
        Returns decoded response bytes, or None on failure.
        """
        dec_str = _bytes_to_dec_string(message)
        try:
            encrypted_order = self._security.aes_encrypt(dec_str).hex()
        except RuntimeError as exc:
            _LOGGER.error("Cannot send command: %s", exc)
            return None

        # Use only the 17 fields accepted by transparent/send — do NOT use _make_general_data()
        # as it includes appVersion and platformId which the endpoint rejects (code 9999).
        data = {
            "appId": self.APP_ID,
            "applianceCode": str(device_id),
            "clientType": "1",
            "deviceId": self._device_id,
            "format": "2",
            "isFull": "false",
            "order": encrypted_order,
            "reqId": token_hex(16),
            "src": self.SRC,
            "stamp": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
            "timestamp": "true",
            "uid": self._uid,
        }
        resp = await self._request("/v1/appliance/transparent/send", data)
        if not resp:
            return None

        reply_hex = resp.get("reply")
        if not reply_hex:
            _LOGGER.warning("transparent/send: no reply field for device %s (resp=%s)", device_id, resp)
            return None

        try:
            dec_reply = self._security.aes_decrypt(reply_hex)
            return _dec_string_to_bytes(dec_reply)
        except Exception as exc:
            _LOGGER.warning("Failed to decode reply from device %s: %s", device_id, exc)
            return None
