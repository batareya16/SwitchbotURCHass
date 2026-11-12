"""The remote's icon must not replace its type or physical button pages."""

from conftest import INTEGRATION, load


commands = load(INTEGRATION / "commands.py")
profiles = load(INTEGRATION / "ir_profiles.py")
cloud_ir = load(INTEGRATION / "cloud_ir.py")


def _pages(stages):
    return [packet for stage, packet, *_ in stages if stage.startswith(("ir_page_", "bind_page_"))]


def test_captured_ir_icon_rewrites_every_page_without_changing_buttons():
    original = profiles.CAPTURED_TV.build_install(
        remote_index=2, name="TV", remote_count=3,
    )
    updated = profiles.CAPTURED_TV.build_install(
        remote_index=2, name="TV", remote_count=3, icon=commands.ICON["floorlamp"],
    )
    assert original[0][1][11] == 0
    assert updated[0][1][11] == commands.ICON["floorlamp"]
    for before, after in zip(_pages(original), _pages(updated), strict=True):
        assert after[8] == before[8]  # device type
        assert after[11] == commands.ICON["floorlamp"]
        assert after[90:] == before[90:]  # key records
        commands.rewrite_ir_page(after, remote_index=2, name="TV")  # CRC valid


def test_cloud_ir_icon_rewrites_header_and_pages():
    profile = cloud_ir.CloudIrProfile(
        key="cloud", title="Cloud", default_name="Lamp",
        remote_id=bytes.fromhex("01141a0a0e17030b1f4d5b"),
        remote_id_text="test", device_type=2,
        code_bank=b"\x10\x20\x30", key_map=((1, 0, 3),),
    )
    original = profile.build_install(remote_index=1, name="Lamp", remote_count=2)
    updated = profile.build_install(
        remote_index=1, name="Lamp", remote_count=2, icon=commands.ICON["strip"],
    )
    assert updated[0][1][11] == commands.ICON["strip"]
    for before, after in zip(_pages(original), _pages(updated), strict=True):
        assert after[8] == before[8]
        assert after[11] == commands.ICON["strip"]
        assert after[90:] == before[90:]


def test_custom_native_recreate_keeps_pages_and_changes_only_icon():
    kwargs = dict(
        key_id=1, target_key=bytes.fromhex("00112233445566778899aabbccddeeff"),
        remote_index=3, name="Home Control", device_id="DA:71:16:E0:1F:92",
        event_remote_id="abcdef01", main_buttons={"ON": "ON", "OFF": "OFF"},
        page_buttons={1: ["BRIGHTER", "DARKER"]},
    )
    original = commands.build_custom_native_bind_sequence(icon_name="tv", **kwargs)
    updated = commands.build_custom_native_bind_sequence(icon_name="floorlamp", **kwargs)
    before_pages = _pages(original)
    after_pages = _pages(updated)
    assert len(after_pages) == len(before_pages) == 2
    for before, after in zip(before_pages, after_pages, strict=True):
        assert after[8] == before[8] == commands.NATIVE_DEVTYPE["FAN"]
        assert after[11] == commands.ICON["floorlamp"]
        assert after[90:] == before[90:]
