"""Physical settings use sparse writes and are confirmed by the remote's status."""
import asyncio
import ast
import logging
import sys
import types

import pytest
import voluptuous as vol

from conftest import INTEGRATION, load

settings = load(INTEGRATION / "device_settings.py")
STATUS = bytes.fromhex("3c3001000132320f00010001002d2d01")


def test_status_settings_offsets():
    values = settings.parse_settings(STATUS)
    assert values == {
        "key_sounds": True, "auto_brightness": False, "lift_to_wake": True,
        "screen_brightness": 50, "key_brightness": 50, "screen_timeout": 15,
        "temperature_unit": 0, "language": 1, "touch_wheel": False, "japan_model": False,
    }
    japan = bytearray(STATUS)
    japan[8] = 0x80
    assert settings.parse_settings(bytes(japan))["japan_model"]


@pytest.mark.parametrize("response", [b"", b"\x01", STATUS[:-1], b"\xff" + STATUS[1:]])
def test_invalid_status_never_creates_default_settings(response):
    with pytest.raises(ValueError):
        settings.parse_settings(response)


def test_touch_wheel_patch_does_not_write_other_settings_or_clear_data():
    assert settings.build_settings({"touch_wheel": True}) == bytes.fromhex("03ffffffffffffffffff01ff")
    assert settings.build_settings({"screen_brightness": 20, "language": 2}) == bytes.fromhex(
        "03ffffff14ffffff02ffffff"
    )


@pytest.mark.parametrize("changes", [
    {"touch_wheel": 1}, {"screen_brightness": 101}, {"key_brightness": -1},
    {"screen_timeout": 255}, {"screen_timeout": 2}, {"language": 3},
    {"temperature_unit": 2}, {"clear_data": False},
])
def test_invalid_writes_are_rejected(changes):
    with pytest.raises(ValueError):
        settings.build_settings(changes)


class Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.commands = []

    async def send_command(self, command):
        self.commands.append(command)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def test_write_reads_fresh_state_then_verifies():
    updated = bytearray(STATUS)
    updated[12] = 1
    client = Client([STATUS, b"\x01", bytes(updated)])
    actual = asyncio.run(settings.apply_settings(client, {"touch_wheel": True}))
    assert actual["touch_wheel"]
    assert client.commands == [b"\x02", settings.build_settings({"touch_wheel": True}), b"\x02"]


def test_unchanged_settings_do_not_trigger_a_write():
    client = Client([STATUS])
    asyncio.run(settings.apply_settings(client, {"touch_wheel": False}))
    assert client.commands == [b"\x02"]


def test_rejected_write_is_not_repeated_or_reported_as_saved():
    client = Client([STATUS, b"\x02"])
    with pytest.raises(RuntimeError, match="rejected"):
        asyncio.run(settings.apply_settings(client, {"touch_wheel": True}))
    assert len(client.commands) == 2


@pytest.mark.parametrize("readback", [STATUS, TimeoutError()])
def test_unconfirmed_write_is_not_reported_as_saved(readback):
    client = Client([STATUS, b"\x01", readback])
    with pytest.raises(settings.SettingsVerificationError):
        asyncio.run(settings.apply_settings(client, {"touch_wheel": True}))
    assert len(client.commands) == 3


def test_manual_brightness_requires_disabling_auto_brightness():
    automatic = bytearray(STATUS)
    automatic[3] = 1
    client = Client([bytes(automatic)])
    with pytest.raises(ValueError, match="automatic brightness"):
        asyncio.run(settings.apply_settings(client, {"screen_brightness": 20}))
    assert client.commands == [b"\x02"]
    updated = bytearray(STATUS)
    updated[5] = 20
    client = Client([bytes(automatic), b"\x01", bytes(updated)])
    result = asyncio.run(settings.apply_settings(client, {"auto_brightness": False, "screen_brightness": 20}))
    assert result["screen_brightness"] == 20


def test_japanese_temperature_unit_cannot_be_changed():
    japan = bytearray(STATUS)
    japan[8] = 0x80
    client = Client([bytes(japan)])
    with pytest.raises(ValueError, match="Japanese"):
        asyncio.run(settings.apply_settings(client, {"temperature_unit": 1}))
    assert client.commands == [b"\x02"]


@pytest.fixture
def flow(monkeypatch):
    """Exercise the actual options step without loading unrelated HA services."""
    source = ast.parse((INTEGRATION / "config_flow.py").read_text())
    options = next(node for node in source.body if isinstance(node, ast.ClassDef) and node.name == "UrcOptionsFlow")
    method = next(node for node in options.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_step_device_settings")
    namespace = {
        "__package__": "switchbot_urc", "device_settings": settings, "vol": vol,
        "cv": types.SimpleNamespace(boolean=bool), "Any": object, "ConfigFlowResult": dict,
        "_LOGGER": logging.getLogger(__name__), "_searchable_select": lambda choices: vol.In(choices),
        "selector": types.SimpleNamespace(
            NumberSelector=lambda config: vol.All(vol.Coerce(float), vol.Range(min=config["min"], max=config["max"])),
            NumberSelectorConfig=lambda **kwargs: kwargs,
        ),
    }
    exec(compile(ast.Module(body=[method], type_ignores=[]), "config_flow.py", "exec"), namespace)
    monkeypatch.setitem(sys.modules, "switchbot_urc.studio_remotes", types.SimpleNamespace(
        remote_management_lock=lambda hass: hass.lock,
    ))
    instance = types.SimpleNamespace(
        hass=types.SimpleNamespace(lock=asyncio.Lock()), _device_settings=None,
        _entry=types.SimpleNamespace(options={"remotes": [{"name": "TV"}]}),
        async_show_form=lambda **kwargs: kwargs,
        async_create_entry=lambda **kwargs: {"created": True, **kwargs},
    )
    instance.step = types.MethodType(namespace[method.name], instance)
    return instance


def test_options_form_reads_current_settings_and_saves_only_changes(flow):
    updated = bytearray(STATUS)
    updated[12] = 1
    client = Client([STATUS, STATUS, b"\x01", bytes(updated)])
    flow._client = lambda: client

    async def run():
        form = await flow.step()
        submitted = form["data_schema"]({})
        assert submitted["touch_wheel"] is False
        assert submitted["language"] == "1"
        submitted["touch_wheel"] = True
        result = await flow.step(submitted)
        assert result["created"]
        assert result["data"] == flow._entry.options

    asyncio.run(run())
    assert client.commands == [b"\x02", b"\x02", settings.build_settings({"touch_wheel": True}), b"\x02"]


def test_options_read_failure_offers_retry_without_fabricated_values(flow):
    client = Client([TimeoutError(), STATUS])
    flow._client = lambda: client

    async def run():
        form = await flow.step()
        assert form["errors"]["base"] == "device_settings_failed"
        assert form["data_schema"]({}) == {"retry": True}
        form = await flow.step({"retry": True})
        assert not form["errors"]
        assert form["data_schema"]({})["screen_brightness"] == 50

    asyncio.run(run())
    assert client.commands == [b"\x02", b"\x02"]


def test_options_write_failure_keeps_the_form_open(flow):
    client = Client([STATUS, STATUS, b"\x02"])
    flow._client = lambda: client

    async def run():
        form = await flow.step()
        submitted = form["data_schema"]({})
        submitted["touch_wheel"] = True
        result = await flow.step(submitted)
        assert result["errors"]["base"] == "device_settings_failed"
        assert result["data_schema"]({})["touch_wheel"] is True

    asyncio.run(run())
