"""Physical page drafts and protocol compilation, separate from HA action mappings."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from . import commands as c
from .ir_glyphs import (
    MENU_SHORTCUT_FUNCTIONS, NUMBER_PAD_FUNCTIONS, NUMBER_PAD_LINK,
    fixed_softkey_functions, list_link_functions, list_page_positions, number_pad_always,
    number_pad_positions, page_only_positions, stock_softkey_glyphs,
)


def _validate_glyph(glyph):
    if (type(glyph) is not int or not 0 <= glyph <= 0xFFFF
            or not (Path(__file__).parent / "frontend" / "native-glyphs"
                    / f"keyfun-{glyph:04x}.png").is_file()):
        raise ValueError("Choose an available firmware icon")


def source_packets(remote: dict) -> list[bytes]:
    if remote.get("physical_packets"):
        return [bytes.fromhex(value) for value in remote["physical_packets"]]
    return []


def ir_screen_preview(remote: dict) -> dict | None:
    """Use stock glyphs for reconstructed cloud layouts and wire glyphs for saved layouts."""
    device_type = str(remote.get("device_type", "")).upper()
    if not device_type.startswith("IR_"):
        return None
    if remote.get("imported_from_cloud") and not remote.get("physical_layout"):
        # The rows already carry the firmware pictures the page builders wrote, so only the A–D
        # softkeys (which are not rows) come from the stock layout.
        return {"softkeys": stock_softkey_glyphs(device_type)}
    try:
        for packet in source_packets(remote):
            c.rewrite_ir_page(packet, remote_index=packet[7], name="")
            if packet[88] == 0:
                return {"disabled_softkeys": {
                    packet[start]: int.from_bytes(packet[start + 1:start + 3], "big")
                    for start in range(90, len(packet), 36)
                    if packet[start] < 4 and packet[start + 3] == 0xFE
                }}
    except (IndexError, TypeError, ValueError):
        pass
    return None


def _ir_menu_link_records(packets: list[bytes]) -> list[bytes]:
    for packet in packets:
        if len(packet) >= 90 and packet[88] == 0:
            c.rewrite_ir_page(packet, remote_index=packet[7], name="")
            return [packet[offset:offset + 36] for offset in range(90, len(packet), 36)
                    if packet[offset] < 4 and packet[offset + 3] == 4]
    return []


def _restore_ir_menu_links(remote: dict, pages: list[dict]) -> None:
    records = {record[0] + 1: record.hex() for record in _ir_menu_link_records(source_packets(remote))}
    for page in pages:
        number = page["index"]
        if number in records:
            page.setdefault("link_record", records[number])


def _key_function(key: dict) -> int | None:
    """The firmware function an IR key carries: its icon for a typed code, else its record's."""
    if key.get("transport") == "stored":
        try:
            return int.from_bytes(bytes.fromhex(str(key.get("record", "")))[1:3], "big")
        except ValueError:
            return None
    value = key.get("glyph", key.get("function"))
    return value if type(value) is int else None


def is_template_key(key: dict) -> bool:
    """A stock A–D template icon: a stored record of kind 254, a picture with no command."""
    if key.get("transport") != "stored":
        return False
    try:
        record = bytes.fromhex(str(key.get("record", "")))
    except ValueError:
        return False
    return len(record) == 36 and record[3] == 254


def _link_function(page: dict) -> int | None:
    try:
        record = bytes.fromhex(str(page.get("link_record") or ""))
    except ValueError:
        return None
    return int.from_bytes(record[1:3], "big") if len(record) == 36 else None


def _place_number_pad_keys(page: dict) -> None:
    """Give each number pad key the position of its function; anything else goes after them."""
    placed, others, taken = [], [], set()
    for key in sorted(page.get("buttons", []), key=lambda item: item.get("index", 0)):
        function = _key_function(key)
        if function in NUMBER_PAD_FUNCTIONS and function not in taken:
            taken.add(function)
            placed.append({**key, "index": NUMBER_PAD_FUNCTIONS.index(function)})
        else:
            others.append(key)
    for offset, key in enumerate(others):
        placed.append({**key, "index": len(NUMBER_PAD_FUNCTIONS) + offset})
    page["buttons"] = placed


def _mark_number_pads(device_type: str, pages: list[dict]) -> None:
    """Mark the pages the remote shows as its number pad rather than as a list.

    The TV and audio windows always open the number pad from A; the other IR windows open it from
    a key whose function is 39 and a list from any other menu key.
    """
    positions = number_pad_positions(device_type)
    for page in pages:
        number = page["index"]
        if not number or number - 1 not in positions:
            page.pop("number_pad", None)
            continue
        if (number_pad_always(device_type) or page.get("number_pad")
                or _link_function(page) == NUMBER_PAD_LINK):
            page["number_pad"] = True
            _place_number_pad_keys(page)
        else:
            page.pop("number_pad", None)


def _check_number_pad_keys(buttons) -> None:
    """Only the pad's own keys, once each, at the position of their function."""
    if not isinstance(buttons, list):
        return
    seen = set()
    for key in buttons:
        function = _key_function(key) if isinstance(key, dict) else None
        if key.get("transport") not in ("ir", "stored") or function not in NUMBER_PAD_FUNCTIONS:
            raise ValueError("A number pad holds only the digits 0–9 and the four keys under "
                             "them; remove the other keys from it")
        if function in seen:
            raise ValueError("A number pad key is there twice")
        seen.add(function)
        key["index"] = NUMBER_PAD_FUNCTIONS.index(function)


def _check_ir_pages(device_type: str, pages: list[dict]) -> None:
    """Refuse a page the remote's window would not open the way Studio shows it."""
    pad_positions = number_pad_positions(device_type)
    list_positions = list_page_positions(device_type)
    pad_pages = [page for page in pages if page.get("number_pad")]
    for page in pages:
        number = page["index"]
        if not number:
            continue
        letter = "ABCD"[number - 1]
        if page.get("number_pad"):
            if number - 1 not in pad_positions:
                raise ValueError(f"Key {letter} cannot open a number pad on this type of remote")
            continue
        if number == 1 and number_pad_always(device_type):
            raise ValueError("Key A opens the number pad on this type of remote, not a list")
        if list_positions is not None and number - 1 not in list_positions:
            raise ValueError(f"Key {letter} cannot open a page on this type of remote")
    if pad_pages:
        for page in pages:
            if page.get("number_pad"):
                continue
            for key in page["buttons"]:
                if _key_function(key) in NUMBER_PAD_FUNCTIONS and key.get("transport") != "icon":
                    raise ValueError("A key outside the number pad uses a number pad icon (0–9, "
                                     "10, 11, 12 or 3-Digit Input); the number pad would send that "
                                     "key's command. Choose another icon for it")


def native_appearance(remote: dict) -> dict:
    """Resolve Studio appearance from the device readback or the cached Main page."""
    name = str(remote.get("device_type", "")).upper()
    device_code = c.NATIVE_DEVTYPE.get(name)
    if device_code is None:
        return {}
    stored_type = remote.get("native_type")
    defaults = c.native_type_metadata(stored_type or name)
    mode = remote.get("control_mode", defaults["control_mode"])
    icon = remote.get("icon_code")
    if not isinstance(icon, int):
        icon = c.ICON.get(str(remote.get("icon", "")).lower(), defaults["icon_code"])
    # Older Studio versions saved the original page when applying the Floor lamp test
    # but left the cached artwork fields pointing at that original page.
    legacy_floor_lamp_test = (
        device_code == 0x72 and "floor_lamp_test_applied" not in remote
        and remote.get("icon_variant_backup_packet")
    )
    try:
        packets = source_packets(remote)
    except (ValueError, TypeError):
        packets = []
    for packet in packets:
        if len(packet) < 90 or packet[:3] != b"\x0f\x62\x06":
            continue
        width = 4 if packet[8] == 0 else 1
        control = 8 + width
        if (len(packet) < 89 + width or packet[87 + width] != 0
                or packet[control] != c.CTRL_NATIVE
                or int.from_bytes(packet[8:control], "big") != device_code
                or int.from_bytes(packet[3:5], "big") != len(packet) - 7
                or int.from_bytes(packet[5:7], "big") != c.crc16_modbus(packet[7:])):
            continue
        mode, icon = packet[control + 1:control + 3]
        break
    readback = remote.get("native_appearance_readback")
    if isinstance(readback, dict):
        mode, icon = readback["mode"], readback["icon"]
    elif readback is not None:
        mode, icon = readback
    elif remote.get("floor_lamp_test_applied") or legacy_floor_lamp_test:
        mode, icon = 3, 1  # The previous test sent these fields and rendered Bulb.
    elif mode is None:
        mode = c.native_type_metadata(stored_type or name)["control_mode"]
    if device_code == c.NATIVE_DEVTYPE["FLOOR_LAMP"]:
        return {"native_type": "FLOOR_LAMP", "control_mode": c.NATIVE_FLOOR_LAMP_CONTROL_MODE,
                "icon_code": c.ICON["floorlamp"]}
    candidates = [item for item in c.native_type_picker_options()
                  if c.NATIVE_DEVTYPE[item["device_type"]] == device_code
                  and item["control_mode"] == mode
                  and item["artwork_id"] == c.native_artwork_id(device_code, icon, mode)]
    preferred = c.NATIVE_TYPE_EQUIVALENTS.get(stored_type or name, stored_type or name)
    # An old cached Floor lamp label cannot override a different illustration read from the device.
    if device_code == 0x72 and preferred == "FLOOR_LAMP" and icon != c.ICON["floorlamp"]:
        preferred = "STRIP"
    match = next((item for item in candidates if item["value"] == preferred),
                 candidates[0] if candidates else None)
    return {"native_type": match["value"] if match else preferred,
            "control_mode": mode, "icon_code": icon}


def match_native_appearance(remote: dict, appearances: dict, device_type: int):
    """Find the physical row by target ID, using the saved slot for shared targets."""
    address = remote.get("physical_device_id") or remote.get("device_id")
    if not address:
        return None
    try:
        device_id = c.id_to_bytes(str(address))
    except (TypeError, ValueError):
        return None
    try:
        slot = int(remote.get("index"))
    except (TypeError, ValueError):
        slot = None
    matches = [key for key in appearances if key[2] == device_id]
    if len(matches) == 1:
        return matches[0]
    slotted = [key for key in matches if key[0] == slot]
    if len(slotted) == 1:
        return slotted[0]
    typed = [key for key in matches if key[1] == device_type]
    return typed[0] if len(typed) == 1 else None


def _hid_ir_wire_fields(remote: dict) -> tuple[int, int, int] | None:
    """(device type, wire icon, screen mode) of an HID or IR remote, read from its saved Main page."""
    name = str(remote.get("device_type", "")).upper()
    if name in c.DEVTYPE:
        device_type = c.DEVTYPE[name]
    elif name == "IR_TV":
        device_type = 2
    elif name.startswith("IR_") and name[3:].isdigit():
        device_type = int(name[3:])
    else:
        return None
    mode = int(remote.get("control_mode") or 0)
    icon = remote.get("icon_code")
    if type(icon) is not int:
        icon = c.ICON.get(str(remote.get("icon", "")).lower(), 0)
    try:
        packets = source_packets(remote)
    except (ValueError, TypeError):
        packets = []
    for packet in packets:
        if len(packet) < 90 or packet[:3] != b"\x0f\x62\x06":
            continue
        width = 4 if packet[8] == 0 else 1
        control = 8 + width
        expected_control = c.CTRL_HID if name in c.DEVTYPE else c.CTRL_IR
        if (len(packet) < 89 + width
                or int.from_bytes(packet[8:control], "big") != device_type
                or packet[control] != expected_control
                or packet[87 + width] != 0
                or int.from_bytes(packet[3:5], "big") != len(packet) - 7
                or int.from_bytes(packet[5:7], "big") != c.crc16_modbus(packet[7:])):
            continue
        mode, icon = packet[control + 1:control + 3]
        break
    return device_type, icon, mode


def page_icon_editable(remote: dict) -> bool:
    """True when the saved pages are the ones Studio itself wrote to the remote.

    A remote imported from the SwitchBot account has pages that Studio rebuilt from the cloud
    profile. They are not what the app wrote to the remote (key glyphs and code-bank references can
    differ), so sending them back only to change the icon byte can break the remote.
    """
    return bool(remote.get("physical_packets")
                and not remote.get("imported_from_cloud")
                and not remote.get("ir_profile_pending"))


def remote_artwork_id(remote: dict) -> int | None:
    """Resolve the illustration from the cached wire fields for Native, HID or IR."""
    if str(remote.get("device_type", "")).upper() in c.NATIVE_DEVTYPE:
        appearance = native_appearance(remote)
        return c.native_artwork_id(
            c.NATIVE_DEVTYPE[str(remote["device_type"]).upper()],
            appearance["icon_code"], appearance["control_mode"])
    fields = _hid_ir_wire_fields(remote)
    return None if fields is None else c.native_artwork_id(*fields)


def remote_original_artwork_id(remote: dict) -> int | None:
    """Picture of the icon an HID or IR remote had before Studio first changed it.

    That is what "Original" gives back: the remembered byte, or the current one when Studio never
    changed it, resolved for this device type and mode.
    """
    fields = _hid_ir_wire_fields(remote)
    if fields is None:
        return None
    device_type, icon, mode = fields
    original = remote.get("icon_code_original")
    return c.native_artwork_id(device_type, int(original) if original is not None else icon, mode)


def remote_wire_icon(remote: dict) -> int | None:
    """The wire icon byte an installed HID or IR remote carries, or None for other kinds."""
    fields = _hid_ir_wire_fields(remote)
    return None if fields is None else fields[1]


# keyFun -> what the V48 firmware actually transmits, from the report table at flash 0x33a4a.
# Useful for keys that have no matching screen position, such as media controls.
HID_FUNCTIONS = {
    "Power": 5,
    "Sleep": 6,
    "Left": 7,
    "Right": 8,
    "Up": 9,
    "Down": 10,
    "OK": 11,
    "Back": 12,
    "Home": 13,
    "Volume up": 15,
    "Volume down": 16,
    "Play / Pause": 22,
    "Rewind": 25,
    "Fast forward": 26,
    "Mute": 2000,
    "Menu": 2105,
    "Back (AC Back)": 2106,
}

# Alternate keyFun values that produce the same Consumer report in V48.
HID_FUNCTION_ALIASES = {
    5: (105,),
    12: (2002,),
    13: (2104,),
    22: (21, 2001, 2101),
    25: (2103,),
    26: (2102,),
    2000: (19, 0x834),
}


# Verified against V48 ARM firmware: `15190` maps a key function to an internal index and the
# table at flash 0x33a4a turns that into a HID consumer usage. Values with no entry there send
# nothing at all, which is why SOUNDOFF used to be silent on 0x834.
def hid_usage(device_type: str, position: str) -> int:
    common = {"ON": 105, "OFF": 105, "UP": 9, "DOWN": 10, "LEFT": 7,
              "RIGHT": 8, "OK": 11, "BACK": 12, "HOME": 0x838,
              "SOUNDOFF": 2000, "VOLADD": 15, "VOLDEL": 16, "CHUP": 15, "CHDOWN": 16,
              "A": 0x837, "B": 0x835, "C": 0x836, "D": 0x839}

    if device_type == "GOOGLE_TV":
        common.update(dict.fromkeys("ABCD", 0x7D3))
        common["BACK"] = 0x83A
    elif device_type == "APPLE_TV":
        common.update({"A": 0x7D1, "B": 0x7D3, "C": 0x7D3, "D": 0x7D3,
                       "BACK": 0x7D2, "HOME": 0x839, "SOUNDOFF": 0x7D0})
    return common.get(position, 115)


def default_hid_buttons(device_type: str) -> list[str]:
    """Include the stock positions that emit a HID action in this profile."""
    functions = set(HID_FUNCTIONS.values())
    functions.update(alias for aliases in HID_FUNCTION_ALIASES.values() for alias in aliases)
    return [position for position in c.TAG if hid_usage(device_type, position) in functions]


def hid_draft_from_cloud(device_type: str, items: list[dict]) -> dict:
    """Preserve the app's HID button/list selections, including custom IR code bytes."""
    from .cloud_ir import decode_code_blob
    positions = {value: name for name, value in c.TAG.items()}
    main, pages = [], []
    def convert(item, index, usage_position=None):
        code = item.get("customKeyValue")
        if code:
            return {"index": index, "transport": "ir", "code_hex": decode_code_blob(code).hex()}
        if item.get("isBLEValue") is False:
            raise ValueError("Cloud IR button is missing its code; cannot preserve the physical layout")
        source_type = {"AppleTV": "APPLE_TV", "FireTV": "FIRE_TV", "UniversalBLE": "UNIVERSAL_BLE", "GoogleTV": "GOOGLE_TV"}.get(item.get("buttonType"), device_type)
        return {"index": index, "transport": "hid", "function": hid_usage(source_type, positions.get(index if usage_position is None else usage_position, ""))}
    for item in items:
        index = int(item["index"])
        if index == c.KATA_POSITION:
            continue
        if item.get("type") == "list":
            if not 0 <= index <= 3:
                raise ValueError("Only A–D can open HID pages")
            pages.append({"index": index + 1, "buttons": [convert(child, child_index, index) for child_index, child in enumerate(item.get("buttonList", []))]})
        else:
            main.append(convert(item, index))
    return {"kind": "hid", "pages": [{"index": 0, "buttons": main}] + pages}


def draft_for(remote: dict) -> dict:
    if remote.get("physical_layout"):
        draft = deepcopy(remote["physical_layout"])
        for page in draft["pages"]:
            if page["index"] == 0:
                page["buttons"] = [
                    key for key in page["buttons"] if key["index"] != c.KATA_POSITION
                ]
        if draft.get("kind") == "native":
            device_type = str(remote.get("device_type", "")).upper()
            stored_template = (remote.get("custom_layout") or {}).get("template")
            draft.setdefault("template", c.NATIVE_PROFILE_ALIASES.get(
                str(stored_template or device_type).upper(), "FAN"))
            draft.update(native_appearance(remote))
            titles = (remote.get("custom_layout") or {}).get("page_names", {})
            for page in draft["pages"]:
                if page["index"]:
                    page.setdefault("title", titles.get(str(page["index"]), ""))
        elif draft.get("kind") == "ir":
            _restore_ir_menu_links(remote, draft["pages"])
            _mark_number_pads(str(remote.get("device_type", "")), draft["pages"])
        return draft
    device_type = str(remote.get("device_type", "")).upper()
    if device_type in c.DEVTYPE:
        return {"kind": "hid", "pages": [{"index": 0, "buttons": [
            {"index": c.TAG[name], "transport": "hid", "function": hid_usage(device_type, name)}
            for name in remote.get("buttons", []) if name in c.TAG and name != "KATA"
        ]}]}
    if device_type in c.NATIVE_DEVTYPE:
        layout = remote.get("custom_layout") or c.editable_layout_from_native_profile(device_type)
        main = c.normalize_main_buttons(layout.get("main_buttons", {}))
        main.pop("KATA", None)
        template = str(layout.get("template") or c.NATIVE_PROFILE_ALIASES.get(device_type, "FAN"))
        template = c.NATIVE_PROFILE_ALIASES.get(template.upper(), template.upper())
        draft = {"kind": "native", "template": template,
                **native_appearance(remote),
                "icon_name": remote.get("icon", "light"), "pages": [{"index": 0, "buttons": [
            {"index": c.TAG[position], "transport": "native", "function": c.custom_action_function(action)}
            for position, action in main.items()
        ]}] + [{"index": int(page), "buttons": [
            {"index": index, "transport": "native", "function": c.custom_action_function(action)}
            for index, action in enumerate(actions)
        ]} for page, actions in layout.get("pages", {}).items()]}
        glyphs = layout.get("glyphs", {})
        main_page = next(page for page in draft["pages"] if page["index"] == 0)
        for position, glyph in (layout.get("icon_only") or {}).items():
            main_page["buttons"].append({"index": c.TAG[position], "transport": "icon", "glyph": glyph})
        for page in draft["pages"]:
            number = page["index"]
            if number and (link := f"p0_k{number - 1}") in glyphs:
                page["link_glyph"] = glyphs[link]
            if number:
                page["title"] = layout.get("page_names", {}).get(str(number), "")
            for key in page["buttons"]:
                identity = f"p{number}_k{key['index']}"
                if identity in glyphs:
                    key["glyph"] = glyphs[identity]
        return draft
    pages = []
    for packet in source_packets(remote):
        c.rewrite_ir_page(packet, remote_index=packet[7], name="")
        body = packet[7:]
        buttons = []
        for offset in range(83, len(body), 36):
            record = body[offset:offset + 36]
            # A–D on Main keep their template icon (kind 254: the stock picture, no command), so a
            # save leaves it where it was; every other kind 4/254 record is a page link or filler.
            template = body[81] == 0 and record[0] < 4 and record[3] == 254
            if (record[3] in (4, 254) and not template) or (body[81] == 0 and record[0] == c.KATA_POSITION):
                continue
            buttons.append({"index": record[0], "function": int.from_bytes(record[1:3], "big"),
                            "transport": "stored", "record": record.hex()})
        pages.append({"index": body[81], "buttons": buttons})
    if not pages:
        raise ValueError("Physical pages are unavailable. Reinstall this IR profile once to cache its commands.")
    _restore_ir_menu_links(remote, pages)
    _mark_number_pads(device_type, pages)
    return {"kind": "ir", "pages": pages}


def _menu_title(title: str) -> str:
    if not isinstance(title, str):
        raise ValueError("Enter a name as text")
    title = title.strip()
    if len(title) > 60 or any(not char.isprintable() for char in title):
        raise ValueError("Enter a name of up to 60 characters on one line")
    return title


def rename_menu_item(draft: dict, page_index: int, row_index: int | None, title: str) -> None:
    """Change a Studio label on an existing submenu without altering its key records."""
    page = next((page for page in draft["pages"] if page["index"] == page_index and page_index), None)
    if page is None:
        raise ValueError("Menu page not found")
    item = page if row_index is None else next(
        (key for key in page["buttons"] if key["index"] == row_index), None)
    if item is None:
        raise ValueError("Menu item not found")
    item["title"] = _menu_title(title)


def validate(remote: dict, draft: dict) -> dict:
    result = deepcopy(draft)
    expected = draft_for({key: value for key, value in remote.items() if key != "physical_layout"})["kind"]
    if result.get("kind") != expected:
        raise ValueError("The remote transport cannot be changed")
    if expected == "native":
        template = str(result.get("template") or draft_for(remote).get("template") or "FAN").upper()
        template = c.NATIVE_PROFILE_ALIASES.get(template, template)
        if template not in c.NATIVE_PROFILE_LAYOUTS:
            raise ValueError(f"Unsupported native screen profile: {template}")
        result["template"] = template
        result["native_type"] = str(result.get("native_type") or template).upper()
        native_type = c.native_type_metadata(result["native_type"])
        if native_type["profile"] != template:
            legacy_type = remote.get("native_type") or remote.get("device_type")
            if result["native_type"] != legacy_type:
                raise ValueError("The selected remote type does not match its button layout")
            result["native_type"] = c.native_profile_device_type(template) or template
            native_type = c.native_type_metadata(result["native_type"])
        if not c.native_device_type_supported(native_type["device_type"]):
            raise ValueError("Choose a type supported by WoRWS local page writes")
        appearance = native_appearance(remote)
        same_type = appearance["native_type"] == native_type["value"]
        result["control_mode"] = appearance["control_mode"] if same_type else native_type["control_mode"]
        icon = appearance["icon_code"] if same_type else native_type["icon_code"]
        result["icon_name"] = next((name for name, value in c.ICON.items() if value == icon),
                                   native_type["icon_name"])
    pages = result.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= 5:
        raise ValueError("Use Main and up to four pages A–D")
    seen_pages = set()
    device_type = str(remote.get("device_type", "")).upper()
    fixed_softkeys = expected == "ir" and fixed_softkey_functions(device_type) is not None
    blocked_positions = page_only_positions(device_type) if expected == "ir" else frozenset()
    for page in pages:
        number = page.get("index")
        if type(number) is not int or not 0 <= number <= 4 or number in seen_pages:
            raise ValueError("Page IDs must be unique numbers from 0 to 4")
        seen_pages.add(number)
        if "title" in page:
            page["title"] = _menu_title(page["title"])
        if "number_pad" in page:
            if page["number_pad"] is not True or expected != "ir" or not number:
                raise ValueError("Only a page of an IR remote can be a number pad")
            _check_number_pad_keys(page.get("buttons"))
        buttons = page.get("buttons")
        if fixed_softkeys and number == 0 and isinstance(buttons, list):
            # This window draws a fixed picture on A–D and ignores any icon, so a chosen icon is
            # dropped (an older layout may carry one) and so is an icon-only key, which it would hide.
            buttons[:] = [key for key in buttons
                          if not (key.get("transport") == "icon" and key.get("index", 9) < 4)]
            for key in buttons:
                if key.get("index", 9) < 4:
                    key.pop("glyph", None)
        limit = 15 if expected == "hid" and number else 18
        minimum = 0 if number == 0 and len(pages) > 1 else 1
        if not isinstance(buttons, list) or not minimum <= len(buttons) <= limit:
            raise ValueError(f"Page {number} must have 1–{limit} buttons")
        if "link_glyph" in page:
            if expected != "native" or not number:
                raise ValueError("Only Native submenu links support a menu icon")
            _validate_glyph(page["link_glyph"])
            c.validate_native_menu_glyph(page["link_glyph"])
        if "link_record" in page:
            record = bytes.fromhex(str(page["link_record"]))
            if expected != "ir" or not number or len(record) != 36:
                raise ValueError("IR menu links must come from the cached profile")
            originals = (_ir_menu_link_records(source_packets(remote)) + _ir_menu_link_records(
                [bytes.fromhex(value) for value in remote.get("physical_original_packets", [])]
            ))
            if not any(record[1:] == original[1:] for original in originals):
                raise ValueError("IR menu links must come from the cached profile")
        seen = set()
        for key in buttons:
            index = key.get("index")
            if type(index) is not int or not 0 <= index <= (18 if number == 0 else limit - 1) or index in seen:
                raise ValueError("Button positions must be unique and within the page")
            if number == 0 and index == c.KATA_POSITION:
                raise ValueError("KATA is reserved for the Universal Remote")
            seen.add(index)
            if "title" in key:
                key["title"] = _menu_title(key["title"])
            if "glyph" in key:
                # An IR remote's own (typed or learned) keys carry their icon as the key's
                # function id, the same way an HID remote's IR keys do. Stored commands keep
                # the record they came with.
                supports_glyph = expected == "native" or (
                    expected in ("hid", "ir") and key.get("transport") == "ir"
                ) or (expected == "ir" and key.get("transport") == "icon")
                if not supports_glyph or (not number and index > 3):
                    raise ValueError("This position does not support a screen icon")
                _validate_glyph(key["glyph"])
                if (expected in ("hid", "ir") or key.get("transport") == "icon") and key["glyph"] == 0:
                    raise ValueError("Choose a nonzero icon for an IR button")
                if (not number and key["glyph"] in MENU_SHORTCUT_FUNCTIONS
                        and (expected, key.get("transport")) in (("ir", "ir"), ("native", "native"))):
                    # The firmware reads these as a menu shortcut: with no page behind the key,
                    # pressing it shows "No list under this shortcut" and sends nothing.
                    raise ValueError("That icon is a menu shortcut; choose another for a key that sends a command")
            transport = key.get("transport")
            if (not number and index < 4 and not fixed_softkeys and not is_template_key(key)
                    and (expected, transport) in (("ir", "ir"), ("ir", "stored"), ("native", "native"))
                    and _key_function(key) in MENU_SHORTCUT_FUNCTIONS):
                # The key's own function (its icon unless one is chosen) decides on these windows:
                # a menu function makes the key open a menu, or show "No list under this shortcut"
                # with none behind it, instead of sending its command.
                raise ValueError(f"Key {'ABCD'[index]} carries a menu icon and would not send its "
                                 "command; choose another icon for it")
            if (transport == "ir" and not number and index in blocked_positions):
                raise ValueError(
                    f"Key {'ABCD'[index]} only opens a page on this type of remote and cannot send a command")
            allowed = ({"native", "icon"} if expected == "native" else {"hid", "ir"} if expected == "hid"
                       else {"stored", "ir", "icon"})
            if transport == "icon" and (number or index > 3 or key.get("glyph") is None):
                # An icon without a command is the record the A–D softkeys use: a shown softkey.
                raise ValueError("Only an A–D key on Main can hold an icon without a command, "
                                 "and it needs an icon")
            if transport not in allowed:
                raise ValueError(f"{transport} commands are not supported inside {expected} profiles")
            if transport in ("native", "hid"):
                function = key.get("function")
                if type(function) is not int or not 0 <= function <= 65535:
                    raise ValueError("Function must be a number from 0 to 65535")
            elif transport == "icon":
                pass
            elif transport == "ir":
                try:
                    code = bytes.fromhex(str(key.get("code_hex", "")))
                except ValueError:
                    raise ValueError("The IR code must be hex, two characters per byte") from None
                if not code or len(code) > 65536:
                    raise ValueError("Enter an IR code of 1–65536 bytes")
                key["code_hex"] = code.hex()
            else:
                record = bytes.fromhex(str(key.get("record", "")))
                packets = source_packets(remote) + [bytes.fromhex(value) for value in remote.get("physical_original_packets", [])]
                originals = [packet[offset:offset + 36] for packet in packets
                             for offset in range(90, len(packet), 36)]
                if len(record) != 36 or not any(record[1:] == original[1:] for original in originals):
                    raise ValueError("Stored IR commands must come from the cached profile")
        if expected == "native" and number and seen != set(range(len(buttons))):
            raise ValueError("Native submenu positions must be consecutive starting at zero")
    if 0 not in seen_pages:
        raise ValueError("The Main page is required")
    if expected == "ir":
        _check_ir_pages(device_type, pages)
    if expected in ("native", "hid", "ir"):
        main = next(page for page in pages if page["index"] == 0)
        reserved = {number - 1 for number in seen_pages if number}
        if any(key["index"] in reserved for key in main["buttons"]):
            raise ValueError("A–D positions with pages are reserved for page links; remove their Main-page commands")
        if len(main["buttons"]) + len(reserved) > 18:
            raise ValueError("Main supports at most 18 commands including page links")
    result["pages"] = sorted(pages, key=lambda page: page["index"])
    return result


def _icon_code(remote: dict, icon_name: str | None) -> int:
    if icon_name:
        return c.ICON[icon_name.lower()]
    stored = remote.get("icon_code")
    if isinstance(stored, int) and 0 <= stored <= 0xFF:
        return stored
    packets = source_packets(remote)
    if packets and len(packets[0]) > 11:
        return packets[0][11]
    name = str(remote.get("icon", "")).lower()
    if name in c.ICON:
        return c.ICON[name]
    return 0


def compile_pages(
    remote: dict, draft: dict, slot: int, *, name: str | None = None,
    icon_name: str | None = None,
) -> tuple[list[tuple[str, bytes, frozenset]], list[bytes]]:
    """Compile all commands before any device mutation. Named IR uploads precede page deletion."""
    draft = validate(remote, draft)
    display_name = name if name is not None else str(remote.get("name", "Remote"))
    icon_code = _icon_code(remote, icon_name)
    uploads = []
    packets = []
    device_type = str(remote["device_type"]).upper()
    stock_softkeys = fixed_softkey_functions(device_type) if draft["kind"] == "ir" else None
    for page in draft["pages"]:
        number = page["index"]
        keys = []
        for key in page["buttons"]:
            index = key["index"]
            transport = key["transport"]
            if transport == "icon":
                # A shown softkey: the picture only, with no command behind it. With no icon it is
                # nothing at all: no record, so the remote leaves the place empty.
                function = int(key["glyph"])
                if function in (0, 115, 0x07D3):
                    continue
                keys.append(bytes([index]) + c.s16(function) + b"\x04" + c.pad(c.s16(function), 32))
            elif transport == "ir":
                # Main names match the official HID editor; submenu names are stable and unique.
                name = str(index) if number == 0 else f"p{number}_k{index}"
                code = bytes.fromhex(key["code_hex"])
                if draft["kind"] == "hid":
                    uploads.extend(c.build_hid_ir_transfer(device_id=remote["device_id"], key_name=name, code=code))
                else:
                    uploads.extend(c.build_ir_transfer_sequence(
                        c.id_to_bytes(remote["device_id"]), code, data_type=3, transfer_name=name))
                default_function = 0x07D3 if draft["kind"] == "hid" else 115
                function = int(key.get("glyph", key.get("function", default_function)))
                if draft["kind"] == "hid" and function == 0:
                    function = default_function
                if stock_softkeys and number == 0 and index < 4:
                    # A fixed window shows an A–D key only for a record with its own id.
                    function = stock_softkeys[index]
                keys.append({"index": index, "ir_name": name,
                             "function": function})
            elif transport == "hid":
                keys.append({"index": index, "hid_usage": key["function"].to_bytes(2, "big")})
            elif transport == "stored":
                record = bytearray.fromhex(key["record"])
                record[0] = index
                keys.append(bytes(record))
        if draft["kind"] == "hid":
            if number == 0:
                keys.extend({"index": p["index"] - 1, "hid_usage": hid_usage(device_type, "ABCD"[p["index"] - 1]).to_bytes(2, "big")}
                            for p in draft["pages"] if p["index"])
            packets.append(c.build_hid_edit_page(remote_index=slot, device_type_name=device_type,
                device_id=remote["device_id"], name=display_name, page_index=number,
                keys=keys, icon=icon_code))
        elif draft["kind"] == "ir":
            records = []
            for key in keys:
                if isinstance(key, bytes):
                    records.append(key)
                else:
                    records.append(bytes([key["index"]]) + c.s16(key["function"]) + b"\x02" + c.pad(key["ir_name"].encode(), 32))
            if number == 0:
                for child in draft["pages"]:
                    if child["index"]:
                        position = child["index"] - 1
                        number_pad = bool(child.get("number_pad"))
                        # 39 opens the number pad and any other menu function a list, so a cached
                        # link is kept only while it still opens what the page is.
                        if (child.get("link_record")
                                and (_link_function(child) == NUMBER_PAD_LINK) == number_pad):
                            records.append(bytes([position]) + bytes.fromhex(child["link_record"])[1:])
                        else:
                            function = (NUMBER_PAD_LINK if number_pad
                                        else list_link_functions(device_type)[position])
                            records.append(bytes([position]) + c.s16(function) + b"\x04" + c.pad(c.s16(function), 32))
                if len(records) > 18:
                    raise ValueError("Main page has more than 18 commands including page links")
            source = source_packets(remote)[0]
            header = bytearray(source[7:90])
            header[0] = slot
            header[4] = icon_code
            name_bytes = bytearray(c.pad(display_name.encode("utf-8"), 64))
            name_bytes[63] = 0
            header[16:80] = name_bytes
            header[81:83] = bytes([number, len(records)])
            body = bytes(header) + b"".join(records)
            packets.append(b"\x0f\x62\x06" + c.s16(len(body)) + c.s16(c.crc16_modbus(body)) + body)
    return uploads, packets


def compile_recreate(
    remote: dict, *, slot: int, device_type: int, control_type: int,
    name: str, icon_name: str | None,
) -> tuple[list[tuple[str, bytes, frozenset[int]]], list[bytes], dict]:
    """Compile a key-only replacement that preserves the installed IR/HID remote row."""
    draft = validate(remote, draft_for(remote))
    uploads, pages = compile_pages(
        remote, draft, slot, name=name, icon_name=icon_name,
    )
    device_id = str(remote["device_id"])
    if draft["kind"] == "hid":
        device_type_name = str(remote["device_type"]).upper()
        delete = c.build_delete_hid_keys(
            remote_index=slot, device_type_name=device_type_name, device_id=device_id,
        )
    elif draft["kind"] == "ir":
        delete = (
            bytes([0x0F, 0x62, 0x04, 0x01, slot & 0xFF])
            + c.device_type_bytes(device_type)
            + bytes([control_type & 0xFF])
            + c.id_to_bytes(device_id)
            + b"\xff\xff"
        )
    else:
        raise ValueError("Only IR and HID layouts can be rebuilt as key pages")
    stages = uploads + [("delete old key pages", delete, frozenset({1}))]
    stages.extend(
        (f"write page {packet[88]}", packet, frozenset({1}))
        for packet in pages
    )
    return stages, pages, draft


def removed_native_keys(previous: dict, draft: dict) -> list[tuple[int, int]]:
    """Find vacated wire positions, including implicit Main links to removed pages."""
    def positions(layout):
        return {
            (page["index"], button["index"])
            for page in layout["pages"] for button in page["buttons"]
        } | {(0, page["index"] - 1) for page in layout["pages"] if page["index"]}

    return sorted(positions(previous) - positions(draft))


def native_layout(draft: dict) -> dict:
    positions = {value: name for name, value in c.TAG.items()}
    glyphs = {}
    icon_only = {}
    for page in draft["pages"]:
        number = page["index"]
        if "link_glyph" in page:
            glyphs[f"p0_k{number - 1}"] = page["link_glyph"]
        for key in page["buttons"]:
            if key["transport"] == "icon":
                # A picture with no action: it is the key's function, not a glyph over one.
                icon_only[positions[key["index"]]] = key["glyph"]
            elif "glyph" in key:
                glyphs[f"p{number}_k{key['index']}"] = key["glyph"]
    return {"layout_version": 2, "template": draft.get("template", "FAN"),
            "glyphs": glyphs, "icon_only": icon_only,
            "native_type": draft.get("native_type", draft.get("template", "FAN")),
            "control_mode": int(draft.get("control_mode", 0)),
            "icon_name": draft.get("icon_name", "light"), "main_buttons": {
        positions[key["index"]]: c.custom_action_name(key["function"])
        for page in draft["pages"] if page["index"] == 0 for key in page["buttons"]
        if key["transport"] != "icon"
    }, "pages": {str(page["index"]): [c.custom_action_name(key["function"]) for key in sorted(page["buttons"], key=lambda k: k["index"])]
                 for page in draft["pages"] if page["index"]}}
