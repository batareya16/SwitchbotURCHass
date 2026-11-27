"""Keep the SwitchBot account's list of this Universal Remote's remotes in step with the remote.

The app compares the remote's device table with the account's bound list (`checkDiffDevice` in
the app's bundle): every non-scene entry becomes an 11-byte id (an IR remote's cloud id, or a
device's address reversed and padded) and a slot (`remoteIndex`), the table gives each row's slot
and id, and any entry or row without its match, or with another slot, is a difference; the scene
list is compared by number and name the same way (`checkDiffScenes`). The type is never compared.
When there is a difference the app offers to "clean" the remote. This module computes those
differences exactly as the app does, and the entries that make them go away.

Nothing here talks to Home Assistant or the network; studio_cloud.py runs it.
"""
from __future__ import annotations

import base64
from datetime import datetime
from typing import Any

from . import commands as c
from .cloud import URC_VERSION
from .inventory import cloud_item_id, stable_id_for_local
from .physical_layout import ir_key_name

# The type the app writes for a HID tile, by the device type byte of the row.
HID_TYPES = {0xF0: "AppleTV", 0xF1: "FireTV", 0xF2: "UniversalBLE", 0xF3: "GoogleTV"}
# The app's device type for a Bluetooth tile, by its device type byte (getDeviceTypeCmd and
# getBytesWithCode in the app); a Bridge remote is listed as the kind of device it shows.
NATIVE_TYPES = {0x72: "WoStrip", 0x75: "WoBulb", 0x66: "WoFan", 0x7E: "WoFan", 0x63: "WoCurtain",
                0x6E: "WoCeiling"}
MATTER_TYPE = "WoMatter"
# A scene's icon and background as the account keeps them: the remote's icon 0–24 and background
# 0–7 are these, in this order (getSceneIconType / getSceneIconBg in the app's bundle).
SCENE_ICON_CSS = tuple(f"icon_32pt_scenarios_{name}" for name in (
    "default", "morning", "night", "turnonthelight", "turnoffthelights", "gethome", "goout", "dance",
    "treadmill", "muscle", "music", "shield", "aircraft", "game", "dumbbell", "leaf", "cultivation",
    "leisuretime", "film", "book", "house", "sleep", "sofa", "walkadog", "takeashower"))
SCENE_COLOR_HEX = ("#FF2D55", "#FF9300", "#FFC700", "#16D429", "#1DE1D5", "#00B2FF", "#5856D6", "#9CA1A4")


def studio_made(scene: dict[str, Any]) -> bool:
    """Whether an account scene is one Studio made: it has nothing to run but pauses.

    The app does not let a scene be saved without an action other than a pause (filterErrorData in
    its scene editor), so such a scene can only have been made by Studio. A scene whose actions
    are not known is taken as the user's own.
    """
    actions = scene.get("actions")
    return isinstance(actions, list) and all(
        isinstance(action, dict) and action.get("optID") == "delay_act_delay" for action in actions)


def scene_look(scene: dict[str, Any]) -> tuple[str, str]:
    """The account's icon and colour for a scene on the remote."""
    icon, color = scene.get("icon"), scene.get("color")
    return (SCENE_ICON_CSS[icon] if isinstance(icon, int) and 0 <= icon < len(SCENE_ICON_CSS) else SCENE_ICON_CSS[0],
            SCENE_COLOR_HEX[color] if isinstance(color, int) and 0 <= color < len(SCENE_COLOR_HEX) else SCENE_COLOR_HEX[5])


def remote_id_from_bytes(raw: bytes) -> str | None:
    """The cloud's decimal-pair id ("01-202611190101-12345678") of an 11-byte IR id."""
    if len(raw) != 11 or any(value > 99 for value in raw):
        return None
    digits = "".join(f"{value:02d}" for value in raw)
    return f"{digits[:2]}-{digits[2:14]}-{digits[14:]}"


def _address(raw: bytes) -> str:
    """A device address as the app keeps it: the table's six bytes reversed, in hex."""
    return c.id_from_bytes(raw).upper()


def _remote_id_bytes(item: dict[str, Any]) -> bytes | None:
    return cloud_item_id(item)


def entry_id(item: dict[str, Any]) -> str:
    """The id the app passes to deleteBindDevices for one bound entry."""
    return str(item.get("deviceID") or item.get("thirdPartyDeviceID") or item.get("remoteID")
               or item.get("sceneID") or "")


def _is_scene(item: dict[str, Any]) -> bool:
    return bool(item.get("sceneID")) or "sceneIndex" in item


def _scene_name_bytes(name: str) -> bytes:
    raw = bytearray(str(name).encode("utf-8")[:64].ljust(64, b"\0"))
    raw[63] = 0
    return bytes(raw)


def differences(bound: list[dict[str, Any]], table: list[tuple[int, int, int, bytes]],
                scenes: list[dict[str, Any]] | None = None) -> list[str]:
    """What the app would call a difference between the account and the remote, in words."""
    found: list[str] = []
    devices = [item for item in bound if not _is_scene(item)]
    rows = {row[3]: row[0] for row in table}
    seen = set()
    for item in devices:
        raw = _remote_id_bytes(item)
        name = str(item.get("remoteName") or item.get("deviceName") or item.get("thirdPartyDeviceName")
                   or entry_id(item))
        if raw is None or raw not in rows:
            found.append(f"{name}: in the account, not on the remote")
            continue
        seen.add(raw)
        if int(item.get("remoteIndex", -1)) != rows[raw]:
            found.append(f"{name}: slot {item.get('remoteIndex')} in the account, {rows[raw]} on the remote")
    for slot, _device_type, _control, raw in sorted(table):
        if raw not in seen:
            found.append(f"Slot {slot}: on the remote, not in the account")
    if scenes is not None:
        cloud_scenes = {(_scene_name_bytes(item.get("sceneName", "")), int(item.get("sceneIndex", -1)))
                        for item in bound if _is_scene(item)}
        device_scenes = {(_scene_name_bytes(scene["name"]), int(scene["index"])) for scene in scenes}
        for name, index in sorted(device_scenes - cloud_scenes, key=lambda pair: pair[1]):
            found.append(f"Scene {index} ({name.rstrip(bytes(1)).decode('utf-8', 'replace')}): "
                         "on the remote, not in the account")
        for name, index in sorted(cloud_scenes - device_scenes, key=lambda pair: pair[1]):
            found.append(f"Scene {index} ({name.rstrip(bytes(1)).decode('utf-8', 'replace')}): "
                         "in the account, not on the remote")
    return found


def _managed_for(row_id: bytes, remotes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for remote in remotes:
        identity = remote.get("physical_device_id") or remote.get("device_id")
        if not identity:
            continue
        try:
            if stable_id_for_local(str(identity)) == row_id:
                return remote
        except ValueError:
            continue
    return None


def _learned_keys(remote: dict[str, Any]) -> list[dict[str, Any]]:
    """The typed IR codes of a Studio remote, as the account keeps learned keys (name and code)."""
    keys = []
    for page in (remote.get("physical_layout") or {}).get("pages", []):
        for key in page.get("buttons", []):
            if key.get("transport") != "ir" or not key.get("code_hex"):
                continue
            try:
                code = bytes.fromhex(str(key["code_hex"]))
            except ValueError:
                continue
            keys.append({"keyName": ir_key_name(int(page["index"]), key), "keyType": "text",
                         "code": base64.b64encode(code).decode()})
    return keys


def plan(table: list[tuple[int, int, int, bytes]], remotes: list[dict[str, Any]],
         bound: list[dict[str, Any]], known_remote_ids: set[str],
         scenes: list[dict[str, Any]], account_devices: set[str] | None = None,
         account_scenes: list[dict[str, Any]] | None = None,
         urc_version: int = URC_VERSION) -> dict[str, Any]:
    """The account entries that match the remote, what to create first, and what to remove.

    `known_remote_ids` are the IR ids the account already has a record for (bound or not); an IR
    remote made in Studio that the account does not know is created first, with its typed codes as
    learned keys, which also keeps a copy of them in the account.

    A Bluetooth tile whose address is not one of the account's SwitchBot devices
    (`account_devices`: a Bridge remote, which no account knows) is listed as a Matter device: the
    app looks every other listed device up among the account's devices and, not finding it, shows
    the remote as not synchronized.

    Every scene is listed with a scene of the account (`account_scenes`), as the app expects: the
    one already listed for it, or one of the account's scenes of the same name; otherwise a new
    tap-to-run scene is made (`scene_create`, its item's sceneID is filled in once it exists). A
    scene whose name or look in the account differs is brought in line (`scene_update`).
    """
    real = account_devices or set()
    as_matter: list[str] = []
    by_id = {raw: item for item in bound if not _is_scene(item)
             if (raw := _remote_id_bytes(item)) is not None}
    items: list[dict[str, Any]] = []
    create: list[dict[str, Any]] = []
    skipped: list[str] = []
    for slot, device_type, control, raw in sorted(table):
        managed = _managed_for(raw, remotes) or {}
        existing = by_id.get(raw, {})
        name = str(managed.get("name") or existing.get("remoteName") or existing.get("deviceName")
                   or existing.get("thirdPartyDeviceName") or f"Remote {slot + 1}")
        if control == c.CTRL_IR:
            remote_id = existing.get("remoteID") or remote_id_from_bytes(raw)
            if not remote_id:
                skipped.append(f"Slot {slot} ({name}): its id has no account form")
                continue
            items.append({"remoteID": remote_id, "remoteName": name, "type": device_type,
                          "remoteIndex": slot, "createFrom": existing.get("createFrom") or "device",
                          "waitModify": False, "urcVersion": urc_version})
            if remote_id not in known_remote_ids:
                create.append({"remoteID": remote_id, "remoteIndex": slot, "remoteName": name,
                               "type": device_type, "code": "no_data", "keyMap": "",
                               "keyDetail": _learned_keys(managed), "dbVersion": 30,
                               "createTime": int(datetime.now().timestamp() * 1000),
                               "waitModify": False, "urcVersion": urc_version})
        elif control == c.CTRL_HID:
            items.append({"thirdPartyDeviceID": existing.get("thirdPartyDeviceID") or _address(raw),
                          "thirdPartyType": existing.get("thirdPartyType") or HID_TYPES.get(device_type, "UniversalBLE"),
                          "thirdPartyDeviceName": name, "remoteIndex": slot, "roomName": "",
                          "urcVersion": urc_version})
        elif control == 3:                                   # the text remote (Matter)
            items.append({"deviceID": existing.get("deviceID") or _address(raw), "deviceName": name,
                          "deviceType": existing.get("deviceType") or MATTER_TYPE,
                          "remoteIndex": slot, "roomName": "", "urcVersion": urc_version})
        else:                                                # a Bluetooth (native or Bridge) tile
            address = existing.get("deviceID") or _address(raw)
            kind = (existing.get("deviceType") or NATIVE_TYPES.get(device_type, "WoStrip")
                    if address in real else MATTER_TYPE)
            if kind == MATTER_TYPE:
                as_matter.append(f"{name} (slot {slot})")
            items.append({"deviceID": address, "deviceName": name, "deviceType": kind,
                          "remoteIndex": slot, "roomName": "", "urcVersion": urc_version})
    real_scenes = {str(item["sceneID"]): item for item in account_scenes or []
                   if isinstance(item, dict) and item.get("sceneID")}
    listed = [item for item in bound if str(item.get("sceneID") or "") in real_scenes]
    scene_create: list[dict[str, Any]] = []
    scene_update: list[dict[str, Any]] = []
    scene_differs: list[str] = []
    # Each scene keeps the account scene already listed for it by name (the user's own scene too),
    # else takes one Studio made: listed at its number (renamed on the remote), or one of the
    # account's with its name. Names are matched first for every scene, so a renamed scene never
    # takes the account scene of another one. A scene of the user's own is never taken for another
    # name, nor changed.
    mine = lambda scene_id: studio_made(real_scenes[scene_id])
    ordered = sorted(scenes, key=lambda item: item["index"])
    chosen: dict[int, str] = {}
    used: set[str] = set()
    passes = (
        lambda name, index: [str(item["sceneID"]) for item in listed if item.get("sceneName") == name],
        lambda name, index: [scene_id for scene_id, item in real_scenes.items()
                             if item.get("name") == name and mine(scene_id)],
        lambda name, index: [str(item["sceneID"]) for item in listed
                             if int(item.get("sceneIndex", -1)) == index and mine(str(item["sceneID"]))],
    )
    for candidates in passes:
        for scene in ordered:
            index = int(scene["index"])
            if index in chosen:
                continue
            scene_id = next((choice for choice in candidates(str(scene["name"]), index) if choice not in used), None)
            if scene_id:
                chosen[index] = scene_id
                used.add(scene_id)
    for scene in ordered:
        css, color = scene_look(scene)
        name, index = str(scene["name"]), int(scene["index"])
        scene_id = chosen.get(index)
        item = {"sceneID": scene_id, "sceneName": name, "sceneIndex": index, "roomName": "",
                "sceneIcon": css, "sceneColor": color}
        items.append(item)
        if scene_id is None:
            scene_create.append({"position": len(items) - 1, "name": name, "icon": css, "color": color})
            continue
        account = real_scenes[scene_id]
        look = account.get("icon") or {}
        if account.get("name") != name or look.get("css") != css or look.get("color") != color:
            if studio_made(account):
                scene_update.append({"sceneID": scene_id, "name": name, "icon": css, "color": color,
                                     "was": str(account.get("name") or "")})
            else:
                scene_differs.append(name)
    wanted = {entry_id(item) for item in items if entry_id(item)}
    remove = [entry_id(item) for item in bound if entry_id(item) and entry_id(item) not in wanted]
    # A scene Studio made that this remote no longer lists is removed from the account, so
    # deleting, renaming and moving scenes leaves nothing behind. The user's own scenes stay.
    scene_delete = [{"sceneID": entry_id(item), "name": str(item.get("sceneName") or "")}
                    for item in bound if _is_scene(item) and entry_id(item) in real_scenes
                    and entry_id(item) not in wanted and studio_made(real_scenes[entry_id(item)])]
    return {"items": items, "create": create, "remove": remove, "skipped": skipped, "as_matter": as_matter,
            "scene_create": scene_create, "scene_update": scene_update, "scene_differs": scene_differs,
            "scene_delete": scene_delete}


def _same_name(left: Any, right: Any) -> bool:
    return str(left or "").strip().casefold() == str(right or "").strip().casefold() != ""


def account_source(create: dict[str, Any], account_remotes: list[dict[str, Any]],
                   table: list[tuple[int, int, int, bytes]]) -> dict[str, Any] | None:
    """The account remote an IR remote on the Universal Remote was installed from, if it is clear.

    Before 0.53.29 Studio installed a remote from the account under a new id, so the account does
    not know the remote's copy. Its source is an account IR remote of the same name and type that
    is not on the Universal Remote itself; only a single such remote counts, else there is none.
    """
    on_remote = {row[3] for row in table}
    found = [item for item in account_remotes
             if item.get("remoteID") and not item.get("isDeleted")
             and _same_name(item.get("remoteName"), create.get("remoteName"))
             and str(item.get("type")) == str(create.get("type"))
             and cloud_item_id(item) not in on_remote]
    unique = {str(item["remoteID"]): item for item in found}
    return next(iter(unique.values())) if len(unique) == 1 else None


def with_source_keys(create: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    """The account record for the copy: every code and key of its source, under the copy's id.

    The source's code bank, key map and keys are kept as they are; codes typed in Studio for
    keys the source does not name are added to its keys.
    """
    merged = {key: value for key, value in source.items()
              if key not in ("remoteID", "remoteIndex", "remoteName", "type", "waitModify",
                             "createTime", "parentRemoteID", "isDeleted", "deviceID", "createFrom",
                             "studioUnbound")}
    merged.update({key: create[key] for key in ("remoteID", "remoteIndex", "remoteName", "type",
                                                "waitModify", "createTime", "urcVersion")})
    merged["code"] = source.get("code") or "no_data"
    merged["keyMap"] = source.get("keyMap") or ""
    details = source.get("keyDetail") or []
    if isinstance(details, str):
        import json
        try:
            details = json.loads(details) if details.strip() else []
        except ValueError:
            details = []
    details = [item for item in details if isinstance(item, dict)] if isinstance(details, list) else []
    named = {str(item.get("keyName")) for item in details}
    merged["keyDetail"] = details + [key for key in create.get("keyDetail", [])
                                     if str(key.get("keyName")) not in named]
    return merged


def preview(steps: dict[str, Any], account_remotes: list[dict[str, Any]],
            table: list[tuple[int, int, int, bytes]], bound: list[dict[str, Any]]) -> list[str]:
    """What Sync would do, in words, before anything is sent."""
    lines = []
    for create in steps["create"]:
        source = account_source(create, account_remotes, table)
        lines.append(f"{create['remoteName']} (slot {create['remoteIndex']}): saved to the account as a copy of "
                     f"your account's {source.get('remoteName')}, with all its buttons" if source else
                     f"{create['remoteName']} (slot {create['remoteIndex']}): saved to the account with the "
                     "codes typed in Studio")
    names = {entry_id(item): str(item.get("remoteName") or item.get("deviceName")
                                 or item.get("thirdPartyDeviceName") or item.get("sceneName") or entry_id(item))
             for item in bound}
    for scene in steps.get("scene_create", []):
        lines.append(f"Scene {scene['name']}: made in your SwitchBot account as a tap-to-run scene with "
                     "nothing to run, so the app knows it")
    for scene in steps.get("scene_delete", []):
        lines.append(f"Scene {scene['name']}: the empty scene Studio made for it is removed from your "
                     "account, as the remote no longer has it")
    for name in steps.get("scene_differs", []):
        lines.append(f"Scene {name}: its name or look differs from your own scene in the account; Sync "
                     "leaves your scene as it is, so change one of them to match")
    for scene in steps.get("scene_update", []):
        lines.append(f"Scene {scene['name']}: its name, icon and colour in your account set as on the remote"
                     + (f" (was {scene['was']})" if scene["was"] and scene["was"] != scene["name"] else ""))
    for tile in steps.get("as_matter", []):
        lines.append(f"{tile}: listed as a Matter device, since your account has no SwitchBot device "
                     "with its address (the app would otherwise show the remote as not synchronized)")
    for removed in steps["remove"]:
        lines.append(f"{names.get(removed, removed)}: no longer listed under this Universal Remote "
                     "(it stays in your account)")
    return lines


def _blank(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def app_warnings(payload: dict[str, Any]) -> list[str]:
    """What else makes the app mark the remote as not in sync, besides the two lists differing.

    The app also looks up every listed Bluetooth device (an entry with a deviceID that is not a
    Matter one) among the account's SwitchBot devices, and every listed scene among the account's
    scenes (`getStatusChangedPhysicDevices` / `getStatusChangeScenes` in its bundle). A device it
    cannot find, or whose name, mode, group or icon differ, lights the "not synchronized" banner
    and the warning on its devices; a scene it cannot find, or whose name or look differ, the
    warning on its scenes.
    """
    bound = [item for item in (payload or {}).get("bindDevices", []) if isinstance(item, dict)]
    devices = [item for item in (payload or {}).get("devices", []) if isinstance(item, dict)]
    scenes = [item for item in (payload or {}).get("scenes", []) if isinstance(item, dict)]
    found: list[str] = []
    for item in bound:
        if _blank(item.get("deviceID")) or item.get("deviceType") == MATTER_TYPE:
            continue
        name = str(item.get("deviceName") or item.get("deviceID"))
        device = next((row for row in devices if row.get("deviceID") == item.get("deviceID")), None)
        status = (device or {}).get("status") or {}
        if device is None:
            found.append(f"{name}: no SwitchBot device {item.get('deviceID')} in the account")
        elif item.get("isDeleted") is True or item.get("inRWSGroup") is False:
            found.append(f"{name}: removed from the account")
        elif (status.get("isGroup") != item.get("isGroup") or status.get("deviceMode") != item.get("deviceMode")
              or device.get("deviceName") != item.get("deviceName")
              or not ((_blank(status.get("icon")) and _blank(item.get("icon"))) or status.get("icon") == item.get("icon"))):
            found.append(f"{name}: its name or settings differ from the device in the account")
    for item in bound:
        third_party = item.get("thirdPartyType") or item.get("deviceType") == MATTER_TYPE
        if _is_scene(item) or third_party or (item.get("urcVersion") or 0) >= 23:
            continue
        name = str(item.get("remoteName") or item.get("deviceName") or entry_id(item))
        found.append(f"{name}: listed without the remote's firmware version, so the app shows "
                     + ("\"key error, delete and add it again\"" if item.get("remoteID")
                        else "\"changed, needs to be synchronized\""))
    for item in bound:
        if _blank(item.get("sceneID")):
            continue
        name = str(item.get("sceneName") or item.get("sceneID"))
        scene = next((row for row in scenes if row.get("sceneID") == item.get("sceneID")), None)
        icon = (scene or {}).get("icon") or {}
        if scene is None:
            found.append(f"Scene {name}: not a scene of your SwitchBot account")
        elif scene.get("name") != item.get("sceneName") or icon.get("css") != item.get("sceneIcon") \
                or icon.get("color") != item.get("sceneColor"):
            found.append(f"Scene {name}: its name or look differ from the scene in the account")
    return found

