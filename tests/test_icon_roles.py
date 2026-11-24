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
