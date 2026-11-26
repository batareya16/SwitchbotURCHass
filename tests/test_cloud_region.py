"""Sign-in finds the account's own partition (issue #2: a North American account got EU and no homes)."""
import asyncio

from conftest import INTEGRATION, load

cloud = load(INTEGRATION / "cloud.py")


def _client(account_answers, homes_by_url):
    settings = {"region": "EU", "api_base_url": "", "token_device_id": "t"}
    saved = []

    async def save(access, refresh):
        saved.append((access, refresh))

    client = cloud.SwitchBotCloudClient(None, settings, save)
    calls = []

    async def account(path, body, *, authenticated=False):
        calls.append(path)
        return account_answers[path]

    async def post(path, body):
        return homes_by_url.get(client.base_url, {"groups": []}) if "group" in path else {}

    client._account_request = account
    client.post = post
    return client, settings, calls


LOGIN = {"statusCode": 100, "body": {"access_token": "a", "refresh_token": "r"}}
US = "https://wonderlabs.us.api.switchbot.net"


def test_a_login_without_a_region_asks_the_account_service_and_uses_its_partition():
    client, settings, calls = _client({
        "/account/api/v1/user/login": LOGIN,
        "/account/api/v1/user/userinfo": {"statusCode": 100, "body": {"botRegion": "us"}},
        "/admin/admin/api/v1/botregion/endpoint": {"statusCode": 100, "body": [
            {"name": "wonderlabs", "host": US}]},
    }, {})
    asyncio.run(client.login("user@example.com", "secret"))
    assert calls == ["/account/api/v1/user/login", "/account/api/v1/user/userinfo",
                     "/admin/admin/api/v1/botregion/endpoint"]
    assert settings["bot_region"] == "us" and settings["region"] == "US"
    assert client.base_url == US


def test_an_empty_region_is_the_us_partition():
    client, settings, _calls = _client({
        "/account/api/v1/user/login": LOGIN,
        "/account/api/v1/user/userinfo": {"statusCode": 100, "body": {"botRegion": ""}},
        "/admin/admin/api/v1/botregion/endpoint": {"statusCode": 100, "body": []},
    }, {})
    asyncio.run(client.login("user@example.com", "secret"))     # discovery empty: falls back
    assert settings["region"] == "US" and client.base_url == US


def test_homes_are_looked_for_in_the_other_partition_before_giving_up():
    client, settings, _calls = _client({}, {US: {"groups": [{"groupID": "H1", "groupName": "Home"}]}})
    homes = asyncio.run(client.get_homes())
    assert [home["groupID"] for home in homes] == ["H1"]
    assert settings["region"] == "US" and client.base_url == US
    # no homes anywhere: the partition it started from is kept
    client, settings, _calls = _client({}, {})
    assert asyncio.run(client.get_homes()) == []
    assert client.base_url == "https://wonderlabs.eu.api.switchbot.net"
