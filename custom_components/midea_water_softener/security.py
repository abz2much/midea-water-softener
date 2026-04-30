"""
Cryptographic helpers for the MSmartHome cloud API.
Constants sourced from the open-source midea_ac_lan / midea_auto_cloud projects (MIT/Apache-2.0).
"""
from __future__ import annotations

import hmac
from hashlib import md5, sha256

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


class MSmartSecurity:
    # Public app credentials for the MSmartHome (com.midea.msmarthome) app
    APP_ID = "1010"
    APP_KEY = "ac21b9f9cbfe4ca5a88562ef25e2b768"

    # Signing keys derived from integer-encoded constants in midea_ac_lan
    _iot_key: str = bytes.fromhex(format(7882822598523843940, "x")).decode()
    _hmac_key: str = bytes.fromhex(
        format(117390035944627627450677220413733956185864939010425, "x")
    ).decode()
    _login_key: str = APP_KEY  # used as salt in encrypt_password and for key derivation

    # Fixed AES key/IV — used only for Lua file decryption (aes_decrypt_with_fixed_key).
    _fixed_key: bytes = (13101328926877700970).to_bytes(8, "big") * 2
    _fixed_iv: bytes = (16429062708050928556).to_bytes(8, "big") * 2

    def __init__(self) -> None:
        self._aes_key: bytes | None = None
        self._aes_iv: bytes | None = None

    # ------------------------------------------------------------------
    # Password / login helpers
    # ------------------------------------------------------------------

    @staticmethod
    def get_device_id(username: str) -> str:
        return sha256(username.encode("utf-8")).hexdigest()[:16]

    def sign(self, data: str, random: str) -> str:
        msg = self._iot_key + data + random
        return hmac.new(
            self._hmac_key.encode("ascii"), msg.encode("ascii"), sha256
        ).hexdigest()

    def encrypt_password(self, login_id: str, password: str) -> str:
        m = sha256()
        m.update(password.encode("ascii"))
        login_hash = login_id + m.hexdigest() + self._login_key
        m2 = sha256()
        m2.update(login_hash.encode("ascii"))
        return m2.hexdigest()

    def encrypt_iam_password(self, login_id: str, password: str) -> str:
        m = md5()
        m.update(password.encode("ascii"))
        m2 = md5()
        m2.update(m.hexdigest().encode("ascii"))
        login_hash = login_id + m2.hexdigest() + self._login_key
        s = sha256()
        s.update(login_hash.encode("ascii"))
        return s.hexdigest()

    # ------------------------------------------------------------------
    # Session key setup (called after login)
    # ------------------------------------------------------------------

    def set_aes_keys(self, encrypted_key: str, encrypted_iv: str) -> None:
        """
        Derive the session AES key and IV from the login response fields.
        'accessToken' (encrypted_key) and 'randomData' (encrypted_iv) are each
        AES-CBC encrypted with a temp key/IV derived from SHA256(APP_KEY).
        The decrypted ASCII strings become the key and IV for device command encryption.
        """
        key_digest = sha256(self._login_key.encode("ascii")).hexdigest()
        tmp_key = key_digest[:16].encode("ascii")
        tmp_iv = key_digest[16:32].encode("ascii")
        self._aes_key = self.aes_decrypt(encrypted_key, tmp_key, tmp_iv).encode("ascii")
        self._aes_iv = self.aes_decrypt(encrypted_iv, tmp_key, tmp_iv).encode("ascii")

    # ------------------------------------------------------------------
    # AES helpers
    # ------------------------------------------------------------------

    def aes_encrypt(self, data: bytes | bytearray | str, key: bytes | None = None, iv: bytes | None = None) -> bytes:
        k = key if key is not None else self._aes_key
        i = iv if iv is not None else self._aes_iv
        if k is None:
            raise RuntimeError("Not logged in — session AES key not set")
        if isinstance(data, str):
            data = data.encode("utf-8")
        if i is None:
            return AES.new(k, AES.MODE_ECB).encrypt(pad(bytes(data), 16))
        return AES.new(k, AES.MODE_CBC, iv=i).encrypt(pad(bytes(data), 16))

    def aes_decrypt(self, data: bytes | str, key: bytes | None = None, iv: bytes | None = None) -> str:
        k = key if key is not None else self._aes_key
        i = iv if iv is not None else self._aes_iv
        if k is None:
            raise RuntimeError("Not logged in — session AES key not set")
        if isinstance(data, str):
            data = bytes.fromhex(data)
        if i is None:
            return unpad(AES.new(k, AES.MODE_ECB).decrypt(data), 16).decode("utf-8")
        return unpad(AES.new(k, AES.MODE_CBC, iv=i).decrypt(data), 16).decode("utf-8")

    def aes_encrypt_with_fixed_key(self, data: bytes | str) -> bytes:
        """Fixed-key encrypt used for Lua download requests."""
        if isinstance(data, str):
            data = data.encode("ascii")
        return AES.new(self._fixed_key, AES.MODE_CBC, iv=self._fixed_iv).encrypt(pad(data, 16))

    def aes_decrypt_with_fixed_key(self, hex_data: str) -> str:
        """Fixed-key decrypt used for Lua file content."""
        raw = bytes.fromhex(hex_data)
        return unpad(
            AES.new(self._fixed_key, AES.MODE_CBC, iv=self._fixed_iv).decrypt(raw), 16
        ).decode("utf-8")
