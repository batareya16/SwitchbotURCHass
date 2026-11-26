"""The account's list of this Universal Remote's remotes, kept in step with the remote.

The SwitchBot app compares the two (checkDiffDevice / checkDiffScenes in its bundle) and offers to
"clean" the remote on any difference; these tests use the user's own table.
"""
from conftest import INTEGRATION, load

sync = load(INTEGRATION / "cloud_sync.py")

TABLE = [
    (0, 0x02, 1, bytes.fromhex("01141a0b13013a153a6331")),     # TV (IR, account)
    (1, 0x18, 1, bytes.fromhex("01141a0a0f01034409390f")),     # Soundbar (IR, account)
    (2, 0x27, 3, bytes.fromhex("00000000544d0000000000")),     # text remote
    (3, 0x72, 0, bytes.fromhex("911fe01b888a0000000000")),     # TV Ambience (Bridge)
    (4, 0x72, 0, bytes.fromhex("921fe01671da0000000000")),     # Floor lamp (Bridge)
    (5, 0x08, 1, bytes.fromhex("01141a0b1811235d572641")),     # Birds light (made in Studio)
    (6, 0xF2, 4, bytes.fromhex("5464379317020000000000")),     # Mi Box S (HID)
]
TV_ID = sync.remote_id_from_bytes(TABLE[0][3])
BAR_ID = sync.remote_id_from_bytes(TABLE[1][3])
BIRDS_ID = sync.remote_id_from_bytes(TABLE[5][3])
BOUND = [
    {"remoteID": TV_ID, "remoteName": "TV", "type": 2, "remoteIndex": 0, "createFrom": "hub"},
    {"remoteID": BAR_ID, "remoteName": "Soundbar", "type": 24, "remoteIndex": 3},     # wrong slot
    {"remoteID": "01-202601010101-11111111", "remoteName": "Old", "type": 2, "remoteIndex": 7},
]
REMOTES = [
    {"name": "Birds light", "device_type": "IR_8", "device_id": TABLE[5][3].hex(),
     "physical_layout": {"kind": "ir", "pages": [{"index": 0, "buttons": [
         {"index": 4, "transport": "ir", "code_hex": "aabb"}]}, {"index": 4, "buttons": [
         {"index": 0, "transport": "ir", "code_hex": "ccdd", "title": "Night"}]}]}},
    {"name": "Mi Box S", "device_type": "UNIVERSAL_BLE", "device_id": "021793376454"},
    {"name": "Floor lamp", "device_type": "STRIP", "device_id": "DA:71:16:E0:1F:92"},
]
SCENES = [{"index": 0, "name": "Sleep", "icon": 21, "color": 6}]


def test_ids_take_the_account_form():
    assert TV_ID == "01-202611190158-21589949"
    assert sync.remote_id_from_bytes(bytes([1, 200] + [0] * 9)) is None       # not decimal pairs


def test_the_differences_are_those_the_app_sees():
    found = sync.differences(BOUND, TABLE, SCENES)
    assert "Soundbar: slot 3 in the account, 1 on the remote" in found
    assert "Old: in the account, not on the remote" in found
    assert "Slot 5: on the remote, not in the account" in found
    assert "Scene 0 (Sleep): on the remote, not in the account" in found
    assert not any(line.startswith("TV") for line in found)


def test_the_plan_lists_every_row_at_its_slot_creates_studio_remotes_and_removes_the_rest():
    known = {TV_ID, BAR_ID, "01-202601010101-11111111"}
    steps = sync.plan(TABLE, REMOTES, BOUND, known, SCENES)
    items = steps["items"]
    assert [item.get("remoteIndex", item.get("sceneIndex")) for item in items] == [0, 1, 2, 3, 4, 5, 6, 0]
    assert items[0]["createFrom"] == "hub" and items[1]["remoteIndex"] == 1
    assert items[2] == {"deviceID": "4D5400000000", "deviceName": "Remote 3", "deviceType": "WoMatter",
                        "remoteIndex": 2, "roomName": ""}
    assert items[4]["deviceID"] == "DA7116E01F92" and items[4]["deviceName"] == "Floor lamp"
    assert items[6]["thirdPartyDeviceID"] == "021793376454" and items[6]["thirdPartyType"] == "UniversalBLE"
    assert items[7]["sceneName"] == "Sleep" and items[7]["sceneIndex"] == 0
    # Birds light is not in the account: created first, with its typed codes as learned keys
    (created,) = steps["create"]
    assert created["remoteID"] == BIRDS_ID and created["type"] == 8 and created["code"] == "no_data"
    assert [key["keyName"] for key in created["keyDetail"]] == ["4", "Night"]
    assert steps["remove"] == ["01-202601010101-11111111"]
    # once the account holds these entries, the app sees no difference
    assert sync.differences(items, TABLE, SCENES) == []
