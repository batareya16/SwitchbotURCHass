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
