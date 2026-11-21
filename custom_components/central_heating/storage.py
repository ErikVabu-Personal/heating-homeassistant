"""Validated immutable snapshots, serialized updates and HA-managed persistence."""

import asyncio
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from math import isfinite
from typing import TYPE_CHECKING, Any

from .const import DOMAIN
from .schedule import Block, Day, Profile, Room, validate_profile, validate_rooms

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

MODES = ("auto", "away", "summer", "manual")


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


@dataclass(frozen=True)
class HeatingData:
    settings: Settings = Settings()
    mode: Mode = Mode()
    profiles: tuple[Profile, ...] = ()
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
    for profile in data.profiles:
        if not profile.id or not isinstance(profile.name, str):
            raise ValueError("Invalid profile identity")
        validate_profile(profile)
    validate_rooms(data.rooms, data.profiles)
    rooms = {room.id: room for room in data.rooms}
    for room in data.rooms:
        if not room.id or not isinstance(room.name, str) or type(room.enabled) is not bool:
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
        "profiles": {
            profile.id: {
                "name": profile.name,
                "days": {
                    day.weekday: [asdict(block) for block in day.blocks] for day in profile.days
                },
            }
            for profile in data.profiles
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
            }
            for item in data.overrides
        },
        "shadow": data.shadow,
    }


def from_json(raw: dict[str, Any]) -> HeatingData:
    """Decode and validate as one operation; malformed storage is never partly loaded."""
    try:
        if not isinstance(raw, dict) or set(raw) - {
            "settings",
            "mode",
            "profiles",
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
            profiles=tuple(
                Profile(
                    value["name"],
                    tuple(
                        Day(day, tuple(Block(**block) for block in blocks))
                        for day, blocks in value["days"].items()
                    ),
                    id=key,
                )
                for key, value in raw.get("profiles", {}).items()
            ),
            rooms=tuple(
                Room(**{**value, "trvs": tuple(value["trvs"])}, id=key)
                for key, value in raw.get("rooms", {}).items()
            ),
            overrides=tuple(
                Override(
                    key, value["target"], datetime.fromisoformat(value["until"]), value["source"]
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
                if old_major != 1:
                    raise ValueError("Unsupported heating Store version")
                return to_json(from_json(raw))

        self._store = VersionedStore(hass, 1, f"{DOMAIN}.{entry_id}", minor_version=2)
        self._lock = asyncio.Lock()
        self.data = HeatingData()

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
