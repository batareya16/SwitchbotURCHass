"""Small client for the private WoRWS cloud API used by the official app.

The integration remains local for BLE operations.  Cloud access is optional and is only
used to discover the account's IR remotes and keep their names/list metadata in sync.
"""
from __future__ import annotations

import base64
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any


DEFAULT_CLIENT_ID = "5nnwmhmsa9xxskm14hd85lm9bm"
DEFAULT_CLIENT_SECRET = "vzxjw7rvmduka4rlysdcv0bfke70icql33ol1pvr"
DEFAULT_COGNITO_CLIENT_ID = "66r90hdllaj4nnlne4qna0muls"
ACCOUNT_BASE_URL = "https://account.api.switchbot.net"
REGION_URLS = {
    "EU": "https://wonderlabs.eu.api.switchbot.net",
    "US": "https://wonderlabs.us.api.switchbot.net",
}

_LOGGER = logging.getLogger(__name__)


def parse_communication_credentials(payload: Any) -> tuple[bytes, int] | None:
    """Extract the rotating 16-byte BLE key and one-byte key ID from cloud JSON."""
    if not isinstance(payload, dict):
        return None
    record = payload.get("communicationKey", payload)
    if isinstance(record, dict) and isinstance(record.get("communicationKey"), dict):
        record = record["communicationKey"]
    if not isinstance(record, dict):
        return None
    try:
        key = bytes.fromhex(str(record.get("key", "")).replace(" ", ""))
        raw_key_id = record.get("keyId", record.get("keyID", ""))
        key_id = raw_key_id if isinstance(raw_key_id, int) else int(str(raw_key_id).strip(), 16)
    except ValueError:
        return None
    if len(key) != 16 or not 0 <= key_id <= 0xFF:
        return None
    return key, key_id


class CloudError(RuntimeError):
    """A WoRWS cloud request failed."""


def jwt_expired(token: str, *, leeway: int = 60) -> bool:
    """Return true when a JWT is expired/about to expire; opaque tokens return false."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        expiry = int(json.loads(base64.urlsafe_b64decode(payload))["exp"])
    except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return False
    return expiry <= int(time.time()) + leeway


def jwt_claims(token: str) -> dict[str, Any]:
    """Decode non-secret JWT claims without validating the already TLS-protected token."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        value = json.loads(base64.urlsafe_b64decode(payload))
        return value if isinstance(value, dict) else {}
    except (ValueError, IndexError, TypeError, json.JSONDecodeError):
        return {}


def unwrap_response(value: Any) -> Any:
    """Unwrap either SwitchBot response envelope used by the production API."""
    if not isinstance(value, dict):
        return value
    code_key = "statusCode" if "statusCode" in value else "resultCode"
    if code_key not in value:
        return value
    code = value.get(code_key)
    if code not in (0, 100, 200, "0", "100", "200"):
        raise CloudError(f"SwitchBot cloud returned status {code}: {value.get('message', '')}")
    return value.get("body", value.get("data", value))


class SwitchBotCloudClient:
    """Authenticated client with transparent access-token refresh."""

    def __init__(
        self,
        session: Any,
        settings: dict[str, Any],
        save_tokens: Callable[[str, str], Awaitable[None]],
    ) -> None:
        self._session = session
        self.settings = settings
        self._save_tokens = save_tokens

    @property
    def base_url(self) -> str:
        custom = str(self.settings.get("api_base_url", "")).strip().rstrip("/")
        return custom or REGION_URLS.get(self.settings.get("region", "EU"), REGION_URLS["EU"])

    def _headers(self, *, authenticated: bool = True) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "appVersion": "10.5",
            "versionFlag": "10.5",
            "requestID": str(uuid.uuid4()),
            "terminalID": str(self.settings.get("token_device_id", "")),
            "uuid": str(self.settings.get("token_device_id", "")),
        }
        if authenticated:
            headers["authorization"] = str(self.settings.get("access_token", ""))
        return headers

    async def login(self, username: str, password: str) -> dict[str, Any]:
        """Sign in with the same password grant used by the Android app.

        The password is sent only to SwitchBot's account endpoint and is never placed in
        ``settings``.  Only the returned renewable tokens are persisted by the caller.
        """
        payload = await self._account_request(
            "/account/api/v1/user/login",
            {
                "username": username,
                "password": password,
                "verifyCode": "",
                "clientId": self.settings.get("client_id", DEFAULT_CLIENT_ID),
                "grantType": "password",
                "deviceInfo": {
                    "deviceId": self.settings.get("token_device_id", ""),
                    "deviceName": self.settings.get("device_name", "Home Assistant"),
                    "model": self.settings.get("device_model", "Home Assistant"),
                },
            },
        )
        result = unwrap_response(payload)
        if not isinstance(result, dict):
            raise CloudError("Login returned an invalid response")
        access = result.get("access_token") or result.get("accessToken")
        refresh = result.get("refresh_token") or result.get("refreshToken")
        if not access or not refresh:
            raise CloudError("Login response did not contain renewable tokens")

        self.settings["username"] = username
        self.settings["access_token"] = str(access)
        self.settings["refresh_token"] = str(refresh)
        bot_region = str(result.get("botRegion", "")).strip()
        self.settings["bot_region"] = bot_region
        region = bot_region.upper()
        if region in REGION_URLS:
            self.settings["region"] = region
        claims = jwt_claims(str(access))
        user_id = (
            result.get("userId")
            or result.get("user_id")
            or claims.get("userId")
            or claims.get("username")
            or claims.get("sub")
        )
        if user_id:
            self.settings["user_id"] = str(user_id)
        await self._save_tokens(str(access), str(refresh))
        if bot_region:
            await self.resolve_endpoints(bot_region)
        return result

    async def resolve_endpoints(self, bot_region: str) -> list[dict[str, Any]]:
        """Resolve the account partition exactly as the app does after login."""
        payload = await self._account_request(
            "/admin/admin/api/v1/botregion/endpoint",
            {"botRegion": bot_region},
            authenticated=True,
        )
        result = unwrap_response(payload)
        endpoints = result if isinstance(result, list) else []
        for item in endpoints:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).lower()
            host = str(item.get("host", "")).strip().rstrip("/")
            if "wonderlabs" in name and host:
                self.settings["api_base_url"] = host
                _LOGGER.info(
                    "SwitchBot cloud partition resolved: botRegion=%s wonderlabs=%s",
                    bot_region,
                    host,
                )
                break
        if not self.settings.get("api_base_url"):
            raise CloudError("SwitchBot endpoint discovery did not return Wonderlabs")
        return [item for item in endpoints if isinstance(item, dict)]

    async def refresh(self) -> None:
        """Refresh credentials using the same primary endpoint as app 10.5."""
        refresh_token = str(self.settings.get("refresh_token", ""))
        if not refresh_token:
            raise CloudError("No refresh token is configured")
        body = {
            "refreshToken": refresh_token,
            "clientSecret": self.settings.get("client_secret", DEFAULT_CLIENT_SECRET),
            "deviceId": self.settings.get("token_device_id", ""),
            "clientId": self.settings.get("client_id", DEFAULT_CLIENT_ID),
            "userId": self.settings.get("user_id", ""),
        }
        payload = await self._account_request("/account/api/v1/user/token/refresh", body)
        if isinstance(payload, dict) and payload.get("statusCode") in (2006, "2006"):
            username = str(self.settings.get("username", ""))
            if not username:
                raise CloudError(
                    "This account uses Cognito refresh; enter the account email/username"
                )
            payload = await self._account_request(
                "/account/api/v1/user/cognito/token/refresh",
                {
                    "refreshToken": refresh_token,
                    "username": username,
                    "clientSecret": self.settings.get("client_secret", DEFAULT_CLIENT_SECRET),
                    "cognitoClientId": self.settings.get(
                        "cognito_client_id", DEFAULT_COGNITO_CLIENT_ID
                    ),
                    "clientId": self.settings.get("client_id", DEFAULT_CLIENT_ID),
                    "userId": self.settings.get("user_id", ""),
                    "deviceInfo": {
                        "deviceId": self.settings.get("token_device_id", ""),
                        "deviceName": self.settings.get("device_name", "Home Assistant"),
                        "model": self.settings.get("device_model", "Home Assistant"),
                    },
                },
            )
        result = unwrap_response(payload)
        if not isinstance(result, dict):
            raise CloudError("Token refresh returned an invalid response")
        access = result.get("access_token") or result.get("accessToken")
        refreshed = result.get("refresh_token") or result.get("refreshToken") or refresh_token
        if not access:
            raise CloudError("Token refresh response did not contain an access token")
        self.settings["access_token"] = str(access)
        self.settings["refresh_token"] = str(refreshed)
        await self._save_tokens(str(access), str(refreshed))

    async def _account_request(
        self, path: str, body: dict[str, Any], *, authenticated: bool = False
    ) -> Any:
        async with self._session.post(
            f"{ACCOUNT_BASE_URL}{path}",
            json=body,
            headers=self._headers(authenticated=authenticated),
            timeout=20,
        ) as response:
            payload = await response.json(content_type=None)
            if response.status >= 400:
                raise CloudError(f"SwitchBot account request failed with HTTP {response.status}")
            return payload

    async def post(self, path: str, body: dict[str, Any] | None) -> Any:
        """POST JSON, refreshing once before/after an expired authorization response."""
        if not self.settings.get("access_token") or jwt_expired(str(self.settings["access_token"])):
            await self.refresh()
        for attempt in range(2):
            request_args: dict[str, Any] = {
                "headers": self._headers(),
                "timeout": 25,
            }
            if body is not None:
                request_args["json"] = body
            async with self._session.post(
                f"{self.base_url}{path}", **request_args
            ) as response:
                payload = await response.json(content_type=None)
                auth_failed = response.status in (401, 403)
                if isinstance(payload, dict):
                    auth_failed = auth_failed or payload.get("statusCode") in (
                        190, 401, 2001, 2005, 2050, "190", "401", "2001", "2005", "2050"
                    )
                if not auth_failed:
                    if response.status >= 400:
                        raise CloudError(f"SwitchBot cloud returned HTTP {response.status}")
                    return unwrap_response(payload)
            if attempt == 0:
                await self.refresh()
        raise CloudError("SwitchBot cloud authorization failed after token refresh")

    def _device_body(self) -> dict[str, Any]:
        return {
            "groupID": self.settings["group_id"],
            "deviceID": self.settings["urc_device_id"],
        }

    async def get_bindable_devices(self) -> dict[str, Any]:
        value = await self.post(
            "/wonder/deviceInfo/v1/WoRWS/getBindableDevices", self._device_body()
        )
        return value if isinstance(value, dict) else {"bindDevices": value or []}

    async def get_homes(self) -> list[dict[str, Any]]:
        """Return the account's homes using the app's v3 home-list endpoint."""
        response_shapes: list[str] = []
        for path in ("/homepage/v1/group/getall", "/homepage/v1/group/getinfo"):
            value = await self.post(path, None)
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    value = {}
            if isinstance(value, list):
                groups = value
                response_shapes.append(f"{path}:list_len={len(value)}")
            elif isinstance(value, dict):
                groups = value.get("groups") or value.get("groupsInfo") or []
                response_shapes.append(f"{path}:dict_keys={sorted(value.keys())}")
            else:
                groups = []
                response_shapes.append(f"{path}:type={type(value).__name__}")
            homes: list[dict[str, Any]] = []
            for item in groups:
                if not isinstance(item, dict):
                    continue
                group_id = item.get("groupID") or item.get("groupId")
                if group_id:
                    homes.append(item | {"groupID": str(group_id)})
            if homes:
                _LOGGER.info(
                    "SwitchBot cloud returned %d home(s) from %s", len(homes), path
                )
                return homes
        _LOGGER.warning(
            "SwitchBot cloud returned no homes; endpoint=%s response_shapes=%s",
            self.base_url,
            response_shapes,
        )
        return []

    async def get_button_data(self, remote_indices: list[int]) -> Any:
        body = self._device_body() | {
            "remoteList": remote_indices,
            "type": "all",
        }
        return await self.post("/wonder/deviceInfo/v1/WoRWS/getButtonData", body)

    async def get_communication_key(self) -> Any:
        """Fetch the current rotating BLE communication key used by the WoRWS."""
        return await self.post(
            "/wonder/keys/v1/communicate",
            {
                "groupID": self.settings["group_id"],
                "keyType": "user",
                "device_mac": self.settings["urc_device_id"],
            },
        )

    async def get_ir_remotes(
        self, remote_ids: list[str], remote_type: str = "hub"
    ) -> Any:
        """Download complete saved IR records, including code and key maps."""
        body = self._device_body() | {
            "remoteType": remote_type,
            "type": "list",
            "remoteList": remote_ids,
        }
        return await self.post("/wonder/deviceInfo/v1/WoRWS/queryIrRemote", body)

    async def get_ir_remote(self, remote_id: str, remote_type: str = "hub") -> Any:
        """Compatibility wrapper for one saved IR record."""
        return await self.get_ir_remotes([remote_id], remote_type)

    async def get_ir_model(self, hxd_index: str, *, db_version: int = 30) -> Any:
        """Download a code bank for one row from the bundled app catalog."""
        return await self.post(
            "/wonder/remote/v3/querymodel",
            {
                "remoteIndex": [str(hxd_index)],
                "deviceVersion": 38,
                "appVersion": "6.16",
                "deviceType": "WoHub2",
                "dbVersion": db_version,
            },
        )

    async def create_ir(self, item: dict[str, Any]) -> Any:
        """Save a newly installed catalog IR remote to the SwitchBot account."""
        return await self.post(
            "/wonder/deviceInfo/v1/WoRWS/createIrRemote",
            {"deviceID": self.settings["urc_device_id"], "items": [item]},
        )

    async def bind_ir(
        self, *, remote_id: str, remote_index: int, name: str, remote_type: int
    ) -> Any:
        """Bind a newly created IR record to its automatically selected WoRWS slot."""
        return await self.post(
            "/wonder/deviceInfo/v1/WoRWS/updateBindDevices",
            self._device_body()
            | {
                "items": [
                    {
                        "createFrom": "device",
                        "remoteID": remote_id,
                        "remoteIndex": remote_index,
                        "remoteName": name,
                        "type": remote_type,
                        "waitModify": True,
                    }
                ]
            },
        )

    async def rename_ir(self, remote_id: str, name: str, wait_modify: bool) -> Any:
        body = self._device_body() | {
            "items": [{"remoteID": remote_id, "waitModify": wait_modify, "remoteName": name}]
        }
        return await self.post("/wonder/deviceInfo/v1/WoRWS/updateIrRemote", body)

    async def delete_ids(self, ids: list[str]) -> Any:
        return await self.post(
            "/wonder/deviceInfo/v1/WoRWS/deleteBindDevices",
            self._device_body() | {"items": ids},
        )
