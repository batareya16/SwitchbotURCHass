"""Re-read my remotes also lists the account's IR remotes made on a Hub.

getBindableDevices answers with `bindDevices` (remotes bound to this Universal Remote), `remotes`
(the account's IR remotes, the list the app's "add a remote" page offers) and `devices` (SwitchBot
devices). Only the first used to be read, so a remote made on a Hub never showed up.
"""
from conftest import INTEGRATION, load

inventory = load(INTEGRATION / "inventory.py")


PAYLOAD = {
    "bindDevices": [{"remoteID": "01-202611190101-11111111", "remoteIndex": 0, "remoteName": "TV", "type": 2}],
    "remotes": [
        {"remoteID": "01-202611190101-11111111", "remoteName": "TV", "type": 2},
        {"remoteID": "01-202611190101-22222222", "remoteName": "Hub fan", "type": 6},
        {"remoteID": "01-202611190101-33333333", "remoteName": "Gone", "type": 2, "isDeleted": True},
        {"remoteName": "no id"},
    ],
    "devices": [{"deviceID": "AABBCCDDEEFF", "deviceType": "WoStrip"}],
}


def test_hub_remotes_are_offered_and_marked_unbound():
    items = inventory.cloud_items(PAYLOAD)
    assert [item["remoteID"] for item in items] == ["01-202611190101-11111111", "01-202611190101-22222222"]
    assert not items[0].get(inventory.UNBOUND_MARK)
    assert items[1][inventory.UNBOUND_MARK] is True
    assert not any(item.get("deviceID") for item in items)        # SwitchBot devices are not IR


def test_an_unbound_account_remote_is_not_listed_as_one_of_this_remotes():
    merged = inventory.merge_inventory([], [], inventory.cloud_items(PAYLOAD))
    assert [item["name"] for item in merged] == ["TV"]


cloud_ir = load(INTEGRATION / "cloud_ir.py")


def test_every_key_of_an_account_remote_is_offered_as_a_code():
    import base64
    bank = bytes(range(40))
    learned = base64.b64encode(bytes.fromhex("303030fdff35aa00")).decode()
    item = {"type": 11, "code": base64.b64encode(bank).decode(), "keyMap": "23:0:10;19:10:10;21:20:10",
            "keyDetail": [{"keyName": "Night", "keyType": "text", "code": learned}]}
    codes = cloud_ir.account_ir_codes(item, "Soundbar")
    by_key = {code["key"]: code for code in codes}
    assert by_key["23"]["code_hex"] == bank[0:10].hex() and by_key["23"]["function"] == 26   # Forward
    assert by_key["21"]["function"] == 21                                                       # Play
    assert by_key["19"]["function"] == 25                                                       # Rewind
    assert by_key["Night"] == {"remote": "Soundbar", "key": "Night", "function": None,
                               "code_hex": "303030fdff35aa00"}
    # an air conditioner has no per-key code; a remote of only learned keys still gives them
    assert cloud_ir.account_ir_codes({**item, "type": 1, "keyDetail": []}, "AC") == []
    diy = cloud_ir.account_ir_codes({"type": 9, "code": "no_data", "keyMap": "",
                                     "keyDetail": item["keyDetail"]}, "Hub lamp")
    assert [code["key"] for code in diy] == ["Night"]
