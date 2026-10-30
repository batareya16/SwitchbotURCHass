"""Physical page drafts and protocol compilation, separate from HA action mappings."""
from __future__ import annotations

from copy import deepcopy

from . import commands as c
from .ir_profiles import PROFILES


def source_packets(remote: dict) -> list[bytes]:
    if remote.get("physical_packets"):
        return [bytes.fromhex(value) for value in remote["physical_packets"]]
    profile = PROFILES.get(remote.get("profile"))
    return list(profile.pages) if profile else []


def hid_usage(device_type: str, position: str) -> int:
    common = {"ON": 105, "OFF": 105, "UP": 9, "DOWN": 10, "LEFT": 7,
              "RIGHT": 8, "OK": 11, "BACK": 12, "HOME": 0x838,
              "SOUNDOFF": 0x834, "VOLADD": 15, "VOLDEL": 16, "CHUP": 15, "CHDOWN": 16,
              "A": 0x837, "B": 0x835, "C": 0x836, "D": 0x839}
    if device_type == "GOOGLE_TV":
        common.update(dict.fromkeys("ABCD", 0x7D3))
        common["BACK"] = 0x83A
    elif device_type == "APPLE_TV":
        common.update({"A": 0x7D1, "B": 0x7D3, "C": 0x7D3, "D": 0x7D3,
                       "BACK": 0x7D2, "HOME": 0x839, "SOUNDOFF": 0x7D0})
    return common.get(position, 115)


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
        if item.get("type") == "list":
            if not 0 <= index <= 3:
                raise ValueError("Only A–D can open HID pages")
            pages.append({"index": index + 1, "buttons": [convert(child, child_index, index) for child_index, child in enumerate(item.get("buttonList", []))]})
        else:
            main.append(convert(item, index))
    return {"kind": "hid", "pages": [{"index": 0, "buttons": main}] + pages}


def draft_for(remote: dict) -> dict:
    if remote.get("physical_layout"):
        return deepcopy(remote["physical_layout"])
    device_type = str(remote.get("device_type", "")).upper()
    if device_type in c.DEVTYPE:
        return {"kind": "hid", "pages": [{"index": 0, "buttons": [
            {"index": c.TAG[name], "transport": "hid", "function": hid_usage(device_type, name)}
            for name in remote.get("buttons", []) if name in c.TAG
        ]}]}
    if device_type in c.NATIVE_DEVTYPE:
        layout = remote.get("custom_layout") or c.editable_layout_from_native_profile(device_type)
        main = c.normalize_main_buttons(layout.get("main_buttons", {}))
        return {"kind": "native", "pages": [{"index": 0, "buttons": [
            {"index": c.TAG[position], "transport": "native", "function": c.custom_action_function(action)}
            for position, action in main.items()
        ]}] + [{"index": int(page), "buttons": [
            {"index": index, "transport": "native", "function": c.custom_action_function(action)}
            for index, action in enumerate(actions)
        ]} for page, actions in layout.get("pages", {}).items()]}
    pages = []
    for packet in source_packets(remote):
        c.rewrite_ir_page(packet, remote_index=packet[7], name="")
        body = packet[7:]
        buttons = []
        for offset in range(83, len(body), 36):
            record = body[offset:offset + 36]
            if record[3] in (4, 254):
                continue
            buttons.append({"index": record[0], "function": int.from_bytes(record[1:3], "big"),
                            "transport": "stored", "record": record.hex()})
        pages.append({"index": body[81], "buttons": buttons})
    if not pages:
        raise ValueError("Physical pages are unavailable. Reinstall this IR profile once to cache its commands.")
    return {"kind": "ir", "pages": pages}


def validate(remote: dict, draft: dict) -> dict:
    result = deepcopy(draft)
    expected = draft_for({key: value for key, value in remote.items() if key != "physical_layout"})["kind"]
    if result.get("kind") != expected:
        raise ValueError("The remote transport cannot be changed")
    pages = result.get("pages")
    if not isinstance(pages, list) or not 1 <= len(pages) <= 5:
        raise ValueError("Use Main and up to four pages A–D")
    seen_pages = set()
    for page in pages:
        number = page.get("index")
        if type(number) is not int or not 0 <= number <= 4 or number in seen_pages:
            raise ValueError("Page IDs must be unique numbers from 0 to 4")
        seen_pages.add(number)
        buttons = page.get("buttons")
        limit = 15 if expected == "hid" and number else 18
        minimum = 0 if number == 0 and len(pages) > 1 else 1
        if not isinstance(buttons, list) or not minimum <= len(buttons) <= limit:
            raise ValueError(f"Page {number} must have 1–{limit} buttons")
        seen = set()
        for key in buttons:
            index = key.get("index")
            if type(index) is not int or not 0 <= index <= (18 if number == 0 else limit - 1) or index in seen:
                raise ValueError("Button positions must be unique and within the page")
            seen.add(index)
            transport = key.get("transport")
            allowed = {"native"} if expected == "native" else {"hid", "ir"} if expected == "hid" else {"stored", "ir"}
            if transport not in allowed:
                raise ValueError(f"{transport} commands are not supported inside {expected} profiles")
            if transport in ("native", "hid"):
                function = key.get("function")
                if type(function) is not int or not 0 <= function <= 65535:
                    raise ValueError("Function must be a number from 0 to 65535")
            elif transport == "ir":
                code = bytes.fromhex(str(key.get("code_hex", "")))
                if not code or len(code) > 65536:
                    raise ValueError("Choose an IR code of 1–65536 bytes")
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
    if expected in ("native", "hid", "ir"):
        main = next(page for page in pages if page["index"] == 0)
        reserved = {number - 1 for number in seen_pages if number}
        if any(key["index"] in reserved for key in main["buttons"]):
            raise ValueError("A–D positions with pages are reserved for page links; remove their Main-page commands")
        if len(main["buttons"]) + len(reserved) > 18:
            raise ValueError("Main supports at most 18 commands including page links")
    result["pages"] = sorted(pages, key=lambda page: page["index"])
    return result


def compile_pages(remote: dict, draft: dict, slot: int) -> tuple[list[tuple[str, bytes, frozenset]], list[bytes]]:
    """Compile all commands before any device mutation. Named IR uploads precede page deletion."""
    draft = validate(remote, draft)
    uploads = []
    packets = []
    device_type = str(remote["device_type"]).upper()
    for page in draft["pages"]:
        number = page["index"]
        keys = []
        for key in page["buttons"]:
            index = key["index"]
            transport = key["transport"]
            if transport == "ir":
                # Main names match the official HID editor; submenu names are stable and unique.
                name = str(index) if number == 0 else f"p{number}_k{index}"
                code = bytes.fromhex(key["code_hex"])
                if draft["kind"] == "hid":
                    uploads.extend(c.build_hid_ir_transfer(device_id=remote["device_id"], key_name=name, code=code))
                else:
                    uploads.extend((stage, packet, frozenset({1})) for stage, packet, _ in c.build_ir_transfer_sequence(
                        c.id_to_bytes(remote["device_id"]), code, data_type=3, transfer_name=name))
                keys.append({"index": index, "ir_name": name, "function": int(key.get("function", 115))})
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
                device_id=remote["device_id"], name=remote["name"], page_index=number, keys=keys))
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
                        function = (39, 20, 210, 100)[position]
                        records.append(bytes([position]) + c.s16(function) + b"\x04" + c.pad(c.s16(function), 32))
                if len(records) > 18:
                    raise ValueError("Main page has more than 18 commands including page links")
            source = source_packets(remote)[0]
            header = bytearray(source[7:90])
            header[0] = slot
            header[81:83] = bytes([number, len(records)])
            body = bytes(header) + b"".join(records)
            packets.append(b"\x0f\x62\x06" + c.s16(len(body)) + c.s16(c.crc16_modbus(body)) + body)
    return uploads, packets


def native_layout(draft: dict) -> dict:
    positions = {value: name for name, value in c.TAG.items()}
    return {"layout_version": 2, "main_buttons": {
        positions[key["index"]]: c.custom_action_name(key["function"])
        for page in draft["pages"] if page["index"] == 0 for key in page["buttons"]
    }, "pages": {str(page["index"]): [c.custom_action_name(key["function"]) for key in sorted(page["buttons"], key=lambda k: k["index"])]
                 for page in draft["pages"] if page["index"]}}
