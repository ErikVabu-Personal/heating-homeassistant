"""Trigger-driven room targets, unconfirmed TRV commands and bounded retries."""

import logging
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.core import Context, CoreState, Event
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .demand import available_temperature
from .schedule import Room, schedule_at, until_next_change
from .storage import Override, bounded

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class SentCommand:
    target: float
    at: datetime
    before: float | None
    context_id: str


@dataclass
class Pending:
    target: float
    observed: float | None
    context: Context
    retries: int = 0
    cancel: object = None
    commands: list[SentCommand] = field(default_factory=list)


class RoomController:
    def __init__(self, engine, entry_id: str) -> None:
        self.engine = engine
        self.hass, self.store = engine.hass, engine.store
        self.entry_id = entry_id
        # Diagnostics only: echo detection uses unconfirmed commands, never this history.
        self.last_commanded: dict[str, tuple[float, datetime, Context]] = {}
        self.pending: dict[str, Pending] = {}
        self.problems: set[str] = set()
        self._timer = None
        self._profiles = {room.id: room.profile_id for room in self.store.data.rooms}

    @property
    def zone(self) -> ZoneInfo:
        return dt_util.get_default_time_zone()

    def room(self, room_id: str) -> Room:
        try:
            return next(room for room in self.store.data.rooms if room.id == room_id)
        except StopIteration as exc:
            raise ServiceValidationError("Unknown room") from exc

    def schedule(self, room: Room, now: datetime | None = None):
        profile = next(
            profile for profile in self.store.data.profiles if profile.id == room.profile_id
        )
        return schedule_at(profile, now or dt_util.utcnow(), self.zone)

    def desired(
        self, room: Room, now: datetime | None = None, *, without_override=False
    ) -> float | None:
        now = now or dt_util.utcnow()
        data = self.store.data
        if not room.enabled or data.mode.value == "manual":
            return None
        if data.mode.value == "summer":
            return data.settings.frost_temperature
        if not without_override:
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
        self,
        room_id: str,
        target: float,
        minutes: int | None = None,
        *,
        source: str = "service",
        kind: str | None = None,
    ) -> None:
        try:
            bounded(target, 5, 30, 0.5)
        except ValueError as exc:
            raise ServiceValidationError(str(exc)) from exc
        room = self.room(room_id)
        if minutes is not None and (type(minutes) is not int or not 1 <= minutes <= 10080):
            raise ServiceValidationError("Override minutes must be an integer from 1 to 10080")
        if kind not in (None, "next_block", "duration"):
            raise ServiceValidationError("Invalid override kind")
        if kind == "next_block" and minutes is not None:
            raise ServiceValidationError("A next-change override cannot include minutes")
        now = dt_util.utcnow()
        settings = self.store.data.settings
        selected_kind = kind or ("duration" if minutes is not None else settings.override_default)
        if selected_kind == "duration":
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
        self._reschedule()

    async def async_clear_override(self, room_id: str) -> None:
        self.room(room_id)
        if not any(item.room_id == room_id for item in self.store.data.overrides):
            return
        await self.store.async_update(
            lambda data: replace(
                data, overrides=tuple(item for item in data.overrides if item.room_id != room_id)
            )
        )
        self._reschedule()

    def _cancel_pending(self, trv: str) -> None:
        pending = self.pending.pop(trv, None)
        if pending is not None and pending.cancel is not None:
            pending.cancel()

    def _clear_problem(self, trv: str) -> None:
        self.problems.discard(trv)
        ir.async_delete_issue(self.hass, DOMAIN, f"sync_{self.entry_id}_{trv}")

    def _prune(self, pending: Pending) -> None:
        cutoff = dt_util.utcnow() - timedelta(seconds=self.store.data.settings.retry_seconds * 4)
        pending.commands[:] = [command for command in pending.commands if command.at > cutoff]

    async def async_changed(self, event: Event) -> str | None:
        if self.hass.state is not CoreState.running:
            return None
        old, new = event.data.get("old_state"), event.data.get("new_state")
        trv = event.data["entity_id"]
        room = next(
            (room for room in self.store.data.rooms if room.enabled and trv in room.trvs), None
        )
        if room is None or new is None or new.state in ("unknown", "unavailable"):
            return None
        if old is None or old.state in ("unknown", "unavailable"):
            self._cancel_pending(trv)
            self._clear_problem(trv)
            return room.id
        # Off is a user's deliberate pause until the next room trigger.
        if new.state == "off" and old.state != "off":
            self._cancel_pending(trv)
            return None
        target = available_temperature(new.attributes.get("temperature"))
        previous = available_temperature(old.attributes.get("temperature"))
        if target is None:
            return None
        pending = self.pending.get(trv)
        if pending is not None:
            self._prune(pending)
            matches = [i for i, command in enumerate(pending.commands) if command.target == target]
            if matches:
                if new.state == "off" and "heat" in (new.attributes.get("hvac_modes") or []):
                    return None  # Equal target alone cannot confirm a pending heat command.
                if any(command.context_id == new.context.id for command in pending.commands):
                    # HA may report the requested value optimistically before the radio write.
                    # Keep both the commands and their stale guards until a device report/retry.
                    return None
                del pending.commands[: matches[-1] + 1]
                pending.observed = target
                if not pending.commands:
                    self._cancel_pending(trv)
                    self._clear_problem(trv)
                return None
            if any(command.before == target for command in pending.commands):
                return (
                    None  # Stale/optimistic value; retry corrects a real turn back in this window.
                )
        if target == previous or self.store.data.mode.value not in ("auto", "away"):
            return None
        self._cancel_pending(trv)
        self._clear_problem(trv)
        target = max(5.0, min(30.0, round(target * 2) / 2))
        if target == self.desired(room, without_override=True):
            await self.async_clear_override(room.id)
        else:
            await self.async_set_override(room.id, target, source="trv")
        return room.id

    async def async_apply(self, *, force: bool = False, room_id: str | None = None) -> None:
        if self.hass.state is not CoreState.running:
            return
        try:
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
                if room_id is not None and room.id != room_id:
                    continue
                desired = self.desired(room, now)
                override = next(
                    (item for item in self.store.data.overrides if item.room_id == room.id), None
                )
                if desired is None or (
                    not force
                    and override is not None
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
                    needs_heat = state.state != "heat" and "heat" in (
                        state.attributes.get("hvac_modes") or []
                    )
                    if not force and target == desired and not needs_heat:
                        # Don't erase a newer unconfirmed command on a stale state snapshot.
                        pending = self.pending.get(trv)
                        if pending is None:
                            self._clear_problem(trv)
                            continue
                        if pending.target == desired:
                            continue  # A normal trigger cannot confirm an optimistic report.
                    previous = self.pending.get(trv)
                    if not force and previous is not None and previous.target == desired:
                        continue
                    if (
                        not force
                        and trv in self.problems
                        and self.last_commanded.get(trv, (None,))[0] == desired
                    ):
                        continue
                    commands = []
                    if previous is not None:
                        self._prune(previous)
                        commands = previous.commands.copy()
                    self._cancel_pending(trv)
                    self._clear_problem(trv)
                    pending = Pending(desired, target, Context(), commands=commands)
                    self.pending[trv] = pending
                    await self._write(trv, pending)
        finally:
            self._reschedule()

    async def _write(self, trv: str, pending: Pending) -> None:
        if self.hass.state is not CoreState.running or self.engine._stopped:
            return
        state = self.hass.states.get(trv)
        values = {"entity_id": trv, "temperature": pending.target}
        if (
            state is not None
            and state.state != "heat"
            and "heat" in (state.attributes.get("hvac_modes") or [])
        ):
            values["hvac_mode"] = "heat"
        now = dt_util.utcnow()
        self.last_commanded[trv] = (pending.target, now, pending.context)
        if not pending.commands or pending.commands[-1].target != pending.target:
            pending.commands.append(
                SentCommand(pending.target, now, pending.observed, pending.context.id)
            )
        try:
            # HA schedules the handler; radio latency never holds either control lock.
            await self.hass.services.async_call(
                "climate", "set_temperature", values, blocking=False, context=pending.context
            )
        except Exception:
            _LOGGER.warning("Central Heating TRV command failed; bounded retry scheduled")
        if self.pending.get(trv) is pending:

            async def retry(at):
                await self._retry(trv, pending)

            pending.cancel = async_track_point_in_time(
                self.hass, retry, now + timedelta(seconds=self.store.data.settings.retry_seconds)
            )

    async def _retry(self, trv: str, pending: Pending) -> None:
        async with self.engine._room_lock:
            if (
                self.engine._stopped
                or self.hass.state is not CoreState.running
                or self.pending.get(trv) is not pending
            ):
                return
            if pending.cancel is not None:
                pending.cancel()
            pending.cancel = None
            state = self.hass.states.get(trv)
            room = next(
                (room for room in self.store.data.rooms if room.enabled and trv in room.trvs), None
            )
            target = available_temperature(state.attributes.get("temperature")) if state else None
            needs_heat = (
                state is not None
                and state.state == "off"
                and "heat" in (state.attributes.get("hvac_modes") or [])
            )
            if target == pending.target and not needs_heat:
                self._cancel_pending(trv)
                self._clear_problem(trv)
            elif (
                room is None
                or state is None
                or state.state in ("unknown", "unavailable")
                or self.desired(room) != pending.target
                or target
                not in {pending.observed, *(command.target for command in pending.commands)}
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
        await self.engine.async_recalculate(apply_rooms=True)

    def stop(self) -> None:
        if self._timer is not None:
            self._timer()
            self._timer = None
        for trv in tuple(self.pending):
            self._cancel_pending(trv)
