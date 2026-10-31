"""Device-mutating operations shared by the options flow and Remote Studio.

Installing an IR profile and deleting a row used to live as methods on the options flow, so
Remote Studio could not reuse them and grew its own thinner versions instead. They are plain
functions here, taking the pieces they need, so both entry points run exactly the same
destructive sequences — including the delete preflight and the post-sync restoration of locally
managed HID/native remotes, both of which were learnt from hardware and must not be reimplemented.
"""
from __future__ import annotations

import logging
from typing import Any

from . import commands
from .catalog import DEFAULT_BUTTONS
from .client import (
    UrcConnectionSetupError,
    UrcHandshakeTimeout,
    UrcPreflightQueryTimeout,
    UrcPreflightRejected,
    UrcResponseDecodeError,
)
from .const import RESP_OK
from .inventory import deletion_verified, stable_id_for_local

_LOGGER = logging.getLogger(__name__)

RESP_ERRORS = {
    0x02: "resp_value_err",
    0x04: "resp_format_err",
    0x11: "resp_hid_no_pair",
}


def resp_error(resp: bytes) -> str | None:
    if not resp:
        return "no_reply"
    if resp[0] == RESP_OK:
        return None
    return RESP_ERRORS.get(resp[0], "resp_unknown")


def delete_resp_error(resp: bytes, command: bytes) -> str | None:
    """Preserve the firmware's real DELETE status instead of hiding it."""
    error = resp_error(resp)
    if error:
        _LOGGER.warning(
            "WoRWS DELETE failed: response=%s plaintext=%s error=%s",
            resp.hex() if resp else "timeout", command.hex(), error,
        )
    return error


async def delete_and_verify(
    client: Any, command: bytes, *, device_type: int, control_type: int, device_id: str
) -> str | None:
    """Delete once, then prove completion from the table if its ACK was lost.

    DELETE is destructive and compacts later slots. Retrying the same bytes after an
    acknowledgement timeout can therefore target a different remote. Read the table before
    the one allowed write and, on a missing ACK only, accept success when exactly one matching
    physical row disappeared.
    """
    target_id = stable_id_for_local(device_id)
    expected_index = command[4] if len(command) > 4 else -1
    # Native rows delete like any other, but the firmware's key entry is keyed on the six-byte
    # address rather than on the profile, so `c724` takes the key away from every other native
    # profile aiming at the same address. Callers deleting a native row must therefore run
    # `reassociate_shared_target` afterwards. (A `0x04` seen here is the ordinary format/session
    # error, not a refusal to delete native rows.)

    def _target_exists(raw: bytes) -> bool:
        return any(
            (index, item_type, item_control, item_id)
            == (expected_index, int(device_type), int(control_type), target_id)
            for index, item_type, item_control, item_id in commands.parse_added_devices(raw)
        )

    # Perform the authenticated handshake first, then read the table and issue the single
    # DELETE on that same connection.  A separate query connection immediately before the
    # handshake made real WoRWS hardware accept GATT but withhold its random notification.
    try:
        before_raw, response = await client.send_command_with_preflight_query(
            command,
            subcommand=0x07,
            query_timeout=20.0,
            command_timeout=10.0,
            prewrite_retries=3,
            refresh_credentials=True,
            preflight_check=_target_exists,
        )
    except UrcPreflightRejected:
        _LOGGER.warning(
            "refusing DELETE because its exact type/control/id identity is absent from "
            "the fresh 0F6307 table: plaintext=%s", command.hex(),
        )
        return "not_found"
    except UrcHandshakeTimeout:
        if getattr(client, "_bridge_pause_unacked", False):
            _LOGGER.warning(
                "WoRWS DELETE was not sent: the handshake timed out and the add-on never "
                "acknowledged the MQTT pause, so the remote is still bonded to the fake "
                "device. plaintext=%s", command.hex(),
            )
            return "native_bridge_not_paused"
        _LOGGER.warning(
            "WoRWS DELETE was not sent because the pre-command handshake timed out: "
            "plaintext=%s", command.hex(),
        )
        return "native_handshake_timeout"
    except UrcPreflightQueryTimeout:
        _LOGGER.warning(
            "WoRWS DELETE was not sent because the authenticated 0F6307 table query "
            "timed out: plaintext=%s", command.hex(),
        )
        return "native_table_timeout"
    except UrcConnectionSetupError:
        _LOGGER.warning(
            "WoRWS DELETE was not sent because BLE setup failed: plaintext=%s", command.hex(),
        )
        return "native_transport_error"
    if not before_raw:
        return "native_table_timeout"
    before = commands.parse_added_devices(before_raw)
    before_count = sum(
        1 for _index, item_type, item_control, item_id in before
        if (item_type, item_control, item_id) == (int(device_type), int(control_type), target_id)
    )
    # The callback above checked this exact identity before the write on this same session.
    assert before_count > 0
    if response:
        return delete_resp_error(response, command)

    after_raw = await client.query(0x07)
    if before_raw and after_raw:
        after = commands.parse_added_devices(after_raw)
        after_count = sum(
            1 for _index, item_type, item_control, item_id in after
            if (item_type, item_control, item_id)
            == (int(device_type), int(control_type), target_id)
        )
        if deletion_verified(
            before, after,
            device_type=device_type, control_type=control_type, device_id=target_id,
        ):
            _LOGGER.warning(
                "WoRWS DELETE acknowledgement was lost, but 0F6307 verified removal: "
                "plaintext=%s rows=%d->%d matching=%d->%d",
                command.hex(), len(before), len(after), before_count, after_count,
            )
            return None
        _LOGGER.warning(
            "WoRWS DELETE had no acknowledgement and 0F6307 did not prove removal: "
            "before=%s after=%s", before_raw.hex(), after_raw.hex(),
        )
    return delete_resp_error(response, command)


async def reassociate_shared_target(client: Any, device_id: str) -> bytes | None:
    """Restore the target-key association when another native row still uses the address.

    Deleting a native remote releases the target-key entry, and that entry is keyed on the
    six-byte BLE address, not on the remote. Any surviving native profile on the same address
    would otherwise lose its key and stop right after service discovery.
    """
    try:
        entries = commands.parse_added_devices(await client.query(0x07))
    except (ValueError, TypeError) as err:
        _LOGGER.warning("could not re-check the device table after deleting: %s", err)
        return None
    address = commands.id_to_bytes(device_id)[:6]
    survivors = [
        entry for entry in entries
        if entry[2] == commands.CTRL_NATIVE and entry[3][:6] == address
    ]
    if not survivors:
        return None
    _LOGGER.info(
        "slot(s) %s still target %s; re-associating the shared target key",
        ", ".join(str(entry[0]) for entry in survivors),
        ":".join(f"{byte:02X}" for byte in reversed(address)),
    )
    return await client.send_command(commands.build_associate_target_key(0x01, device_id))


async def restore_managed_after_sync(
    client: Any, *, remotes: list[dict[str, Any]], targets: list[dict[str, Any]]
) -> None:
    """Recreate locally managed HID/native entries if a full IR sync removed them."""
    raw = await client.query(0x07)
    if not raw:
        raise RuntimeError("post-sync device table timeout")
    entries = commands.parse_added_devices(raw)
    present: dict[tuple[bytes, int, int], int] = {}
    for _index, dev_type, control_type, item_id in entries:
        signature = (item_id, dev_type, control_type)
        present[signature] = present.get(signature, 0) + 1
    for remote in sorted(
        remotes,
        key=lambda item: item.get("index") if isinstance(item.get("index"), int) else 0x10000,
    ):
        device_type = str(remote.get("device_type", ""))
        if device_type == "IR_TV" or device_type.startswith("IR_"):
            continue
        try:
            expected = stable_id_for_local(str(remote["device_id"]))
            expected_type = commands.devtype_byte(device_type)
            expected_control = commands.control_type_for(device_type)
        except (KeyError, ValueError):
            continue
        signature = (expected, expected_type, expected_control)
        if present.get(signature, 0):
            present[signature] -= 1
            continue
        index = len(entries)
        if device_type in commands.NATIVE_DEVTYPE:
            # Each native remote belongs to the bridge whose address it was bound to.
            wanted = str(remote.get("physical_device_id") or "").replace(":", "").lower()
            native_target = next(
                (target for target in targets
                 if str(target.get("device_id", "")).replace(":", "").lower() == wanted),
                targets[0] if targets else {},
            )
            physical_device_id = str(
                remote.get("physical_device_id") or native_target.get("device_id", "")
            )
            if not native_target or not physical_device_id:
                raise RuntimeError("native recovery credentials are unavailable")
            custom_layout = remote.get("custom_layout")
            if custom_layout:
                stages = commands.build_custom_native_bind_sequence(
                    key_id=0x01,
                    target_key=bytes.fromhex(str(native_target["target_key"])),
                    remote_index=index,
                    name=str(remote.get("name", "Home Control")),
                    device_id=str(remote["device_id"]),
                    icon_name=str(remote.get("icon", "tv")),
                    event_remote_id=str(remote["remote_id"]),
                    main_buttons=commands.normalize_main_buttons(custom_layout["main_buttons"]),
                    page_buttons={
                        int(page): list(actions)
                        for page, actions in custom_layout["pages"].items()
                    },
                )
            else:
                stages = commands.build_native_bind_sequence(
                    # Captured native provisioning uses the fixed selector 0x01 here. This is
                    # not the WoRWS communication key ID (commonly 0x95) and is not a user slot.
                    key_id=0x01,
                    target_key=bytes.fromhex(str(native_target["target_key"])),
                    device_type_name=device_type,
                    remote_index=index,
                    name=str(remote.get("name", native_target.get("name", "HASS Bridge"))),
                    device_id=str(remote["device_id"]),
                    icon_name=str(remote.get("icon", native_target.get("icon", "strip"))),
                    # Native targets are direct BLE peers. Firmware only takes the
                    # connect-and-send path for mode 0; other values can still be accepted
                    # while binding but never cause a connection when a button is pressed.
                    control_mode=0,
                    event_remote_id=remote.get("remote_id"),
                )
            responses = await client.send_command_sequence(
                tuple(command for _stage, command in stages), timeout=35.0, timeout_retries=3,
            )
            if len(responses) != len(stages) or any(
                not response or response[0] != RESP_OK for response in responses
            ):
                raise RuntimeError("native remote restoration was rejected")
        elif device_type in commands.DEVTYPE:
            response = await client.send_command(
                commands.build_remote(
                    device_type_name=device_type,
                    remote_index=index,
                    name=str(remote.get("name", f"Remote {index}")),
                    device_id=str(remote["device_id"]),
                    icon_name=str(remote.get("icon", "light")),
                    buttons=list(remote.get("buttons", DEFAULT_BUTTONS)),
                )
            )
            if not response or response[0] != RESP_OK:
                raise RuntimeError("HID remote restoration was rejected")
        else:
            continue
        entries.append((index, expected_type, expected_control, expected))


async def install_ir_profile(
    client: Any,
    profile: Any,
    *,
    name: str,
    replace_existing: bool,
    remotes: list[dict[str, Any]],
    targets: list[dict[str, Any]],
    status: Any = None,
) -> tuple[dict[str, str], int | None, dict[str, Any] | None]:
    """Install any profile exposing the IrProfile protocol.

    Returns ``(errors, remote_index, record)``. The caller persists ``record`` into its own
    options, because the options flow and Studio store them through different machinery; the
    device-side sequence is identical for both.
    """
    def _status(text: str) -> None:
        if status is not None:
            status(text)

    errors: dict[str, str] = {}
    try:
        raw_table = await client.query(0x07)
        if not raw_table:
            return {"base": "ir_table_timeout"}, None, None
        entries = commands.parse_added_devices(raw_table)
        duplicates = [entry for entry in entries if entry[3] == profile.remote_id]
        if duplicates and not replace_existing:
            return {"replace_existing": "ir_duplicate_requires_replace"}, None, None
        for index, dev_type, control_type, _entry_id in sorted(
            duplicates, key=lambda entry: entry[0], reverse=True
        ):
            delete_command = commands.build_delete(
                remote_index=index,
                device_type=dev_type,
                control_type=control_type,
                device_id=profile.remote_id.hex(),
            )
            error = await delete_and_verify(
                client, delete_command,
                device_type=int(dev_type), control_type=int(control_type),
                device_id=profile.remote_id.hex(),
            )
            _status(f"delete duplicate slot {index}: {'verified' if error is None else error}")
            if error:
                return {"base": error}, None, None
        if duplicates:
            raw_table = await client.query(0x07)
            if not raw_table:
                return {"base": "ir_table_timeout"}, None, None
            entries = commands.parse_added_devices(raw_table)
            if any(entry[3] == profile.remote_id for entry in entries):
                return {"base": "ir_delete_failed"}, None, None

        remote_index = len(entries)
        stages = profile.build_install(
            remote_index=remote_index, name=name, remote_count=len(entries) + 1
        )
        responses = await client.send_command_sequence(
            tuple(command for _stage, command, _accepted in stages),
            timeout=45.0,
            timeout_retries=3,
            accepted_codes=tuple(accepted for _stage, _command, accepted in stages),
        )
        for (stage, _command, accepted), response in zip(stages, responses):
            shown = response.hex() if response else "timeout"
            _status(f"{stage}: {shown}")
            _LOGGER.info("IR profile install stage %s -> %s", stage, shown)
            if not response:
                errors["base"] = "ir_install_timeout"
                break
            if response[0] not in accepted:
                errors["base"] = "ir_install_rejected"
                break
        if len(responses) != len(stages) and not errors:
            errors["base"] = "ir_install_rejected"
        if errors:
            return errors, None, None

        await restore_managed_after_sync(client, remotes=remotes, targets=targets)
        record = {
            "index": remote_index,
            "name": name,
            "device_type": f"IR_{profile.device_type}",
            "icon": "tv" if profile.device_type == 2 else "light",
            "device_id": profile.remote_id.hex(),
            "remote_id": getattr(profile, "remote_id_text", "") or profile.remote_id.hex(),
            "studio_pages": commands.studio_pages_from_packets(tuple(
                packet for stage, packet, _ in stages if stage.startswith("ir_page_")
            )),
            "physical_packets": [
                packet.hex() for stage, packet, _ in stages if stage.startswith("ir_page_")
            ],
            "ir_code_bank": profile.code_bank.hex(),
            "buttons": [],
            "profile": profile.key,
        }
        return {}, remote_index, record
    except UrcResponseDecodeError:
        _status("encrypted response could not be decoded")
        return {"base": "communication_key_invalid"}, None, None
    except Exception:  # noqa: BLE001
        _LOGGER.exception("IR profile install failed")
        _status("transport error — see Home Assistant log")
        return {"base": "ir_transport_error"}, None, None
