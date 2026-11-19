"""Every IR type gets the official app's layout through the cloud profile, and catalog ids map to it."""
from conftest import INTEGRATION, load

ir_catalog = load(INTEGRATION / "ir_catalog.py")
cloud_ir = load(INTEGRATION / "cloud_ir.py")

REMOTE_ID = "01-202611190101-12345678"


def profile(device_type, key_map="11:0:10;9:10:10", **extra):
    item = {"code": cloud_ir.base64.b64encode(bytes(range(64))).decode(), "keyMap": key_map, **extra}
    return cloud_ir.profile_from_cloud(item, remote_id=REMOTE_ID, name="Remote",
                                       remote_type=device_type)


def test_catalog_types_become_the_remote_types_of_the_app():
    assert ir_catalog.app_remote_type(3) == 14      # light
    assert ir_catalog.app_remote_type(4) == 3       # IPTV
    assert ir_catalog.app_remote_type(11) == 10     # air purifier
    assert ir_catalog.app_remote_type(14) == 13     # robot vacuum
    assert ir_catalog.app_remote_type(1) == 1 and ir_catalog.app_remote_type(2) == 2
    # every catalog type has a layout (air conditioners and TVs included)
    for catalog_type in ir_catalog.REMOTE_TYPES:
        remote_type = ir_catalog.app_remote_type(catalog_type)
        assert remote_type in cloud_ir.PAGE_LAYOUTS or remote_type in (2, 16), catalog_type


def test_each_type_is_laid_out_by_its_own_builder_not_the_generic_one():
    generic = cloud_ir.commands.build_ir_pages
    for remote_type in cloud_ir.PAGE_LAYOUTS:
        extra = {"keyMap": "1:0:10;3:10:10;5:20:10"}
        pages = profile(remote_type, **extra).build_pages(remote_index=3, name="Remote")
        assert pages, remote_type
        assert pages != generic(remote_index=3, device_type=remote_type,
                                remote_id=cloud_ir.commands.cloud_remote_id_to_bytes(REMOTE_ID),
                                name="Remote", key_map=[(1, 0, 10), (3, 10, 10), (5, 20, 10)]), remote_type


def test_an_air_conditioner_needs_no_code_references_in_its_key_map():
    ac = profile(1, key_map="")
    assert ac.build_pages(remote_index=3, name="AC")
