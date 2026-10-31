"""SwitchBot Universal Remote (WoRWS) — local BLE integration (no hub, no cloud)."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import logging
import uuid

import voluptuous as vol

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.script import Script, async_validate_actions_config
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import commands
from .bindings import (
    ACTION_BRIGHTER,
    ACTION_COOLER,
    ACTION_DARKER,
    ACTION_TOGGLE,
    ACTION_TURN_OFF,
    ACTION_TURN_ON,
    ACTION_WARMER,
    RGB_ACTIONS,
    event_matches_remote_address,
    resolve_button_action_sequence,
    resolve_binding_action,
)
from .client import UrcClient, UrcResponseDecodeError
from .cloud import SwitchBotCloudClient, parse_communication_credentials
from .const import (
    CHAR_NOTIFY,
    CONF_ADDRESS,
    CONF_KEY,
    CONF_KEY_ID,
    DOMAIN,
    EVENT_BUTTON,
    EVENT_NATIVE_BIND,
    EVENT_NOTIFY,
    MQTT_BUTTON_TOPIC,
    MQTT_BRIDGE_CONTROL_TOPIC,
    MQTT_BRIDGE_INFO_TOPIC,
    MQTT_BRIDGE_MANAGE_RESULT_TOPIC,
    MQTT_BRIDGE_MANAGE_TOPIC,
    MQTT_BRIDGE_STATUS_TOPIC,
    PLATFORMS,
    RESP_OK,
)
from .crypto import UrcCrypto
from .hid import decode_report, is_press
from .studio import async_register_studio

_LOGGER = logging.getLogger(__name__)

SERVICE_SEND_COMMAND = "send_command"
SERVICE_CREATE_REMOTE = "create_remote"
SERVICE_DELETE_REMOTE = "delete_remote"
SERVICE_HID_PAIR = "hid_pair"
SERVICE_BIND_NATIVE = "bind_native"
SERVICE_SET_STATE_AC = "set_state_ac"
SERVICE_POLL_STATUS = "poll_status"
SERVICE_DUMP_DEVICE_TABLE = "dump_device_table"
SERVICE_SEND_COMMAND_SEQUENCE = "send_command_sequence"

_ADDR = vol.Optional("address")

SEND_COMMAND_SCHEMA = vol.Schema({_ADDR: cv.string, vol.Required("plaintext"): cv.string})
CREATE_REMOTE_SCHEMA = vol.Schema(
    {
        _ADDR: cv.string,
        vol.Required("remote_index"): vol.All(int, vol.Range(min=0, max=254)),
        vol.Required("name"): cv.string,
        vol.Required("device_id"): cv.string,  # 12 hex chars (target/exec id)
        vol.Optional("device_type", default="UNIVERSAL_BLE"): cv.string,
        vol.Optional("icon", default="light"): cv.string,
        vol.Optional("control_mode", default=0): int,
    }
)
DELETE_REMOTE_SCHEMA = vol.Schema(
    {
        _ADDR: cv.string,
        vol.Required("remote_index"): vol.All(int, vol.Range(min=0, max=254)),
        vol.Required("device_id"): cv.string,
        vol.Optional("device_type", default="UNIVERSAL_BLE"): cv.string,
    }
)
HID_PAIR_SCHEMA = vol.Schema({_ADDR: cv.string, vol.Required("host_mac"): cv.string})
BIND_NATIVE_SCHEMA = vol.Schema(
    {
        _ADDR: cv.string,
        # Kept as an optional compatibility hint; the firmware requires the sequential
        # bindDevices.length index, which is discovered from 0F 63 07 at runtime.
        vol.Optional("remote_index"): vol.All(int, vol.Range(min=0, max=254)),
        vol.Required("name"): cv.string,
        vol.Required("device_id"): cv.string,
        vol.Optional("device_type", default="STRIP"): cv.string,
        vol.Optional("icon", default="strip"): cv.string,
        vol.Optional("control_mode", default=0): int,
        vol.Optional("target_key_id", default="01"): cv.string,
        vol.Required("target_key"): cv.string,
        vol.Optional("replace_existing", default=False): cv.boolean,
    }
)
SET_STATE_AC_SCHEMA = vol.Schema(
    {
        _ADDR: cv.string,
        vol.Required("temp"): int,
        vol.Required("mode"): int,
        vol.Required("fan"): int,
        vol.Optional("power_on", default=True): cv.boolean,
    }
)
POLL_STATUS_SCHEMA = vol.Schema({_ADDR: cv.string})
DUMP_DEVICE_TABLE_SCHEMA = vol.Schema({_ADDR: cv.string})
SEND_COMMAND_SEQUENCE_SCHEMA = vol.Schema(
    {_ADDR: cv.string, vol.Required("plaintexts"): vol.All(cv.ensure_list, [cv.string])}
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from a config entry."""
    address: str = entry.data[CONF_ADDRESS]
    key = bytes.fromhex(entry.data[CONF_KEY])
    key_id = int(entry.data[CONF_KEY_ID], 16)

    scanner_devices = bluetooth.async_scanner_devices_by_address(
        hass, address.upper(), connectable=True
    )
    native_target = entry.data.get("native_target", {})
    bridge_address = (
        str(native_target.get("device_id", ""))
        if isinstance(native_target, dict)
        else ""
    )
    if not bridge_address:
        bridge_address = str(entry.options.get("native_device_id", ""))
    if not bridge_address:
        bridge_address = next(
            (
                str(remote.get("physical_device_id", ""))
                for remote in entry.options.get("remotes", [])
                if remote.get("physical_device_id")
            ),
            "",
        )
    compact_bridge = "".join(
        char for char in bridge_address.lower() if char in "0123456789abcdef"
    )
    if compact_bridge:
        usable_scanners = []
        for candidate in scanner_devices:
            source = str(getattr(candidate.scanner, "source", ""))
            scanner_name = str(getattr(candidate.scanner, "name", ""))
            scanner_identity = f"{source} {scanner_name}"
            compact_identity = "".join(
                char for char in scanner_identity.lower()
                if char in "0123456789abcdef"
            )
            adapter_address = await hass.async_add_executor_job(
                UrcClient.bluez_adapter_address, candidate.ble_device
            )
            if compact_bridge in compact_identity or adapter_address == compact_bridge:
                _LOGGER.warning(
                    "excluding dedicated bridge adapter %s (%s, address=%s) from WoRWS "
                    "central routes",
                    source,
                    scanner_name,
                    adapter_address or "unresolved",
                )
                continue
            usable_scanners.append(candidate)
        scanner_devices = usable_scanners
    ble_devices = [candidate.ble_device for candidate in scanner_devices]
    # An unqualified fallback can resolve right back to the dedicated peripheral
    # adapter that was excluded above.  With a configured native target it is
    # safer to wait for a route reported by another scanner than to deadlock the
    # fake hub's adapter in central mode.
    if not ble_devices and not compact_bridge and (
        fallback := bluetooth.async_ble_device_from_address(
            hass, address.upper(), connectable=True
        )
    ) is not None:
        ble_devices = [fallback]
    if not ble_devices:
        raise ConfigEntryNotReady(f"SwitchBot URC {address} not found via Bluetooth")

    routes = []
    for candidate in scanner_devices:
        scanner = candidate.scanner
        routes.append(
            {
                "source": getattr(scanner, "source", None),
                "name": getattr(scanner, "name", None),
                "details": getattr(candidate.ble_device, "details", None),
            }
        )
    _LOGGER.warning("WoRWS BLE connection routes: %s", routes or ["default route"])

    async def _refresh_communication_credentials() -> tuple[bytes, int] | None:
        settings = entry.data.get("cloud")
        if not isinstance(settings, dict):
            _LOGGER.warning(
                "WoRWS handshake failed on both transports, but cloud credentials are not "
                "configured; open SwitchBot cloud account in the integration options"
            )
            return None

        async def _save_tokens(access_token: str, refresh_token: str) -> None:
            data = dict(entry.data)
            cloud_settings = dict(data.get("cloud", {}))
            cloud_settings["access_token"] = access_token
            cloud_settings["refresh_token"] = refresh_token
            data["cloud"] = cloud_settings
            hass.config_entries.async_update_entry(entry, data=data)

        cloud = SwitchBotCloudClient(
            async_get_clientsession(hass), dict(settings), _save_tokens
        )
        payload = await cloud.get_communication_key()
        credentials = parse_communication_credentials(payload)
        if credentials is None:
            _LOGGER.warning("SwitchBot cloud returned no valid WoRWS communication credentials")
            return None
        refreshed_key, refreshed_key_id = credentials
        data = dict(entry.data)
        changed = (
            str(data.get(CONF_KEY, "")).lower() != refreshed_key.hex()
            or str(data.get(CONF_KEY_ID, "")).lower() != f"{refreshed_key_id:02x}"
        )
        data[CONF_KEY] = refreshed_key.hex()
        data[CONF_KEY_ID] = f"{refreshed_key_id:02X}"
        hass.config_entries.async_update_entry(entry, data=data)
        _LOGGER.warning(
            "SwitchBot cloud communication credentials fetched for the WoRWS management "
            "session (key ID %02X, changed=%s)",
            refreshed_key_id,
            changed,
        )
        return credentials

    crypto = UrcCrypto(key, key_id)
    client = UrcClient(
        ble_devices,
        crypto,
        credential_refresh_cb=_refresh_communication_credentials,
        bridge_pause_cb=lambda: _set_bridge_paused(hass, True),
        bridge_resume_cb=lambda: _set_bridge_paused(hass, False),
        management_proxy_cb=lambda addr, k, kid, steps: _run_addon_management(
            hass, addr, k, kid, steps
        ),
    )
    if bridge_identity := hass.data.setdefault(DOMAIN, {}).get("_bridge_identity"):
        client.prefer_adapter(
            str(bridge_identity.get("adapter", "")),
            str(bridge_identity.get("adapter_address", "")),
        )

    def _on_notify(source_uuid: str, raw: bytes, plaintext: bytes) -> None:
        if source_uuid.lower() == CHAR_NOTIFY:
            hass.bus.async_fire(
                EVENT_NOTIFY,
                {"address": address, "raw": raw.hex(), "plaintext": plaintext.hex()},
            )
            return
        # Any other notify char (HID report / vendor) = candidate physical button press.
        if is_press(raw):
            decoded = decode_report(raw)
            hass.bus.async_fire(
                EVENT_BUTTON,
                {"address": address, "source": source_uuid, **decoded},
            )

    client.set_notify_callback(_on_notify)

    # WoRWS is an intermittent, battery-powered BLE peripheral. It may be asleep, temporarily
    # connected to the native bridge, or outside its short connection window while Home Assistant
    # is starting. A mandatory startup handshake made the entire integration unavailable in those
    # normal states and left its options flow without a client. Register the lazy client now;
    # query/mutation methods establish and release their own fresh connection when actually used.
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"client": client, "address": address}
    await async_register_studio(hass)
    _register_services(hass)
    await _subscribe_bridge_mqtt(hass)
    _register_binding_dispatcher(hass)
    await hass.config_entries.async_forward_entry_setups(
        entry, [Platform(platform) for platform in PLATFORMS]
    )
    return True


def _register_binding_dispatcher(hass: HomeAssistant) -> None:
    """Execute saved whole-remote bindings for normalized button events."""
    store = hass.data[DOMAIN]
    if store.get("_binding_unsub"):
        return

    async def _run_button_actions(
        sequence: list[dict[str, object]], event: Event, event_data: dict[str, object],
        owner: str = "",
    ) -> None:
        """Validate and run one user-authored HA action sequence.

        `owner` is the remote the binding belongs to. It is logged next to the remote the press
        came from, because "they should be the same" is exactly the kind of assumption that is
        worth being able to check in a log rather than reason about.
        """
        action_script: Script | None = None
        remote_id = str(event_data.get("remote_id", "unknown"))
        button_id = str(event_data.get("button_id", "unknown"))
        if owner and owner != remote_id:
            _LOGGER.error(
                "a binding for remote %s answered a press from remote %s; this should be "
                "impossible and the actions are not run",
                owner, remote_id,
            )
            return
        try:
            validated = await async_validate_actions_config(hass, deepcopy(sequence))
            action_script = Script(
                hass,
                validated,
                f"WoRWS {remote_id} {button_id}",
                DOMAIN,
                script_mode="parallel",
                max_runs=10,
            )
            await action_script.async_run(
                {
                    "remote_id": remote_id,
                    "remote_slot": event_data.get("remote_slot"),
                    "button_id": button_id,
                    "button": event_data.get("button"),
                    "button_name": event_data.get("button_name"),
                    "button_page": event_data.get("button_page"),
                    "button_index": event_data.get("button_index"),
                    "button_function": event_data.get("button_function"),
                    "event_data": dict(event_data),
                },
                context=event.context,
            )
            _LOGGER.info(
                "WoRWS custom action remote_id=%s button_id=%s completed",
                remote_id,
                button_id,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception(
                "WoRWS custom action failed for remote %s button %s",
                remote_id,
                button_id,
            )
        finally:
            if action_script is not None:
                await action_script.async_unload()

    async def _handle_event(event: Event) -> None:
        event_data = dict(event.data)
        remote_id = str(event_data.get("remote_id", ""))
        if not remote_id or remote_id == "legacy":
            return
        for config_entry in hass.config_entries.async_entries(DOMAIN):
            if not event_matches_remote_address(
                str(config_entry.data.get(CONF_ADDRESS, "")), event_data
            ):
                continue
            # A remote should have exactly one binding, but older versions and the options
            # flow could leave a second behind. Keeping the first is what the rest of this
            # function assumes, so make that true rather than acting on every one of them.
            seen_remotes: set[str] = set()
            for binding in config_entry.options.get("bindings", []):
                if not isinstance(binding, dict):
                    continue
                owner = str(binding.get("remote_id", ""))
                if owner in seen_remotes:
                    _LOGGER.warning(
                        "remote %s has more than one stored binding; ignoring the extra one",
                        owner,
                    )
                    continue
                seen_remotes.add(owner)
                button_actions = resolve_button_action_sequence(binding, event_data)
                if button_actions is not None:
                    if button_actions:
                        hass.async_create_task(
                            _run_button_actions(button_actions, event, event_data, owner)
                        )
                    else:
                        _LOGGER.info(
                            "WoRWS binding remote_id=%s button_id=%s is disabled",
                            remote_id,
                            event_data.get("button_id", "unknown"),
                        )
                    return
                action = resolve_binding_action(binding, event_data)
                if action is None:
                    continue
                if owner != remote_id:
                    _LOGGER.error(
                        "a binding for remote %s matched a press from remote %s; refusing to "
                        "drive %s",
                        owner, remote_id, binding.get("entity_id", "its target"),
                    )
                    continue
                entity_id = str(binding.get("entity_id", ""))
                if not entity_id.startswith("light."):
                    _LOGGER.warning(
                        "ignoring unsupported WoRWS binding target %s for remote %s",
                        entity_id,
                        remote_id,
                    )
                    continue
                service_data: dict[str, object] = {"entity_id": entity_id}
                service = "turn_on"
                if action == ACTION_TURN_OFF:
                    service = "turn_off"
                elif action == ACTION_TOGGLE:
                    service = "toggle"
                elif action == ACTION_BRIGHTER:
                    service_data["brightness_step_pct"] = 10
                elif action == ACTION_DARKER:
                    service_data["brightness_step_pct"] = -10
                elif action in (ACTION_WARMER, ACTION_COOLER):
                    state = hass.states.get(entity_id)
                    attributes = state.attributes if state is not None else {}
                    minimum_value = attributes.get("min_color_temp_kelvin")
                    maximum_value = attributes.get("max_color_temp_kelvin")
                    minimum = (
                        int(minimum_value)
                        if isinstance(minimum_value, (int, float))
                        else 2000
                    )
                    maximum = (
                        int(maximum_value)
                        if isinstance(maximum_value, (int, float))
                        else 6500
                    )
                    current_value = attributes.get("color_temp_kelvin")
                    current = (
                        int(current_value)
                        if isinstance(current_value, (int, float))
                        else (minimum + maximum) // 2
                    )
                    delta = -250 if action == ACTION_WARMER else 250
                    service_data["color_temp_kelvin"] = max(
                        minimum, min(maximum, current + delta)
                    )
                elif action in RGB_ACTIONS:
                    service_data["rgb_color"] = list(RGB_ACTIONS[action])
                elif action != ACTION_TURN_ON:
                    continue
                try:
                    await hass.services.async_call(
                        "light", service, service_data, blocking=False
                    )
                    _LOGGER.info(
                        "WoRWS binding owner=%s press=%s button=%s -> %s.%s target=%s",
                        owner,
                        remote_id,
                        event_data.get("button", event_data.get("button_id", "unknown")),
                        "light",
                        service,
                        entity_id,
                    )
                except Exception:  # noqa: BLE001
                    _LOGGER.exception(
                        "WoRWS binding action failed for remote %s and %s",
                        remote_id,
                        entity_id,
                    )
                # One press, one action. The exact-override branch above already stops here;
                # this one fell through and let every further binding that matched act too, so
                # a remote with more than one stored binding drove all of their targets at once.
                return

    store["_binding_unsub"] = hass.bus.async_listen(EVENT_BUTTON, _handle_event)


async def _set_bridge_paused(hass: HomeAssistant, paused: bool) -> bool:
    """Ask the add-on to release or restore the fake hub radio and await its ACK."""
    return await async_bridge_control(hass, "pause" if paused else "resume")


async def async_bridge_control(
    hass: HomeAssistant, action: str, extra: dict | None = None
) -> bool:
    """Send one control request to the add-on and await its acknowledgement.

    `pause`/`resume` free and restore the controller for a management session. `addresses`
    changes which BLE addresses the bridge advertises, which is how a newly bound native tile
    starts being answered without anyone editing the add-on's configuration.
    """
    store = hass.data[DOMAIN]
    waiters: dict[str, asyncio.Future[bool]] = store.setdefault(
        "_bridge_control_waiters", {}
    )
    if not store.get("_mqtt_status_unsub"):
        # Subscriptions can fail at setup when the integration loads before the mqtt integration
        # is ready. Retry on demand before giving up — by the time the user triggers management
        # MQTT is virtually always available.
        await _subscribe_bridge_mqtt(hass)
    if not store.get("_mqtt_status_unsub"):
        _LOGGER.warning(
            "native bridge MQTT control is unavailable; continuing BLE management without "
            "pausing the fake hub"
        )
        return False
    from homeassistant.components import mqtt

    # The control topic is published with retain=False, so a request sent while the add-on is
    # still (re)connecting or re-subscribing is silently dropped. Re-publish a few times before
    # giving up so a brief add-on unavailability does not doom the whole management operation.
    attempts = 3
    per_attempt_timeout = 4.0
    for attempt in range(1, attempts + 1):
        request_id = uuid.uuid4().hex
        future: asyncio.Future[bool] = hass.loop.create_future()
        waiters[request_id] = future
        try:
            # mqtt.async_publish is a coroutine; without await the publish is never actually sent
            # (the control message silently never reaches the broker), which is exactly why the
            # add-on only ever answered a manual DevTools publish and never this pause request.
            await mqtt.async_publish(
                hass,
                MQTT_BRIDGE_CONTROL_TOPIC,
                json.dumps({"action": action, "request_id": request_id, **(extra or {})}),
                qos=1,
                retain=False,
            )
            result = await asyncio.wait_for(future, timeout=per_attempt_timeout)
        except TimeoutError:
            if attempt < attempts:
                _LOGGER.debug(
                    "native bridge did not answer MQTT %s (attempt %d/%d); re-publishing",
                    action,
                    attempt,
                    attempts,
                )
                continue
            _LOGGER.warning(
                "native bridge did not acknowledge MQTT %s request after %d attempts",
                action,
                attempts,
            )
            return False
        finally:
            waiters.pop(request_id, None)
        if result:
            _LOGGER.warning("native bridge %sd for WoRWS management", action)
        else:
            _LOGGER.warning("native bridge reported it could not %s", action)
        return result
    return False


async def _run_addon_management(
    hass: HomeAssistant, address: str, key: bytes, key_id: int, steps: list[dict]
) -> dict | None:
    """Ask the add-on to run a WoRWS management session on the controller the remote is bound to.

    The add-on owns that controller (Home Assistant's own BLE stack cannot drive it), so it
    performs the get-random handshake, the preflight query and the mutation there and returns the
    per-step responses. Returns None when the MQTT channel is unavailable so the caller can fall
    back to its local BLE transport.
    """
    store = hass.data[DOMAIN]
    if not store.get("_mqtt_manage_unsub"):
        await _subscribe_bridge_mqtt(hass)
    if not store.get("_mqtt_manage_unsub"):
        _LOGGER.warning("native bridge management channel is unavailable over MQTT")
        return None
    from homeassistant.components import mqtt

    waiters: dict[str, asyncio.Future[dict]] = store.setdefault("_bridge_manage_waiters", {})
    request_id = uuid.uuid4().hex
    future: asyncio.Future[dict] = hass.loop.create_future()
    waiters[request_id] = future
    payload = {
        "request_id": request_id,
        "address": address.upper(),
        "key": key.hex(),
        "key_id": int(key_id),
        "steps": steps,
    }
    # Allow time for pause + up to three connect retries (scan+connect ~15s each) + the 35s
    # get-random handshake + every step, plus headroom. A too-short budget makes the integration
    # give up while the add-on is still mid-retry (orphaning the operation).
    budget = 95.0 + sum(float(step.get("timeout", 20.0)) for step in steps)
    try:
        await mqtt.async_publish(
            hass, MQTT_BRIDGE_MANAGE_TOPIC, json.dumps(payload), qos=1, retain=False
        )
        return await asyncio.wait_for(future, timeout=budget)
    except TimeoutError:
        _LOGGER.warning("native bridge did not return a management result in time")
        return None
    finally:
        waiters.pop(request_id, None)


def _apply_bridge_identity(hass: HomeAssistant, data: dict[str, object]) -> None:
    """Persist add-on controller identity and remove it from every live BLE client."""
    adapter = str(data.get("adapter", ""))
    address = str(data.get("adapter_address", ""))
    if not adapter and not address:
        return
    store = hass.data[DOMAIN]
    first_time = store.get("_bridge_identity") is None
    if first_time:
        # A clear, one-time confirmation that the add-on -> integration MQTT path is alive. If
        # this never appears, the add-on's broker and Home Assistant's MQTT integration are not
        # the same broker (or an ACL blocks switchbot_urc/#), which also breaks the pause ACK.
        _LOGGER.warning(
            "received native bridge identity over MQTT (adapter=%s address=%s); the add-on "
            "MQTT bridge is reachable",
            adapter or "unknown",
            address or "unknown",
        )
    store["_bridge_identity"] = {"adapter": adapter, "adapter_address": address}
    # What this controller can carry, so Remote Studio can plan addresses without anyone
    # reading an add-on log. Keyed by controller address: one add-on instance per adapter.
    if data.get("multi_address"):
        bridges = dict(store.get("_bridge_capabilities") or {})
        bridges[address.upper()] = {
            "adapter": adapter,
            "address": address.upper(),
            "advertising_sets": int(data.get("advertising_sets") or 1),
            "extended_advertising": bool(data.get("extended_advertising")),
            "serving": [str(item) for item in (data.get("serving") or [])],
        }
        store["_bridge_capabilities"] = bridges
    for value in store.values():
        if not isinstance(value, dict):
            continue
        client = value.get("client")
        if isinstance(client, UrcClient):
            # Pin management onto the add-on's controller (the remote only handshakes on the
            # controller it is bound to); the add-on frees it during the pause window.
            client.prefer_adapter(adapter, address)


async def _subscribe_bridge_mqtt(hass: HomeAssistant) -> None:
    """Re-fire button presses the add-on publishes over MQTT as EVENT_BUTTON (best-effort).

    Lets automations use one event (switchbot_urc_button) whether a press came via the integration
    (HID/notify) or via the fake-device add-on (MQTT). No-op if MQTT isn't configured.
    """
    store = hass.data[DOMAIN]
    if store.get("_mqtt_manage_unsub"):
        return
    try:
        from homeassistant.components import mqtt
    except ImportError:
        return
    # async_setup_entry can race ahead of the mqtt integration; wait for the client so the
    # control/status/info subscriptions actually register instead of failing silently (which
    # left the pause publish gated off and looked like "add-on did not acknowledge the pause").
    waiter = getattr(mqtt, "async_wait_for_mqtt_client", None)
    if waiter is not None:
        try:
            await asyncio.wait_for(waiter(hass), timeout=10)
        except Exception:  # noqa: BLE001 - fall through to a best-effort subscribe attempt
            pass

    @callback
    def _on_msg(msg) -> None:  # noqa: ANN001
        try:
            data = json.loads(msg.payload)
        except (ValueError, TypeError):
            data = {"raw": str(msg.payload)}
        # The add-on only sees the compact on-air identity.  Enrich custom-builder events with
        # the friendly names stored in this integration, without changing the stable IDs used
        # by existing automations.
        remote_id = str(data.get("remote_id", ""))
        for config_entry in hass.config_entries.async_entries(DOMAIN):
            for remote in config_entry.options.get("remotes", []):
                if str(remote.get("remote_id", "")) != remote_id:
                    continue
                layout = remote.get("custom_layout")
                if not isinstance(layout, dict):
                    continue
                data.setdefault("remote_name", remote.get("name"))
                page = int(data.get("button_page", 0))
                key_index = int(data.get("button_index", -1))
                page_names = layout.get("page_names", {})
                data.setdefault(
                    "page_name",
                    "Main" if page == 0 else page_names.get(str(page), f"Page {'ABCD'[page - 1]}"),
                )
                if page == 0:
                    button_name = next(
                        (
                            name for name, (index, _function)
                            in commands.CUSTOM_MAIN_BUTTONS.items() if index == key_index
                        ),
                        None,
                    )
                    if button_name is None and 0 <= key_index <= 3:
                        button_name = page_names.get(
                            str(key_index + 1), f"Page {'ABCD'[key_index]}"
                        )
                else:
                    actions = layout.get("pages", {}).get(str(page), [])
                    button_name = actions[key_index] if 0 <= key_index < len(actions) else None
                if button_name:
                    data.setdefault("button_name", button_name)
                    data.setdefault("button_icon", commands.custom_action_ha_icon(button_name))
                break
        hass.bus.async_fire(EVENT_BUTTON, {"source": "mqtt", **data})

    @callback
    def _on_status(msg) -> None:  # noqa: ANN001
        try:
            data = json.loads(msg.payload)
            request_id = str(data["request_id"])
        except (KeyError, ValueError, TypeError):
            return
        _apply_bridge_identity(hass, data)
        waiters = store.get("_bridge_control_waiters", {})
        future = waiters.get(request_id)
        if future is not None and not future.done():
            future.set_result(bool(data.get("ok")))

    @callback
    def _on_bridge_info(msg) -> None:  # noqa: ANN001
        try:
            data = json.loads(msg.payload)
        except (ValueError, TypeError):
            return
        if isinstance(data, dict):
            _apply_bridge_identity(hass, data)

    @callback
    def _on_manage_result(msg) -> None:  # noqa: ANN001
        try:
            data = json.loads(msg.payload)
            request_id = str(data["request_id"])
        except (KeyError, ValueError, TypeError):
            return
        _apply_bridge_identity(hass, data)
        waiters = store.get("_bridge_manage_waiters", {})
        future = waiters.get(request_id)
        if future is not None and not future.done():
            future.set_result(data)

    try:
        if not store.get("_mqtt_unsub"):
            store["_mqtt_unsub"] = await mqtt.async_subscribe(hass, MQTT_BUTTON_TOPIC, _on_msg)
        store["_mqtt_status_unsub"] = await mqtt.async_subscribe(
            hass, MQTT_BRIDGE_STATUS_TOPIC, _on_status
        )
        store["_mqtt_info_unsub"] = await mqtt.async_subscribe(
            hass, MQTT_BRIDGE_INFO_TOPIC, _on_bridge_info
        )
        store["_mqtt_manage_unsub"] = await mqtt.async_subscribe(
            hass, MQTT_BRIDGE_MANAGE_RESULT_TOPIC, _on_manage_result
        )
        _LOGGER.info("subscribed to add-on MQTT control/status/info/manage topics")
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "MQTT subscribe for native bridge control failed; pause/resume stays unavailable "
            "until this succeeds (retried on each management attempt): %s",
            err,
        )


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        return

    def _pick(call: ServiceCall) -> UrcClient:
        entries = hass.data[DOMAIN]
        wanted = call.data.get("address")
        for rec in entries.values():
            if not isinstance(rec, dict) or "client" not in rec:
                continue  # skip bookkeeping entries like _mqtt_unsub
            if wanted is None or rec["address"].upper() == wanted.upper():
                return rec["client"]
        raise HomeAssistantError(f"no SwitchBot URC client for address {wanted!r}")

    def _log_resp(resp: bytes, what: str) -> None:
        code = resp[0] if resp else None
        ok = code == RESP_OK
        log = _LOGGER.info if ok else _LOGGER.warning
        log("%s -> resp=%s (%s)", what, resp.hex() or "<timeout>",
            "ok" if ok else f"code 0x{code:02X}" if code is not None else "no reply")

    async def _send(call: ServiceCall) -> None:
        resp = await _pick(call).send_command(bytes.fromhex(call.data["plaintext"]))
        _log_resp(resp, "send_command")

    async def _send_sequence(call: ServiceCall) -> ServiceResponse:
        """Run several raw commands inside ONE management session, like bind_native does.

        `send_command` opens its own connection and handshake per call, so commands that the
        firmware only accepts after an earlier command in the same session cannot be tested
        with it. This keeps the session open across the whole list and returns every response.
        """
        plaintexts = [bytes.fromhex(item) for item in call.data["plaintexts"]]
        responses = await _pick(call).send_command_sequence(
            tuple(plaintexts), timeout=35.0, timeout_retries=1
        )
        results = [
            {
                "step": index,
                "response": resp.hex() if resp else "",
                "ok": bool(resp and resp[0] == RESP_OK),
            }
            for index, resp in enumerate(responses)
        ]
        for item in results:
            _log_resp(
                bytes.fromhex(item["response"]) if item["response"] else b"",
                f"send_command_sequence[{item['step']}]",
            )
        return {"responses": results}

    async def _create(call: ServiceCall) -> None:
        device_type = call.data.get("device_type", "UNIVERSAL_BLE")
        plaintext = commands.build_remote(
            device_type_name=device_type,
            remote_index=call.data["remote_index"],
            name=call.data["name"],
            device_id=call.data["device_id"],
            icon_name=call.data.get("icon", "light"),
            control_mode=call.data.get("control_mode", 0),
        )
        resp = await _pick(call).send_command(plaintext)
        _log_resp(resp, f"create_remote[{call.data['remote_index']}] {device_type}")

    async def _delete(call: ServiceCall) -> None:
        device_type = call.data.get("device_type", "UNIVERSAL_BLE")
        control_type = commands.control_type_for(device_type)
        client = _pick(call)
        plaintext = commands.build_delete(
            remote_index=call.data["remote_index"],
            device_type=commands.devtype_byte(device_type),
            control_type=control_type,
            device_id=call.data["device_id"],
        )
        resp = await client.send_command(plaintext)
        _log_resp(resp, f"delete_remote[{call.data['remote_index']}] {device_type}")
        if not resp or resp[0] != RESP_OK or control_type != commands.CTRL_NATIVE:
            return
        # Deleting a native remote releases the target-key entry, and that entry is keyed on
        # the six-byte BLE address rather than on the remote. Any other native profile aiming
        # at the same address loses its key and then stops after service discovery, so the
        # association has to be written back.
        await _reassociate_shared_target(client, call.data["device_id"])

    async def _reassociate_shared_target(client: UrcClient, device_id: str) -> None:
        """Restore the target-key association when another native row still uses the address."""
        try:
            entries = commands.parse_added_devices(await client.query(0x07))
        except (ValueError, TypeError) as err:
            _LOGGER.warning("could not re-check the device table after deleting: %s", err)
            return
        address = commands.id_to_bytes(device_id)[:6]
        survivors = [
            entry for entry in entries
            if entry[2] == commands.CTRL_NATIVE and entry[3][:6] == address
        ]
        if not survivors:
            return
        _LOGGER.info(
            "slot(s) %s still target %s; re-associating the shared target key",
            ", ".join(str(entry[0]) for entry in survivors),
            ":".join(f"{byte:02X}" for byte in reversed(address)),
        )
        resp = await client.send_command(
            commands.build_associate_target_key(0x01, device_id)
        )
        _log_resp(resp, "delete_remote re-associate shared target key")

    async def _bind_native(call: ServiceCall) -> None:
        """Provision target credentials, associate its id, then bind its real native page."""
        device_type = call.data.get("device_type", "STRIP")
        client = _pick(call)
        try:
            # Native provisioning uses the fixed target selector 0x01. This is unrelated
            # to the rotating WoRWS communication key ID.
            key_id = 0x01
            target_key = bytes.fromhex(call.data["target_key"])
            raw_table = await client.query(0x07)
            if not raw_table:
                raise HomeAssistantError("could not read the current WoRWS device table")
            entries = commands.parse_added_devices(raw_table)
            target_id = commands.id_to_bytes(call.data["device_id"])
            duplicates = [entry for entry in entries if entry[3] == target_id]
            if duplicates and not call.data.get("replace_existing", False):
                slots = ", ".join(str(entry[0]) for entry in duplicates)
                raise HomeAssistantError(
                    f"target device ID is already used by slot(s) {slots}; "
                    "set replace_existing=true to delete and replace it"
                )
            # Delete from the highest slot down so firmware-side compaction cannot invalidate
            # the index of another duplicate before it is removed.
            for index, dev_type, control_type, _entry_id in sorted(
                duplicates, key=lambda entry: entry[0], reverse=True
            ):
                delete = commands.build_delete(
                    remote_index=index,
                    device_type=dev_type,
                    control_type=control_type,
                    device_id=call.data["device_id"],
                )
                resp = await client.send_command(delete)
                _log_resp(resp, f"bind_native delete duplicate slot {index}")
                if not resp or resp[0] != RESP_OK:
                    code = f"0x{resp[0]:02X}" if resp else "timeout"
                    raise HomeAssistantError(
                        f"could not delete duplicate slot {index}: {code}"
                    )
            if duplicates:
                raw_table = await client.query(0x07)
                if not raw_table:
                    raise HomeAssistantError(
                        "could not verify the WoRWS device table after deleting the duplicate"
                    )
                entries = commands.parse_added_devices(raw_table)
                remaining_slots = [entry[0] for entry in entries if entry[3] == target_id]
                if remaining_slots:
                    slots = ", ".join(str(index) for index in remaining_slots)
                    raise HomeAssistantError(
                        f"target device ID is still present in slot(s) {slots} after deletion"
                    )
            remote_index = len(entries)
            requested_index = call.data.get("remote_index")
            if requested_index is not None and requested_index != remote_index:
                _LOGGER.warning(
                    "ignoring requested native index %s; firmware requires sequential index %s",
                    requested_index,
                    remote_index,
                )
            stages = commands.build_native_bind_sequence(
                key_id=key_id,
                target_key=target_key,
                device_type_name=device_type,
                remote_index=remote_index,
                name=call.data["name"],
                device_id=call.data["device_id"],
                icon_name=call.data.get("icon", "strip"),
                # Native fake targets use firmware's direct BLE mode exclusively.
                # Keep accepting the legacy service field, but never persist a value that
                # binds successfully and then suppresses connections on button presses.
                control_mode=0,
            )
        except ValueError as err:
            raise HomeAssistantError(f"invalid native bind data: {err}") from err

        try:
            responses = await client.send_command_sequence(
                tuple(plaintext for _, plaintext in stages),
                timeout=35.0,
                timeout_retries=3,
            )
        except UrcResponseDecodeError as err:
            raise HomeAssistantError(
                "the WoRWS communication key/keyId is stale or incorrect; update integration "
                "credentials and retry"
            ) from err
        for (stage, _), resp in zip(stages, responses):
            _log_resp(resp, f"bind_native[{remote_index}] {stage}")
            result = {
                "address": call.data.get("address"),
                "remote_index": remote_index,
                "device_id": call.data["device_id"],
                "stage": stage,
                "response": resp.hex(),
                "ok": bool(resp and resp[0] == RESP_OK),
            }
            hass.bus.async_fire(EVENT_NATIVE_BIND, result)
            if not result["ok"]:
                code = f"0x{resp[0]:02X}" if resp else "timeout"
                raise HomeAssistantError(f"native bind failed at {stage}: {code}")

    async def _hid_pair(call: ServiceCall) -> None:
        resp = await _pick(call).send_command(commands.build_hid_pair(call.data["host_mac"]))
        _log_resp(resp, f"hid_pair -> {call.data['host_mac']}")

    async def _set_state_ac(call: ServiceCall) -> None:
        plaintext = commands.build_set_state_ac(
            call.data["temp"], call.data["mode"], call.data["fan"], call.data["power_on"]
        )
        resp = await _pick(call).send_command(plaintext)
        _log_resp(resp, "set_state_ac")

    async def _poll(call: ServiceCall) -> None:
        resp = await _pick(call).send_command(commands.build_status_poll())
        _log_resp(resp, "poll_status")

    async def _dump_device_table(call: ServiceCall) -> ServiceResponse:
        """Return the remote's own device table (0F 63 07). Read-only; changes nothing.

        The slot index a new remote must use is the current row count, so the raw table is
        the only reliable source for it. Each row's id is the eleven-byte field the firmware
        stores: a reversed six-byte MAC followed by five bytes that take part in the
        uniqueness check but are never transmitted.
        """
        raw = await _pick(call).query(0x07)
        if not raw:
            raise HomeAssistantError("the remote did not answer the device-table query")
        try:
            entries = commands.parse_added_devices(raw)
        except ValueError as err:
            raise HomeAssistantError(f"could not parse the device table: {err}") from err
        rows = [
            {
                "index": index,
                # Newer products use a four-byte type whose leading byte is 00; keep its width.
                "device_type": f"0x{device_type:08X}" if device_type > 0xFF
                else f"0x{device_type:02X}",
                "control_type": control_type,
                "device_id": device_id.hex(),
                "target_mac": ":".join(
                    f"{byte:02X}" for byte in reversed(device_id[:6])
                ),
                "id_tail": device_id[6:].hex(),
            }
            for index, device_type, control_type, device_id in entries
        ]
        _LOGGER.info("dump_device_table -> %d row(s)", len(rows))
        return {"count": len(rows), "next_free_index": len(rows), "rows": rows,
                "raw": raw.hex()}

    hass.services.async_register(DOMAIN, SERVICE_SEND_COMMAND, _send, schema=SEND_COMMAND_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CREATE_REMOTE, _create, schema=CREATE_REMOTE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_DELETE_REMOTE, _delete, schema=DELETE_REMOTE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_HID_PAIR, _hid_pair, schema=HID_PAIR_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_BIND_NATIVE, _bind_native, schema=BIND_NATIVE_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_SET_STATE_AC, _set_state_ac, schema=SET_STATE_AC_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_POLL_STATUS, _poll, schema=POLL_STATUS_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_DUMP_DEVICE_TABLE,
        _dump_device_table,
        schema=DUMP_DEVICE_TABLE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND_SEQUENCE,
        _send_sequence,
        schema=SEND_COMMAND_SEQUENCE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(
        entry, [Platform(platform) for platform in PLATFORMS]
    ):
        return False
    rec = hass.data[DOMAIN].pop(entry.entry_id, None)
    if rec and isinstance(rec, dict) and "client" in rec:
        await rec["client"].disconnect()
    # Only service/client records remain keyed by entry_id; the mqtt unsub is a bare callable.
    clients_left = [v for v in hass.data[DOMAIN].values() if isinstance(v, dict) and "client" in v]
    if not clients_left:
        for key in (
            "_mqtt_unsub",
            "_mqtt_status_unsub",
            "_mqtt_info_unsub",
            "_mqtt_manage_unsub",
        ):
            unsub = hass.data[DOMAIN].pop(key, None)
            if unsub:
                unsub()
        binding_unsub = hass.data[DOMAIN].pop("_binding_unsub", None)
        if binding_unsub:
            binding_unsub()
        for svc in (SERVICE_SEND_COMMAND, SERVICE_CREATE_REMOTE, SERVICE_DELETE_REMOTE,
                    SERVICE_HID_PAIR, SERVICE_BIND_NATIVE, SERVICE_SET_STATE_AC,
                    SERVICE_POLL_STATUS, SERVICE_DUMP_DEVICE_TABLE,
                    SERVICE_SEND_COMMAND_SEQUENCE):
            hass.services.async_remove(DOMAIN, svc)
    return True
