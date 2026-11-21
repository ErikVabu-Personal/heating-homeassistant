"""Room scheduling, temporary overrides and bounded TRV write retries."""

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.core import Context, Event
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .demand import available_temperature
from .schedule import Room, schedule_at, until_next_change
from .storage import Override, bounded

_LOGGER = logging.getLogger(__name__)


@dataclass
class Pending:
    target: float
    observed: float | None
    context: Context
    retries: int = 0
    cancel: object = None


class RoomController:
    def __init__(self, engine, entry_id: str) -> None:
        self.engine = engine
        self.hass, self.store = engine.hass, engine.store
        self.entry_id = entry_id
        self.last_commanded: dict[str, tuple[float, datetime, Context]] = {}
        self.pending: dict[str, Pending] = {}
        self.problems: set[str] = set()
        self._timer = None
        self._profiles = {room.id: room.profile_id for room in self.store.data.rooms}

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.hass.config.time_zone)

    def room(self, room_id: str) -> Room:
        return next(room for room in self.store.data.rooms if room.id == room_id)

    def schedule(self, room: Room, now: datetime | None = None):
        profile = next(
            profile for profile in self.store.data.profiles if profile.id == room.profile_id
        )
        return schedule_at(profile, now or dt_util.utcnow(), self.zone)

    def desired(self, room: Room, now: datetime | None = None) -> float | None:
        now = now or dt_util.utcnow()
        data = self.store.data
        if not room.enabled or data.mode.value == "manual":
            return None
        if data.mode.value == "summer":
            return data.settings.frost_temperature
        override = next(
            (
                item
                for item in data.overrides
                if item.room_id == room.id and item.until.astimezone(UTC) > now
            ),
            None,
        )
        if override is not None:
            return override.target
        if data.mode.value == "away":
            return data.settings.away_temperature
        return self.schedule(room, now).current.block.target

    async def async_set_override(
        self, room_id: str, target: float, minutes: int | None = None, *, source: str = "service"
    ) -> None:
        bounded(target, 5, 30, 0.5)
        room = self.room(room_id)
        if minutes is not None and (type(minutes) is not int or minutes <= 0):
            raise ValueError("Override minutes must be a positive integer")
        now = dt_util.utcnow()
        settings = self.store.data.settings
        if minutes is not None or settings.override_default == "duration":
            until = now + timedelta(
                minutes=minutes if minutes is not None else settings.override_minutes
            )
        else:
            profile = next(
                profile for profile in self.store.data.profiles if profile.id == room.profile_id
            )
            until = until_next_change(profile, now, self.zone)
        override = Override(room_id, target, until, source)
        await self.store.async_update(
            lambda data: replace(
                data,
                overrides=tuple(item for item in data.overrides if item.room_id != room_id)
                + (override,),
            )
        )

    async def async_clear_override(self, room_id: str) -> None:
        self.room(room_id)
        await self.store.async_update(
            lambda data: replace(
                data, overrides=tuple(item for item in data.overrides if item.room_id != room_id)
            )
        )

    def _cancel_pending(self, trv: str) -> None:
        pending = self.pending.pop(trv, None)
        if pending is not None and pending.cancel is not None:
            pending.cancel()

    def _clear_problem(self, trv: str) -> None:
        self.problems.discard(trv)
        ir.async_delete_issue(self.hass, DOMAIN, f"sync_{self.entry_id}_{trv}")

    async def async_changed(self, event: Event) -> None:
        old, new = event.data.get("old_state"), event.data.get("new_state")
        trv = event.data["entity_id"]
        if new is None or new.state in ("unknown", "unavailable"):
            return
        target = available_temperature(new.attributes.get("temperature"))
        commanded = self.last_commanded.get(trv)
        if commanded is not None and target == commanded[0]:
            self._cancel_pending(trv)
            self._clear_problem(trv)
            return
        if old is None or old.state in ("unknown", "unavailable"):
            self._cancel_pending(trv)
            self.problems.discard(trv)
            return
        previous = available_temperature(old.attributes.get("temperature"))
        if target is None or target == previous or self.store.data.mode.value == "manual":
            return
        room = next(
            (room for room in self.store.data.rooms if room.enabled and trv in room.trvs), None
        )
        if room is not None:
            self._cancel_pending(trv)
            self.problems.discard(trv)
            try:
                await self.async_set_override(room.id, target, source="trv")
            except ValueError:
                _LOGGER.warning("Ignoring an invalid thermostat override target")

    async def async_apply(self) -> None:
        now = dt_util.utcnow()
        changed_profiles = {
            room.id
            for room in self.store.data.rooms
            if room.id in self._profiles and self._profiles[room.id] != room.profile_id
        }
        surviving = tuple(
            item
            for item in self.store.data.overrides
            if item.until.astimezone(UTC) > now and item.room_id not in changed_profiles
        )
        if surviving != self.store.data.overrides:
            await self.store.async_update(lambda data: replace(data, overrides=surviving))
        self._profiles = {room.id: room.profile_id for room in self.store.data.rooms}
        active = {trv for room in self.store.data.rooms if room.enabled for trv in room.trvs}
        for trv in set(self.pending) | self.problems:
            if trv not in active or self.store.data.mode.value == "manual":
                self._cancel_pending(trv)
                self._clear_problem(trv)
        for room in self.store.data.rooms:
            desired = self.desired(room, now)
            override = next(
                (item for item in self.store.data.overrides if item.room_id == room.id), None
            )
            if desired is None or (
                override is not None
                and override.source == "trv"
                and not self.store.data.settings.sync_rooms_on_knob_change
                and self.store.data.mode.value != "summer"
            ):
                continue
            for trv in room.trvs:
                state = self.hass.states.get(trv)
                if state is None or state.state in ("unknown", "unavailable"):
                    continue
                target = available_temperature(state.attributes.get("temperature"))
                if target == desired:
                    self._cancel_pending(trv)
                    self._clear_problem(trv)
                    continue
                pending = self.pending.get(trv)
                if pending is not None and pending.target == desired:
                    continue
                if trv in self.problems and self.last_commanded.get(trv, (None,))[0] == desired:
                    continue
                self._cancel_pending(trv)
                self._clear_problem(trv)
                pending = Pending(desired, target, Context())
                self.pending[trv] = pending
                await self._write(trv, pending)
        self._reschedule()

    async def _write(self, trv: str, pending: Pending) -> None:
        state = self.hass.states.get(trv)
        values = {"entity_id": trv, "temperature": pending.target}
        if (
            state is not None
            and state.state != "heat"
            and "heat" in state.attributes.get("hvac_modes", [])
        ):
            values["hvac_mode"] = "heat"
        self.last_commanded[trv] = (pending.target, dt_util.utcnow(), pending.context)
        try:
            await self.hass.services.async_call(
                "climate", "set_temperature", values, blocking=True, context=pending.context
            )
        except Exception:
            _LOGGER.warning("Central Heating TRV command failed; bounded retry scheduled")
        if self.pending.get(trv) is pending:

            async def retry(at):
                await self._retry(trv, pending)

            pending.cancel = async_track_point_in_time(
                self.hass,
                retry,
                dt_util.utcnow() + timedelta(seconds=self.store.data.settings.retry_seconds),
            )

    async def _retry(self, trv: str, pending: Pending) -> None:
        async with self.engine._lock:
            if self.engine._stopped or self.pending.get(trv) is not pending:
                return
            pending.cancel = None
            state = self.hass.states.get(trv)
            room = next(
                (room for room in self.store.data.rooms if room.enabled and trv in room.trvs), None
            )
            target = (
                available_temperature(state.attributes.get("temperature"))
                if state is not None
                else None
            )
            if target == pending.target:
                self._cancel_pending(trv)
                self._clear_problem(trv)
            elif (
                room is None
                or state is None
                or state.state in ("unknown", "unavailable")
                or self.desired(room) != pending.target
                or target != pending.observed
            ):
                self._cancel_pending(trv)
            elif pending.retries >= 3:
                self._cancel_pending(trv)
                self.problems.add(trv)
                _LOGGER.warning("Central Heating TRV did not synchronize after three retries")
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"sync_{self.entry_id}_{trv}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="sync_problem",
                )
            else:
                pending.retries += 1
                await self._write(trv, pending)
            self.engine._notify()

    def _reschedule(self) -> None:
        if self._timer is not None:
            self._timer()
        now = dt_util.utcnow()
        times = [
            self.schedule(room, now).next.at.astimezone(UTC)
            for room in self.store.data.rooms
            if room.enabled
        ]
        times += [
            item.until.astimezone(UTC)
            for item in self.store.data.overrides
            if item.until.astimezone(UTC) > now
        ]
        if (
            self.store.data.mode.until is not None
            and self.store.data.mode.until.astimezone(UTC) > now
        ):
            times.append(self.store.data.mode.until.astimezone(UTC))
        self._timer = (
            async_track_point_in_time(self.hass, self._at_boundary, min(times)) if times else None
        )

    async def _at_boundary(self, now: datetime) -> None:
        self._timer = None
        await self.engine.async_recalculate()

    def stop(self) -> None:
        if self._timer is not None:
            self._timer()
            self._timer = None
        for trv in tuple(self.pending):
            self._cancel_pending(trv)
