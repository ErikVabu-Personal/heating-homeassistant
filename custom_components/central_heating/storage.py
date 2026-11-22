"""Validated immutable snapshots, serialized updates and HA-managed persistence."""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .const import DOMAIN
from .schedule import Block, Day, Room, Week, new_id, validate_week

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

STORE_MINOR = 4
MODES = ("schedule", "away", "off", "manual")
MODE_ALIASES = {"auto": "schedule", "summer": "off"}
MODE_INPUTS = (*MODES, *MODE_ALIASES)


def canonical_mode(value: str) -> str:
    return MODE_ALIASES.get(value, value)


@dataclass(frozen=True)
class RoomWeek:
    room_id: str
    days: tuple[Day, ...]


@dataclass(frozen=True)
class Schedule:
    name: str
    rooms: tuple[RoomWeek, ...] = ()
    id: str = field(default_factory=new_id)


def default_days() -> tuple[Day, ...]:
    from .schedule import WEEKDAYS

    return tuple(Day(day, (Block("00:00", 18),)) for day in WEEKDAYS)


def active_schedule(data):
    return next(item for item in data.schedules if item.id == data.active_schedule_id)


def room_week(data, room_id):
    return next(item for item in active_schedule(data).rooms if item.room_id == room_id)


def seed_room(data, room, copy_from=None):
    if copy_from is not None and not any(item.id == copy_from for item in data.rooms):
        raise ValueError("Unknown room to copy weeks from")
    schedules = tuple(
        replace(
            schedule,
            rooms=(
                *schedule.rooms,
                RoomWeek(
                    room.id,
                    next(item.days for item in schedule.rooms if item.room_id == copy_from)
                    if copy_from is not None
                    else default_days(),
                ),
            ),
        )
        for schedule in data.schedules
    )
    return replace(data, rooms=(*data.rooms, room), schedules=schedules)


@dataclass(frozen=True)
class Settings:
    frost_temperature: float = 16.0
    hysteresis: float = 0.3
    away_temperature: float = 15.0
    override_default: str = "next_block"
    override_minutes: int = 120
    sync_rooms_on_knob_change: bool = True
    retry_seconds: float = 300


@dataclass(frozen=True)
class Mode:
    value: str = "manual"
    until: datetime | None = None


@dataclass(frozen=True)
class Override:
    room_id: str
    target: float
    until: datetime
    source: str
    kind: str = "duration"


@dataclass(frozen=True)
class HeatingData:
    settings: Settings = Settings()
    mode: Mode = Mode()
    schedules: tuple[Schedule, ...] = (Schedule("Winter", id="winter"),)
    active_schedule_id: str = "winter"
    rooms: tuple[Room, ...] = ()
    overrides: tuple[Override, ...] = ()
    shadow: bool = True


def bounded(value: Any, low: float, high: float, step: float | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("Expected a finite number")
    if not low <= value <= high:
        raise ValueError("Value outside allowed range")
    if step is not None and abs(value / step - round(value / step)) > 1e-8:
        raise ValueError("Value is not on the allowed step")


def aware(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Expected a timezone-aware timestamp")


def validate_data(data: HeatingData) -> None:
    settings = data.settings
    bounded(settings.hysteresis, 0.1, 1.0, 0.1)
    bounded(settings.frost_temperature, 5, 18, 0.5)
    bounded(settings.away_temperature, 5, 30, 0.5)
    if settings.override_default not in ("next_block", "duration"):
        raise ValueError("Invalid default override kind")
    if type(settings.override_minutes) is not int or not 1 <= settings.override_minutes <= 10080:
        raise ValueError("Override minutes must be an integer from 1 to 10080")
    if type(settings.sync_rooms_on_knob_change) is not bool or type(data.shadow) is not bool:
        raise ValueError("Expected a boolean")
    if (
        isinstance(settings.retry_seconds, bool)
        or not isinstance(settings.retry_seconds, (int, float))
        or not isfinite(settings.retry_seconds)
        or settings.retry_seconds <= 0
    ):
        raise ValueError("Retry interval must be positive and finite")
    if data.mode.value not in MODES or (data.mode.until is not None and data.mode.value != "away"):
        raise ValueError("Invalid mode or mode expiration")
    if data.mode.until is not None:
        aware(data.mode.until)
    if not data.schedules or data.active_schedule_id not in {item.id for item in data.schedules}:
        raise ValueError("An active schedule is required")
    if len({item.id for item in data.schedules}) != len(data.schedules):
        raise ValueError("Schedule IDs must be unique")
    names = []
    room_ids = {room.id for room in data.rooms}
    if len(room_ids) != len(data.rooms):
        raise ValueError("Room IDs must be unique")
    for schedule in data.schedules:
        if (
            not isinstance(schedule.id, str)
            or not schedule.id
            or not isinstance(schedule.name, str)
            or not schedule.name.strip()
        ):
            raise ValueError("Schedule names must be non-empty")
        if any(
            schedule.name.strip().casefold() == other.id.casefold()
            for other in data.schedules
            if other.id != schedule.id
        ):
            raise ValueError("Schedule name cannot equal another schedule's id")
        names.append(schedule.name.strip().casefold())
        if (
            len(schedule.rooms) != len(room_ids)
            or {week.room_id for week in schedule.rooms} != room_ids
        ):
            raise ValueError("Every schedule needs exactly one week for every room")
        for week in schedule.rooms:
            validate_week(Week("Room week", week.days))
    if len(set(names)) != len(names):
        raise ValueError("Schedule names must be unique")
    assigned = set()
    for room in data.rooms:
        if (
            not room.trvs
            or len(set(room.trvs)) != len(room.trvs)
            or assigned.intersection(room.trvs)
        ):
            raise ValueError("Each room needs distinct physical thermostats")
        assigned.update(room.trvs)
    rooms = {room.id: room for room in data.rooms}
    for room in data.rooms:
        if (
            not isinstance(room.id, str)
            or not room.id
            or not isinstance(room.name, str)
            or type(room.enabled) is not bool
        ):
            raise ValueError("Invalid room")
        if room.area_id is not None and not isinstance(room.area_id, str):
            raise ValueError("Invalid room area")
        for trv in room.trvs:
            if not isinstance(trv, str) or not re.fullmatch(r"climate\.[a-z0-9_]+", trv):
                raise ValueError("TRVs must be climate entity IDs")
    if len({override.room_id for override in data.overrides}) != len(data.overrides):
        raise ValueError("Only one override per room")
    for override in data.overrides:
        if override.room_id not in rooms or not isinstance(override.source, str):
            raise ValueError("Invalid override room or source")
        if override.kind not in ("next_block", "duration"):
            raise ValueError("Invalid override kind")
        bounded(override.target, 5, 30, 0.5)
        aware(override.until)


def to_json(data: HeatingData) -> dict[str, Any]:
    """Produce a detached JSON object in the design's version-1 format."""
    validate_data(data)
    return {
        "settings": asdict(data.settings),
        "mode": {
            "value": data.mode.value,
            "until": data.mode.until.isoformat() if data.mode.until else None,
        },
        "active_schedule_id": data.active_schedule_id,
        "schedules": {
            schedule.id: {
                "name": schedule.name,
                "rooms": {
                    week.room_id: {
                        "days": {
                            day.weekday: [asdict(block) for block in day.blocks]
                            for day in week.days
                        }
                    }
                    for week in schedule.rooms
                },
            }
            for schedule in data.schedules
        },
        "rooms": {
            room.id: {
                key: list(value) if key == "trvs" else value
                for key, value in asdict(room).items()
                if key != "id"
            }
            for room in data.rooms
        },
        "overrides": {
            item.room_id: {
                "target": item.target,
                "until": item.until.isoformat(),
                "source": item.source,
                "kind": item.kind,
            }
            for item in data.overrides
        },
        "shadow": data.shadow,
    }


def _decode_schedule(key, value):
    if set(value) != {"name", "rooms"}:
        raise ValueError("Unexpected schedule fields")
    weeks = []
    for room_id, week in value["rooms"].items():
        if set(week) != {"days"}:
            raise ValueError("Unexpected room-week fields")
        weeks.append(
            RoomWeek(
                room_id,
                tuple(
                    Day(day, tuple(Block(**block) for block in blocks))
                    for day, blocks in week["days"].items()
                ),
            )
        )
    return Schedule(value["name"], tuple(weeks), id=key)


def from_json(raw: dict[str, Any]) -> HeatingData:
    """Decode and validate as one operation; malformed storage is never partly loaded."""
    try:
        if not isinstance(raw, dict) or set(raw) - {
            "settings",
            "mode",
            "schedules",
            "active_schedule_id",
            "rooms",
            "overrides",
            "shadow",
        }:
            raise ValueError("Unexpected storage fields")
        mode = raw.get("mode", {"value": "manual", "until": None})
        if set(mode) != {"value", "until"}:
            raise ValueError("Invalid mode fields")
        data = HeatingData(
            settings=Settings(**raw.get("settings", {})),
            mode=Mode(
                mode["value"],
                datetime.fromisoformat(mode["until"]) if mode["until"] is not None else None,
            ),
            schedules=tuple(
                _decode_schedule(key, value)
                for key, value in raw.get(
                    "schedules", {"winter": {"name": "Winter", "rooms": {}}}
                ).items()
            ),
            active_schedule_id=raw.get("active_schedule_id", "winter"),
            rooms=tuple(
                Room(**{**value, "trvs": tuple(value["trvs"])}, id=key)
                for key, value in raw.get("rooms", {}).items()
            ),
            overrides=tuple(
                Override(
                    key,
                    value["target"],
                    datetime.fromisoformat(value["until"]),
                    value["source"],
                    value.get("kind", "duration"),
                )
                for key, value in raw.get("overrides", {}).items()
            ),
            shadow=raw.get("shadow", True),
        )
        validate_data(data)
        return data
    except (KeyError, TypeError, AttributeError, OverflowError) as exc:
        raise ValueError("Invalid heating data") from exc


class HeatingStore:
    """Serialize validated updates. HA logs disk errors; memory still advances."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        from homeassistant.helpers.storage import Store

        class VersionedStore(Store):
            async def _async_migrate_func(self, old_major, old_minor, raw):
                if old_major != 1 or old_minor > STORE_MINOR:
                    raise ValueError("Unsupported heating Store version")
                from .migration import migrate_store

                migrated = to_json(from_json(migrate_store(raw)))
                if "schedules" not in raw:
                    from homeassistant.util.file import WriteError, write_utf8_file_atomic

                    def backup():
                        path = Path(self.path)
                        original = path.read_bytes()
                        if json.loads(original)["data"] != raw:
                            raise ValueError("Store changed before migration backup")
                        destination = path.with_name(path.name + ".pre_schedules")
                        if destination.exists():
                            if destination.read_bytes() != original:
                                raise ValueError("A different pre-schedules backup already exists")
                            return
                        write_utf8_file_atomic(str(destination), original, private=True, mode="wb")

                    try:
                        await hass.async_add_executor_job(backup)
                    except (OSError, ValueError, WriteError) as exc:
                        raise ValueError(
                            "Cannot back up original heating Store; schedules migration stopped"
                        ) from exc
                    used = {room.get("profile_id") for room in raw.get("rooms", {}).values()}
                    dropped = [
                        f"{profile['name']} ({key})"
                        for key, profile in raw.get("profiles", {}).items()
                        if key not in used
                    ]
                    if dropped:
                        _LOGGER.warning(
                            "Unused profiles omitted from schedules: %s. Originals retained in %s.pre_schedules",
                            ", ".join(dropped),
                            self.path,
                        )
                return migrated

        self._store = VersionedStore(
            hass, 1, f"{DOMAIN}.{entry_id}", minor_version=STORE_MINOR, atomic_writes=True
        )
        self._lock = asyncio.Lock()
        self.data = HeatingData()

    @staticmethod
    async def async_read_only(hass: HomeAssistant, entry_id: str) -> HeatingData:
        """Read ownership without Store migration, caching, or delayed disk writes."""

        def read():
            path = Path(hass.config.path(".storage", f"{DOMAIN}.{entry_id}"))
            try:
                envelope = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return HeatingData()
            if envelope.get("version") != 1 or envelope.get("minor_version", 1) > STORE_MINOR:
                raise ValueError("Unsupported heating Store version")
            from .migration import migrate_store

            return from_json(migrate_store(envelope["data"]))

        return await hass.async_add_executor_job(read)

    async def async_remove(self) -> None:
        await self._store.async_remove()

    async def async_load(self) -> None:
        raw = await self._store.async_load()
        if raw is not None:
            self.data = from_json(raw)

    async def async_update(self, update: Callable[[HeatingData], HeatingData]) -> HeatingData:
        async with self._lock:
            candidate = update(self.data)
            payload = to_json(candidate)
            # Round-tripping also detaches containers accidentally supplied as lists.
            candidate = from_json(payload)
            await self._store.async_save(payload)
            self.data = candidate
            return candidate

    async def async_settings(self, **changes: Any) -> HeatingData:
        return await self.async_update(
            lambda data: replace(data, settings=replace(data.settings, **changes))
        )
