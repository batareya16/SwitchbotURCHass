"""Sign-in finds the account's own partition (issue #2: a North American account got EU and no homes)."""
import asyncio

from conftest import INTEGRATION, load

cloud = load(INTEGRATION / "cloud.py")


def _client(account_answers, homes_by_url):
    settings = {"region": "EU", "api_base_url": "", "token_device_id": "t", "access_token": "a"}
    saved = []

    async def save(access, refresh):
        saved.append((access, refresh))

    client = cloud.SwitchBotCloudClient(None, settings, save)
    calls = []

    async def account(path, body, *, authenticated=False):
        calls.append(path)
        return account_answers[path]

    async def post(path, body, renew=True):
        answer = homes_by_url.get(client.base_url, {"groups": []}) if "group" in path else {}
        if callable(answer):
            return answer(settings)
        return answer

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


def test_a_partition_that_refuses_the_fresh_token_is_skipped_without_a_token_refresh():
    def refuse(settings):
        raise cloud.CloudError("SwitchBot cloud refused the sign-in token (status 2005: )")
    client, settings, calls = _client({}, {
        "https://wonderlabs.eu.api.switchbot.net": refuse,
        US: {"groups": [{"groupID": "H1", "groupName": "Home"}]}})
    settings["bot_region"] = "us"
    homes = asyncio.run(client.get_homes())
    assert [home["groupID"] for home in homes] == ["H1"] and client.base_url == US
    assert calls == []                                  # no token refresh, no account request


def test_a_server_that_wants_only_the_authorization_header_is_tried_that_way_and_remembered():
    def plain_only(settings):
        if not settings.get("plain_headers"):
            raise cloud.CloudError("refused")
        return {"groups": [{"groupID": "H2", "groupName": "Home"}]}
    client, settings, _calls = _client({}, {US: plain_only,
                                            "https://wonderlabs.eu.api.switchbot.net": plain_only})
    homes = asyncio.run(client.get_homes())
    assert [home["groupID"] for home in homes] == ["H2"]
    assert settings["plain_headers"] is True
    assert client._headers() == {"Content-Type": "application/json", "authorization": "a"}


def test_when_every_server_refuses_the_reasons_are_reported():
    def refuse(settings):
        raise cloud.CloudError("refused")
    client, settings, _calls = _client({}, {US: refuse, "https://wonderlabs.eu.api.switchbot.net": refuse})
    try:
        asyncio.run(client.get_homes())
    except cloud.CloudError as err:
        assert "No SwitchBot server returned the homes" in str(err) and str(err).count("refused") == 4
    else:
        raise AssertionError("expected a CloudError")
    assert client.base_url == "https://wonderlabs.eu.api.switchbot.net" and not settings["plain_headers"]


def test_any_account_region_has_a_host_as_pyswitchbot_builds_it():
    assert cloud.region_url("ap") == "https://wonderlabs.ap.api.switchbot.net"
    assert cloud.region_url("us") == US
    assert cloud.region_url("") is None and cloud.region_url("a/b") is None


def test_a_wrong_refresh_token_answer_tries_the_cognito_refresh():
    client, settings, calls = _client({
        "/account/api/v1/user/token/refresh": {"statusCode": 2005, "message": "refreshToken is wrong"},
        "/account/api/v1/user/cognito/token/refresh": {"statusCode": 100, "body": {"access_token": "b"}},
    }, {})
    settings.update(refresh_token="r", username="user@example.com")
    asyncio.run(client.refresh())
    assert calls[-1] == "/account/api/v1/user/cognito/token/refresh" and settings["access_token"] == "b"


def test_the_firmware_check_asks_as_the_app_and_reads_the_remotes_package():
    sent = []

    async def post(path, body, renew=True):
        sent.append((path, body))
        if path.endswith("/query"):
            return [{"deviceID": "B0E9FE531145", "packInfo": [
                {"packType": "WoRWS_ble_freq", "version": "50"}, {"packType": "WoRWS_wifi", "version": "90"}]}]
        raise cloud.CloudError("SwitchBot cloud returned status 190: none")

    client = cloud.SwitchBotCloudClient(None, {"urc_device_id": "b0:e9:fe:53:11:45"}, None)
    client.post = post
    found = asyncio.run(client.firmware_versions(48))
    assert found["current"] == 48 and found["latest"] == 50 and found["required"] is None
    assert [path for path, _ in sent] == ["/firmware/v1/version/query", "/firmware/v1/version/queryForcedUpgrade"]
    assert sent[0][1] == {"deviceList": [{"deviceID": "B0E9FE531145", "deviceType": "WoRWS", "bleVersion": 48}],
                          "langCode": "en"}
    assert cloud.firmware_package_version({"targetBleVersion": 49}) == 49
    assert cloud.firmware_package_version([]) is None


def test_scenes_are_listed_and_deleted_the_way_the_app_does():
    sent = []

    async def post(path, body, renew=True):
        sent.append((path, body))
        return {"scenes": [{"sceneID": "S1", "name": "QWERT", "actions": []}]} if path.endswith("getList") else {}

    client = cloud.SwitchBotCloudClient(None, {"group_id": "G"}, None)
    client.post = post
    assert asyncio.run(client.list_scenes()) == [{"sceneID": "S1", "name": "QWERT", "actions": []}]
    asyncio.run(client.delete_scenes([{"sceneID": "S1"}]))
    assert sent == [("/scene/v1/scene/getList", {"groupID": "G", "sceneType": "scene"}),
                    ("/scene/v1/scene/delete", {"scenes": [{"id": "S1", "isOldData": False}],
                                                "groupID": "G", "sceneType": "scene"})]
