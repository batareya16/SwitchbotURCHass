"""Create and edit the Matter text remote, and deliver its A-D presses to Home Assistant.

The remote has four captions. A press never leaves the remote as a command: the remote only
advertises it, so Home Assistant listens passively and fires the normal button event. That event
reaches the same action editor every other remote uses (``button_actions`` in the binding).
"""
from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant.components import bluetooth, websocket_api
from homeassistant.core import callback

from . import commands as c
from . import install
from .catalog import ICON_CHOICES
from .const import CONF_ADDRESS, DOMAIN, EVENT_BUTTON
from .matter_text import (
    COMPANY_ID,
    CONTROL_TYPE,
    LETTERS,
    STUDIO_DEVICE_TYPE,
    MIN_INTERVAL_DEFAULT,
    MatterPressTracker,
    build_matter_create,
    fit_caption,
    is_matter_row,
    is_template,
    new_device_id,
    normalize_captions,
    normalize_interval,
)
from .studio_physical import read_device_table
from .studio_remotes import _client, new_remote_id, remote_management_lock

_LOGGER = logging.getLogger(__name__)


def matter_remote(entry) -> dict[str, Any] | None:
    """The one text remote this Universal Remote can show (the firmware takes the first)."""
    return next(
        (remote for remote in entry.options.get("remotes", [])
         if isinstance(remote, dict) and remote.get("device_type") == STUDIO_DEVICE_TYPE),
        None,
    )


def captions_of(remote: dict[str, Any]) -> tuple[str, ...]:
    try:
        return normalize_captions(remote.get("matter_captions"))
    except ValueError:
        return tuple(LETTERS)


async def _send(client, packet: bytes) -> None:
    response = await client.send_command(packet)
    if error := install.resp_error(response):
        raise ValueError(f"the remote rejected the text remote ({error})")


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): f"{DOMAIN}/studio/matter/save",
    vol.Required("entry_id"): str,
    vol.Required("captions"): [str],
    vol.Optional("name"): str,
    vol.Optional("remote_id"): str,
    vol.Optional("icon"): vol.In(ICON_CHOICES),
    vol.Optional("min_interval"): int,
})
@websocket_api.async_response
async def ws_save_matter(hass, connection, msg):
    """Install the text remote, or rewrite its four captions."""
    async with remote_management_lock(hass):
        try:
            result = await _save(hass, msg)
        except Exception as err:  # noqa: BLE001 - the panel shows the message as-is
            _LOGGER.exception("Remote Studio text remote save failed")
            connection.send_error(msg["id"], "matter_save_failed", str(err))
            return
    connection.send_result(msg["id"], result)


def render_caption(hass, text: str) -> str:
    """Render one caption template now, cut to what the field holds."""
    from homeassistant.helpers.template import Template  # noqa: PLC0415

    try:
        return fit_caption(Template(text, hass).async_render(parse_result=False))
    except Exception as err:  # noqa: BLE001 - the editor shows the template's own message
        raise ValueError(f"The template {text!r} does not render: {err}") from err


def prepare_captions(hass, fields) -> tuple[list[str], tuple[str, ...]]:
    """Split what the editor sent into template sources and the captions to write now.

    A field holding a template is rendered here, so a broken one is refused before anything is
    written; a plain field is checked exactly as before.
    """
    if not isinstance(fields, (list, tuple)) or len(fields) != 4:
        raise ValueError("A text remote has four captions, A to D")
    templates = [str(item).strip() if is_template(item) else "" for item in fields]
    texts = [render_caption(hass, template) if template else item
             for template, item in zip(templates, fields)]
    return templates, normalize_captions(texts)


def _find_row(existing: dict[str, Any], table) -> tuple | None:
    # Slots shift when an earlier remote is deleted, so the stored index can be stale. The
    # id is what the device keeps, so find the row by it and fall back to the slot only.
    on_device = [row for row in table if is_matter_row(row)]
    identity = c.id_to_bytes(existing["device_id"])
    return (next((item for item in on_device if item[3] == identity), None)
            or next((item for item in on_device if item[0] == existing.get("index")), None))


async def _rewrite_existing(
    hass, entry, client, existing, row, captions, icon_code: int, updates: dict[str, Any],
) -> bytes:
    """Resend the whole text remote with new captions and save what was written."""
    packet = build_matter_create(
        remote_index=row[0], device_id=existing["device_id"],
        name=str(existing.get("name") or "Accessory"), captions=captions, icon=icon_code,
    )
    await _send(client, packet)
    after = await read_device_table(hass, entry, client)
    if not any(is_matter_row(item) and item[0] == row[0] and item[3] == row[3] for item in after):
        raise ValueError("The remote no longer lists the text remote after the update")
    remotes = deepcopy(list(entry.options.get("remotes", [])))
    for remote in remotes:
        if remote.get("remote_id") == existing["remote_id"]:
            remote.update({
                "index": row[0], "matter_captions": list(captions),
                "physical_packets": [packet.hex()], "icon_code": icon_code, **updates,
            })
    hass.config_entries.async_update_entry(entry, options={**entry.options, "remotes": remotes})
    return packet


async def write_live_captions(hass, entry, captions: tuple[str, ...]) -> None:
    """Write already rendered captions to the existing text remote (the live-caption path).

    Name, icon and slot stay as they are. Callers hold the remote-management lock.
    """
    client = _client(hass, entry)
    existing = matter_remote(entry)
    if existing is None:
        raise ValueError("There is no text remote to write to")
    row = _find_row(existing, await read_device_table(hass, entry, client))
    if row is None:
        raise ValueError("The text remote is no longer on the device")
    await _rewrite_existing(
        hass, entry, client, existing, row, normalize_captions(captions),
        int(existing.get("icon_code") or 0), {})


def _reconfigure_live(hass, entry) -> None:
    live = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("matter_live")
    if live is not None:
        live.reconfigure(wrote=True)


async def _save(hass, msg) -> dict[str, Any]:
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN:
        raise ValueError("Integration not found")
    client = _client(hass, entry)
    templates, captions = prepare_captions(hass, msg["captions"])
    existing = matter_remote(entry)
    table = await read_device_table(hass, entry, client)
    on_device = [row for row in table if is_matter_row(row)]

    if msg.get("remote_id"):
        if existing is None or existing.get("remote_id") != msg["remote_id"]:
            raise ValueError("That is not the text remote")
        row = _find_row(existing, table)
        if row is None:
            raise ValueError("The text remote is no longer on the device. Refresh, then add it again.")
        # A caption rewrite resends the whole create packet, so keep the tile's icon byte.
        icon_code = (c.ICON[msg["icon"]] if msg.get("icon")
                     else int(existing.get("icon_code") or 0))
        updates: dict[str, Any] = {
            "matter_templates": templates,
            "matter_min_interval": normalize_interval(
                msg.get("min_interval", existing.get("matter_min_interval", MIN_INTERVAL_DEFAULT))),
        }
        if msg.get("icon"):
            updates["icon"] = msg["icon"]
        await _rewrite_existing(hass, entry, client, existing, row, captions, icon_code, updates)
        _reconfigure_live(hass, entry)
        return {"remote_id": existing["remote_id"], "slot": row[0], "captions": list(captions)}

    if existing is not None or on_device:
        # V48 draws the first Matter record and all four channels are shared, so a second text
        # remote could never be told apart from the first.
        raise ValueError("This Universal Remote already has a text remote. Edit that one instead.")
    name = str(msg.get("name") or "").strip()
    if not name:
        raise ValueError("Give the remote a name")
    c.require_remote_slot(len(table))
    if not c.remaining_remote_kind_slots(table, CONTROL_TYPE):
        raise ValueError("No more remotes can be added.")
    slot = len(table)
    device_id = new_device_id({row[3] for row in table}, c.id_to_bytes)
    icon_code = c.ICON[msg["icon"]] if msg.get("icon") else 0
    packet = build_matter_create(
        remote_index=slot, device_id=device_id, name=name, captions=captions,
        icon=icon_code)
    await _send(client, packet)
    identity = c.id_to_bytes(device_id)
    after = await read_device_table(hass, entry, client)
    if not any(is_matter_row(row) and row[0] == slot and row[3] == identity for row in after):
        # The device table is the truth: an ACK alone is not proof that the type was kept.
        raise ValueError(
            "The remote acknowledged the text remote but does not list it as a Matter type. "
            "Its table now reads: " + ", ".join(f"{r[0]}:0x{r[1]:02X}/{r[2]}" for r in after)
        )
    remote_id = new_remote_id(entry)
    remotes = list(entry.options.get("remotes", []))
    remotes.append({
        "index": slot, "name": name, "device_type": STUDIO_DEVICE_TYPE,
        "icon": msg.get("icon") or "light", "icon_code": icon_code,
        "device_id": device_id, "remote_id": remote_id, "buttons": [],
        "matter_captions": list(captions), "physical_packets": [packet.hex()],
        "matter_templates": templates,
        "matter_min_interval": normalize_interval(msg.get("min_interval", MIN_INTERVAL_DEFAULT)),
    })
    hass.config_entries.async_update_entry(entry, options={**entry.options, "remotes": remotes})
    _reconfigure_live(hass, entry)
    return {"remote_id": remote_id, "slot": slot, "captions": list(captions)}


def listen_for_matter(hass, entry, runtime):
    """Watch the remote's advertisements and fire the usual button event for A-D presses."""
    address = entry.data[CONF_ADDRESS].upper()
    address_bytes = bytes.fromhex(address.replace(":", ""))
    tracker = MatterPressTracker()

    def _matches(payload: bytes) -> bool:
        return payload[:6] in (address_bytes, address_bytes[::-1])

    @callback
    def receive(info, _change):
        payload = info.manufacturer_data.get(COMPANY_ID, b"")
        if not _matches(payload):
            return
        index = tracker.feed(payload)
        remote = matter_remote(entry) if index is not None else None
        if remote is None:
            return
        caption = captions_of(remote)[index]
        hass.bus.async_fire(EVENT_BUTTON, {
            "address": entry.data[CONF_ADDRESS],
            "source": "matter_advertisement",
            "remote_id": remote["remote_id"],
            "remote_slot": remote.get("index"),
            "button_id": f"p0_k{index}",
            "button": LETTERS[index],
            "button_name": caption,
            "button_page": 0,
            "button_index": index,
            "button_function": index + 1,
        })

    cached = bluetooth.async_last_service_info(hass, address, connectable=False)
    if cached:
        payload = cached.manufacturer_data.get(COMPANY_ID, b"")
        if _matches(payload):
            tracker.feed(payload)
    return bluetooth.async_register_callback(
        hass, receive, bluetooth.BluetoothCallbackMatcher(address=address, connectable=False),
        bluetooth.BluetoothScanningMode.PASSIVE,
    )


def register(hass):
    websocket_api.async_register_command(hass, ws_save_matter)
