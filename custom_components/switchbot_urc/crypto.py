"""AES-CTR crypto + command framing for the SwitchBot Universal Remote (WoRWS).

Verified facts (from the app's native DeviceCTRCipher hook + HTTP key API):
- Cipher: AES-128 / CTR / NoPadding, 16-byte key (per device, cloud-provisioned).
- Outgoing BLE command (write -> cba20002):  57 <keyId> <iv[0:2]> <AES-CTR(plaintext)>
- Both encrypt and decrypt use the SAME 16-byte session IV.

The app obtains the 16-byte IV at connect time through the unencrypted get-random handshake:
`57 00 00 00 0F 21 03 <keyId>`; response bytes 4..19 are the AES-CTR session IV.
"""
from __future__ import annotations

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from .const import CMD_MAGIC


def _aes_ctr(key: bytes, iv: bytes, data: bytes) -> bytes:
    """AES-128-CTR is symmetric: same call encrypts and decrypts."""
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv))
    enc = cipher.encryptor()
    return enc.update(data) + enc.finalize()


class UrcCrypto:
    """Holds the static device key + the per-session IV and frames commands."""

    def __init__(self, key: bytes, key_id: int) -> None:
        if len(key) != 16:
            raise ValueError("key must be 16 bytes")
        if not 0 <= key_id <= 0xFF:
            raise ValueError("key id must fit in one byte")
        self._key = key
        self._key_id = key_id
        self._iv: bytes | None = None

    @property
    def ready(self) -> bool:
        return self._iv is not None

    @property
    def key(self) -> bytes:
        return self._key

    @property
    def key_id(self) -> int:
        return self._key_id

    def clear_session_iv(self) -> None:
        """Invalidate session state when the BLE link is closed."""
        self._iv = None

    def set_session_iv(self, iv: bytes) -> None:
        if len(iv) != 16:
            raise ValueError("iv must be 16 bytes")
        self._iv = iv

    def encrypt(self, plaintext: bytes) -> bytes:
        assert self._iv is not None, "session IV not set"
        return _aes_ctr(self._key, self._iv, plaintext)

    def decrypt(self, ciphertext: bytes) -> bytes:
        assert self._iv is not None, "session IV not set"
        return _aes_ctr(self._key, self._iv, ciphertext)

    def get_random_command(self) -> bytes:
        """Unencrypted handshake that asks the device for the 16-byte session random (IV).

        Verified from DeviceRandomGetter: 57 00 00 00 0F 21 03 <keyId>. The device replies on
        the notify characteristic; the random is response bytes [4:20] (16 bytes).
        """
        return bytes([CMD_MAGIC, 0x00, 0x00, 0x00, 0x0F, 0x21, 0x03, self._key_id])

    @staticmethod
    def parse_random_response(resp: bytes) -> bytes:
        """Extract the 16-byte random/IV from the get-random reply (bytes [4:20])."""
        if len(resp) < 20:
            raise ValueError(f"random reply too short: {resp.hex()}")
        return resp[4:20]

    def frame_command(self, plaintext: bytes) -> bytes:
        """Build the full BLE write payload: 57 <keyId> <iv[0:2]> <ciphertext>."""
        assert self._iv is not None, "session IV not set"
        ct = self.encrypt(plaintext)
        return bytes([CMD_MAGIC, self._key_id, self._iv[0], self._iv[1]]) + ct

    def parse_notification(self, data: bytes) -> bytes:
        """Decrypt an incoming notify payload.

        Confirmed frame: <01|57> <keyId> <nonce0> <nonce1> <ciphertext...>.
        Strip the 4-byte header, decrypt the rest with the session IV. A rejected long command
        can return only the four-byte header, with the response code in byte 0 and no encrypted
        body (observed `02 <keyId> <iv0> <iv1>` after native 62 06).
        """
        if len(data) >= 4 and data[1] == self._key_id:
            if len(data) == 4:
                return data[:1]
            return self.decrypt(data[4:])
        return self.decrypt(data)
