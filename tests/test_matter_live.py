"""Live captions: templates on the text remote, and the rule that spares the remote's flash."""
import asyncio
import importlib
import sys
import types

import pytest

from conftest import INTEGRATION, load
from test_studio_matter import FakeRemote, NATIVE_ROW, make, run, studio  # noqa: F401  (studio is a fixture)

matter = load(INTEGRATION / "matter_text.py")


# -- the pure rules -------------------------------------------------------------------------------

def test_templates_are_recognised_and_intervals_are_kept_in_range():
    assert matter.is_template("Battery {{ states('sensor.x') }}%")
    assert matter.is_template("{% if a %}b{% endif %}")
    assert not matter.is_template("Lamp") and not matter.is_template(None)
    assert matter.normalize_interval(None) == 60 and matter.normalize_interval("abc") == 60
    assert matter.normalize_interval(1) == 1 and matter.normalize_interval(0) == 0
    assert matter.normalize_interval(-5) == 0 and matter.normalize_interval(99999) == 3600
    assert matter.normalize_interval("90") == 90


def test_a_rendered_caption_is_made_to_fit_never_rejected():
    assert matter.fit_caption("  Charging 84%  ") == "Charging 84%"
    assert matter.fit_caption("") == "-" and matter.fit_caption("\n\t") == "-"
    assert matter.fit_caption("a\0b\x07c") == "abc"
    long = matter.fit_caption("я" * 40)
    assert len(long.encode()) <= 31 and long == "я" * 15  # never half of a two-byte letter
    assert len(matter.fit_caption("x" * 100).encode()) == 31


def test_scheduler_never_writes_what_the_remote_already_shows():
    scheduler = matter.CaptionScheduler(60, ("a", "b", "c", "d"))
    assert scheduler.offer(("a", "b", "c", "d"), 0) is None
    assert scheduler.pending is None
    assert scheduler.offer(("a", "b", "c", "e"), 0) == 0  # first write is not delayed


def test_scheduler_waits_out_the_interval_and_keeps_only_the_latest():
    scheduler = matter.CaptionScheduler(60, ("a", "b", "c", "d"))
    scheduler.written(("a", "b", "c", "1"), 100)
    assert scheduler.offer(("a", "b", "c", "2"), 110) == pytest.approx(50)
    assert scheduler.offer(("a", "b", "c", "3"), 130) == pytest.approx(30)
    assert scheduler.pending == ("a", "b", "c", "3")
    # The value went back to what is shown: nothing is left to write.
    assert scheduler.offer(("a", "b", "c", "1"), 140) is None and scheduler.pending is None
    scheduler.written(("a", "b", "c", "3"), 200)
    assert scheduler.offer(("a", "b", "c", "4"), 500) == 0  # long past the interval


def test_scheduler_backs_off_after_failures_up_to_ten_minutes():
    scheduler = matter.CaptionScheduler(60, ("a", "b", "c", "d"))
    scheduler.offer(("x", "b", "c", "d"), 0)
    scheduler.failed()
    assert scheduler.delay(0) == 60
    scheduler.failed()
    assert scheduler.delay(0) == 120
    for _ in range(10):
        scheduler.failed()
    assert scheduler.delay(0) == 600
    scheduler.written(("x", "b", "c", "d"), 1000)
    assert scheduler.failures == 0


def test_a_zero_interval_still_never_retries_a_failed_write_in_a_loop():
    scheduler = matter.CaptionScheduler(0, ("a", "b", "c", "d"))
    scheduler.written(("a", "b", "c", "1"), 100)
    assert scheduler.offer(("a", "b", "c", "2"), 100) == 0  # no interval: write at once
    scheduler.failed()
    assert scheduler.delay(100) == 5
    scheduler.failed()
    assert scheduler.delay(100) == 10


# -- saving templates through Studio -------------------------------------------------------------

def test_studio_renders_templates_before_it_writes_and_keeps_their_source(studio, monkeypatch):
    module = studio.studio_matter
    monkeypatch.setattr(module, "render_caption", lambda hass, text: "84%" if "battery" in text else "?")
    client = FakeRemote([NATIVE_ROW])
    hass, entry, connection, out = make(studio, client)
    calls = []
    hass.data["switchbot_urc"]["entry"]["matter_live"] = types.SimpleNamespace(
        reconfigure=lambda wrote=False: calls.append(wrote))
    fields = ["Lamp", "Battery {{ states('sensor.battery') }}", "Music", "Scene D"]
    run(module.ws_save_matter(hass, connection, {
        "id": 1, "entry_id": "entry", "name": "Accessory", "captions": fields, "min_interval": 5}))
    assert out["errors"] == []
    remote = entry.options["remotes"][0]
    assert remote["matter_captions"] == ["Lamp", "84%", "Music", "Scene D"]  # what the remote shows
    assert remote["matter_templates"] == ["", fields[1], "", ""]
    assert remote["matter_min_interval"] == 5  # no lower limit
    assert calls == [True]
    assert b"84%" in client.sent[0] and b"{{" not in client.sent[0]

    payload = studio._matter_payload(remote)
    assert payload["fields"] == ["Lamp", fields[1], "Music", "Scene D"]
    assert payload["captions"] == ["Lamp", "84%", "Music", "Scene D"]
    assert payload["min_interval"] == 5


def test_a_template_that_does_not_render_is_refused_and_nothing_is_written(studio, monkeypatch):
    module = studio.studio_matter

    def broken(hass, text):
        raise ValueError(f"The template {text!r} does not render: boom")

    monkeypatch.setattr(module, "render_caption", broken)
    client = FakeRemote([NATIVE_ROW])
    hass, entry, connection, out = make(studio, client)
    run(module.ws_save_matter(hass, connection, {
        "id": 1, "entry_id": "entry", "name": "Accessory",
        "captions": ["{{ nope", "b", "c", "d"]}))
    assert out["errors"] and "does not render" in out["errors"][0][1]
    assert client.sent == [] and entry.options["remotes"] == []


# -- the manager ----------------------------------------------------------------------------------

class Harness:
    """Fake templates, a fake template tracker and a fake timer, with a clock the test moves."""

    def __init__(self, monkeypatch, entry, hass):
        self.values = {}
        self.timers = []
        self.tracker = None
        self.written = []
        self.now = 1000.0
        outer = self

        class Template:
            def __init__(self, text, _hass):
                self.text = text

            def async_render(self, parse_result=False):
                value = outer.values[self.text]
                if isinstance(value, Exception):
                    raise value
                return value

        class Tracked:
            def __init__(self, tracks, action):
                self.tracks, self.action, self.removed = tracks, action, False

            def async_remove(self):
                self.removed = True

        def track(_hass, tracks, action):
            outer.tracker = Tracked(tracks, action)
            return outer.tracker

        def later(_hass, delay, action):
            timer = {"delay": delay, "action": action, "cancelled": False}
            outer.timers.append(timer)
            return lambda: timer.update(cancelled=True)

        monkeypatch.setitem(sys.modules, "homeassistant.helpers.template",
                            types.SimpleNamespace(Template=Template))
        monkeypatch.setitem(sys.modules, "homeassistant.helpers.event", types.SimpleNamespace(
            TrackTemplate=lambda template, variables: (template, variables),
            async_track_template_result=track, async_call_later=later))
        self.live = importlib.import_module("switchbot_urc.matter_live")
        self.studio_matter = sys.modules["switchbot_urc.studio_matter"]

        async def write(_hass, entry_, captions):
            outer.written.append(tuple(captions))
            if outer.fail:
                raise ValueError("the remote is asleep")
            for remote in entry_.options["remotes"]:
                remote["matter_captions"] = list(captions)

        self.fail = False
        monkeypatch.setattr(self.live, "write_live_captions", write)
        self.manager = self.live.MatterLiveCaptions(hass, entry, clock=lambda: self.now)

    def pending_timer(self):
        return [t for t in self.timers if not t["cancelled"]][-1]

    async def fire(self):
        timer = self.pending_timer()
        timer["cancelled"] = True
        timer["action"](None)
        for _ in range(5):
            await asyncio.sleep(0)


def live_remote(**extra):
    return {"index": 1, "name": "Accessory", "device_type": "MATTER_TEXT",
            "device_id": "4d5400000001", "remote_id": "abcd1234", "buttons": [],
            "matter_captions": ["Lamp", "Battery 80%", "Music", "Scene D"],
            "matter_templates": ["", "Battery {{ b }}%", "", ""], **extra}


def manager_setup(studio, monkeypatch, **extra):
    hass, entry, _, _ = make(studio, FakeRemote([]), [live_remote(**extra)])
    hass.is_running = True
    hass.async_create_task = lambda coro: asyncio.ensure_future(coro)
    return hass, entry, Harness(monkeypatch, entry, hass)


def test_manager_writes_a_changed_value_once_and_not_an_unchanged_one(studio, monkeypatch):
    async def scenario():
        hass, entry, h = manager_setup(studio, monkeypatch)
        h.values["Battery {{ b }}%"] = "Battery 80%"
        h.manager.reconfigure()
        assert h.timers == [] and h.written == []  # the remote already shows exactly this

        h.values["Battery {{ b }}%"] = "Battery 79%"
        h.tracker.action(None, None)
        assert h.pending_timer()["delay"] == 0  # first write is not delayed
        await h.fire()
        assert h.written == [("Lamp", "Battery 79%", "Music", "Scene D")]

        h.tracker.action(None, None)  # nothing changed since
        assert all(t["cancelled"] for t in h.timers)
        assert len(h.written) == 1

    asyncio.run(scenario())


def test_manager_spares_the_remote_between_changes(studio, monkeypatch):
    async def scenario():
        hass, entry, h = manager_setup(studio, monkeypatch, matter_min_interval=120)
        h.values["Battery {{ b }}%"] = "Battery 79%"
        h.manager.reconfigure()
        await h.fire()
        h.now += 30
        h.values["Battery {{ b }}%"] = "Battery 78%"
        h.tracker.action(None, None)
        assert h.pending_timer()["delay"] == pytest.approx(90)
        h.now += 10
        h.values["Battery {{ b }}%"] = "Battery 77%"
        h.tracker.action(None, None)
        assert h.pending_timer()["delay"] == pytest.approx(80)
        h.now += 80
        await h.fire()
        assert h.written[-1][1] == "Battery 77%" and len(h.written) == 2  # only the latest

    asyncio.run(scenario())


def test_manager_retries_later_after_a_failed_write_and_warns_once(studio, monkeypatch, caplog):
    async def scenario():
        hass, entry, h = manager_setup(studio, monkeypatch)
        h.values["Battery {{ b }}%"] = "Battery 70%"
        h.manager.reconfigure()
        h.fail = True
        await h.fire()
        assert h.pending_timer()["delay"] == 60  # backed off, not retried in a loop
        h.now += 60
        await h.fire()
        assert h.pending_timer()["delay"] == 120
        h.fail = False
        h.now += 120
        await h.fire()
        assert h.written[-1][1] == "Battery 70%"
        assert [r for r in caplog.records if "Could not update" in r.message].__len__() == 1

    asyncio.run(scenario())


def test_a_template_that_fails_while_running_keeps_the_last_text(studio, monkeypatch):
    async def scenario():
        hass, entry, h = manager_setup(studio, monkeypatch)
        h.values["Battery {{ b }}%"] = ValueError("sensor gone")
        h.manager.reconfigure()
        assert h.timers == [] and h.written == []

    asyncio.run(scenario())


def test_manager_follows_a_saved_change_and_stops_cleanly(studio, monkeypatch):
    async def scenario():
        hass, entry, h = manager_setup(studio, monkeypatch)
        h.values["Battery {{ b }}%"] = "Battery 80%"
        h.manager.reconfigure()
        first = h.tracker
        entry.options["remotes"][0]["matter_templates"] = ["", "", "", ""]  # all plain again
        h.manager.reconfigure(wrote=True)
        assert first.removed and h.tracker is first  # nothing new to track
        h.manager.stop()

    asyncio.run(scenario())
