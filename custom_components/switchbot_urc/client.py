"""BLE client for the SwitchBot Universal Remote (WoRWS)."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Optional

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak_retry_connector import establish_connection

from .const import CHAR_NOTIFY, CHAR_WRITE
from .crypto import UrcCrypto

_LOGGER = logging.getLogger(__name__)

# Notify callback: (source_char_uuid, raw_bytes, decrypted_plaintext).
# For the encrypted SwitchBot char, plaintext is the AES-CTR decryption; for other chars
# (e.g. the HID report char) plaintext == raw (not encrypted).
NotifyCallback = Callable[[str, bytes, bytes], None]
CredentialRefreshCallback = Callable[[], Awaitable[Optional[tuple[bytes, int]]]]
BridgeControlCallback = Callable[[], Awaitable[bool]]
# (address, key, key_id, steps) -> {"ok", "responses": [hex...], "error", ...} | None
ManagementProxyCallback = Callable[
    [str, bytes, int, list[dict]], Awaitable[Optional[dict]]
]
# 0x00 is the successful per-part acknowledgement used by the IR bank uploader. Normal
# commands still validate their stage-specific accepted codes in send_command_sequence.
_STATUS_RESPONSES = frozenset({0x00, 0x01, 0x02, 0x04, 0x05, 0x10, 0x11})
# Observed decrypted status packets start with 0x3C, 0x4A, 0x4C, 0x4D, 0x4E or 0x4F: the first
# byte is not fixed, so an allowlist of it keeps going stale. Every capture so far is sixteen
# bytes whose second byte is 0x2D or 0x30, which is what is matched instead.
_STATUS_POLL_RESPONSES = frozenset({0x3C, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F})


def is_status_packet(plaintext: bytes) -> bool:
    """Whether a decrypted notify is an unsolicited status record rather than a reply.

    Treating one as a reply shifts every later response in a sequence by one, which is hard to
    spot and easy to misread as the device rejecting a command.
    """
    if len(plaintext) != 16 or plaintext[1] not in (0x2D, 0x30):
        return False
    return plaintext[0] not in _STATUS_RESPONSES


class UrcResponseDecodeError(RuntimeError):
    """A notify arrived, but it did not decrypt as the expected command response."""


class UrcHandshakeTimeout(TimeoutError):
    """The get-random request was written, but no session-random notify arrived."""


class UrcPreflightQueryTimeout(TimeoutError):
    """The secure session exists, but the device-table query did not answer."""


class UrcConnectionSetupError(ConnectionError):
    """BLE connection/service setup failed before an application command was written."""


class UrcPreflightRejected(RuntimeError):
    """A caller-supplied state check rejected a mutation before it was written."""

    def __init__(self, response: bytes) -> None:
        super().__init__("WoRWS management preflight rejected the command")
        self.response = response


class UrcClient:
    """Connect, send framed commands, and surface decrypted notifications + HID reports."""

    def __init__(
        self,
        device: BLEDevice | list[BLEDevice],
        crypto: UrcCrypto,
        credential_refresh_cb: CredentialRefreshCallback | None = None,
        bridge_pause_cb: BridgeControlCallback | None = None,
        bridge_resume_cb: BridgeControlCallback | None = None,
        management_proxy_cb: ManagementProxyCallback | None = None,
    ) -> None:
        devices = list(device) if isinstance(device, list) else [device]
        if not devices:
            raise ValueError("at least one BLE route is required")
        self._devices = devices
        self._device_index = 0
        self._device = devices[0]
        self._route_exclusion_error: str | None = None
        # Adapters/addresses the dedicated fake-hub peripheral owns. Central-mode WoRWS routes
        # must never resolve to these, and a fresh direct scan must never silently fall back to
        # the BlueZ default controller when that default is the excluded bridge adapter.
        self._excluded_adapters: set[str] = set()
        self._excluded_addresses: set[str] = set()
        self._preferred_adapter: str | None = None
        # When set, every management connection is pinned to this controller regardless of the
        # route's own adapter. The WoRWS remote only completes its get-random handshake on the
        # controller it is bound to (the add-on's adapter), which the add-on frees during a pause.
        self._force_preferred_adapter = False
        # True when the last management window needed the add-on to pause its peripheral but the
        # add-on never acknowledged over MQTT. A following handshake timeout is then almost always
        # caused by the remote still being bonded to the fake device, so the UI can say so exactly.
        self._bridge_pause_unacked = False
        self._crypto = crypto
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._command_lock = asyncio.Lock()
        self._notify_cb: NotifyCallback | None = None
        self._handshake_fut: asyncio.Future[bytes] | None = None
        self._response_fut: asyncio.Future[bytes] | None = None
        self._query_fut: asyncio.Future[bytes] | None = None
        self._expected_response_codes: frozenset[int] | None = None
        self._expect_status_reply = False
        self._unexpected_response: tuple[bytes, bytes] | None = None
        self._credential_refresh_cb = credential_refresh_cb
        self._bridge_pause_cb = bridge_pause_cb
        self._bridge_resume_cb = bridge_resume_cb
        # When the add-on can reach the remote on the controller it is bound to, management runs
        # there (it owns that controller) instead of over Home Assistant's own BLE transport.
        self._management_proxy = management_proxy_cb
        # Start every client with the same direct Bleak transport as the hardware-proven
        # standalone bind script. HA's connector remains the alternate fresh-session path.
        self._direct_connect = True

    def exclude_adapter(self, adapter: str, address: str = "") -> None:
        """Remove the fake-hub controller from central-mode WoRWS routes."""
        adapter = adapter.strip().lower()
        compact_address = "".join(
            char for char in address.lower() if char in "0123456789abcdef"
        )
        # Record the bridge identity so the fresh-scan path can pin a safe controller even when
        # a kept route's BLEDevice.details do not expose their /org/bluez/hciX adapter path.
        if adapter:
            self._excluded_adapters.add(adapter)
        if len(compact_address) == 12:
            self._excluded_addresses.add(compact_address)
        self._recompute_preferred_adapter()
        kept: list[BLEDevice] = []
        removed: list[BLEDevice] = []
        for device in self._devices:
            route_adapter = (self._bluez_adapter(device) or "").lower()
            # Match on the adapter name when it resolves; otherwise fall back to the controller
            # address via sysfs. Either signal alone is enough to drop the bridge route.
            matches = bool(adapter and route_adapter == adapter)
            if not matches and len(compact_address) == 12:
                matches = self.bluez_adapter_address(device) == compact_address
            if matches:
                removed.append(device)
            else:
                kept.append(device)
        if not removed:
            return
        if not kept:
            # Every discovered route named the bridge adapter. If another physical controller
            # exists, keep one bridge route as a scan seed but let the fresh direct scan pin the
            # preferred non-bridge controller (details often fail to name a route's adapter, so an
            # empty kept-list can be a false negative). Only block when no alternative exists.
            if self._preferred_adapter is not None:
                self._route_exclusion_error = None
                _LOGGER.warning(
                    "all discovered WoRWS routes named bridge adapter %s; pinning preferred "
                    "controller %s for central-mode management",
                    adapter or compact_address,
                    self._preferred_adapter,
                )
                return
            self._route_exclusion_error = (
                f"only the dedicated bridge adapter {adapter or compact_address} can see WoRWS"
            )
            _LOGGER.error(self._route_exclusion_error)
            return
        self._devices = kept
        self._route_exclusion_error = None
        if self._device in removed:
            self._device_index = 0
            self._device = kept[0]
        else:
            self._device_index = self._devices.index(self._device)
        _LOGGER.warning(
            "removed dedicated bridge adapter %s (%s) from live WoRWS management routes; "
            "remaining=%s",
            adapter or "unknown",
            address or "unknown",
            [self._bluez_adapter(device) for device in self._devices],
        )

    def prefer_adapter(self, adapter: str, address: str = "") -> None:
        """Pin management to the add-on's controller (where the remote is bound).

        This replaces exclusion for the fake-hub topology: the WoRWS remote only answers the
        get-random handshake on the controller it is bound to, so management must run on the
        add-on's adapter while the add-on has paused its peripheral to free that controller.
        """
        adapter = adapter.strip().lower()
        compact_address = "".join(
            char for char in address.lower() if char in "0123456789abcdef"
        )
        if not adapter and len(compact_address) == 12:
            adapter = self._adapter_for_address(compact_address) or ""
        if not adapter:
            return
        # A pinned route is reachable, so clear any earlier exclusion state that would block it.
        self._excluded_adapters.clear()
        self._excluded_addresses.clear()
        self._route_exclusion_error = None
        self._preferred_adapter = adapter
        self._force_preferred_adapter = True
        _LOGGER.warning(
            "pinning WoRWS management to the add-on controller %s (%s); the add-on frees it "
            "during the pause window",
            adapter,
            address or "unknown",
        )

    @classmethod
    def _adapter_for_address(cls, compact_address: str) -> str | None:
        """Resolve a controller address to its ``hciX`` index via sysfs."""
        for name in cls._list_local_adapters():
            if cls._adapter_sysfs_address(name) == compact_address:
                return name
        return None

    @asynccontextmanager
    async def _management_window(self):
        """Temporarily stop the fake hub competing with WoRWS management GATT."""
        paused = False
        if self._bridge_pause_cb is not None:
            try:
                paused = await self._bridge_pause_cb()
            except Exception:  # noqa: BLE001 - BLE management may work without the add-on
                _LOGGER.exception("could not pause the native bridge before BLE management")
            self._bridge_pause_unacked = not paused
            if paused:
                # Allow the remote-side link to fully leave firmware's connection state.
                await asyncio.sleep(0.5)
        else:
            self._bridge_pause_unacked = False
        try:
            yield
        finally:
            if paused and self._bridge_resume_cb is not None:
                try:
                    await self._bridge_resume_cb()
                except Exception:  # noqa: BLE001 - do not hide the management result
                    _LOGGER.exception("could not resume the native bridge after BLE management")

    def set_notify_callback(self, cb: NotifyCallback) -> None:
        self._notify_cb = cb

    def update_credentials(self, key: bytes, key_id: int) -> None:
        """Replace rotating static credentials; the next connection obtains a fresh IV."""
        self._crypto = UrcCrypto(key, key_id)
        self._direct_connect = True

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @staticmethod
    def _bluez_adapter(device: BLEDevice) -> str | None:
        """Extract ``hciX`` from Home Assistant's adapter-specific BLEDevice."""
        details = getattr(device, "details", None)
        if not isinstance(details, dict):
            return None
        props = details.get("props")
        adapter_path = props.get("Adapter") if isinstance(props, dict) else None
        if not adapter_path:
            adapter_path = details.get("adapter") or details.get("Adapter")
        value = str(adapter_path or "")
        adapter = value.rsplit("/", 1)[-1]
        return adapter if adapter.startswith("hci") else None

    @classmethod
    def bluez_adapter_address(cls, device: BLEDevice) -> str | None:
        """Resolve an adapter-specific BLE route to the controller's public address.

        Home Assistant's local BlueZ scanner may expose ``source='hci1'`` instead of the
        controller MAC.  The BLEDevice still carries ``/org/bluez/hci1``; Linux sysfs is the
        authoritative link from that index to the controller address.
        """
        adapter = cls._bluez_adapter(device)
        if adapter is None:
            return None
        return cls._adapter_sysfs_address(adapter)

    @staticmethod
    def _adapter_sysfs_address(adapter: str) -> str | None:
        """Read a controller's public address from sysfs by its ``hciX`` index."""
        try:
            value = Path(f"/sys/class/bluetooth/{adapter}/address").read_text().strip()
        except (OSError, UnicodeError):
            return None
        compact = "".join(char for char in value.lower() if char in "0123456789abcdef")
        return compact if len(compact) == 12 else None

    @staticmethod
    def _list_local_adapters() -> list[str]:
        """List local ``hciX`` controllers in index order via sysfs."""
        try:
            names = [
                entry.name
                for entry in Path("/sys/class/bluetooth").iterdir()
                if entry.name.startswith("hci")
            ]
        except OSError:
            return []
        return sorted(names, key=lambda name: int(name[3:]) if name[3:].isdigit() else 0)

    def _recompute_preferred_adapter(self) -> None:
        """Pick a local controller that is not the dedicated bridge adapter.

        Used only as the fallback when a kept route cannot name its own adapter; the fresh
        direct scan must then target this controller instead of the BlueZ default, which may be
        the excluded bridge adapter.
        """
        for name in self._list_local_adapters():
            if name in self._excluded_adapters:
                continue
            address = self._adapter_sysfs_address(name)
            if address and address in self._excluded_addresses:
                continue
            self._preferred_adapter = name
            return

    def _route_is_safe(self, device: BLEDevice) -> bool:
        """True only when a route provably avoids the dedicated bridge adapter.

        With no exclusions configured every route is safe. Otherwise the route must resolve to a
        known controller that is neither the excluded adapter name nor its address; a route whose
        BLEDevice.details cannot name its adapter is treated as unsafe, because HA's connector
        could still open it through the bridge controller.
        """
        if not self._excluded_adapters and not self._excluded_addresses:
            return True
        adapter = (self._bluez_adapter(device) or "").lower()
        if not adapter or adapter in self._excluded_adapters:
            return False
        address = self._adapter_sysfs_address(adapter)
        return not (address and address in self._excluded_addresses)

    async def _fresh_direct_device(self) -> tuple[BLEDevice, str | None]:
        """Rescan the selected adapter exactly like the proven standalone bind script."""
        adapter = self._bluez_adapter(self._device)
        if self._force_preferred_adapter and self._preferred_adapter:
            # Management is pinned to the add-on's controller regardless of the route's own
            # adapter (the remote only handshakes on the controller it is bound to).
            if adapter != self._preferred_adapter:
                _LOGGER.warning(
                    "pinning WoRWS management scan to the add-on controller %s (route reported %s)",
                    self._preferred_adapter,
                    adapter or "unknown",
                )
            adapter = self._preferred_adapter
        # A kept route whose details do not expose an adapter path would otherwise scan on the
        # BlueZ default controller, which can be the excluded bridge adapter. Pin the preferred
        # non-bridge controller instead so central-mode WoRWS never lands back on the fake hub.
        elif (adapter is None or adapter in self._excluded_adapters) and self._preferred_adapter:
            if adapter in self._excluded_adapters:
                _LOGGER.warning(
                    "selected WoRWS route resolved to excluded bridge adapter %s; pinning %s",
                    adapter,
                    self._preferred_adapter,
                )
            adapter = self._preferred_adapter
        kwargs = {"adapter": adapter} if adapter else {}
        fresh = await BleakScanner.find_device_by_address(
            self._device.address,
            timeout=20.0,
            **kwargs,
        )
        if fresh is None:
            raise UrcConnectionSetupError(
                f"WoRWS was not found in a fresh scan on {adapter or 'the default adapter'}"
            )
        self._device = fresh
        return fresh, adapter

    async def connect(self, *, handshake: bool = True) -> None:
        async with self._lock:
            if self._route_exclusion_error is not None:
                raise UrcConnectionSetupError(self._route_exclusion_error)
            if self._client and self._client.is_connected:
                if handshake and not self._crypto.ready:
                    await self._handshake_session_iv()
                return
            try:
                if self._direct_connect or self._force_preferred_adapter:
                    direct_device, adapter = await self._fresh_direct_device()
                    _LOGGER.info(
                        "connecting to WoRWS with a fresh hardware-proven direct scan "
                        "(adapter=%s): %s",
                        adapter or "default",
                        getattr(direct_device, "details", None),
                    )
                    kwargs = {"adapter": adapter} if adapter else {}
                    self._client = BleakClient(direct_device, **kwargs)
                    await self._client.connect()
                elif not self._route_is_safe(self._device) and self._preferred_adapter:
                    # HA's connector would pick a scanner/adapter from this route, which cannot be
                    # proven to avoid the dedicated bridge controller. Fall back to a pinned direct
                    # scan on the preferred non-bridge adapter instead of risking hci1.
                    direct_device, adapter = await self._fresh_direct_device()
                    _LOGGER.warning(
                        "HA-connector route is not provably off the bridge adapter; using a "
                        "pinned direct scan on %s: %s",
                        adapter or "default",
                        getattr(direct_device, "details", None),
                    )
                    kwargs = {"adapter": adapter} if adapter else {}
                    self._client = BleakClient(direct_device, **kwargs)
                    await self._client.connect()
                else:
                    self._client = await establish_connection(
                        BleakClient, self._device, self._device.address
                    )
                await self._client.start_notify(CHAR_NOTIFY, self._on_encrypted_notify)
                await self._negotiate_mtu()
                # SwitchBot's Android client polls device readiness in 100 ms steps after GATT
                # initialization. Bleak has completed the CCCD write here, but allow one of the
                # same readiness intervals before the first 0F2103 application request.
                await asyncio.sleep(0.1)
            except Exception as err:  # noqa: BLE001 - retried before any command is sent
                failed = "direct Bleak" if self._direct_connect else "HA connector"
                self._direct_connect = not self._direct_connect
                failed_client = self._client
                if failed_client is not None and failed_client.is_connected:
                    try:
                        await failed_client.disconnect()
                    except Exception:  # noqa: BLE001 - preserve the original setup failure
                        pass
                self._client = None
                self._crypto.clear_session_iv()
                _LOGGER.warning(
                    "WoRWS BLE setup failed through %s; next fresh session will use %s: %s",
                    failed,
                    "direct Bleak" if self._direct_connect else "HA connector",
                    err,
                )
                raise UrcConnectionSetupError(
                    f"WoRWS BLE setup failed through {failed}"
                ) from err
            if handshake:
                await self._handshake_session_iv()

    def _advance_ble_route(self) -> None:
        """Use the next adapter-specific BLEDevice after a failed fresh session."""
        if len(self._devices) < 2:
            return
        self._device_index = (self._device_index + 1) % len(self._devices)
        self._device = self._devices[self._device_index]
        _LOGGER.debug(
            "switching WoRWS BLE route to candidate %d/%d (%s)",
            self._device_index + 1,
            len(self._devices),
            getattr(self._device, "details", None),
        )

    def _toggle_connection_transport(self) -> None:
        """Switch transport for the next fresh session without changing protocol bytes."""
        self._direct_connect = not self._direct_connect

    async def _refresh_credentials(self) -> bool:
        """Refresh rotating cloud credentials after both pre-write transports failed."""
        if self._credential_refresh_cb is None:
            return False
        try:
            credentials = await self._credential_refresh_cb()
        except Exception:  # noqa: BLE001 - preserve the original BLE failure
            _LOGGER.exception("automatic WoRWS communication credential refresh failed")
            return False
        if credentials is None:
            return False
        key, key_id = credentials
        self.update_credentials(key, key_id)
        _LOGGER.warning(
            "refreshed WoRWS communication credentials from SwitchBot cloud (key ID %02X)",
            key_id,
        )
        return True

    async def refresh_credentials(self) -> bool:
        """Fetch the current app communication key when cloud access is available.

        The official compatibility layer resolves/caches the user communication key before
        requesting the per-connection random.  Management transactions use this method
        proactively; a cloud failure is non-fatal because the persisted key may still be valid.
        """
        return await self._refresh_credentials()

    async def _negotiate_mtu(self) -> None:
        """Make BlueZ acquire the real ATT MTU before any encrypted command is sent.

        Bleak's BlueZ backend otherwise commonly reports the fallback MTU 23. That splits the
        24-byte target-key frame into 20+4 bytes, while Android requests a large MTU and sends it
        as one WNR packet. `_acquire_mtu` is Bleak's documented BlueZ workaround; keep the
        fallback for other backends and future Bleak versions.
        """
        assert self._client is not None
        backend = getattr(self._client, "_backend", None)
        acquire_mtu = getattr(backend, "_acquire_mtu", None)
        if callable(acquire_mtu):
            try:
                await acquire_mtu()
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("could not acquire larger BLE MTU; using backend default: %s", err)
        char = self._client.services.get_characteristic(CHAR_WRITE)
        reported_size = getattr(char, "max_write_without_response_size", 20) if char else 20
        write_size = self._write_without_response_size(char)
        _LOGGER.info(
            "BLE transport ready: mtu=%s write-without-response-reported=%s effective=%s",
            self._client.mtu_size, reported_size, write_size,
        )

    def _write_without_response_size(self, char=None) -> int:
        """Return the usable ATT write-command payload after MTU negotiation.

        BlueZ/Bleak can transiently keep the characteristic property at its default 20 even when
        the connection already reports MTU 512. Android uses MTU-3 for writeLongData. Prefer the
        larger negotiated transport value so one connection does not fragment the same bind into
        20-byte writes merely because the lazy Bleak property has not refreshed yet.
        """
        assert self._client is not None
        if char is None:
            char = self._client.services.get_characteristic(CHAR_WRITE)
        reported = int(getattr(char, "max_write_without_response_size", 20) or 20)
        mtu = int(getattr(self._client, "mtu_size", 23) or 23)
        mtu_payload = mtu - 3 if mtu > 23 else 20
        return max(20, reported, mtu_payload)

    async def _subscribe_extra_notifies(self) -> None:
        """Subscribe to every other notifiable char (vendor + HID report), tagged by UUID.

        Once the remote is HID-configured against a host it may expose the standard HID service
        (0x1812) with a report char (0x2A4D) that notifies on key press — this is the clean path
        for catching physical buttons in HASS without any OS-level HID stack.
        """
        assert self._client is not None
        for service in self._client.services:
            for ch in service.characteristics:
                if "notify" not in ch.properties:
                    continue
                if ch.uuid.lower() == CHAR_NOTIFY:
                    continue
                try:
                    await self._client.start_notify(ch, self._make_plain_handler(ch.uuid))
                    _LOGGER.debug("subscribed extra notify char %s", ch.uuid)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.debug("cannot subscribe %s: %s", ch.uuid, err)

    def _make_plain_handler(self, uuid: str):
        def _handler(_char, data: bytearray) -> None:
            raw = bytes(data)
            _LOGGER.debug("notify [%s] raw=%s", uuid, raw.hex())
            if self._notify_cb:
                self._notify_cb(uuid, raw, raw)  # not encrypted
        return _handler

    async def disconnect(self) -> None:
        async with self._lock:
            disconnected = False
            if self._client and self._client.is_connected:
                await self._client.disconnect()
                disconnected = True
            self._client = None
            self._crypto.clear_session_iv()
            # The official WoBleManager leaves 500 ms after disconnect. WoRWS otherwise often
            # accepts the next GATT connection but ignores its immediate 0F2103 get-random write,
            # especially when a read-only inventory query is followed by DELETE/recreate.
            if disconnected:
                await asyncio.sleep(0.5)

    async def _handshake_session_iv(self) -> None:
        """Obtain the 16-byte session IV via the get-random handshake.

        Send (unencrypted) 57 00 00 00 0F 21 03 <keyId> with an acknowledged ATT write;
        the official app's short-command path uses Android WRITE_TYPE_DEFAULT (2), not a
        write command. The device replies on the notify characteristic with the random at
        bytes [4:20], which becomes the AES-CTR IV.
        """
        assert self._client is not None
        loop = asyncio.get_running_loop()
        self._handshake_fut = loop.create_future()
        request = self._crypto.get_random_command()
        _LOGGER.debug(
            "WoRWS handshake write=%s mode=with-response transport=%s route=%s",
            request.hex(),
            "direct" if self._direct_connect else "ha-connector",
            getattr(self._device, "details", None),
        )
        try:
            await self._client.write_gatt_char(
                CHAR_WRITE, request, response=True
            )
            try:
                # Match the timeout of the standalone bind script that succeeded on this
                # hardware.  Connection and service discovery can finish before WoRWS's command
                # task is ready to return the random notification.
                resp = await asyncio.wait_for(self._handshake_fut, timeout=35)
            except asyncio.TimeoutError as err:
                failed_direct = self._direct_connect
                self._toggle_connection_transport()
                adapter = self._bluez_adapter(self._device) or "unknown"
                services = getattr(self._client, "services", None)
                get_characteristic = getattr(services, "get_characteristic", None)
                write_char = (
                    get_characteristic(CHAR_WRITE) if callable(get_characteristic) else None
                )
                notify_char = (
                    get_characteristic(CHAR_NOTIFY) if callable(get_characteristic) else None
                )
                _LOGGER.warning(
                    "WoRWS handshake timed out before any management command was sent; "
                    "transport=%s adapter=%s mtu=%s write_properties=%s "
                    "notify_properties=%s; next fresh session will use %s",
                    "direct Bleak" if failed_direct else "HA connector",
                    adapter,
                    getattr(self._client, "mtu_size", "unknown"),
                    getattr(write_char, "properties", None),
                    getattr(notify_char, "properties", None),
                    "direct Bleak" if self._direct_connect else "HA connector",
                )
                raise UrcHandshakeTimeout(
                    "WoRWS get-random handshake timed out"
                ) from err
        finally:
            self._handshake_fut = None
        iv = self._crypto.parse_random_response(resp)
        self._crypto.set_session_iv(iv)
        _LOGGER.debug("session IV established: %s", iv.hex())

    def _on_encrypted_notify(self, _char, data: bytearray) -> None:
        raw = bytes(data)
        # Ignore unrelated notifications during handshake; the random reply is exactly
        # 01 00 00 00 <16-byte IV> (some firmware may append bytes, hence >= 20).
        if self._handshake_fut is not None:
            if not self._handshake_fut.done():
                if len(raw) >= 20 and raw[:4] == bytes([0x01, 0x00, 0x00, 0x00]):
                    self._handshake_fut.set_result(raw)
                else:
                    _LOGGER.debug("ignored non-random notify during handshake: %s", raw.hex())
            return
        # The 0F 63 read commands use the legacy unencrypted response envelope even when the
        # WoRWS command channel itself is encrypted. Consume it before attempting AES-CTR.
        if self._query_fut is not None and not self._query_fut.done():
            if len(raw) >= 8 and raw[:4] == b"\x01\x00\x00\x00":
                self._query_fut.set_result(raw)
                if self._notify_cb:
                    self._notify_cb(CHAR_NOTIFY, raw, raw)
                return
        plaintext = b""
        if self._crypto.ready:
            try:
                plaintext = self._crypto.parse_notification(raw)
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("notify decrypt failed: %s", err)
        _LOGGER.debug("notify [%s] raw=%s plain=%s", CHAR_NOTIFY, raw.hex(), plaintext.hex())
        # Deliver a command response to any waiter.
        if self._response_fut is not None and not self._response_fut.done() and plaintext:
            if (
                self._expected_response_codes is None
                or plaintext[0] in self._expected_response_codes
                or (self._expect_status_reply and is_status_packet(plaintext))
            ):
                self._response_fut.set_result(plaintext)
            elif is_status_packet(plaintext):
                _LOGGER.debug(
                    "ignored unsolicited status notify while waiting for command response: %s",
                    plaintext.hex(),
                )
            else:
                self._unexpected_response = (raw, plaintext)
                _LOGGER.warning(
                    "notify did not decrypt as the expected response; communication key/IV may "
                    "be stale (raw=%s decrypted=%s)", raw.hex(), plaintext.hex()
                )
        if self._notify_cb:
            self._notify_cb(CHAR_NOTIFY, raw, plaintext)

    async def send_plaintext(self, plaintext: bytes) -> None:
        """Encrypt + frame + write a command. The leading 0x57 magic is added by frame_command."""
        if not self._crypto.ready:
            raise RuntimeError("session IV not established; cannot send commands yet")
        await self.connect()
        payload = self._crypto.frame_command(plaintext)
        assert self._client is not None
        if len(payload) <= 20:
            _LOGGER.debug("write %s (response)", payload.hex())
            await self._client.write_gatt_char(CHAR_WRITE, payload, response=True)
            return

        # Prefer Android's WNR path when the negotiated characteristic limit can carry the frame.
        # BlueZ can occasionally keep reporting the fallback 20-byte WNR limit even after MTU
        # acquisition. Do not split a small command such as the 24-byte target-key frame into
        # 20+4: that opcode has no embedded length and the remote may discard both writes. A
        # response=True write lets BlueZ perform one reliable ATT long write (up to 512 bytes).
        char = self._client.services.get_characteristic(CHAR_WRITE)
        chunk_size = self._write_without_response_size(char)
        if len(payload) <= 512 and len(payload) > chunk_size:
            _LOGGER.info(
                "writing %d-byte frame as one ATT write; WNR limit is only %d",
                len(payload), chunk_size,
            )
            await self._client.write_gatt_char(CHAR_WRITE, payload, response=True)
            return

        # Frames larger than one write are split exactly like Android's writeLongData. The remote
        # acknowledges the complete application command separately on CHAR_NOTIFY.
        _LOGGER.debug("write %d-byte frame in %d-byte WNR chunks", len(payload), chunk_size)
        for offset in range(0, len(payload), chunk_size):
            await self._client.write_gatt_char(
                CHAR_WRITE, payload[offset:offset + chunk_size], response=False
            )
            await asyncio.sleep(0.05)

    async def _send_command_locked(self, plaintext: bytes, timeout: float) -> bytes:
        """Send one command while `_command_lock` is held and keep the current BLE session."""
        await self.connect()
        loop = asyncio.get_running_loop()
        self._response_fut = loop.create_future()
        self._unexpected_response = None
        # The status poll is answered with a status record, so for that command alone a
        # status-shaped notify is the reply rather than something to skip.
        self._expect_status_reply = plaintext == bytes([0x02])
        if plaintext == bytes([0x02]):
            self._expected_response_codes = _STATUS_POLL_RESPONSES
        elif plaintext.startswith(bytes([0x0F])):
            self._expected_response_codes = _STATUS_RESPONSES
        else:
            self._expected_response_codes = None
        try:
            await self.send_plaintext(plaintext)
            try:
                return await asyncio.wait_for(self._response_fut, timeout=timeout)
            except asyncio.TimeoutError:
                if self._unexpected_response is not None:
                    raise UrcResponseDecodeError(
                        "received a notification that could not be decoded with the configured "
                        "communication key"
                    )
                return b""
        finally:
            self._response_fut = None
            self._expected_response_codes = None
            self._unexpected_response = None

    @property
    def _use_management_proxy(self) -> bool:
        """Route management through the add-on when it owns the controller the remote is bound to."""
        return self._management_proxy is not None and self._force_preferred_adapter

    async def _run_proxy_steps(self, steps: list[dict]) -> list[bytes]:
        """Execute a management step list on the add-on and return per-step responses."""
        assert self._management_proxy is not None
        result = await self._management_proxy(
            self._device.address, self._crypto.key, self._crypto.key_id, steps
        )
        if result is None:
            raise UrcConnectionSetupError("native bridge did not return a management result")
        if not result.get("ok"):
            stage = str(result.get("failed_stage", ""))
            error = str(result.get("error", "")) or "unknown bridge management error"
            if stage in ("connect", "handshake"):
                # No command reached the device yet, so this is safe to retry (and matches the
                # local handshake-timeout path). Surfaced as a handshake timeout for callers.
                raise UrcHandshakeTimeout(
                    f"native bridge management failed at {stage}: {error}"
                )
            # A failure during a command step may have partially applied a mutation; never retry
            # it blindly (re-running a bind would duplicate pages). Surface a non-retryable error.
            raise UrcConnectionSetupError(
                f"native bridge management failed at {stage or 'command'}: {error}"
            )
        responses = result.get("responses", [])
        self._proxy_strict_accepted_codes = result.get("strict_accepted_codes") is True
        if len(responses) < len(steps):
            raise UrcConnectionSetupError("native bridge returned an incomplete management result")
        return [bytes.fromhex(str(item)) for item in responses]

    async def _run_proxy_steps_with_refresh(self, steps: list[dict]) -> list[bytes]:
        """Run steps via the add-on; on a handshake failure, refresh cloud credentials and retry.

        A handshake failure happens before any command is written, so retrying the whole step list
        with a rotated key/key-id is safe. This gives the proxy path the same automatic WoRWS
        credential rotation the local BLE path already has.
        """
        try:
            responses = await self._run_proxy_steps(steps)
        except UrcHandshakeTimeout:
            if self._credential_refresh_cb is not None and await self._refresh_credentials():
                _LOGGER.warning(
                    "retrying add-on management once with refreshed WoRWS communication key"
                )
                return await self._run_proxy_steps(steps)
            raise
        # A session whose very first command is rejected with 0x04 was unusable: the remote
        # could not decrypt it, so nothing was applied and every later step was skipped. This
        # happens when the handshake produced an IV the remote does not accept, and a fresh
        # connection and handshake clears it. Only the first step qualifies — once any step has
        # been accepted, re-running the list could repeat a change that already took effect.
        if responses and responses[0][:1] == b"\x04":
            _LOGGER.warning(
                "add-on management session rejected its first command with 0x04; retrying once "
                "with a new connection and handshake"
            )
            responses = await self._run_proxy_steps(steps)
        return responses

    async def ensure_strict_sequence_support(self) -> None:
        """Require the add-on to stop on device rejection before a physical layout update."""
        if self._use_management_proxy:
            await self._run_proxy_steps_with_refresh([])
            if not getattr(self, "_proxy_strict_accepted_codes", False):
                raise UrcConnectionSetupError("Update the Bridge add-on to 0.19.32 before editing physical pages")

    async def send_command(self, plaintext: bytes, timeout: float = 20.0) -> bytes:
        """Run one encrypted command, via the add-on proxy when available, else over local BLE."""
        if self._use_management_proxy:
            responses = await self._run_proxy_steps_with_refresh(
                [{"kind": "command", "plaintext": plaintext.hex(), "timeout": timeout}]
            )
            return responses[0]
        async with self._management_window():
            return await self._send_command_in_window(plaintext, timeout)

    async def _send_command_in_window(
        self, plaintext: bytes, timeout: float = 20.0
    ) -> bytes:
        """Run one command, retrying only failures proven safe to repeat.

        A setup/handshake failure happens before the application command is written.  An
        explicit 0x04 response is also safe: firmware rejected the command without applying it.
        A missing command acknowledgement is deliberately returned to the caller and is never
        retried here because the write may already have changed device state.
        """
        async with self._command_lock:
            credentials_refreshed = False
            for attempt in range(3):
                await self.disconnect()
                try:
                    response = await self._send_command_locked(plaintext, timeout)
                    if (
                        response[:1] == b"\x04"
                        and not credentials_refreshed
                        and await self._refresh_credentials()
                    ):
                        credentials_refreshed = True
                        _LOGGER.warning(
                            "WoRWS rejected the command with 0x04; credentials were refreshed "
                            "and the explicitly rejected command will be retried once"
                        )
                        continue
                    return response
                except (UrcConnectionSetupError, UrcHandshakeTimeout):
                    if attempt == 1 and not credentials_refreshed:
                        credentials_refreshed = await self._refresh_credentials()
                        if credentials_refreshed:
                            continue
                    if attempt:
                        raise
                    _LOGGER.warning(
                        "WoRWS session failed before command write; retrying once through %s",
                        "direct Bleak" if self._direct_connect else "HA connector",
                    )
                    self._advance_ble_route()
                finally:
                    await self.disconnect()
            raise RuntimeError("unreachable")

    async def _query_locked(self, subcommand: int, timeout: float) -> bytes:
        """Run one query attempt while the command lock is held."""
        # 0F63 reads and their 01 00 00 00 response envelope are unencrypted. Live captures used
        # an authenticated session first, but the IV is not consumed by either frame. Avoid making
        # read-only inventory depend on 0F2103 when WoRWS resolves GATT yet withholds its random.
        await self.connect(handshake=False)
        return await self._query_on_connected(subcommand, timeout)

    async def _query_on_connected(self, subcommand: int, timeout: float) -> bytes:
        """Run an unencrypted 0F63 query on the already connected BLE session."""
        assert self._client is not None
        self._query_fut = asyncio.get_running_loop().create_future()
        request = bytes([0x57, 0x00, 0x00, 0x00, 0x0F, 0x63, subcommand])
        _LOGGER.debug("WoRWS read-only query without handshake: %s", request.hex())
        try:
            await self._client.write_gatt_char(CHAR_WRITE, request, response=True)
            return await asyncio.wait_for(self._query_fut, timeout=timeout)
        except asyncio.TimeoutError:
            return b""
        finally:
            self._query_fut = None

    async def send_command_with_preflight_query(
        self,
        plaintext: bytes,
        *,
        subcommand: int = 0x07,
        query_timeout: float = 20.0,
        command_timeout: float = 10.0,
        prewrite_retries: int = 3,
        refresh_credentials: bool = True,
        preflight_check: Callable[[bytes], bool] | None = None,
    ) -> tuple[bytes, bytes]:
        """Verify state and run one mutation, via the add-on proxy when available."""
        if self._use_management_proxy:
            # The add-on runs the handshake, the preflight 0F63 query and the mutation in one
            # session on its own controller, then returns both responses.
            before, response = await self._run_proxy_steps_with_refresh(
                [
                    {"kind": "query", "subcmd": subcommand, "timeout": query_timeout},
                    {"kind": "command", "plaintext": plaintext.hex(), "timeout": command_timeout},
                ]
            )
            if not before:
                raise UrcPreflightQueryTimeout("WoRWS preflight query timed out via the add-on")
            if preflight_check is not None and not preflight_check(before):
                raise UrcPreflightRejected(before)
            return before, response
        async with self._management_window():
            return await self._send_command_with_preflight_query_in_window(
                plaintext,
                subcommand=subcommand,
                query_timeout=query_timeout,
                command_timeout=command_timeout,
                prewrite_retries=prewrite_retries,
                refresh_credentials=refresh_credentials,
                preflight_check=preflight_check,
            )

    async def _send_command_with_preflight_query_in_window(
        self,
        plaintext: bytes,
        *,
        subcommand: int = 0x07,
        query_timeout: float = 20.0,
        command_timeout: float = 10.0,
        prewrite_retries: int = 3,
        refresh_credentials: bool = True,
        preflight_check: Callable[[bytes], bool] | None = None,
    ) -> tuple[bytes, bytes]:
        """Read device state and perform one mutation in the same authenticated session.

        The query is deliberately made *after* the get-random handshake.  Previously DELETE
        used one connection for 0F6307, disconnected, and immediately opened another for
        0F2103.  WoRWS can accept that second GATT connection while withholding the random,
        producing the repeatable handshake timeout seen during recreate.

        Only failures before the application command is written are retried.  Once the command
        write starts, a missing acknowledgement is returned to the caller for read-back
        verification; the mutation is never sent blindly a second time.
        """
        if not 0 <= subcommand <= 0xFF:
            raise ValueError("query subcommand must fit in one byte")
        if prewrite_retries < 0:
            raise ValueError("prewrite_retries must be non-negative")

        async with self._command_lock:
            credentials_refreshed = False
            if refresh_credentials and self._credential_refresh_cb is not None:
                credentials_refreshed = await self._refresh_credentials()

            for attempt in range(prewrite_retries + 1):
                await self.disconnect()
                try:
                    # This is the hardware-proven ordering used by the app command path:
                    # subscribe, negotiate MTU, get the random, then exchange commands.
                    await self.connect(handshake=True)
                    before = await self._query_on_connected(subcommand, query_timeout)
                    if not before:
                        raise UrcPreflightQueryTimeout("WoRWS preflight query timed out")
                    if preflight_check is not None and not preflight_check(before):
                        raise UrcPreflightRejected(before)

                    # `_send_command_locked` reuses this connected authenticated session.  Do
                    # not catch command/ACK failures below: after this point the mutation may
                    # have reached firmware and is unsafe to retry.
                    response = await self._send_command_locked(plaintext, command_timeout)
                    if (
                        response[:1] == b"\x04"
                        and not credentials_refreshed
                        and await self._refresh_credentials()
                    ):
                        credentials_refreshed = True
                        _LOGGER.warning(
                            "WoRWS explicitly rejected the management command with 0x04; "
                            "retrying once with refreshed credentials"
                        )
                        continue
                    return before, response
                except (
                    UrcConnectionSetupError,
                    UrcHandshakeTimeout,
                    UrcPreflightQueryTimeout,
                ):
                    if attempt >= prewrite_retries:
                        raise
                    _LOGGER.warning(
                        "WoRWS management preflight failed before command write; retrying in "
                        "a fresh session (%d/%d)",
                        attempt + 1,
                        prewrite_retries,
                    )
                    self._advance_ble_route()
                finally:
                    await self.disconnect()

            raise RuntimeError("unreachable")

    async def query(
        self, subcommand: int, timeout: float = 20.0, timeout_retries: int = 3
    ) -> bytes:
        """Run one read-only 0F63 query, via the add-on proxy when available."""
        if self._use_management_proxy:
            responses = await self._run_proxy_steps_with_refresh(
                [{"kind": "query", "subcmd": subcommand, "timeout": timeout}]
            )
            return responses[0]
        async with self._management_window():
            return await self._query_in_window(subcommand, timeout, timeout_retries)

    async def _query_in_window(
        self, subcommand: int, timeout: float = 20.0, timeout_retries: int = 3
    ) -> bytes:
        """Run an unencrypted 0F 63 read, retrying in fresh authenticated BLE sessions."""
        if not 0 <= subcommand <= 0xFF:
            raise ValueError("query subcommand must fit in one byte")
        if timeout_retries < 0:
            raise ValueError("timeout_retries must be non-negative")
        async with self._command_lock:
            last_error: Exception | None = None
            for attempt in range(timeout_retries + 1):
                attempt_error: Exception | None = None
                await self.disconnect()
                try:
                    response = await self._query_locked(subcommand, timeout)
                    if response:
                        return response
                except Exception as err:  # noqa: BLE001 - fresh sessions recover transient BLE
                    attempt_error = last_error = err
                else:
                    last_error = None
                finally:
                    await self.disconnect()
                if attempt < timeout_retries:
                    detail = type(last_error).__name__ if last_error else "response timeout"
                    _LOGGER.warning(
                        "query 0F63%02X failed (%s); retrying in fresh session (%d/%d)",
                        subcommand,
                        detail,
                        attempt + 1,
                        timeout_retries,
                    )
                    # connect() already switched after setup failure. A response/write timeout
                    # happened later, so switch here before the next otherwise-identical session.
                    if not isinstance(attempt_error, UrcConnectionSetupError):
                        self._toggle_connection_transport()
                    self._advance_ble_route()
            if last_error is not None:
                raise last_error
            return b""

    async def send_command_sequence(
        self,
        plaintexts: list[bytes] | tuple[bytes, ...],
        timeout: float = 20.0,
        retry_first_timeout: bool = False,
        timeout_retries: int = 0,
        accepted_codes: list[frozenset[int]] | tuple[frozenset[int], ...] | None = None,
    ) -> list[bytes]:
        """Run an ordered encrypted transaction, via the add-on proxy when available."""
        if self._use_management_proxy:
            # One management session on the add-on's controller: handshake once, then every page
            # in order. The caller validates each response (bind pages, IR sync acks, etc.).
            return await self._run_proxy_steps_with_refresh(
                [{"kind": "command", "plaintext": p.hex(), "timeout": timeout,
                  **({"accepted_codes": sorted(accepted_codes[index])} if accepted_codes is not None else {})}
                 for index, p in enumerate(plaintexts)]
            )
        async with self._management_window():
            return await self._send_command_sequence_in_window(
                plaintexts,
                timeout=timeout,
                retry_first_timeout=retry_first_timeout,
                timeout_retries=timeout_retries,
                accepted_codes=accepted_codes,
            )

    async def _send_command_sequence_in_window(
        self,
        plaintexts: list[bytes] | tuple[bytes, ...],
        timeout: float = 20.0,
        retry_first_timeout: bool = False,
        timeout_retries: int = 0,
        accepted_codes: list[frozenset[int]] | tuple[frozenset[int], ...] | None = None,
    ) -> list[bytes]:
        """Run an ordered transaction in one fresh session, then release the BLE connection.

        Stops on the first exhausted timeout or non-01 status. Timeout retries always use a new
        connection, handshake and IV. Explicit firmware rejections are never retried.

        `retry_first_timeout` is retained for compatibility and guarantees one retry of only the
        first command. `timeout_retries` applies to every command in the sequence.
        """
        if timeout_retries < 0:
            raise ValueError("timeout_retries must be non-negative")
        if accepted_codes is not None and len(accepted_codes) != len(plaintexts):
            raise ValueError("accepted_codes must have one entry per command")
        results: list[bytes] = []
        async with self._command_lock:
            prewrite_failures = 0
            credentials_refreshed = False
            await self.disconnect()
            try:
                for index, plaintext in enumerate(plaintexts):
                    retries = timeout_retries
                    if index == 0 and retry_first_timeout:
                        retries = max(retries, 1)
                    attempt = 0
                    try:
                        resp = await self._send_command_locked(plaintext, timeout)
                    except (UrcConnectionSetupError, UrcHandshakeTimeout):
                        timeout_stage = "handshake"
                        prewrite_failures += 1
                        resp = b""
                    except (asyncio.TimeoutError, TimeoutError):
                        timeout_stage = "command"
                        # A missing session-IV response is the same transient timeout class as a
                        # missing command acknowledgement. Previously it escaped before the retry
                        # loop, so `timeout_retries=3` never applied to handshake failures.
                        resp = b""
                    else:
                        timeout_stage = "command"
                    if (
                        resp[:1] == b"\x04"
                        and not credentials_refreshed
                        and await self._refresh_credentials()
                    ):
                        credentials_refreshed = True
                        _LOGGER.warning(
                            "transaction command %d was explicitly rejected with 0x04; "
                            "retrying it once with refreshed credentials",
                            index + 1,
                        )
                        await self.disconnect()
                        try:
                            resp = await self._send_command_locked(plaintext, timeout)
                        except (UrcConnectionSetupError, UrcHandshakeTimeout):
                            timeout_stage = "handshake"
                            prewrite_failures += 1
                            resp = b""
                        except (asyncio.TimeoutError, TimeoutError):
                            timeout_stage = "command"
                            resp = b""
                        else:
                            timeout_stage = "command"
                    while not resp and attempt < retries:
                        attempt += 1
                        if (
                            timeout_stage == "handshake"
                            and prewrite_failures >= 2
                            and not credentials_refreshed
                        ):
                            credentials_refreshed = await self._refresh_credentials()
                        _LOGGER.warning(
                            "transaction %s timed out before command %d completed; "
                            "retrying in fresh session (%d/%d)",
                            timeout_stage,
                            index + 1,
                            attempt,
                            retries,
                        )
                        await self.disconnect()
                        if timeout_stage == "command":
                            self._toggle_connection_transport()
                        self._advance_ble_route()
                        try:
                            resp = await self._send_command_locked(plaintext, timeout)
                        except (UrcConnectionSetupError, UrcHandshakeTimeout):
                            timeout_stage = "handshake"
                            prewrite_failures += 1
                            resp = b""
                        except (asyncio.TimeoutError, TimeoutError):
                            timeout_stage = "command"
                            resp = b""
                        else:
                            timeout_stage = "command"
                    results.append(resp)
                    success = (
                        accepted_codes[index]
                        if accepted_codes is not None
                        else frozenset({0x01})
                    )
                    if not resp or resp[0] not in success:
                        break
                return results
            finally:
                await self.disconnect()
