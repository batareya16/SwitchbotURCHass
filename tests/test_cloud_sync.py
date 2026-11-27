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
                        "remoteIndex": 2, "roomName": "", "urcVersion": 48}
    assert items[4]["deviceID"] == "DA7116E01F92" and items[4]["deviceName"] == "Floor lamp"
    # Bridge tiles: no account device has their address, so they are listed as Matter devices
    assert items[3]["deviceType"] == items[4]["deviceType"] == "WoMatter"
    assert steps["as_matter"] == ["Remote 4 (slot 3)", "Floor lamp (slot 4)"]   # slot 3 has no name here
    real = sync.plan(TABLE, REMOTES, BOUND, known, SCENES, {"DA7116E01F92"})["items"]
    assert real[4]["deviceType"] == "WoStrip"                      # a real SwitchBot device keeps its type
    assert items[6]["thirdPartyDeviceID"] == "021793376454" and items[6]["thirdPartyType"] == "UniversalBLE"
    assert items[7]["sceneName"] == "Sleep" and items[7]["sceneIndex"] == 0
    # Birds light is not in the account: created first, with its typed codes as learned keys
    (created,) = steps["create"]
    assert created["remoteID"] == BIRDS_ID and created["type"] == 8 and created["code"] == "no_data"
    assert [key["keyName"] for key in created["keyDetail"]] == ["4", "Night"]
    assert steps["remove"] == ["01-202601010101-11111111"]
    # once the account holds these entries, the app sees no difference
    assert sync.differences(items, TABLE, SCENES) == []


def test_a_remote_installed_from_the_account_under_a_new_id_is_saved_as_a_copy_of_its_source():
    # The account's TV is not on the remote; the remote's TV (slot 0) has a Studio id
    table = [(0, 0x02, 1, bytes.fromhex("01141a0b13013a153a6331"))]
    tv_on_remote = sync.remote_id_from_bytes(table[0][3])
    account_tv = {"remoteID": "01-202611010101-12345678", "remoteName": "TV", "type": 2,
                  "remoteIndex": 0, "createFrom": "hub"}
    remotes = [{"name": "TV", "device_type": "IR_2", "device_id": table[0][3].hex(),
                "physical_layout": {"kind": "ir", "pages": [{"index": 1, "buttons": [
                    {"index": 0, "transport": "ir", "code_hex": "aabb", "title": "Night"}]}]}}]
    steps = sync.plan(table, remotes, [account_tv], {account_tv["remoteID"]}, [])
    (create,) = steps["create"]
    assert create["remoteID"] == tv_on_remote
    assert steps["remove"] == [account_tv["remoteID"]]
    source = sync.account_source(create, [account_tv, {**account_tv}], table)
    assert source is account_tv or source == account_tv
    # a second account remote of that name and type makes the source unclear: none is used
    other = {**account_tv, "remoteID": "01-202611010101-87654321"}
    assert sync.account_source(create, [account_tv, other], table) is None
    # nor one that is on the remote itself, nor one of another type
    assert sync.account_source(create, [{**account_tv, "remoteID": tv_on_remote}], table) is None
    assert sync.account_source(create, [{**account_tv, "type": 8}], table) is None
    downloaded = {**account_tv, "code": "QUJD", "keyMap": "1:0:4", "brandEn": "LG", "hxdIndex": "123",
                  "keyDetail": '[{"keyName": "Blue", "code": "AAA="}, {"keyName": "Night", "code": "BBB="}]'}
    copy = sync.with_source_keys(create, downloaded)
    assert copy["remoteID"] == tv_on_remote and copy["remoteIndex"] == 0 and copy["waitModify"] is False
    assert copy["code"] == "QUJD" and copy["keyMap"] == "1:0:4" and copy["brandEn"] == "LG"
    assert [key["keyName"] for key in copy["keyDetail"]] == ["Blue", "Night"]   # the source's Night wins
    assert "createFrom" not in copy
    words = sync.preview(steps, [account_tv], table, [account_tv])
    assert words == ["TV (slot 0): saved to the account as a copy of your account's TV, with all its buttons",
                     "TV: no longer listed under this Universal Remote (it stays in your account)"]


def test_check_also_reports_what_lights_the_apps_banner_and_warnings():
    payload = {
        "bindDevices": [
            {"deviceID": "DA7116E01F92", "deviceName": "Floor lamp", "deviceType": "WoStrip", "remoteIndex": 4,
             "urcVersion": 48},
            {"deviceID": "4D5400000000", "deviceName": "Text", "deviceType": "WoMatter", "remoteIndex": 2},
            {"thirdPartyDeviceID": "021793376454", "thirdPartyType": "UniversalBLE", "remoteIndex": 7},
            {"deviceID": "AABBCCDDEEFF", "deviceName": "Bulb", "deviceType": "WoBulb", "remoteIndex": 5,
             "urcVersion": 48},
            {"sceneID": "studio-scene-0", "sceneName": "QWERT", "sceneIndex": 0},
            {"sceneID": "S1", "sceneName": "Flow vibe", "sceneIndex": 1, "sceneIcon": "a", "sceneColor": 2},
        ],
        "devices": [{"deviceID": "AABBCCDDEEFF", "deviceName": "Bulb", "status": {}}],
        "scenes": [{"sceneID": "S1", "name": "Flow vibe", "icon": {"css": "a", "color": 2}}],
    }
    assert sync.app_warnings(payload) == [
        "Floor lamp: no SwitchBot device DA7116E01F92 in the account",
        "Scene QWERT: not a scene of your SwitchBot account",
    ]
    payload["devices"][0]["deviceName"] = "Bulb 2"
    payload["scenes"][0]["icon"]["color"] = 3
    found = sync.app_warnings(payload)
    assert "Bulb: its name or settings differ from the device in the account" in found
    assert "Scene Flow vibe: its name or look differ from the scene in the account" in found


def test_scenes_are_listed_with_scenes_of_the_account_made_or_brought_in_line():
    import asyncio
    table = []
    scenes = [{"index": 0, "name": "QWERT", "icon": 21, "color": 6},
              {"index": 1, "name": "Flow vibe", "icon": 10, "color": 0},
              {"index": 2, "name": "Movie", "icon": 18, "color": 5}]
    account = [{"sceneID": "S-flow", "name": "Flow vibe", "icon": {"css": "icon_32pt_scenarios_music", "color": "#FF2D55"}},
               {"sceneID": "S-old", "name": "Film", "icon": {"css": "icon_32pt_scenarios_film", "color": "#00B2FF"}}]
    bound = [{"sceneID": "studio-scene-0", "sceneName": "QWERT", "sceneIndex": 0},      # made up earlier
             {"sceneID": "S-old", "sceneName": "Film", "sceneIndex": 2}]                # renamed on the remote
    steps = sync.plan(table, [], bound, set(), scenes, set(), account)
    by_name = {item["sceneName"]: item for item in steps["items"]}
    assert by_name["QWERT"]["sceneID"] is None                          # made in the account by Sync
    assert by_name["QWERT"]["sceneIcon"] == "icon_32pt_scenarios_sleep" and by_name["QWERT"]["sceneColor"] == "#5856D6"
    assert by_name["Flow vibe"]["sceneID"] == "S-flow"                  # an account scene of that name
    assert by_name["Movie"]["sceneID"] == "S-old"                       # the one listed at its number
    assert [scene["name"] for scene in steps["scene_create"]] == ["QWERT"]
    assert [(scene["sceneID"], scene["was"]) for scene in steps["scene_update"]] == [("S-old", "Film")]
    assert steps["remove"] == ["studio-scene-0"]
    words = sync.preview(steps, [], table, bound)
    assert "Scene QWERT: made in your SwitchBot account as a tap-to-run scene with nothing to run, so the app knows it" in words
    assert "Scene Movie: its name, icon and colour in your account set as on the remote (was Film)" in words
    # once made, the app finds every scene: no warning on the scenes
    for scene in steps["scene_create"]:
        steps["items"][scene["position"]]["sceneID"] = "S-new"
    made = account + [{"sceneID": "S-new", "name": "QWERT", "icon": {"css": "icon_32pt_scenarios_sleep", "color": "#5856D6"}}]
    made[0]["icon"]["css"] = "icon_32pt_scenarios_music"
    fixed = [dict(item) for item in made]
    fixed[1] = {"sceneID": "S-old", "name": "Movie", "icon": {"css": "icon_32pt_scenarios_film", "color": "#00B2FF"}}
    assert sync.app_warnings({"bindDevices": steps["items"], "devices": [], "scenes": fixed}) == []
    assert sync.differences(steps["items"], table, scenes) == []


cloud = load(INTEGRATION / "cloud.py")


def test_a_scene_is_made_empty_or_with_a_one_second_pause_when_empty_is_refused():
    import asyncio
    sent = []

    async def post(path, body, renew=True):
        sent.append((path, body))
        if not body.get("actions"):
            raise cloud.CloudError("SwitchBot cloud returned status 190: actions empty")
        return {"sceneID": "S-1"}

    client = cloud.SwitchBotCloudClient(None, {"group_id": "G"}, None)
    client.post = post
    assert asyncio.run(client.create_scene(name="QWERT", icon="icon_32pt_scenarios_sleep", color="#5856D6")) == "S-1"
    assert [path for path, _ in sent] == ["/scene/v1/scene/create"] * 2
    first, second = sent[0][1], sent[1][1]
    assert first == {"icon": {"css": "icon_32pt_scenarios_sleep", "color": "#5856D6"}, "groupID": "G",
                     "name": "QWERT", "enable": True, "notifyEnable": False, "sceneType": "scene", "actions": []}
    assert second["actions"][0]["optID"] == "delay_act_delay" and second["actions"][0]["data"] == {"delaySecond": 1}


def test_every_listed_remote_carries_the_firmware_version_the_app_checks():
    known = {TV_ID, BAR_ID, "01-202601010101-11111111"}
    steps = sync.plan(TABLE, REMOTES, BOUND, known, SCENES)
    assert all(item["urcVersion"] == 48 for item in steps["items"] if "sceneIndex" not in item)
    assert steps["create"][0]["urcVersion"] == 48
    # an IR remote listed without it is what the app marks "key error, delete and add it again"
    found = sync.app_warnings({"bindDevices": [{"remoteID": TV_ID, "remoteName": "TV", "remoteIndex": 0},
                                               {"thirdPartyDeviceID": "02", "thirdPartyType": "UniversalBLE"}]})
    assert found == ['TV: listed without the remote\'s firmware version, so the app shows "key error, delete and add it again"']


def test_the_version_read_from_the_remote_is_what_the_account_is_told():
    steps = sync.plan(TABLE, REMOTES, BOUND, {TV_ID, BAR_ID}, SCENES, urc_version=50)
    assert {item["urcVersion"] for item in steps["items"] if "sceneIndex" not in item} == {50}
    client = cloud.SwitchBotCloudClient(None, {"urc_version": 50}, None)
    assert client.urc_version == 50
    assert cloud.SwitchBotCloudClient(None, {}, None).urc_version == 48
