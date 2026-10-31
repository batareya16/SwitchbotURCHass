"""Config and visual remote-management flows for SwitchBot Universal Remote (WoRWS)."""
from __future__ import annotations

from copy import deepcopy
import logging
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

import voluptuous as vol
from bleak import BleakScanner

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import selector
from homeassistant.helpers.script import async_validate_actions_config

from . import commands
from . import install
from . import targets
from .bindings import (
    ACTION_LABELS,
    LIGHT_MAPPING_DEFAULTS,
    LIGHT_MAPPING_ROWS,
    light_mapping_from_rows,
    light_rows_from_mapping,
)
from .catalog import DEFAULT_BUTTONS, DEVICE_TYPES, ICONS, buttons_for
from .client import UrcResponseDecodeError
from .cloud import (
    CloudError,
    SwitchBotCloudClient,
    parse_communication_credentials,
)
from .cloud_ir import find_cloud_items, generate_remote_id, profile_from_cloud
from .const import CONF_ADDRESS, CONF_KEY, CONF_KEY_ID, DOMAIN
from .inventory import (
    cloud_items,
    format_inventory,
    merge_inventory,
    stable_id_for_local,
)
from .ir_profiles import PROFILES
from .ir_catalog import available as catalog_available
from .ir_catalog import REMOTE_TYPES, brands as catalog_brands, profiles as catalog_profiles

_LOGGER = logging.getLogger(__name__)


def _searchable_select(choices: list[str] | dict[str, str]) -> selector.SelectSelector:
    """A dropdown that can be typed into instead of only scrolled.

    Some IR catalog sections hold over a thousand brands, which a plain `vol.In` renders as one
    long list. Accepts either values or a value -> label mapping.
    """
    options = (
        [selector.SelectOptionDict(value=value, label=label) for value, label in choices.items()]
        if isinstance(choices, dict)
        else [selector.SelectOptionDict(value=value, label=value) for value in choices]
    )
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=options, mode=selector.SelectSelectorMode.DROPDOWN, sort=False
        )
    )


_RESP_ERR = install.RESP_ERRORS


def _valid(data: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not data.get(CONF_KEY) and not data.get(CONF_KEY_ID):
        # Both blank means "fetch them from the account"; the cloud step then fills them in.
        return errors
    try:
        if len(bytes.fromhex(data[CONF_KEY])) != 16:
            errors[CONF_KEY] = "key_length"
    except ValueError:
        errors[CONF_KEY] = "key_hex"
    try:
        key_id = int(data[CONF_KEY_ID], 16)
        if not 0 <= key_id <= 0xFF:
            errors[CONF_KEY_ID] = "key_id_range"
    except ValueError:
        errors[CONF_KEY_ID] = "key_id_hex"
    return errors


class UrcConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the add-device config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered_address: str | None = None
        self._pending_data: dict[str, Any] | None = None
        self._pending_cloud: dict[str, Any] | None = None
        self._cloud_homes: dict[str, str] = {}
        self._cloud_home_users: dict[str, str] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "UrcOptionsFlow":
        return UrcOptionsFlow(config_entry)

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovered_address = discovery_info.address
        return await self.async_step_user()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _valid(user_input)
            if not errors:
                await self.async_set_unique_id(
                    user_input[CONF_ADDRESS].upper(), raise_on_progress=False
                )
                self._abort_if_unique_id_configured()
                self._pending_data = dict(user_input)
                return await self.async_step_cloud_setup()

        schema = vol.Schema(
            {
                vol.Required(CONF_ADDRESS, default=self._discovered_address or ""): str,
                vol.Optional(CONF_KEY_ID, default=""): str,
                vol.Optional(CONF_KEY, default=""): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_cloud_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer optional cloud metadata during initial setup."""
        return self.async_show_menu(
            step_id="cloud_setup", menu_options=["cloud_connect", "cloud_skip"]
        )

    async def async_step_cloud_skip(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._pending_data is None:
            return await self.async_step_user()
        if not self._pending_data.get(CONF_KEY):
            return self.async_abort(reason="key_or_account_required")
        return self.async_create_entry(
            title=f"Universal Remote {self._pending_data[CONF_ADDRESS]}",
            data=self._pending_data,
        )

    async def async_step_cloud_connect(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sign in like the official app; never retain the submitted password."""
        if self._pending_data is None:
            return await self.async_step_user()
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = {
                "region": "EU",
                "api_base_url": "",
                "group_id": "",
                "urc_device_id": self._pending_data[CONF_ADDRESS].replace(":", "").upper(),
                "token_device_id": uuid.uuid4().hex,
                "user_id": "",
                "username": user_input["username"].strip(),
                "access_token": "",
                "refresh_token": "",
            }

            async def _capture_tokens(access: str, refresh: str) -> None:
                candidate["access_token"] = access
                candidate["refresh_token"] = refresh

            try:
                cloud = SwitchBotCloudClient(
                    async_get_clientsession(self.hass), candidate, _capture_tokens
                )
                await cloud.login(candidate["username"], user_input["password"])
                homes = await cloud.get_homes()
                self._pending_cloud = candidate
                self._cloud_homes = {
                    str(item["groupID"]): str(
                        item.get("alias") or item.get("groupName") or item["groupID"]
                    )
                    for item in homes
                }
                self._cloud_home_users = {
                    str(item["groupID"]): str(item.get("userID") or "")
                    for item in homes
                }
                if len(self._cloud_homes) == 1:
                    self._select_cloud_home(next(iter(self._cloud_homes)))
                    return await self._finish_cloud_setup()
                if self._cloud_homes:
                    return await self.async_step_cloud_home()
                errors["base"] = "cloud_no_homes"
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("SwitchBot cloud login failed: %s", err)
                errors["base"] = "cloud_auth_failed"

        return self.async_show_form(
            step_id="cloud_connect",
            data_schema=vol.Schema(
                {
                    vol.Required("username", default=(user_input or {}).get("username", "")): str,
                    vol.Required("password"): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_cloud_home(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose by friendly home name when the account has several."""
        if self._pending_cloud is None or not self._cloud_homes:
            return await self.async_step_cloud_connect()
        if user_input is not None:
            self._select_cloud_home(user_input["home"])
            return await self._finish_cloud_setup()
        return self.async_show_form(
            step_id="cloud_home",
            data_schema=vol.Schema({vol.Required("home"): vol.In(self._cloud_homes)}),
        )

    def _select_cloud_home(self, group_id: str) -> None:
        """Apply the selected home and its refresh-token user identity."""
        assert self._pending_cloud is not None
        self._pending_cloud["group_id"] = group_id
        if self._cloud_home_users.get(group_id):
            self._pending_cloud["user_id"] = self._cloud_home_users[group_id]

    async def _finish_cloud_setup(self) -> ConfigFlowResult:
        """Validate the selected home and persist tokens, but never a password."""
        assert self._pending_data is not None and self._pending_cloud is not None
        candidate = self._pending_cloud

        async def _capture_tokens(access: str, refresh: str) -> None:
            candidate["access_token"] = access
            candidate["refresh_token"] = refresh

        try:
            cloud = SwitchBotCloudClient(
                async_get_clientsession(self.hass), candidate, _capture_tokens
            )
            await cloud.get_bindable_devices()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("SwitchBot cloud home validation failed: %s", err)
            return self.async_abort(reason="cloud_home_failed")
        data = dict(self._pending_data)
        data["cloud"] = candidate
        if not data.get(CONF_KEY):
            # The communication key rotates and the account is its source of truth, so there is
            # no reason to make anyone copy it by hand when they have just signed in.
            try:
                credentials = parse_communication_credentials(
                    await cloud.get_communication_key()
                )
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("could not fetch the WoRWS communication key: %s", err)
                credentials = None
            if credentials is None:
                return self.async_abort(reason="cloud_no_communication_key")
            key, key_id = credentials
            data[CONF_KEY] = key.hex()
            data[CONF_KEY_ID] = f"{key_id:02X}"
        return self.async_create_entry(
            title=f"Universal Remote {data[CONF_ADDRESS]}", data=data
        )


class UrcOptionsFlow(OptionsFlow):
    """Visual management of remotes on the device."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        # NB: do not assign self.config_entry — in modern HA it's a read-only property set by the
        # framework; assigning it raises and the options flow fails to load (500).
        self._entry = config_entry
        # Working copy of persisted options; {"remotes": [ {index,name,device_type,icon,
        # device_id,buttons}, ... ], "host_mac": str}
        self.options: dict[str, Any] = dict(config_entry.options)
        self.options.setdefault("remotes", [])
        self.options.setdefault("bindings", [])
        self._native_status = "—"
        self._ir_status = "—"
        self._diagnostic_status = "Not run yet."
        self._bridge_test_status = "Not run yet."
        self._inventory: list[dict[str, Any]] = []
        self._inventory_status = "Open this page to refresh the device and cloud lists."
        self._selected_remote_key: str | None = None
        self._catalog_type: int | None = None
        self._catalog_brand: str | None = None
        self._catalog_models: dict[str, Any] = {}
        self._pending_ir_cloud_sync: dict[str, Any] | None = None
        self._pending_cloud: dict[str, Any] | None = None
        self._cloud_homes: dict[str, str] = {}
        self._cloud_home_users: dict[str, str] = {}
        self._custom_native_draft: dict[str, Any] | None = None
        self._custom_page_queue: list[int] = []
        self._pending_binding: dict[str, Any] | None = None
        self._selected_binding_remote_id: str | None = None
        self._selected_button_id: str | None = None

    # -- helpers -----------------------------------------------------------------------------

    def _client(self):
        rec = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id)
        return rec["client"] if rec else None

    async def _persist(self) -> None:
        self.hass.config_entries.async_update_entry(
            self._entry, options=self.options
        )

    def _cloud_settings(self) -> dict[str, Any] | None:
        settings = self._entry.data.get("cloud")
        return dict(settings) if isinstance(settings, dict) else None

    def _cloud_client(self) -> SwitchBotCloudClient | None:
        settings = self._cloud_settings()
        if not settings:
            return None

        async def _save_tokens(access_token: str, refresh_token: str) -> None:
            data = dict(self._entry.data)
            cloud = dict(data.get("cloud", {}))
            cloud["access_token"] = access_token
            cloud["refresh_token"] = refresh_token
            data["cloud"] = cloud
            self.hass.config_entries.async_update_entry(self._entry, data=data)

        return SwitchBotCloudClient(
            async_get_clientsession(self.hass), settings, _save_tokens
        )

    async def _refresh_remote_inventory(self) -> None:
        client = self._client()
        if client is None:
            raise RuntimeError("not connected")
        raw = await client.query(0x07)
        if not raw:
            raise RuntimeError("device table timeout")
        physical = commands.parse_added_devices(raw)
        cached_cloud = self.options.get("cloud_remotes", [])
        cloud_records: list[dict[str, Any]] = [
            dict(item) for item in cached_cloud if isinstance(item, dict)
        ]
        cloud_status = "not configured"
        cloud = self._cloud_client()
        if cloud is not None:
            try:
                payload = await cloud.get_bindable_devices()
                cloud_records = cloud_items(payload)
                cloud_status = f"connected, {len(cloud_records)} remote(s)"
                self.options["cloud_remotes"] = cloud_records
            except Exception as err:  # noqa: BLE001 - cloud is optional; keep physical list usable
                _LOGGER.warning("SwitchBot cloud list refresh failed: %s", err)
                cloud_status = (
                    f"error — {err}; showing {len(cloud_records)} cached remote(s)"
                )
        self._inventory = merge_inventory(
            physical, self.options.get("remotes", []), cloud_records
        )
        # Persist each matched logical remote's current slot. Several native pages can share the
        # same adapter MAC/table ID, so an id->index dictionary would collapse them into one.
        for item in self._inventory:
            local = item.get("managed_item")
            if item["physical"] and local:
                local["index"] = item["index"]
        refreshed_at = datetime.now(UTC).isoformat(timespec="seconds")
        # Store a deliberately sanitized merged snapshot in HA options.  Runtime-only
        # values (bytes and raw cloud records/tokens) must never leak into config storage.
        self.options["remote_inventory"] = [
            {
                "id": item["key"],
                "device_id": item["device_key"],
                "index": item["index"],
                "name": item["name"],
                "kind": item["kind"],
                "device_type": item["device_type_byte"],
                "control_type": item["control_type"],
                "physical": item["physical"],
                "cloud": item["cloud"],
            }
            for item in self._inventory
        ]
        self.options["remote_inventory_updated_at"] = refreshed_at
        self._inventory_status = (
            f"{format_inventory(self._inventory, cloud_status)}"
            f"\n\nCached in Home Assistant: {refreshed_at}"
        )
        await self._persist()

    async def _restore_managed_after_sync(self) -> None:
        """Recreate locally managed HID/native entries if a full IR sync removed them."""
        client = self._client()
        if client is None:
            raise RuntimeError("not connected")
        await install.restore_managed_after_sync(
            client,
            remotes=self.options.get("remotes", []),
            targets=targets.all_targets(self._entry),
        )

    @staticmethod
    def _resp_error(resp: bytes) -> str | None:
        return install.resp_error(resp)

    @classmethod
    def _delete_resp_error(cls, resp: bytes, command: bytes) -> str | None:
        return install.delete_resp_error(resp, command)

    async def _delete_and_verify(
        self,
        client: Any,
        command: bytes,
        *,
        device_type: int,
        control_type: int,
        device_id: str,
    ) -> str | None:
        return await install.delete_and_verify(
            client, command,
            device_type=device_type, control_type=control_type, device_id=device_id,
        )

    # -- menu --------------------------------------------------------------------------------

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_remote_menu", "manage_existing_remote", "remote_manager",
                "remote_bindings", "refresh_all_remotes", "cloud_account",
                "update_credentials", "diagnostics_menu",
            ],
        )

    async def async_step_diagnostics_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Group the rarely used checks so the main menu stays about everyday actions.

        Updating the communication key stays one level up: it is what you reach for when nothing
        else works, and it should not be buried.
        """
        return self.async_show_menu(
            step_id="diagnostics_menu",
            menu_options=["test_native_bridge", "native_diagnostics", "pair_host"],
        )

    def _bindable_remote_choices(self) -> dict[str, str]:
        """Return logical remotes that emit a stable remote_id."""
        return {
            str(remote["remote_id"]): str(remote.get("name") or remote["remote_id"])
            for remote in self.options.get("remotes", [])
            if isinstance(remote, dict) and remote.get("remote_id")
        }

    def _binding_choices(self) -> dict[str, str]:
        """Return existing whole-remote bindings."""
        return {
            str(binding["remote_id"]): (
                f"{binding.get('remote_name', binding['remote_id'])} → "
                f"{binding.get('entity_id', 'unknown')}"
            )
            for binding in self.options.get("bindings", [])
            if isinstance(binding, dict) and binding.get("remote_id")
        }

    def _selected_binding(self) -> dict[str, Any] | None:
        """Return the binding selected by the options flow."""
        return next(
            (
                item
                for item in self.options.get("bindings", [])
                if isinstance(item, dict)
                and str(item.get("remote_id", ""))
                == self._selected_binding_remote_id
            ),
            None,
        )

    def _button_action_choices(self, binding: dict[str, Any]) -> dict[str, str]:
        """Enumerate actionable physical buttons using stable page/index IDs."""
        remote_id = str(binding.get("remote_id", ""))
        remote = next(
            (
                item
                for item in self.options.get("remotes", [])
                if isinstance(item, dict)
                and str(item.get("remote_id", "")) == remote_id
            ),
            None,
        )
        if remote is None:
            return {}

        choices: dict[str, str] = {}
        from .studio import remote_pages

        for page in remote_pages(remote, binding):
            for button in page["buttons"]:
                choices[button["button_id"]] = f"{page['name']} · {button['label']}"

        # Never strand an override after a future layout/version change.
        saved = binding.get("button_actions", {})
        if isinstance(saved, dict):
            for button_id in saved:
                choices.setdefault(str(button_id), f"Saved button · {button_id}")
        return choices

    @staticmethod
    def _format_light_mapping(binding: dict[str, Any]) -> str:
        rows = light_rows_from_mapping(binding.get("mappings", {}))
        return "\n".join(
            f"- {row.replace('_', ' ').title()}: {ACTION_LABELS.get(action, action)}"
            for row, action in rows.items()
        )

    async def async_step_remote_bindings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Open whole-remote Home Assistant bindings."""
        return self.async_show_menu(
            step_id="remote_bindings",
            menu_options=["quick_bind", "edit_mappings"],
        )

    async def async_step_quick_bind(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a complete default light mapping in one operation."""
        choices = self._bindable_remote_choices()
        if not choices:
            return self.async_abort(reason="no_bindable_remotes")
        if user_input is not None:
            remote_id = str(user_input["remote_id"])
            self._pending_binding = {
                "remote_id": remote_id,
                "remote_name": choices[remote_id],
                "entity_id": str(user_input["entity_id"]),
                "profile": "light",
                "enabled": True,
                "mappings": light_mapping_from_rows(LIGHT_MAPPING_DEFAULTS),
                "button_actions": {},
            }
            old_binding = next(
                (
                    binding
                    for binding in self.options.get("bindings", [])
                    if isinstance(binding, dict)
                    and str(binding.get("remote_id", "")) == remote_id
                ),
                None,
            )
            if old_binding and isinstance(old_binding.get("button_actions"), dict):
                self._pending_binding["button_actions"] = dict(
                    old_binding["button_actions"]
                )
            return await self.async_step_quick_bind_review()
        return self.async_show_form(
            step_id="quick_bind",
            data_schema=vol.Schema(
                {
                    vol.Required("remote_id"): vol.In(choices),
                    vol.Required("entity_id"): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="light")
                    ),
                }
            ),
        )

    async def async_step_quick_bind_review(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Preview and save the generated mapping."""
        if self._pending_binding is None:
            return await self.async_step_quick_bind()
        if user_input is not None:
            if not user_input["confirm"]:
                self._pending_binding = None
                return await self.async_step_remote_bindings()
            remote_id = self._pending_binding["remote_id"]
            self.options["bindings"] = [
                binding
                for binding in self.options.get("bindings", [])
                if not isinstance(binding, dict)
                or str(binding.get("remote_id", "")) != remote_id
            ]
            self.options["bindings"].append(self._pending_binding)
            self._pending_binding = None
            await self._persist()
            return self.async_create_entry(title="", data=self.options)
        binding = self._pending_binding
        return self.async_show_form(
            step_id="quick_bind_review",
            data_schema=vol.Schema({vol.Required("confirm", default=True): cv.boolean}),
            description_placeholders={
                "remote": str(binding["remote_name"]),
                "entity": str(binding["entity_id"]),
                "mappings": self._format_light_mapping(binding),
            },
        )

    async def async_step_edit_mappings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select one saved binding to edit."""
        choices = self._binding_choices()
        if not choices:
            return self.async_abort(reason="no_bindings")
        if user_input is not None:
            self._selected_binding_remote_id = str(user_input["binding"])
            self._selected_button_id = None
            return await self.async_step_mapping_menu()
        return self.async_show_form(
            step_id="edit_mappings",
            data_schema=vol.Schema({vol.Required("binding"): vol.In(choices)}),
        )

    async def async_step_mapping_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose between the generated light preset and exact button actions."""
        binding = self._selected_binding()
        if binding is None:
            return await self.async_step_edit_mappings()
        return self.async_show_menu(
            step_id="mapping_menu",
            menu_options=["edit_mapping", "edit_button_action"],
            description_placeholders={
                "remote": str(binding.get("remote_name", binding["remote_id"]))
            },
        )

    async def async_step_edit_mapping(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the complete light mapping without rewriting the physical remote."""
        binding = self._selected_binding()
        if binding is None:
            return await self.async_step_edit_mappings()
        current_rows = light_rows_from_mapping(binding.get("mappings", {}))
        if user_input is not None:
            binding["entity_id"] = str(user_input["entity_id"])
            binding["enabled"] = bool(user_input["enabled"])
            binding["mappings"] = light_mapping_from_rows(
                {row: str(user_input[row]) for row in LIGHT_MAPPING_ROWS}
            )
            await self._persist()
            return self.async_create_entry(title="", data=self.options)
        schema: dict[Any, Any] = {
            vol.Required("entity_id", default=binding.get("entity_id")): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="light")
            ),
            vol.Required("enabled", default=binding.get("enabled", True)): cv.boolean,
        }
        for row in LIGHT_MAPPING_ROWS:
            schema[vol.Required(row, default=current_rows[row])] = vol.In(ACTION_LABELS)
        return self.async_show_form(
            step_id="edit_mapping",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "remote": str(binding.get("remote_name", binding["remote_id"])),
            },
        )

    async def async_step_edit_button_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select one exact physical button from the saved remote layout."""
        binding = self._selected_binding()
        if binding is None:
            return await self.async_step_edit_mappings()
        choices = self._button_action_choices(binding)
        if not choices:
            return self.async_abort(reason="button_list_unavailable")
        if user_input is not None:
            self._selected_button_id = str(user_input["button_id"])
            return await self.async_step_configure_button_action()
        return self.async_show_form(
            step_id="edit_button_action",
            data_schema=vol.Schema({vol.Required("button_id"): vol.In(choices)}),
            description_placeholders={
                "remote": str(binding.get("remote_name", binding["remote_id"]))
            },
        )

    async def async_step_configure_button_action(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit a native Home Assistant action sequence for one physical button."""
        binding = self._selected_binding()
        if binding is None:
            return await self.async_step_edit_mappings()
        choices = self._button_action_choices(binding)
        button_id = self._selected_button_id
        if not button_id or button_id not in choices:
            return await self.async_step_edit_button_action()
        saved = binding.get("button_actions", {})
        if not isinstance(saved, dict):
            saved = {}
        existing = saved.get(button_id, [])
        if not isinstance(existing, list):
            existing = []
        errors: dict[str, str] = {}
        if user_input is not None:
            actions = user_input.get("actions", [])
            if not isinstance(actions, list):
                actions = []
            if user_input.get("use_quick_bind_default"):
                saved.pop(button_id, None)
            else:
                try:
                    # Validation compiles templates in-place. Validate a copy so HA options
                    # retain only JSON-serializable selector output.
                    await async_validate_actions_config(self.hass, deepcopy(actions))
                except Exception:  # noqa: BLE001
                    errors["base"] = "invalid_actions"
                else:
                    # An empty list is intentionally retained: it disables this button instead
                    # of falling through to the generated Quick-bind light preset.
                    saved[button_id] = actions
            if not errors:
                binding["button_actions"] = saved
                await self._persist()
                return self.async_create_entry(title="", data=self.options)
        return self.async_show_form(
            step_id="configure_button_action",
            data_schema=vol.Schema(
                {
                    vol.Optional("actions", default=existing): selector.ActionSelector(),
                    vol.Required("use_quick_bind_default", default=False): cv.boolean,
                }
            ),
            errors=errors,
            description_placeholders={
                "remote": str(binding.get("remote_name", binding["remote_id"])),
                "button": choices[button_id],
            },
        )

    async def async_step_refresh_all_remotes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """One-click refresh followed by the merged remote manager view."""
        return await self.async_step_remote_manager()

    async def async_step_test_native_bridge(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verify that HA's other adapter can observe the dedicated fake target."""
        errors: dict[str, str] = {}
        native_target = self._entry.data.get("native_target", {})
        if not isinstance(native_target, dict) or not native_target.get("device_id"):
            errors["base"] = "bridge_not_configured"
        elif user_input is not None and user_input["run"]:
            compact = "".join(
                char for char in str(native_target["device_id"]) if char in "0123456789abcdefABCDEF"
            )
            address = ":".join(compact[index:index + 2] for index in range(0, 12, 2)).upper()
            device = bluetooth.async_ble_device_from_address(
                self.hass, address, connectable=True
            )
            # HA may deliberately omit the MAC addresses of local controllers from its shared
            # advertisement cache. The bridge is exactly such a controller, so fall back to a
            # direct BlueZ scan on the normal HA adapter. This bypasses the local-adapter filter
            # while leaving the dedicated bridge adapter in peripheral mode.
            if device is None:
                device = await BleakScanner.find_device_by_address(
                    address, timeout=12.0, bluez={"adapter": "hci0"}
                )
            if device is None:
                self._bridge_test_status = (
                    f"{address} was not observed by a direct hci0 scan."
                )
                errors["base"] = "bridge_not_found"
            else:
                self._bridge_test_status = (
                    f"Success: {address} is advertising and was observed through hci0. "
                    "The bridge uses a firmware-specific raw ATT server, so standard Bleak "
                    "characteristic discovery is intentionally not used for this test. "
                    "An actual WoRWS button press verifies the ATT/command path."
                )

        return self.async_show_form(
            step_id="test_native_bridge",
            data_schema=vol.Schema({vol.Required("run", default=True): cv.boolean}),
            errors=errors,
            description_placeholders={"status": self._bridge_test_status},
        )

    # -- list-driven manager ---------------------------------------------------------------

    async def async_step_remote_manager(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show inventory and keep add operations separate from existing-remote actions."""
        errors: dict[str, str] = {}
        try:
            await self._refresh_remote_inventory()
        except UrcResponseDecodeError:
            errors["base"] = "communication_key_invalid"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("could not refresh the remote inventory")
            errors["base"] = "inventory_refresh_failed"

        if user_input is not None and not errors:
            action = user_input["action"]
            if action == "refresh":
                return await self.async_step_remote_manager()
            if action == "add":
                return await self.async_step_add_remote_menu()
            if action == "manage":
                return await self.async_step_manage_existing_remote()

        return self.async_show_form(
            step_id="remote_manager",
            data_schema=vol.Schema(
                {
                    vol.Required("action", default="refresh"): vol.In(
                        {
                            "refresh": "Refresh all remotes from device + cloud",
                            "add": "Add remote",
                            "manage": "Edit / recreate remote",
                        }
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"remotes": self._inventory_status},
        )

    async def async_step_add_remote_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a remote kind only after the user explicitly chose Add remote."""
        return self.async_show_menu(
            step_id="add_remote_menu",
            menu_options=[
                "bind_native", "add_ir_remote", "add_remote"
            ],
        )

    async def async_step_manage_existing_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select exactly one existing remote before showing mutating actions."""
        errors: dict[str, str] = {}
        try:
            await self._refresh_remote_inventory()
        except UrcResponseDecodeError:
            errors["base"] = "communication_key_invalid"
        except TimeoutError:
            _LOGGER.warning(
                "could not refresh inventory: WoRWS handshake timed out after retries"
            )
            errors["base"] = "inventory_refresh_failed"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("could not refresh inventory before selecting a remote")
            errors["base"] = "inventory_refresh_failed"

        choices = {
            item["key"]: (
                f"{item['name']} ({item['kind']}, "
                f"{'slot ' + str(item['index']) if item['physical'] else 'cloud only'})"
            )
            for item in self._inventory
        }
        if not choices and not errors:
            return self.async_abort(reason="no_remotes")
        if user_input is not None and not errors:
            selected = user_input["remote"]
            if selected not in choices:
                errors["remote"] = "not_found"
            else:
                self._selected_remote_key = selected
                return await self.async_step_existing_remote_actions()
        return self.async_show_form(
            step_id="manage_existing_remote",
            data_schema=vol.Schema(
                {vol.Required("remote"): vol.In(choices)}
            ),
            errors=errors,
            description_placeholders={"remotes": self._inventory_status},
        )

    async def async_step_existing_remote_actions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show actions only after an existing remote has been selected."""
        item = self._selected_inventory_item()
        if item is None:
            return await self.async_step_manage_existing_remote()
        managed = item.get("managed_item") or {}
        device_type = str(managed.get("device_type", "")).upper()
        if (
            item.get("control_type") == commands.CTRL_NATIVE
            and device_type in commands.NATIVE_DEVTYPE
        ):
            menu_options = ["edit_remote", "customize_native_remote", "delete_managed_remote"]
        else:
            menu_options = ["edit_remote", "recreate_remote", "delete_managed_remote"]
        return self.async_show_menu(
            step_id="existing_remote_actions",
            menu_options=menu_options,
            description_placeholders={
                "remote": f"{item['name']} ({item['kind']})"
            },
        )

    def _selected_inventory_item(self) -> dict[str, Any] | None:
        return next(
            (item for item in self._inventory if item["key"] == self._selected_remote_key),
            None,
        )

    async def async_step_customize_native_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Open any existing native layout in the guided editor."""
        item = self._selected_inventory_item()
        if item is None:
            return await self.async_step_manage_existing_remote()
        managed = item.get("managed_item") or {}
        layout = managed.get("custom_layout")
        target = self._entry.data.get("native_target", {})
        if not isinstance(layout, dict):
            try:
                layout = commands.editable_layout_from_native_profile(
                    str(managed.get("device_type", ""))
                )
            except ValueError:
                return self.async_abort(reason="recreate_not_supported")
        if not isinstance(target, dict):
            return self.async_abort(reason="recreate_not_supported")
        pages = {int(page): list(actions) for page, actions in layout.get("pages", {}).items()}
        page_names = {
            int(page): str(name)
            for page, name in layout.get("page_names", {}).items()
        }
        self._custom_native_draft = {
            "name": managed.get("name", item["name"]),
            "device_id": managed.get("physical_device_id", target.get("device_id", "")),
            "icon": managed.get("icon", target.get("icon", "tv")),
            "target_key": target.get("target_key", ""),
            "main_buttons": commands.normalize_main_buttons(
                layout.get("main_buttons", {})
            ),
            "pages": pages,
            "page_names": {
                page: page_names.get(page, f"Page {'ABCD'[page - 1]}") for page in pages
            },
            "template": str(
                layout.get("template") or managed.get("device_type") or "FAN"
            ),
            "replace_remote_id": managed.get("remote_id"),
        }
        return await self.async_step_custom_native_builder()

    async def async_step_recreate_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit stored metadata, then reinstall the selected remote in an automatic slot."""
        try:
            await self._refresh_remote_inventory()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("could not refresh the table before recreation")
            return self.async_abort(reason="inventory_unavailable")
        item = self._selected_inventory_item()
        if item is None:
            return self.async_abort(reason="no_remotes")
        errors: dict[str, str] = {}
        managed = item.get("managed_item", {})
        target = self._entry.data.get("native_target", {})
        if not isinstance(target, dict):
            target = {}
        if user_input is not None:
            if not user_input["confirm"]:
                return await self.async_step_existing_remote_actions()
            try:
                if item["control_type"] == commands.CTRL_NATIVE:
                    event_remote_id = str(
                        managed.get("remote_id") or uuid.uuid4().hex[:8]
                    )
                    try:
                        target_key = bytes.fromhex(user_input["target_key"])
                        if len(target_key) != 16:
                            errors["target_key"] = "target_key_length"
                    except ValueError:
                        errors["target_key"] = "target_key_hex"
                    try:
                        commands.native_logical_device_id(
                            user_input["device_id"], event_remote_id
                        )
                    except ValueError:
                        errors["device_id"] = "device_id_invalid"
                    if not errors:
                        # Recreate is safe only after the selected physical entry is removed.
                        # Hardware rejects a second native tile that reuses the same target MAC.
                        client = self._client()
                        if client is None:
                            errors["base"] = "not_connected"
                        else:
                            delete_command = commands.build_delete(
                                    remote_index=int(item["index"]),
                                    device_type=int(item["device_type_byte"]),
                                    control_type=int(item["control_type"]),
                                    device_id=item["device_key"],
                                )
                            error = await self._delete_and_verify(
                                client,
                                delete_command,
                                device_type=int(item["device_type_byte"]),
                                control_type=int(item["control_type"]),
                                device_id=str(item["device_key"]),
                            )
                            if error:
                                errors["base"] = error
                    if not errors:
                        return await self.async_step_bind_native(
                            {
                                "name": user_input["name"],
                                "device_id": user_input["device_id"],
                                "device_type": user_input["device_type"],
                                "icon": user_input["icon"],
                                "target_key": user_input["target_key"],
                                "_event_remote_id": event_remote_id,
                                "_replaces_remote_id": event_remote_id,
                            }
                        )
                elif item["control_type"] == commands.CTRL_IR:
                    profile_key = str(managed.get("profile", ""))
                    if profile_key in PROFILES:
                        install_errors, _index = await self._install_ir_profile(
                            PROFILES[profile_key], name=user_input["name"], replace_existing=True
                        )
                        errors.update(install_errors)
                    else:
                        cloud_item = item.get("cloud_item", {})
                        remote_id = cloud_item.get("remoteID")
                        cloud = self._cloud_client()
                        if not remote_id or cloud is None:
                            errors["base"] = "recreate_profile_missing"
                        else:
                            payload = await cloud.get_ir_remote(
                                str(remote_id), str(cloud_item.get("createFrom") or "hub")
                            )
                            downloaded = find_cloud_items(payload)
                            if not downloaded:
                                raise ValueError("queryIrRemote returned no IR record")
                            profile = profile_from_cloud(
                                downloaded[0], remote_id=str(remote_id),
                                name=user_input["name"], metadata=cloud_item,
                            )
                            install_errors, _index = await self._install_ir_profile(
                                profile, name=user_input["name"], replace_existing=True
                            )
                            errors.update(install_errors)
                    if not errors:
                        return await self.async_step_remote_manager()
                elif item["control_type"] == commands.CTRL_HID:
                    if not managed:
                        errors["base"] = "recreate_profile_missing"
                    else:
                        client = self._client()
                        if client is None:
                            errors["base"] = "not_connected"
                        else:
                            delete_command = commands.build_delete(
                                    remote_index=int(item["index"]),
                                    device_type=int(item["device_type_byte"]),
                                    control_type=int(item["control_type"]),
                                    device_id=item["device_key"],
                                )
                            error = await self._delete_and_verify(
                                client,
                                delete_command,
                                device_type=int(item["device_type_byte"]),
                                control_type=int(item["control_type"]),
                                device_id=str(item["device_key"]),
                            )
                            if error:
                                errors["base"] = error
                            else:
                                raw_table = await client.query(0x07)
                                if not raw_table:
                                    errors["base"] = "native_table_timeout"
                                else:
                                    recreated = await client.send_command(
                                        commands.build_remote(
                                            device_type_name=user_input["device_type"],
                                            remote_index=len(commands.parse_added_devices(raw_table)),
                                            name=user_input["name"],
                                            device_id=user_input["device_id"],
                                            icon_name=user_input["icon"],
                                            buttons=user_input["buttons"],
                                        )
                                    )
                                    error = self._resp_error(recreated)
                                    if error:
                                        errors["base"] = error
                                    else:
                                        return await self.async_step_remote_manager()
                else:
                    errors["base"] = "recreate_not_supported"
            except (CloudError, ValueError, KeyError, TypeError, TimeoutError):
                _LOGGER.exception("selected remote recreation failed")
                errors["base"] = "remote_operation_failed"

        if item["control_type"] == commands.CTRL_NATIVE:
            schema = vol.Schema(
                {
                    vol.Required("name", default=(user_input or {}).get(
                        "name", target.get("name", item["name"])
                    )): str,
                    vol.Required("device_id", default=(user_input or {}).get(
                        "device_id", target.get(
                            "device_id", item["device_id_bytes"][:6][::-1].hex()
                        )
                    )): str,
                    vol.Required("device_type", default=(user_input or {}).get(
                        "device_type", target.get("device_type", "STRIP")
                    )): vol.In(commands.SUPPORTED_NATIVE_DEVICE_TYPES),
                    vol.Required("icon", default=(user_input or {}).get(
                        "icon", target.get("icon", "strip")
                    )): vol.In(ICONS),
                    vol.Required("target_key", default=(user_input or {}).get(
                        "target_key", target.get("target_key", "")
                    )): selector.TextSelector(
                        selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                    ),
                    vol.Required("confirm", default=(user_input or {}).get(
                        "confirm", False
                    )): cv.boolean,
                }
            )
        elif item["control_type"] == commands.CTRL_HID:
            schema = vol.Schema(
                {
                    vol.Required("name", default=(user_input or {}).get(
                        "name", managed.get("name", item["name"])
                    )): str,
                    vol.Required("device_type", default=(user_input or {}).get(
                        "device_type", managed.get("device_type", "UNIVERSAL_BLE")
                    )): vol.In(DEVICE_TYPES),
                    vol.Required("icon", default=(user_input or {}).get(
                        "icon", managed.get("icon", "light")
                    )): vol.In(ICONS),
                    vol.Required("device_id", default=(user_input or {}).get(
                        "device_id", managed.get(
                            "device_id", item["device_id_bytes"][:6][::-1].hex()
                        )
                    )): str,
                    vol.Required("buttons", default=(user_input or {}).get(
                        "buttons", managed.get("buttons", DEFAULT_BUTTONS)
                    )): cv.multi_select({name: name for name in buttons_for("UNIVERSAL_BLE")}),
                    vol.Required("confirm", default=(user_input or {}).get(
                        "confirm", False
                    )): cv.boolean,
                }
            )
        else:
            schema = vol.Schema(
                {
                    vol.Required("name", default=(user_input or {}).get(
                        "name", item["name"]
                    )): str,
                    vol.Required("confirm", default=(user_input or {}).get(
                        "confirm", False
                    )): cv.boolean,
                }
            )
        return self.async_show_form(
            step_id="recreate_remote",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "remote": item["name"],
                "kind": item["kind"],
            },
        )

    async def async_step_edit_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Rename by stable id; the current physical slot is never entered by the user."""
        try:
            await self._refresh_remote_inventory()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("could not refresh the table before rename")
            return self.async_abort(reason="inventory_unavailable")
        item = self._selected_inventory_item()
        if item is None or not item["physical"]:
            return self.async_abort(reason="remote_not_on_device")
        errors: dict[str, str] = {}
        if user_input is not None:
            client = self._client()
            if client is None:
                errors["base"] = "not_connected"
            else:
                try:
                    response = await client.send_command(
                        commands.build_rename(
                            remote_index=int(item["index"]),
                            device_type=int(item["device_type_byte"]),
                            control_type=int(item["control_type"]),
                            device_id=item["device_id_bytes"],
                            name=user_input["name"],
                        )
                    )
                    if self._resp_error(response):
                        errors["base"] = "rename_failed"
                    else:
                        cloud_item = item.get("cloud_item", {})
                        if item["control_type"] == commands.CTRL_IR and cloud_item.get("remoteID"):
                            cloud = self._cloud_client()
                            if cloud is not None:
                                await cloud.rename_ir(
                                    str(cloud_item["remoteID"]), user_input["name"],
                                    bool(cloud_item.get("waitModify", False)),
                                )
                        found_local = False
                        for remote in self.options.get("remotes", []):
                            try:
                                same_managed = remote is item.get("managed_item")
                                same_unmanaged_slot = (
                                    not item.get("managed_item")
                                    and stable_id_for_local(str(remote["device_id"])).hex()
                                    == item["device_key"]
                                    and int(remote.get("index", -1)) == int(item["index"])
                                )
                                if same_managed or same_unmanaged_slot:
                                    remote["name"] = user_input["name"]
                                    remote["name_override"] = True
                                    found_local = True
                            except (KeyError, ValueError):
                                continue
                        if not found_local:
                            reverse_hid = {
                                value: key for key, value in commands.DEVTYPE.items()
                            }
                            device_type = (
                                "IR_TV" if item["control_type"] == commands.CTRL_IR
                                else reverse_hid.get(item["device_type_byte"], "UNKNOWN")
                            )
                            stored_id = (
                                item["device_key"] if device_type == "IR_TV"
                                else item["device_id_bytes"][:6][::-1].hex()
                            )
                            self.options["remotes"].append(
                                {
                                    "index": item["index"],
                                    "name": user_input["name"],
                                    "device_type": device_type,
                                    "icon": "tv" if device_type == "IR_TV" else "light",
                                    "device_id": stored_id,
                                    "buttons": [],
                                    "name_override": True,
                                }
                            )
                        await self._persist()
                        return await self.async_step_remote_manager()
                except CloudError:
                    errors["base"] = "cloud_update_failed"
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("remote rename failed")
                    errors["base"] = "remote_operation_failed"
        return self.async_show_form(
            step_id="edit_remote",
            data_schema=vol.Schema(
                {vol.Required("name", default=item["name"]): str}
            ),
            errors=errors,
            description_placeholders={"remote": item["name"]},
        )

    async def async_step_delete_managed_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete the selected stable id using its freshly read physical index."""
        try:
            await self._refresh_remote_inventory()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("could not refresh the table before deletion")
            return self.async_abort(reason="inventory_unavailable")
        item = self._selected_inventory_item()
        if item is None:
            return self.async_abort(reason="no_remotes")
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input["confirm"]:
                return await self.async_step_remote_manager()
            try:
                if item["physical"]:
                    client = self._client()
                    if client is None:
                        errors["base"] = "not_connected"
                    else:
                        delete_command = commands.build_delete(
                                remote_index=int(item["index"]),
                                device_type=int(item["device_type_byte"]),
                                control_type=int(item["control_type"]),
                                device_id=item["device_key"],
                            )
                        error = await self._delete_and_verify(
                            client,
                            delete_command,
                            device_type=int(item["device_type_byte"]),
                            control_type=int(item["control_type"]),
                            device_id=str(item["device_key"]),
                        )
                        if error:
                            errors["base"] = error
                if not errors and item["cloud"]:
                    cloud_item = item.get("cloud_item", {})
                    cloud_id = cloud_item.get("remoteID") or cloud_item.get("deviceID") \
                        or cloud_item.get("thirdPartyDeviceID")
                    cloud = self._cloud_client()
                    if cloud is not None and cloud_id:
                        await cloud.delete_ids([str(cloud_id)])
                if not errors:
                    kept: list[dict[str, Any]] = []
                    for remote in self.options.get("remotes", []):
                        try:
                            matches = remote is item.get("managed_item") or (
                                not item.get("managed_item")
                                and stable_id_for_local(
                                    str(remote.get("device_id", ""))
                                ).hex() == item["device_key"]
                                and int(remote.get("index", -1)) == int(item["index"])
                            )
                        except ValueError:
                            matches = False
                        if not matches:
                            kept.append(remote)
                    self.options["remotes"] = kept
                    await self._persist()
                    return await self.async_step_remote_manager()
            except CloudError:
                errors["base"] = "cloud_update_failed"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("remote deletion failed")
                errors["base"] = "remote_operation_failed"
        return self.async_show_form(
            step_id="delete_managed_remote",
            data_schema=vol.Schema({vol.Required("confirm", default=False): cv.boolean}),
            errors=errors,
            description_placeholders={"remote": item["name"]},
        )

    # -- optional SwitchBot cloud ----------------------------------------------------------

    async def async_step_cloud_account(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Sign in with email/password and discover account metadata automatically."""
        errors: dict[str, str] = {}
        current = self._cloud_settings() or {}
        if user_input is not None:
            candidate = {
                "region": "EU",
                "api_base_url": "",
                "group_id": "",
                "urc_device_id": self._entry.data[CONF_ADDRESS].replace(":", "").upper(),
                "token_device_id": str(current.get("token_device_id") or uuid.uuid4().hex),
                "user_id": "",
                "username": user_input["username"].strip(),
                "access_token": "",
                "refresh_token": "",
            }
            try:
                async def _capture_tokens(access: str, refresh: str) -> None:
                    candidate["access_token"] = access
                    candidate["refresh_token"] = refresh

                cloud = SwitchBotCloudClient(
                    async_get_clientsession(self.hass), candidate, _capture_tokens
                )
                await cloud.login(candidate["username"], user_input["password"])
                homes = await cloud.get_homes()
                self._pending_cloud = candidate
                self._cloud_homes = {
                    str(item["groupID"]): str(
                        item.get("alias") or item.get("groupName") or item["groupID"]
                    )
                    for item in homes
                }
                self._cloud_home_users = {
                    str(item["groupID"]): str(item.get("userID") or "")
                    for item in homes
                }
                if len(self._cloud_homes) == 1:
                    self._select_options_cloud_home(next(iter(self._cloud_homes)))
                    return await self._finish_options_cloud()
                if self._cloud_homes:
                    return await self.async_step_cloud_account_home()
                errors["base"] = "cloud_no_homes"
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning("SwitchBot cloud login failed: %s", err)
                errors["base"] = "cloud_auth_failed"

        return self.async_show_form(
            step_id="cloud_account",
            data_schema=self._cloud_schema(
                {"username": (user_input or {}).get("username", current.get("username", ""))}
            ),
            errors=errors,
        )

    async def async_step_cloud_account_home(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select one friendly home name if the account contains several homes."""
        if self._pending_cloud is None or not self._cloud_homes:
            return await self.async_step_cloud_account()
        if user_input is not None:
            self._select_options_cloud_home(user_input["home"])
            return await self._finish_options_cloud()
        return self.async_show_form(
            step_id="cloud_account_home",
            data_schema=vol.Schema({vol.Required("home"): vol.In(self._cloud_homes)}),
        )

    def _select_options_cloud_home(self, group_id: str) -> None:
        """Apply the selected home and the user identity returned for it."""
        assert self._pending_cloud is not None
        self._pending_cloud["group_id"] = group_id
        if self._cloud_home_users.get(group_id):
            self._pending_cloud["user_id"] = self._cloud_home_users[group_id]

    async def _finish_options_cloud(self) -> ConfigFlowResult:
        """Validate and store discovered cloud settings without storing a password."""
        assert self._pending_cloud is not None
        candidate = self._pending_cloud

        async def _capture_tokens(access: str, refresh: str) -> None:
            candidate["access_token"] = access
            candidate["refresh_token"] = refresh

        try:
            cloud = SwitchBotCloudClient(
                async_get_clientsession(self.hass), candidate, _capture_tokens
            )
            await cloud.get_bindable_devices()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("SwitchBot cloud home validation failed: %s", err)
            return self.async_show_form(
                step_id="cloud_account_home",
                data_schema=vol.Schema({vol.Required("home"): vol.In(self._cloud_homes)}),
                errors={"base": "cloud_home_failed"},
            )
        data = dict(self._entry.data)
        data["cloud"] = candidate
        self.hass.config_entries.async_update_entry(self._entry, data=data)
        return await self.async_step_remote_manager()

    @staticmethod
    def _cloud_schema(values: dict[str, Any]) -> vol.Schema:
        """Simple app-style login; the password is deliberately never persisted."""
        return vol.Schema(
            {
                vol.Required("username", default=values.get("username", "")): str,
                vol.Required("password"): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }
        )

    # -- install IR remotes from cloud, catalog, or captured fallback -----------------------

    async def _install_ir_profile(
        self, profile: Any, *, name: str, replace_existing: bool
    ) -> tuple[dict[str, str], int | None]:
        """Install any profile exposing the IrProfile protocol and persist its stable id."""
        client = self._client()
        if client is None:
            return {"base": "not_connected"}, None

        def _status(text: str) -> None:
            self._ir_status = text

        errors, remote_index, record = await install.install_ir_profile(
            client, profile,
            name=name, replace_existing=replace_existing,
            remotes=self.options.get("remotes", []),
            targets=targets.all_targets(self._entry),
            status=_status,
        )
        if errors or record is None:
            return errors, remote_index
        self.options["remotes"] = [
            remote for remote in self.options["remotes"]
            if remote.get("device_id") != profile.remote_id.hex()
        ]
        self.options["remotes"].append(record)
        await self._persist()
        return {}, remote_index

    async def async_step_add_ir_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the source of the IR profile; slots remain fully automatic."""
        # The bundled catalog is optional; without it only the cloud and captured paths work.
        options = ["ir_saved_cloud", "ir_captured"]
        if catalog_available():
            options.insert(1, "ir_catalog_type")
        return self.async_show_menu(step_id="add_ir_remote", menu_options=options)

    async def async_step_ir_saved_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Download and install an IR remote already saved in the account."""
        cloud = self._cloud_client()
        if cloud is None:
            return self.async_abort(reason="cloud_not_configured")
        records = [
            item for item in self.options.get("cloud_remotes", [])
            if isinstance(item, dict) and item.get("remoteID")
        ]
        if not records:
            try:
                await self._refresh_remote_inventory()
                records = [
                    item for item in self.options.get("cloud_remotes", [])
                    if isinstance(item, dict) and item.get("remoteID")
                ]
            except Exception:  # noqa: BLE001
                _LOGGER.exception("could not refresh cloud remotes before IR install")
        if not records:
            return self.async_abort(reason="cloud_no_ir_remotes")
        errors: dict[str, str] = {}
        choices = {
            str(item["remoteID"]): str(item.get("remoteName") or item["remoteID"])
            for item in records
        }
        if user_input is not None:
            remote_id = user_input["remote_id"]
            metadata = next(item for item in records if str(item["remoteID"]) == remote_id)
            try:
                payload = await cloud.get_ir_remote(
                    remote_id, str(metadata.get("createFrom") or "hub")
                )
                downloaded = find_cloud_items(payload)
                if not downloaded:
                    raise ValueError("queryIrRemote returned no IR record")
                profile = profile_from_cloud(
                    downloaded[0], remote_id=remote_id,
                    name=user_input["name"],
                    metadata=metadata,
                )
                errors, remote_index = await self._install_ir_profile(
                    profile, name=user_input["name"],
                    replace_existing=user_input["replace_existing"],
                )
                if not errors and remote_index is not None:
                    return await self.async_step_remote_manager()
            except (CloudError, ValueError, TypeError):
                _LOGGER.exception("saved cloud IR download failed")
                errors["base"] = "ir_cloud_download_failed"
        selected = (user_input or {}).get("remote_id", next(iter(choices)))
        selected_item = next(
            item for item in records if str(item["remoteID"]) == selected
        )
        return self.async_show_form(
            step_id="ir_saved_cloud",
            data_schema=vol.Schema(
                {
                    vol.Required("remote_id", default=selected): vol.In(choices),
                    vol.Required(
                        "name", default=(user_input or {}).get(
                            "name", selected_item.get("remoteName", "IR remote")
                        )
                    ): str,
                    vol.Required("replace_existing", default=False): cv.boolean,
                }
            ),
            errors=errors,
            description_placeholders={"status": self._ir_status},
        )

    async def async_step_ir_catalog_type(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._cloud_client() is None:
            return self.async_abort(reason="cloud_not_configured")
        if user_input is not None:
            self._catalog_type = int(user_input["remote_type"])
            return await self.async_step_ir_catalog_brand()
        return self.async_show_form(
            step_id="ir_catalog_type",
            data_schema=vol.Schema(
                {vol.Required("remote_type", default=2): vol.In(REMOTE_TYPES)}
            ),
        )

    async def async_step_ir_catalog_brand(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._catalog_type is None:
            return await self.async_step_ir_catalog_type()
        choices = await self.hass.async_add_executor_job(catalog_brands, self._catalog_type)
        if not choices:
            return self.async_abort(reason="catalog_empty")
        if user_input is not None:
            self._catalog_brand = user_input["brand"]
            models = await self.hass.async_add_executor_job(
                catalog_profiles, self._catalog_type, self._catalog_brand
            )
            self._catalog_models = {
                f"{item.hxd_index}:{item.serial}": item for item in models
            }
            return await self.async_step_ir_catalog_model()
        return self.async_show_form(
            step_id="ir_catalog_brand",
            data_schema=vol.Schema(
                {vol.Required("brand", default=choices[0]): _searchable_select(choices)}
            ),
            description_placeholders={"remote_type": REMOTE_TYPES[self._catalog_type]},
        )

    async def async_step_ir_catalog_model(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if not self._catalog_models or self._catalog_type is None:
            return await self.async_step_ir_catalog_brand()
        errors: dict[str, str] = {}
        choices = {
            key: f"{item.model} — {item.hxd_index}"
            for key, item in self._catalog_models.items()
        }
        selected = (user_input or {}).get("model", next(iter(choices)))
        metadata = self._catalog_models[selected]
        if user_input is not None:
            cloud = self._cloud_client()
            assert cloud is not None
            if self._pending_ir_cloud_sync is not None:
                pending = self._pending_ir_cloud_sync
                try:
                    await cloud.create_ir(pending["item"])
                    await cloud.bind_ir(**pending["binding"])
                    self._pending_ir_cloud_sync = None
                    return await self.async_step_remote_manager()
                except CloudError:
                    _LOGGER.exception("retrying catalog IR cloud save failed")
                    errors["base"] = "cloud_update_failed"
                    self._ir_status = "installed locally; cloud save is still pending"
                    return self.async_show_form(
                        step_id="ir_catalog_model",
                        data_schema=vol.Schema(
                            {
                                vol.Required("model", default=selected): _searchable_select(choices),
                                vol.Required("name", default=user_input["name"]): str,
                                vol.Required("replace_existing", default=True): cv.boolean,
                            }
                        ),
                        errors=errors,
                        description_placeholders={"status": self._ir_status},
                    )
            try:
                payload = await cloud.get_ir_model(metadata.hxd_index)
                downloaded = find_cloud_items(payload)
                model_item = next(
                    (
                        item for item in downloaded
                        if str(item.get("itemID", item.get("hxdIndex", "")))
                        == metadata.hxd_index
                    ),
                    downloaded[0] if downloaded else None,
                )
                if model_item is None:
                    raise ValueError("querymodel returned no matching model")
                profile = profile_from_cloud(
                    model_item,
                    remote_id=generate_remote_id(),
                    name=user_input["name"],
                    remote_type=self._catalog_type,
                    metadata=asdict(metadata),
                )
                errors, remote_index = await self._install_ir_profile(
                    profile, name=user_input["name"],
                    replace_existing=user_input["replace_existing"],
                )
                if not errors and remote_index is not None:
                    item = profile.create_cloud_item(
                        remote_index=remote_index, name=user_input["name"]
                    )
                    binding = dict(
                        remote_id=profile.remote_id_text,
                        remote_index=remote_index,
                        name=user_input["name"],
                        remote_type=profile.device_type,
                    )
                    try:
                        await cloud.create_ir(item)
                        await cloud.bind_ir(**binding)
                        return await self.async_step_remote_manager()
                    except CloudError:
                        self._pending_ir_cloud_sync = {
                            "item": item, "binding": binding
                        }
                        self._ir_status = "installed locally; cloud save is pending"
                        errors["base"] = "cloud_update_failed"
            except (CloudError, ValueError, TypeError):
                _LOGGER.exception("catalog IR download failed")
                errors["base"] = "ir_cloud_download_failed"
        return self.async_show_form(
            step_id="ir_catalog_model",
            data_schema=vol.Schema(
                {
                    vol.Required("model", default=selected): _searchable_select(choices),
                    vol.Required(
                        "name", default=(user_input or {}).get(
                            "name", f"{metadata.brand} {metadata.model}"
                        )
                    ): str,
                    vol.Required("replace_existing", default=False): cv.boolean,
                }
            ),
            errors=errors,
            description_placeholders={"status": self._ir_status},
        )

    async def async_step_ir_captured(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Keep the known-good captured profile as an offline fallback."""
        errors: dict[str, str] = {}
        profile_choices = {key: value.title for key, value in PROFILES.items()}
        selected = (user_input or {}).get("profile", next(iter(PROFILES)))
        profile = PROFILES.get(selected, next(iter(PROFILES.values())))
        if user_input is not None:
            errors, remote_index = await self._install_ir_profile(
                profile, name=user_input["name"],
                replace_existing=user_input["replace_existing"],
            )
            if not errors and remote_index is not None:
                return await self.async_step_remote_manager()
        return self.async_show_form(
            step_id="ir_captured",
            data_schema=vol.Schema(
                {
                    vol.Required("profile", default=selected): vol.In(profile_choices),
                    vol.Required(
                        "name", default=(user_input or {}).get("name", profile.default_name)
                    ): str,
                    vol.Required("replace_existing", default=False): cv.boolean,
                }
            ),
            errors=errors,
            description_placeholders={"status": self._ir_status},
        )

    # -- read-only native diagnostics -------------------------------------------------------

    async def async_step_native_diagnostics(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dump the read-only 0F 63 query namespace without Developer Tools."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input["run"]:
                return await self.async_step_init()
            client = self._client()
            if client is None:
                errors["base"] = "not_connected"
            else:
                lines: list[str] = []
                try:
                    for subcommand in range(0x16):
                        raw = await client.query(subcommand, timeout=1.5)
                        value = raw.hex() if raw else "timeout"
                        lines.append(f"{subcommand:02X}: {value}")
                        _LOGGER.info("native diagnostic 0F63%02X -> %s", subcommand, value)
                    self._diagnostic_status = "\n".join(lines)
                except UrcResponseDecodeError:
                    errors["base"] = "communication_key_invalid"
                    self._diagnostic_status = "Encrypted response could not be decoded."
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("native diagnostic query failed")
                    errors["base"] = "native_transport_error"
                    self._diagnostic_status = "Transport error — see Home Assistant log."

        return self.async_show_form(
            step_id="native_diagnostics",
            data_schema=vol.Schema({vol.Required("run", default=False): cv.boolean}),
            errors=errors,
            description_placeholders={"results": self._diagnostic_status},
        )

    # -- update WoRWS communication credentials ---------------------------------------------

    async def async_step_update_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update the rotating WoRWS key/keyId and reload the integration."""
        errors: dict[str, str] = {}
        if user_input is not None:
            candidate = {
                CONF_ADDRESS: self._entry.data[CONF_ADDRESS],
                CONF_KEY_ID: user_input[CONF_KEY_ID],
                CONF_KEY: user_input[CONF_KEY],
            }
            errors = _valid(candidate)
            if not errors:
                new_data = dict(self._entry.data)
                new_data[CONF_KEY_ID] = user_input[CONF_KEY_ID]
                new_data[CONF_KEY] = user_input[CONF_KEY]
                self.hass.config_entries.async_update_entry(self._entry, data=new_data)
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self._entry.entry_id)
                )
                return self.async_create_entry(title="", data=self.options)

        schema = vol.Schema(
            {
                vol.Required(CONF_KEY_ID, default=self._entry.data[CONF_KEY_ID]): str,
                vol.Required(CONF_KEY): selector.TextSelector(
                    selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(
            step_id="update_credentials", data_schema=schema, errors=errors
        )

    # -- bind native target -----------------------------------------------------------------

    async def async_step_custom_native_builder(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start the guided Main/A/B/C/D native-remote layout editor."""
        errors: dict[str, str] = {}
        saved_native = self._entry.data.get("native_target", {})
        if not isinstance(saved_native, dict):
            saved_native = {}
        existing = self._custom_native_draft or {}
        if user_input is not None:
            try:
                key = bytes.fromhex(user_input["target_key"])
                if len(key) != 16:
                    errors["target_key"] = "target_key_length"
            except ValueError:
                errors["target_key"] = "target_key_hex"
            try:
                commands.id_to_bytes(user_input["device_id"])
            except ValueError:
                errors["device_id"] = "device_id_invalid"
            if not errors:
                enabled_pages = sorted(int(page) for page in user_input["pages"])
                old_pages = existing.get("pages", {})
                old_names = existing.get("page_names", {})
                self._custom_native_draft = {
                    "name": user_input["name"],
                    "device_id": user_input["device_id"],
                    "icon": user_input["icon"],
                    "target_key": user_input["target_key"],
                    "main_buttons": commands.normalize_main_buttons(
                        existing.get("main_buttons", {})
                        or ["ON", "OFF", "UP", "DOWN", "OK"]
                    ),
                    "pages": {page: list(old_pages.get(page, [])) for page in enabled_pages},
                    "page_names": {
                        page: str(
                            user_input.get(f"page_{page}_name")
                            or old_names.get(page)
                            or f"Page {'ABCD'[page - 1]}"
                        )
                        for page in enabled_pages
                    },
                    "template": str(existing.get("template") or "FAN"),
                }
                if existing.get("replace_remote_id"):
                    self._custom_native_draft["replace_remote_id"] = existing["replace_remote_id"]
                self._custom_page_queue = list(enabled_pages)
                return await self.async_step_custom_native_main()

        values = user_input or existing
        existing_pages = existing.get("pages", {})
        existing_names = existing.get("page_names", {})
        return self.async_show_form(
            step_id="custom_native_builder",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=values.get("name", "Home Control")): str,
                    vol.Required(
                        "device_id",
                        default=values.get(
                            "device_id",
                            saved_native.get("device_id", self.options.get("native_device_id", "")),
                        ),
                    ): str,
                    vol.Required("icon", default=values.get("icon", "tv")): vol.In(
                        {
                            "light": "Light", "desklamp": "Desk lamp",
                            "floorlamp": "Floor lamp", "ceilinglamp": "Ceiling light",
                            "strip": "LED strip", "switch": "Switch", "tv": "TV / remote",
                        }
                    ),
                    vol.Required(
                        "target_key",
                        default=values.get(
                            "target_key",
                            saved_native.get("target_key", "00112233445566778899aabbccddeeff"),
                        ),
                    ): str,
                    vol.Required(
                        "pages",
                        default=[str(page) for page in existing_pages]
                        or values.get("pages", ["1", "2", "3", "4"]),
                    ): cv.multi_select({"1": "A", "2": "B", "3": "C", "4": "D"}),
                    vol.Optional("page_1_name", default=existing_names.get(1, values.get("page_1_name", "Lights"))): str,
                    vol.Optional("page_2_name", default=existing_names.get(2, values.get("page_2_name", "Climate"))): str,
                    vol.Optional("page_3_name", default=existing_names.get(3, values.get("page_3_name", "Media"))): str,
                    vol.Optional("page_4_name", default=existing_names.get(4, values.get("page_4_name", "Scenes"))): str,
                }
            ),
            errors=errors,
        )

    async def async_step_custom_native_main(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the physical controls shown on the custom main page."""
        if self._custom_native_draft is None:
            return await self.async_step_custom_native_builder()
        reserved = {
            "ABCD"[int(page) - 1]
            for page in self._custom_native_draft.get("pages", {})
        }
        if user_input is not None:
            self._custom_native_draft["main_buttons"] = {
                position: str(user_input[f"slot_{position.lower()}"])
                for position in commands.TAG
                if position not in reserved
                and user_input.get(f"slot_{position.lower()}")
            }
            if self._custom_page_queue:
                return await self.async_step_custom_native_page()
            return await self.async_step_custom_native_review()
        current = commands.normalize_main_buttons(
            self._custom_native_draft.get("main_buttons", {})
        )
        action_names = list(commands.CUSTOM_ACTION_FUNCTIONS)
        for action in current.values():
            if action not in action_names:
                action_names.append(action)
        labels = {"": "Empty"}
        labels.update({name: commands.custom_action_label(name) for name in action_names})
        schema: dict[Any, Any] = {}
        for position in commands.TAG:
            if position in reserved:
                continue
            schema[vol.Optional(
                f"slot_{position.lower()}", default=current.get(position, "")
            )] = vol.In(labels)
        return self.async_show_form(
            step_id="custom_native_main",
            data_schema=vol.Schema(schema),
            description_placeholders={
                "page_links": ", ".join(
                    f"{'ABCD'[page - 1]} — {name}"
                    for page, name in self._custom_native_draft["page_names"].items()
                ) or "None",
            },
        )

    async def async_step_custom_native_page(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one enabled submenu, then advance through the remaining pages."""
        if self._custom_native_draft is None:
            return await self.async_step_custom_native_builder()
        if not self._custom_page_queue:
            return await self.async_step_custom_native_review()
        page = self._custom_page_queue[0]
        errors: dict[str, str] = {}
        if user_input is not None:
            actions = list(user_input["actions"])
            if len(actions) > 18:
                errors["actions"] = "too_many_custom_buttons"
            elif not actions:
                errors["actions"] = "empty_custom_page"
            else:
                self._custom_native_draft["pages"][page] = actions
                self._custom_page_queue.pop(0)
                if self._custom_page_queue:
                    return await self.async_step_custom_native_page()
                return await self.async_step_custom_native_review()
        labels = {
            name: commands.custom_action_label(name)
            for name in commands.CUSTOM_ACTION_FUNCTIONS
        }
        for name in self._custom_native_draft["pages"].get(page, []):
            labels.setdefault(name, commands.custom_action_label(name))
        return self.async_show_form(
            step_id="custom_native_page",
            data_schema=vol.Schema(
                {
                    vol.Required("actions", default=(user_input or {}).get(
                        "actions", self._custom_native_draft["pages"].get(page) or ["ON", "OFF"]
                    )): cv.multi_select(labels)
                }
            ),
            errors=errors,
            description_placeholders={
                "page": "ABCD"[page - 1],
                "name": self._custom_native_draft["page_names"][page],
            },
        )

    def _show_custom_native_review(
        self, errors: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        """Render the native HA review/confirmation page for the current draft."""
        assert self._custom_native_draft is not None
        draft = self._custom_native_draft
        main = commands.normalize_main_buttons(draft["main_buttons"])
        lines = [
            "Main: "
            + (", ".join(f"{position}={action}" for position, action in main.items())
               or "page links only")
        ]
        for page, actions in draft["pages"].items():
            lines.append(
                f"{'ABCD'[page - 1]} — {draft['page_names'][page]}: {', '.join(actions)}"
            )
        return self.async_show_form(
            step_id="custom_native_review",
            data_schema=vol.Schema({vol.Required("confirm", default=True): cv.boolean}),
            errors=errors or {},
            description_placeholders={"layout": "\n".join(lines)},
        )

    async def async_step_custom_native_review(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Review and install the completed custom layout."""
        if self._custom_native_draft is None:
            return await self.async_step_custom_native_builder()
        if user_input is None:
            return self._show_custom_native_review()
        if not user_input["confirm"]:
            self._custom_native_draft = None
            self._custom_page_queue = []
            return await self.async_step_add_remote_menu()
        draft = self._custom_native_draft
        replace_remote_id = draft.get("replace_remote_id")
        if replace_remote_id and not draft.get("replace_deleted"):
            try:
                await self._refresh_remote_inventory()
                item = next(
                    (
                        candidate for candidate in self._inventory
                        if (candidate.get("managed_item") or {}).get("remote_id")
                        == replace_remote_id and candidate.get("physical")
                    ),
                    None,
                )
                client = self._client()
                if item is None or client is None:
                    return self._show_custom_native_review({"base": "remote_not_on_device"})
                delete_command = commands.build_delete(
                        remote_index=int(item["index"]),
                        device_type=int(item["device_type_byte"]),
                        control_type=int(item["control_type"]),
                        device_id=item["device_key"],
                    )
                error = await self._delete_and_verify(
                    client,
                    delete_command,
                    device_type=int(item["device_type_byte"]),
                    control_type=int(item["control_type"]),
                    device_id=str(item["device_key"]),
                )
                if error:
                    return self._show_custom_native_review({"base": error})
                draft["replace_deleted"] = True
            except Exception:  # noqa: BLE001
                _LOGGER.exception("editable native remote replacement failed before install")
                return self._show_custom_native_review({"base": "remote_operation_failed"})
        return await self.async_step_bind_native(
            {
                "name": draft["name"],
                "device_id": draft["device_id"],
                "device_type": "FAN",
                "icon": draft["icon"],
                "target_key": draft["target_key"],
                "_custom_layout": {
                    "layout_version": 2,
                    "main_buttons": dict(
                        commands.normalize_main_buttons(draft["main_buttons"])
                    ),
                    "pages": {str(page): list(actions) for page, actions in draft["pages"].items()},
                    "page_names": {
                        str(page): name for page, name in draft["page_names"].items()
                    },
                    "template": str(draft.get("template") or "FAN"),
                },
                "_event_remote_id": replace_remote_id,
            }
        )

    async def async_step_bind_native(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Provision a fake native target and bind every page of its decoded layout."""
        errors: dict[str, str] = {}
        if user_input is not None:
            target_key = b""
            try:
                target_key = bytes.fromhex(user_input["target_key"])
                if len(target_key) != 16:
                    errors["target_key"] = "target_key_length"
            except ValueError:
                errors["target_key"] = "target_key_hex"
            try:
                commands.id_to_bytes(user_input["device_id"])
            except ValueError:
                errors["device_id"] = "device_id_invalid"
            client = self._client()
            if client is None:
                errors["base"] = "not_connected"
            elif not errors:
                try:
                    event_remote_id = str(
                        user_input.get("_event_remote_id") or uuid.uuid4().hex[:8]
                    )
                    logical_device_id = commands.native_logical_device_id(
                        user_input["device_id"], event_remote_id
                    )
                    raw_table = await client.query(0x07)
                    if not raw_table:
                        errors["base"] = "native_table_timeout"
                        raise RuntimeError("device-table query timed out")
                    entries = commands.parse_added_devices(raw_table)
                    target_device_id = bytes.fromhex(logical_device_id)
                    if any(
                        control_type == commands.CTRL_NATIVE
                        and device_id == target_device_id
                        for _, _, control_type, device_id in entries
                    ):
                        # Live hardware returns 02 for every page of a second native tile using
                        # the same MAC. V3 remote_id metadata distinguishes buttons inside one
                        # tile; it cannot create another independently connectable BLE target.
                        errors["base"] = "native_target_mac_in_use"
                        self._native_status = "target MAC already belongs to a native tile"
                        raise RuntimeError("native target MAC is already installed")
                    remote_index = len(entries)
                    custom_layout = user_input.get("_custom_layout")
                    if custom_layout:
                        stages = commands.build_custom_native_bind_sequence(
                            key_id=0x01,
                            target_key=target_key,
                            remote_index=remote_index,
                            name=user_input["name"],
                            device_id=logical_device_id,
                            icon_name=user_input["icon"],
                            event_remote_id=event_remote_id,
                            main_buttons=commands.normalize_main_buttons(
                                custom_layout["main_buttons"]
                            ),
                            page_buttons={
                                int(page): list(actions)
                                for page, actions in custom_layout["pages"].items()
                            },
                        )
                    else:
                        stages = commands.build_native_bind_sequence(
                            # 0x01 is the fixed selector observed in every successful native bind.
                            # Exposing it as a configurable key ID allowed the WoRWS communication
                            # key ID (for example 0x95) to be entered here, which firmware rejects
                            # as malformed (0x04).
                            key_id=0x01,
                            target_key=target_key,
                            device_type_name=user_input["device_type"],
                            remote_index=remote_index,
                            name=user_input["name"],
                            device_id=logical_device_id,
                            icon_name=user_input["icon"],
                            # The native direct-BLE path is firmware mode 0. Do not make this a
                            # user-selectable byte: the remote accepts other values during bind,
                            # but then does not connect to the target on button presses.
                            control_mode=0,
                            event_remote_id=event_remote_id,
                        )
                    responses = await client.send_command_sequence(
                        tuple(plaintext for _, plaintext in stages),
                        timeout=35.0,
                        timeout_retries=3,
                    )
                    for (stage, _), resp in zip(stages, responses):
                        err = self._resp_error(resp)
                        self._native_status = f"{stage}: {resp.hex() if resp else 'timeout'}"
                        log = _LOGGER.warning if err else _LOGGER.info
                        log("native UI bind stage %s -> %s", stage,
                            resp.hex() if resp else "timeout")
                        if err:
                            # Preserve stage-specific timeout guidance, but show known device
                            # rejection codes directly. UrcClient has already performed the one
                            # safe cloud-credential refresh/retry for 0x04; another UI-level
                            # refresh here would create an endless "retry the operation" loop for
                            # a genuine command-format error.
                            errors["base"] = (
                                f"native_{stage}_timeout" if not resp else err
                            )
                            break
                except UrcResponseDecodeError:
                    errors["base"] = "communication_key_invalid"
                    self._native_status = "encrypted response could not be decoded"
                except Exception:  # noqa: BLE001
                    if errors:
                        pass
                    else:
                        _LOGGER.exception("native target bind failed with a transport error")
                        errors["base"] = "native_transport_error"
                        self._native_status = "transport error — see Home Assistant log"

                if not errors:
                    kept_remotes: list[dict[str, Any]] = []
                    for remote in self.options["remotes"]:
                        if remote.get("remote_id") == event_remote_id:
                            continue
                        kept_remotes.append(remote)
                    self.options["remotes"] = kept_remotes
                    stored_remote = {
                            "index": remote_index,
                            "name": user_input["name"],
                            "device_type": user_input["device_type"],
                            "icon": user_input["icon"],
                            "device_id": logical_device_id,
                            "physical_device_id": user_input["device_id"],
                            "remote_id": event_remote_id,
                            "buttons": [],
                        }
                    if user_input.get("_custom_layout"):
                        stored_remote["custom_layout"] = user_input["_custom_layout"]
                    self.options["remotes"].append(stored_remote)
                    self.options["native_device_id"] = user_input["device_id"]
                    self.options["native_key_id"] = "01"
                    # Needed to restore this locally managed target if a future full IR sync
                    # unexpectedly removes it. Config-entry data is HA's normal credential
                    # store; never expose this value in logs or descriptions.
                    targets.remember_target(self.hass, self._entry, {
                        "name": user_input["name"],
                        "device_id": user_input["device_id"],
                        "device_type": user_input["device_type"],
                        "icon": user_input["icon"],
                        "control_mode": 0,
                        "target_key_id": "01",
                        "target_key": user_input["target_key"],
                    })
                    await self._persist()
                    if user_input.get("_custom_layout"):
                        self._custom_native_draft = None
                        self._custom_page_queue = []
                    return await self.async_step_remote_manager()

        if user_input is not None and user_input.get("_custom_layout") and errors:
            return self._show_custom_native_review(errors)

        values = user_input or {}
        saved_native = self._entry.data.get("native_target", {})
        schema = vol.Schema(
            {
                vol.Required(
                    "name", default=values.get("name", saved_native.get("name", "HASS Bridge"))
                ): str,
                vol.Required(
                    "device_id",
                    default=values.get(
                        "device_id", saved_native.get(
                            "device_id", self.options.get("native_device_id", "")
                        )
                    ),
                ): str,
                vol.Required(
                    "device_type", default=values.get(
                        "device_type", saved_native.get("device_type", "STRIP")
                    )
                ): vol.In(commands.SUPPORTED_NATIVE_DEVICE_TYPES),
                vol.Required(
                    "icon", default=values.get("icon", saved_native.get("icon", "strip"))
                ): vol.In(ICONS),
                vol.Required(
                    "target_key",
                    default=values.get(
                        "target_key",
                        saved_native.get("target_key", "00112233445566778899aabbccddeeff"),
                    ),
                ): str,
            }
        )
        return self.async_show_form(
            step_id="bind_native",
            data_schema=schema,
            errors=errors,
            description_placeholders={"status": self._native_status},
        )

    # -- add remote --------------------------------------------------------------------------

    async def async_step_add_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = self._client()
            if client is None:
                errors["base"] = "not_connected"
            else:
                device_type = user_input["device_type"]
                try:
                    raw_table = await client.query(0x07)
                    if not raw_table:
                        errors["base"] = "native_table_timeout"
                    else:
                        index = len(commands.parse_added_devices(raw_table))
                        plaintext = commands.build_remote(
                            device_type_name=device_type,
                            remote_index=index,
                            name=user_input["name"],
                            device_id=user_input["device_id"],
                            icon_name=user_input["icon"],
                            buttons=user_input["buttons"],
                        )
                        resp = await client.send_command(plaintext)
                        err = self._resp_error(resp)
                        if err:
                            errors["base"] = err
                        else:
                            self.options["remotes"].append(
                                {
                                    "index": index,
                                    "name": user_input["name"],
                                    "device_type": device_type,
                                    "icon": user_input["icon"],
                                    "device_id": user_input["device_id"],
                                    "remote_id": uuid.uuid4().hex[:8],
                                    "buttons": user_input["buttons"],
                                }
                            )
                            await self._persist()
                            return await self.async_step_remote_manager()
                except Exception:  # noqa: BLE001
                    _LOGGER.exception("HID remote creation failed")
                    errors["base"] = "remote_operation_failed"

        buttons = buttons_for("UNIVERSAL_BLE")
        schema = vol.Schema(
            {
                vol.Required("name", default="New HID remote"): str,
                vol.Required("device_type", default=DEVICE_TYPES[0]): vol.In(DEVICE_TYPES),
                vol.Required("icon", default=ICONS[0]): vol.In(ICONS),
                vol.Required("device_id", default=self.options.get("host_mac", "")): str,
                vol.Required("buttons", default=DEFAULT_BUTTONS): cv.multi_select(
                    {b: b for b in buttons}
                ),
            }
        )
        return self.async_show_form(
            step_id="add_remote", data_schema=schema, errors=errors,
        )

    # -- remove remote -----------------------------------------------------------------------

    async def async_step_remove_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        remotes = self.options["remotes"]
        if not remotes:
            return self.async_abort(reason="no_remotes")

        if user_input is not None:
            client = self._client()
            if client is None:
                errors["base"] = "not_connected"
            else:
                index = int(user_input["remote"])
                rec = next((r for r in remotes if r["index"] == index), None)
                if rec is None:
                    errors["base"] = "not_found"
                else:
                    plaintext = commands.build_delete(
                        remote_index=index,
                        device_type=commands.devtype_byte(rec["device_type"]),
                        control_type=commands.control_type_for(rec["device_type"]),
                        device_id=rec["device_id"],
                    )
                    resp = await client.send_command(plaintext)
                    err = self._resp_error(resp)
                    if err:
                        errors["base"] = err
                    else:
                        self.options["remotes"] = [
                            r for r in remotes if r["index"] != index
                        ]
                        await self._persist()
                        return await self.async_step_init()

        choices = {str(r["index"]): f"{r['index']}: {r['name']}" for r in remotes}
        schema = vol.Schema({vol.Required("remote"): vol.In(choices)})
        return self.async_show_form(
            step_id="remove_remote", data_schema=schema, errors=errors
        )

    # -- pair host ---------------------------------------------------------------------------

    async def async_step_pair_host(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = self._client()
            if client is None:
                errors["base"] = "not_connected"
            else:
                resp = await client.send_command(
                    commands.build_hid_pair(user_input["host_mac"])
                )
                err = self._resp_error(resp)
                if err:
                    errors["base"] = err
                else:
                    self.options["host_mac"] = user_input["host_mac"]
                    await self._persist()
                    return await self.async_step_init()

        schema = vol.Schema(
            {vol.Required("host_mac", default=self.options.get("host_mac", "")): str}
        )
        return self.async_show_form(
            step_id="pair_host", data_schema=schema, errors=errors
        )
