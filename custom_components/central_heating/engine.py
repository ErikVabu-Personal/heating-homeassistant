"""Per-entry boiler recalculation and lifecycle; room control follows in PR 2b."""

import asyncio
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.util import dt as dt_util

from .boiler.base import BoilerAdapter, BoilerCommand
from .demand import DemandResult, TRVReading, calculate_demand
from .smoothing import SmoothingInput, SmoothingState, smooth
from .storage import HeatingStore, Mode


class HeatingEngine:
    def __init__(
        self,
        hass: HomeAssistant,
        store: HeatingStore,
        adapter: BoilerAdapter,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.hass, self.store, self.adapter = hass, store, adapter
        self.monotonic = monotonic
        self.demand = DemandResult(0, None, store.data.settings.frost_temperature)
        self.temperature: float | None = None
        self.command = BoilerCommand(False, None, store.data.settings.frost_temperature)
        self.last_sent: datetime | None = None
        self._last_command: BoilerCommand | None = None
        self._last_send_tick: float | None = None
        self._last_source_tick: float | None = None
        self._smoothing = SmoothingState()
        self._lock = asyncio.Lock()
        self._listeners: set[Callable[[], None]] = set()
        self._unsubscribers: list[Callable[[], None]] = []
        self._state_unsubscribe: Callable[[], None] | None = None
        self._stopped = False
        self._shutting_down = False

    @callback
    def listen(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            listener()

    async def async_start(self) -> None:
        self._unsubscribers.append(
            self.hass.bus.async_listen(EVENT_HOMEASSISTANT_STOP, self._shutdown)
        )
        self._unsubscribers.append(
            async_track_time_interval(self.hass, self._tick, timedelta(seconds=10))
        )
        self._watch_trvs()
        if self.hass.state is CoreState.running:
            await self.async_recalculate()
        else:
            self._unsubscribers.append(
                self.hass.bus.async_listen(EVENT_HOMEASSISTANT_STARTED, self._started)
            )

    def _watch_trvs(self) -> None:
        if self._state_unsubscribe is not None:
            self._state_unsubscribe()
        trvs = [trv for room in self.store.data.rooms if room.enabled for trv in room.trvs]
        self._state_unsubscribe = (
            async_track_state_change_event(self.hass, trvs, self._trv_changed) if trvs else None
        )

    async def _started(self, event: Event) -> None:
        await self.async_recalculate()

    async def _tick(self, now: datetime) -> None:
        await self.async_recalculate()

    async def _trv_changed(self, event: Event) -> None:
        await self.async_recalculate()

    async def _shutdown(self, event: Event) -> None:
        self._shutting_down = True
        await self.async_stop(unloading=False)

    async def async_stop(self, *, unloading: bool) -> None:
        async with self._lock:
            if self._stopped:
                return
            self._stopped = True
            for unsubscribe in self._unsubscribers:
                unsubscribe()
            self._unsubscribers.clear()
            if self._state_unsubscribe is not None:
                self._state_unsubscribe()
                self._state_unsubscribe = None
            if unloading and not self._shutting_down and not self.store.data.shadow:
                await self.adapter.async_stop(unloading=True)

    async def async_recalculate(self) -> None:
        async with self._lock:
            if self._stopped or self._shutting_down or self.hass.state is not CoreState.running:
                return
            now = dt_util.utcnow()
            mode = self.store.data.mode
            if mode.until is not None and mode.until.astimezone(UTC) <= now:
                await self.store.async_update(lambda data: replace(data, mode=Mode("auto")))
            readings = []
            for room in self.store.data.rooms:
                if not room.enabled:
                    continue
                for trv in room.trvs:
                    state = self.hass.states.get(trv)
                    if state is None or state.state in ("unknown", "unavailable"):
                        readings.append(TRVReading(None, None))
                    else:
                        readings.append(
                            TRVReading(
                                state.attributes.get("current_temperature"),
                                state.attributes.get("temperature"),
                            )
                        )
            settings = self.store.data.settings
            self.demand = calculate_demand(
                readings,
                hysteresis=settings.hysteresis,
                frost_temperature=settings.frost_temperature,
            )
            tick = self.monotonic()
            filtered = smooth(SmoothingInput(self.demand.virtual_temp_raw, tick), self._smoothing)
            self._smoothing, self.temperature = filtered.state, filtered.value
            self.command = BoilerCommand(
                self.demand.demand_count > 0 and self.store.data.mode.value != "summer",
                self.temperature,
                self.demand.virtual_setpoint,
            )
            if not self.store.data.shadow:
                if self._last_source_tick is None or tick - self._last_source_tick >= 21600:
                    await self.adapter.async_start()
                    if self.adapter.last_success:
                        self._last_source_tick = tick
                keepalive = self._last_send_tick is None or tick - self._last_send_tick >= 30
                if self.command != self._last_command or keepalive:
                    await self.adapter.async_apply(self.command, keepalive=keepalive)
                    if self.adapter.last_success:
                        self._last_command = self.command
                        self._last_send_tick = tick
                        self.last_sent = now
            self._notify()

    async def async_set_mode(self, value: str, until: datetime | None = None) -> None:
        async with self._lock:
            try:
                await self.store.async_update(lambda data: replace(data, mode=Mode(value, until)))
            except ValueError as exc:
                raise ServiceValidationError(str(exc)) from exc
        await self.async_recalculate()

    async def async_set_shadow(self, enabled: bool) -> None:
        async with self._lock:
            await self.store.async_update(lambda data: replace(data, shadow=enabled))
            self._last_command = None
            self._last_send_tick = self._last_source_tick = None
        await self.async_recalculate()

    async def async_settings(self, **changes) -> None:
        async with self._lock:
            try:
                await self.store.async_settings(**changes)
            except ValueError as exc:
                raise ServiceValidationError(str(exc)) from exc
        await self.async_recalculate()

    async def async_data_changed(self) -> None:
        self._watch_trvs()
        await self.async_recalculate()
