"""What an icon does besides its picture depends on where the key is (WoRWS V48, decoded).

evidence/mixed-v48/icon-roles.md: on Main A–D of IR and Native remotes a menu icon makes the key a
menu shortcut ("No list under this shortcut" with no page behind it) and 123 (39) opens the number
pad; list rows and HID keys never look at the icon, so any icon is only the picture there.
"""
import pytest

from conftest import INTEGRATION, load

physical = load(INTEGRATION / "physical_layout.py")
glyphs = load(INTEGRATION / "ir_glyphs.py")


def _native_remote():
    return {"device_type": "STRIP", "device_id": "001122334455", "name": "Strip", "icon": "strip"}


def _with_main_glyph(draft, index, glyph):
    main = next(page for page in draft["pages"] if page["index"] == 0)
    key = next((key for key in main["buttons"] if key["index"] == index), None)
    if key is None:
        key = {"index": index, "transport": "native", "function": 5}
        main["buttons"].append(key)
    key["glyph"] = glyph
    return draft


def test_a_native_command_on_a_to_d_refuses_menu_icons():
    remote = _native_remote()
    draft = physical.draft_for(remote)
    free = next(index for index in range(4) if not any(
        page["index"] == index + 1 for page in draft["pages"]))
    for glyph in (39, 100, 20):
        with pytest.raises(ValueError, match="menu shortcut"):
            physical.validate(remote, _with_main_glyph(physical.draft_for(remote), free, glyph))
    physical.validate(remote, _with_main_glyph(physical.draft_for(remote), free, 105))


def test_the_123_icon_is_named_for_the_number_pad():
    import re
    source = (INTEGRATION / "frontend" / "switchbot-urc-panel.js").read_text()
    assert re.search(r'"39": "123 \(number\xa0pad\)"', source)
    assert 39 in glyphs.MENU_SHORTCUT_FUNCTIONS and glyphs.NUMBER_PAD_LINK == 39


def _blank_ir(device_type):
    cloud_ir = load(INTEGRATION / "cloud_ir.py")
    packets = cloud_ir.blank_profile(device_type, "Empty").build_pages(remote_index=5, name="Empty")
    return {"device_type": f"IR_{device_type}", "device_id": "001122334455", "name": "Empty",
            "physical_packets": [bytes(packet).hex() for packet in packets]}


@pytest.mark.parametrize("device_type", [2, 8])
def test_an_ir_command_on_a_to_d_is_refused_when_its_own_function_is_a_menu_one(device_type):
    # A new A key used to take its stock link function (39, the 123 icon) as its function: the
    # remote would then show "No list under this shortcut" instead of sending the code.
    remote = _blank_ir(device_type)
    key = {"index": 0, "transport": "ir", "code_hex": "aa", "function": 39}
    with pytest.raises(ValueError, match="menu icon"):
        physical.validate(remote, {"kind": "ir", "pages": [{"index": 0, "buttons": [key]}]})
    key["glyph"] = 105                                       # a chosen icon decides instead
    physical.validate(remote, {"kind": "ir", "pages": [{"index": 0, "buttons": [key]}]})
    # an HID key always sends its command, whatever its function
    hid = {"device_type": "UNIVERSAL_BLE", "device_id": "001122334455", "buttons": ["ON"]}
    physical.validate(hid, {"kind": "hid", "pages": [{"index": 0, "buttons": [
        {"index": 0, "transport": "hid", "function": 39}]}]})


def test_a_native_a_to_d_action_with_a_menu_function_is_refused():
    remote = _native_remote()
    draft = physical.draft_for(remote)
    main = next(page for page in draft["pages"] if page["index"] == 0)
    free = next(index for index in range(4) if not any(
        page["index"] == index + 1 for page in draft["pages"]))
    main["buttons"] = [key for key in main["buttons"] if key["index"] != free]
    main["buttons"].append({"index": free, "transport": "native", "function": 119})   # MODE
    with pytest.raises(ValueError, match="menu icon"):
        physical.validate(remote, draft)
