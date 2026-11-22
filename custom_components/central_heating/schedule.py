"""Pure weekly week validation and local-wall-clock schedule calculations."""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from uuid import uuid4
from zoneinfo import ZoneInfo

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def new_id() -> str:
    """Names are display-only; generated identities remain independent of them."""
    return uuid4().hex


@dataclass(frozen=True)
class Block:
    start: str
    target: float


@dataclass(frozen=True)
class Day:
    weekday: str
    blocks: tuple[Block, ...]


@dataclass(frozen=True)
class Week:
    name: str
    days: tuple[Day, ...]
    id: str = field(default_factory=new_id)


@dataclass(frozen=True)
class Room:
    name: str
    trvs: tuple[str, ...]
    id: str = field(default_factory=new_id)
    enabled: bool = True
    area_id: str | None = None


@dataclass(frozen=True)
class BlockStart:
    block: Block
    at: datetime


@dataclass(frozen=True)
class ScheduleResult:
    current: BlockStart
    next: BlockStart
    next_change: BlockStart | None
    until_next_change: datetime

    @property
    def next_target(self) -> float | None:
        """A constant week has no next target; its override still has a cap."""
        return self.next_change.block.target if self.next_change is not None else None


def validate_day(day: Day) -> None:
    """Reject invalid data instead of sorting, rounding or partly applying it."""
    if day.weekday not in WEEKDAYS:
        raise ValueError("Invalid weekday")
    if not day.blocks:
        raise ValueError("Each day needs at least one block")
    previous = ""
    for block in day.blocks:
        if not isinstance(block.start, str) or not re.fullmatch(
            r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", block.start
        ):
            raise ValueError("Block start must be HH:MM")
        if int(block.start[-2:]) % 5:
            raise ValueError("Block start must be on the five-minute grid")
        if block.start <= previous:
            raise ValueError("Block starts must be strictly increasing")
        if (
            isinstance(block.target, bool)
            or not isinstance(block.target, (int, float))
            or not isfinite(block.target)
        ):
            raise ValueError("Block target must be finite")
        if not 5 <= block.target <= 30 or block.target * 2 != round(block.target * 2):
            raise ValueError("Block target must be 5–30 in steps of 0.5")
        previous = block.start
    if day.blocks[0].start != "00:00":
        raise ValueError("Each day must start at 00:00")


def validate_week(week: Week) -> None:
    if len(week.days) != 7 or {day.weekday for day in week.days} != set(WEEKDAYS):
        raise ValueError("A week needs each weekday exactly once")
    for day in week.days:
        validate_day(day)


def resolve_start(day: date, start: str, zone: ZoneInfo) -> datetime:
    """Resolve a local minute: first fold, or next valid minute after a DST gap."""
    hour, minute = map(int, start.split(":"))
    local = datetime(day.year, day.month, day.day, hour, minute)
    while True:
        candidate = local.replace(tzinfo=zone, fold=0)
        # A nonexistent local minute does not survive a UTC round trip.
        if candidate.astimezone(UTC).astimezone(zone).replace(tzinfo=None) == local:
            return candidate
        local += timedelta(minutes=1)


def schedule_at(week: Week, now: datetime, zone: ZoneInfo) -> ScheduleResult:
    """Return the active block and strictly next start, comparing absolute instants.

    An aware caller timestamp may use any timezone. Ambiguous starts occur once,
    at fold zero; they are not replayed when the wall clock moves backwards.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Schedule time must be timezone-aware")
    validate_week(week)
    instant = now.astimezone(UTC)
    today = now.astimezone(zone).date()
    days = {day.weekday: day for day in week.days}
    starts: list[BlockStart] = []
    # Cover skipped dates and two weeks of transitions: a spring gap can hide
    # the only distinct target for one week, deferring it to the next week.
    for offset in range(-2, 18):
        day = today + timedelta(days=offset)
        for block in days[WEEKDAYS[day.weekday()]].blocks:
            starts.append(BlockStart(block, resolve_start(day, block.start, zone)))
    active = max(
        start.at.astimezone(UTC) for start in starts if start.at.astimezone(UTC) <= instant
    )
    following = min(
        start.at.astimezone(UTC) for start in starts if start.at.astimezone(UTC) > instant
    )

    def last_start(at: datetime) -> BlockStart:
        # Starts are appended in local date/day order. The last scheduled block
        # wins when a DST gap maps multiple starts onto the same instant.
        return next(start for start in reversed(starts) if start.at.astimezone(UTC) == at)

    current = last_start(active)
    # Collapse coinciding starts before looking for a different target: a block
    # shadowed by a later block at the same instant never becomes effective.
    effective = {start.at.astimezone(UTC): start for start in starts}
    cap = instant + timedelta(days=7)
    changes = [
        (at, start)
        for at, start in effective.items()
        if instant < at and start.block.target != current.block.target
    ]
    change = min(changes, key=lambda pair: pair[0])[1] if changes else None
    expiry = change.at if change is not None else cap.astimezone(zone)
    return ScheduleResult(current, last_start(following), change, expiry)


def until_next_change(week: Week, now: datetime, zone: ZoneInfo) -> datetime:
    """Expire at the next different target, or seven elapsed days for a constant week."""
    return schedule_at(week, now, zone).until_next_change
