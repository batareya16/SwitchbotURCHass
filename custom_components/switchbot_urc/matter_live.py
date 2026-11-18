"""Live captions for the text remote: captions written as Home Assistant templates.

A caption that contains ``{{ ... }}`` is rendered whenever an entity it reads changes, and the new
text is written to the remote's own screen. Writing is not free: every write pauses the bridge
for a few seconds and rewrites a file in the remote's flash. So a change is written only when the
text really differs from what the remote shows, never sooner than the configured interval after
the previous write, and when values change meanwhile only the latest set is written
(:class:`~.matter_text.CaptionScheduler`).

Hardware, 2026-11-18: a caption rewritten while its screen is open changes on that screen by
itself, so this needs no extra command.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from homeassistant.core import HomeAssistant, callback

from .matter_text import (
    MIN_INTERVAL_DEFAULT,
    CaptionScheduler,
    fit_caption,
    normalize_interval,
)
from .studio_matter import captions_of, matter_remote, write_live_captions
from .studio_remotes import remote_management_lock

_LOGGER = logging.getLogger(__name__)


class MatterLiveCaptions:
    """Keeps the text remote's templated captions up to date for one config entry."""

    def __init__(self, hass: HomeAssistant, entry, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._hass = hass
        self._entry = entry
        self._clock = clock
        self._scheduler: CaptionScheduler | None = None
        self._templates: list[Any] = []
        self._tracker: Any = None
        self._timer: Callable[[], None] | None = None
        self._started_unsub: Callable[[], None] | None = None
        self._writing = False
        self._last_error = ""
        self._warned_templates: set[int] = set()

    # -- configuration -------------------------------------------------------------------------

    @callback
    def reconfigure(self, wrote: bool = False) -> None:
        """Read the saved remote again. ``wrote`` is true right after Studio wrote it itself."""
        self._release()
        remote = matter_remote(self._entry)
        if remote is None:
            self._scheduler = None
            return
        interval = normalize_interval(remote.get("matter_min_interval", MIN_INTERVAL_DEFAULT))
        shown = captions_of(remote)
        if self._scheduler is None:
            self._scheduler = CaptionScheduler(interval, shown)
        else:
            self._scheduler.interval = interval
            self._scheduler.shown = shown
            self._scheduler.pending = None
        if wrote:
            self._scheduler.last_write = self._clock()
        sources = [str(item or "") for item in (remote.get("matter_templates") or [])][:4]
        sources += [""] * (4 - len(sources))
        if not any(sources):
            return
        from homeassistant.helpers.template import Template  # noqa: PLC0415

        self._warned_templates = set()
        self._templates = [Template(text, self._hass) if text else None for text in sources]
        self._track()
        if self._hass.is_running:
            self._evaluate()
        else:
            from homeassistant.const import EVENT_HOMEASSISTANT_STARTED  # noqa: PLC0415

            self._started_unsub = self._hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STARTED, lambda _event: self._evaluate())

    def _track(self) -> None:
        from homeassistant.helpers.event import (  # noqa: PLC0415
            TrackTemplate,
            async_track_template_result,
        )

        tracks = [TrackTemplate(template, None) for template in self._templates if template]
        self._tracker = async_track_template_result(self._hass, tracks, self._on_update)

    @callback
    def stop(self) -> None:
        self._release()

    def _release(self) -> None:
        if self._tracker is not None:
            self._tracker.async_remove()
            self._tracker = None
        if self._timer is not None:
            self._timer()
            self._timer = None
        if self._started_unsub is not None:
            self._started_unsub()
            self._started_unsub = None
        self._templates = []

    # -- rendering and scheduling --------------------------------------------------------------

    @callback
    def _on_update(self, _event, _updates) -> None:
        self._evaluate()

    @callback
    def _evaluate(self) -> None:
        remote = matter_remote(self._entry)
        if remote is None or self._scheduler is None or not any(self._templates):
            return
        written = captions_of(remote)
        rendered = []
        for index, template in enumerate(self._templates):
            if template is None:
                rendered.append(written[index])
                continue
            try:
                rendered.append(fit_caption(template.async_render(parse_result=False)))
            except Exception as err:  # noqa: BLE001 - one broken template must not stop the others
                if index not in self._warned_templates:
                    self._warned_templates.add(index)
                    _LOGGER.warning("Text remote caption %s does not render: %s", "ABCD"[index], err)
                rendered.append(written[index])
        delay = self._scheduler.offer(tuple(rendered), self._clock())
        if delay is None:
            self._cancel_timer()
            return
        self._arm(delay)

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer()
            self._timer = None

    def _arm(self, delay: float) -> None:
        from homeassistant.helpers.event import async_call_later  # noqa: PLC0415

        self._cancel_timer()
        self._timer = async_call_later(self._hass, delay, self._flush)

    @callback
    def _flush(self, _now) -> None:
        self._timer = None
        scheduler = self._scheduler
        if scheduler is None or scheduler.pending is None or self._writing:
            return
        self._hass.async_create_task(self._write(scheduler.pending))

    async def _write(self, captions: tuple[str, ...]) -> None:
        scheduler = self._scheduler
        if scheduler is None:
            return
        self._writing = True
        try:
            async with remote_management_lock(self._hass):
                await write_live_captions(self._hass, self._entry, captions)
        except Exception as err:  # noqa: BLE001 - the remote may be asleep or out of range
            scheduler.failed()
            if str(err) != self._last_error:
                self._last_error = str(err)
                _LOGGER.warning("Could not update the text remote's captions: %s", err)
            self._arm(scheduler.delay(self._clock()))
        else:
            self._last_error = ""
            scheduler.written(captions, self._clock())
            if scheduler.pending is not None:
                self._arm(scheduler.delay(self._clock()))
        finally:
            self._writing = False
