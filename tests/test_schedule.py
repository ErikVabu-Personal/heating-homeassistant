"""Weekly profile and room invariants use generic, invented records only."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from custom_components.central_heating.schedule import (
    WEEKDAYS,
    Block,
    Day,
    Profile,
    Room,
    resolve_start,
    schedule_at,
    until_next_change,
    validate_day,
    validate_profile,
    validate_profile_deletion,
    validate_rooms,
)


def profile() -> Profile:
    return Profile(
        "Profile A", tuple(Day(day, (Block("00:00", 18), Block("06:30", 21))) for day in WEEKDAYS)
    )


@pytest.mark.parametrize("day", WEEKDAYS)
def test_all_weekdays_validate(day):
    validate_day(Day(day, (Block("00:00", 5), Block("23:55", 30))))


@pytest.mark.parametrize("target", [5 + index / 2 for index in range(51)])
def test_every_target_step_validates(target):
    validate_day(Day("mon", (Block("00:00", target),)))


def test_every_five_minute_start_validates():
    blocks = tuple(Block(f"{minute // 60:02}:{minute % 60:02}", 20) for minute in range(0, 1440, 5))
    validate_day(Day("mon", blocks))


@pytest.mark.parametrize(
    "start",
    [
        "0:00",
        "00:0",
        "24:00",
        "12:60",
        "-1:00",
        "12:00:00",
        " 00:00",
        "00:00 ",
        "aa:bb",
        "00:01",
        "12:34",
        "２３:００",
        None,
    ],
)
def test_invalid_time_format_or_grid_rejected(start):
    with pytest.raises(ValueError):
        validate_day(Day("mon", (Block("00:00", 18), Block(start, 20))))


@pytest.mark.parametrize(
    "blocks",
    [
        (),
        (Block("00:05", 20),),
        (Block("00:00", 20), Block("00:00", 21)),
        (Block("00:00", 20), Block("07:00", 21), Block("06:00", 18)),
    ],
)
def test_day_structure_rejected(blocks):
    with pytest.raises(ValueError):
        validate_day(Day("mon", blocks))


@pytest.mark.parametrize(
    "target", [4.5, 30.5, 20.1, float("nan"), float("inf"), float("-inf"), True, "20", None]
)
def test_invalid_targets_rejected(target):
    with pytest.raises(ValueError):
        validate_day(Day("mon", (Block("00:00", target),)))


@pytest.mark.parametrize("day", ["Monday", "MON", "", "other"])
def test_invalid_weekday_rejected(day):
    with pytest.raises(ValueError):
        validate_day(Day(day, (Block("00:00", 20),)))


def test_profile_accepts_all_days_in_any_order():
    value = profile()
    validate_profile(value)
    validate_profile(replace(value, days=value.days[::-1]))


@pytest.mark.parametrize("variant", ["empty", "missing", "duplicate", "extra", "invalid-day"])
def test_profile_requires_exactly_seven_distinct_valid_days(variant):
    value = profile()
    days = {
        "empty": (),
        "missing": value.days[:-1],
        "duplicate": (*value.days[:-1], value.days[0]),
        "extra": (*value.days, value.days[0]),
        "invalid-day": (*value.days[:-1], replace(value.days[-1], weekday="other")),
    }[variant]
    with pytest.raises(ValueError):
        validate_profile(replace(value, days=days))


def test_profile_checks_every_day():
    value = profile()
    with pytest.raises(ValueError):
        validate_profile(replace(value, days=(*value.days[:-1], Day("sun", ()))))


def test_room_membership_and_deletion():
    value = profile()
    room = Room("Room A", ("climate.trv_a", "climate.trv_b"), value.id)
    validate_rooms((room,), (value,))
    validate_rooms((), (value,))
    validate_profile_deletion(value.id, ())
    with pytest.raises(ValueError, match="in use"):
        validate_profile_deletion(value.id, (room,))
    with pytest.raises(ValueError, match="in use"):
        validate_profile_deletion(value.id, (replace(room, enabled=False),))


@pytest.mark.parametrize(
    "variant",
    [
        "empty",
        "within-room",
        "across-rooms",
        "disabled",
        "missing-profile",
        "duplicate-room-id",
        "duplicate-profile-id",
    ],
)
def test_invalid_rooms_rejected(variant):
    value = profile()
    a = Room("Room A", ("climate.trv_a",), value.id)
    b = Room("Room B", ("climate.trv_b",), value.id)
    rooms, profiles = {
        "empty": ((replace(a, trvs=()),), (value,)),
        "within-room": ((replace(a, trvs=("climate.trv_a", "climate.trv_a")),), (value,)),
        "across-rooms": ((a, replace(b, trvs=a.trvs)), (value,)),
        "disabled": ((a, replace(b, trvs=a.trvs, enabled=False)), (value,)),
        "missing-profile": ((a,), ()),
        "duplicate-room-id": ((a, replace(b, id=a.id)), (value,)),
        "duplicate-profile-id": ((a,), (value, value)),
    }[variant]
    with pytest.raises(ValueError):
        validate_rooms(rooms, profiles)


def test_names_do_not_define_identity():
    first, second = profile(), profile()
    assert first.name == second.name
    assert first.id != second.id
    assert UUID(first.id).version == UUID(second.id).version == 4
    room = Room("Room A", ("climate.trv_a",), first.id)
    assert UUID(room.id).version == 4
    assert replace(first, name="Profile B").id == first.id
    assert replace(room, name="Room B").id == room.id


def test_schedule_records_are_frozen():
    for value, attribute in [
        (profile(), "name"),
        (Day("mon", ()), "weekday"),
        (Block("00:00", 20), "start"),
        (Room("Room A", ("climate.trv_a",), "profile_a"), "name"),
    ]:
        with pytest.raises(FrozenInstanceError):
            setattr(value, attribute, "changed")


def test_nonexistent_start_moves_to_first_valid_minute():
    zone = ZoneInfo("Europe/Berlin")
    for start in ("02:00", "02:30", "02:55"):
        result = resolve_start(date(2026, 3, 29), start, zone)
        assert result.hour == 3 and result.minute == 0
        assert result.astimezone(UTC).hour == 1


def test_ambiguous_start_uses_first_occurrence():
    result = resolve_start(date(2026, 10, 25), "02:30", ZoneInfo("Europe/Berlin"))
    assert result.fold == 0
    assert result.astimezone(UTC).hour == 0
    assert result.utcoffset().total_seconds() == 7200


def weekly(blocks: tuple[Block, ...]) -> Profile:
    return Profile("Profile A", tuple(Day(day, blocks) for day in WEEKDAYS))


@pytest.mark.parametrize(
    "now,current,next_start",
    [
        ("2026-01-05T00:00:00+01:00", "00:00", "2026-01-05T06:30:00+01:00"),
        ("2026-01-05T06:29:59+01:00", "00:00", "2026-01-05T06:30:00+01:00"),
        ("2026-01-05T06:30:00+01:00", "06:30", "2026-01-06T00:00:00+01:00"),
        ("2026-01-05T23:59:59+01:00", "06:30", "2026-01-06T00:00:00+01:00"),
        ("2026-01-11T23:59:59+01:00", "06:30", "2026-01-12T00:00:00+01:00"),
        ("2026-12-31T23:59:59+01:00", "06:30", "2027-01-01T00:00:00+01:00"),
    ],
)
def test_current_next_and_override_expiry(now, current, next_start):
    value = profile()
    now = datetime.fromisoformat(now)
    zone = ZoneInfo("Europe/Berlin")
    result = schedule_at(value, now, zone)
    assert result.current.block.start == current
    assert result.next.at.isoformat() == next_start
    assert result.next.at.astimezone(UTC) > now.astimezone(UTC)
    assert result.until_next_change == until_next_change(value, now, zone) == result.next.at
    assert schedule_at(value, result.next.at, zone).current.block == result.next.block


def test_weekday_targets_and_sunday_to_monday_rollover():
    value = Profile(
        "Profile A",
        tuple(Day(day, (Block("00:00", 18 + index / 2),)) for index, day in enumerate(WEEKDAYS)),
    )
    zone = ZoneInfo("Europe/Berlin")
    result = schedule_at(value, datetime(2026, 1, 11, 23, 59, tzinfo=zone), zone)
    assert result.current.block.target == 21
    assert result.next.block.target == 18
    assert result.next.at.weekday() == 0


def test_timezone_is_explicit_and_datetime_may_use_another_zone():
    zone = ZoneInfo("Europe/Berlin")
    result = schedule_at(profile(), datetime(2026, 1, 5, 5, 30, tzinfo=UTC), zone)
    assert result.current.block.start == "06:30"
    assert result.current.at.utcoffset() == timedelta(hours=1)


def test_naive_datetime_rejected():
    with pytest.raises(ValueError, match="timezone-aware"):
        schedule_at(profile(), datetime(2026, 1, 5), ZoneInfo("Europe/Berlin"))


def test_spring_gap_block_moves_to_next_valid_minute():
    value = weekly((Block("00:00", 18), Block("02:30", 21), Block("04:00", 20)))
    zone = ZoneInfo("Europe/Berlin")
    before = schedule_at(value, datetime(2026, 3, 29, 0, 59, tzinfo=UTC), zone)
    assert before.current.block.start == "00:00"
    assert before.next.at.isoformat() == "2026-03-29T03:00:00+02:00"
    after = schedule_at(value, datetime(2026, 3, 29, 1, 0, tzinfo=UTC), zone)
    assert after.current.block.start == "02:30"
    assert after.next.block.start == "04:00"


def test_autumn_blocks_run_once_at_the_first_occurrence():
    value = weekly((Block("00:00", 18), Block("02:30", 21), Block("03:00", 20)))
    zone = ZoneInfo("Europe/Berlin")
    before = schedule_at(value, datetime(2026, 10, 25, 0, 29, tzinfo=UTC), zone)
    assert before.current.block.start == "00:00"
    assert before.next.at.astimezone(UTC) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    # First occurrence, before and after the clocks fall back, and second occurrence.
    for hour, minute in [(0, 30), (0, 59), (1, 0), (1, 29), (1, 30), (1, 59)]:
        instant = datetime(2026, 10, 25, hour, minute, tzinfo=UTC)
        result = schedule_at(value, instant, zone)
        assert result.current.block.start == "02:30"
        assert result.next.at.astimezone(UTC) == datetime(2026, 10, 25, 2, tzinfo=UTC)
        assert result.next.at.astimezone(UTC) > instant
    fold_one = datetime(2026, 10, 25, 2, 5, tzinfo=zone, fold=1)
    assert schedule_at(value, fold_one, zone).current.block.start == "02:30"


def test_dst_days_have_23_and_25_hours_between_midnight_blocks():
    value = weekly((Block("00:00", 18),))
    zone = ZoneInfo("Europe/Berlin")
    for month, day, hours in [(3, 29, 23), (10, 25, 25)]:
        now = datetime(2026, month, day, tzinfo=zone)
        result = schedule_at(value, now, zone)
        assert result.next.at.astimezone(UTC) - now.astimezone(UTC) == timedelta(hours=hours)


def test_schedule_outputs_are_frozen():
    result = schedule_at(profile(), datetime(2026, 1, 5, tzinfo=UTC), ZoneInfo("UTC"))
    for value, attribute in [(result, "current"), (result.current, "at")]:
        with pytest.raises(FrozenInstanceError):
            setattr(value, attribute, None)


@pytest.mark.parametrize("explicit_three", [False, True])
@pytest.mark.parametrize("query_zone", ["UTC", "Europe/Berlin"])
def test_spring_collision_last_scheduled_block_wins(explicit_three, query_zone):
    blocks = (
        Block("00:00", 18),
        Block("02:00", 19),
        Block("02:30", 20),
        Block("02:55", 21),
    )
    if explicit_three:
        blocks += (Block("03:00", 22),)
    blocks += (Block("04:00", 23),)
    value = weekly(blocks)
    validate_profile(value)  # DST collisions do not invalidate a profile.
    zone = ZoneInfo("Europe/Berlin")
    instant = datetime(2026, 3, 29, 1, tzinfo=UTC)
    before = schedule_at(
        value, (instant - timedelta(seconds=1)).astimezone(ZoneInfo(query_zone)), zone
    )
    assert before.current.block.start == "00:00"
    assert before.next.block.start == ("03:00" if explicit_three else "02:55")
    assert before.next.at.astimezone(UTC) == instant
    assert until_next_change(value, instant - timedelta(seconds=1), zone).astimezone(UTC) == instant
    for after in (instant, instant + timedelta(seconds=1), instant + timedelta(minutes=59)):
        result = schedule_at(value, after.astimezone(ZoneInfo(query_zone)), zone)
        assert result.current.block == before.next.block
        assert result.current.at.astimezone(UTC) == instant
        assert result.next.block.start == "04:00"
        assert result.next.at.astimezone(UTC) == datetime(2026, 3, 29, 2, tzinfo=UTC)


def test_full_missing_hour_of_blocks_and_explicit_boundary():
    blocks = (
        (Block("00:00", 18),)
        + tuple(Block(f"02:{minute:02}", 20) for minute in range(0, 60, 5))
        + (Block("03:00", 22),)
    )
    value = weekly(blocks)
    zone = ZoneInfo("Europe/Berlin")
    result = schedule_at(value, datetime(2026, 3, 29, 1, tzinfo=UTC), zone)
    assert result.current.block == Block("03:00", 22)
    assert result.next.block.start == "00:00"


def test_half_hour_dst_gap_uses_next_valid_minute():
    zone = ZoneInfo("Australia/Lord_Howe")
    shifted = resolve_start(date(2026, 10, 4), "02:15", zone)
    assert shifted.hour == 2 and shifted.minute == 30
    value = weekly((Block("00:00", 18), Block("02:15", 20), Block("02:30", 21)))
    assert schedule_at(value, shifted, zone).current.block.start == "02:30"


def test_override_skips_midnight_and_equal_target_blocks_until_next_change():
    value = weekly((Block("00:00", 18), Block("07:00", 21), Block("18:00", 18), Block("22:00", 18)))
    zone = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 1, 5, 23, tzinfo=zone)
    result = schedule_at(value, now, zone)
    assert result.next.at == datetime(2026, 1, 6, 0, tzinfo=zone)
    assert result.next_change.at == datetime(2026, 1, 6, 7, tzinfo=zone)
    assert result.next_target == 21
    assert until_next_change(value, now, zone) == result.next_change.at
    assert schedule_at(value, result.next_change.at, zone).current.block.target == 21


def test_next_change_searches_across_days_and_week_boundary():
    days = tuple(Day(day, (Block("00:00", 18),)) for day in WEEKDAYS)
    days = (*days[:2], Day("wed", (Block("00:00", 18), Block("07:00", 21))), *days[3:])
    value = Profile("Profile A", days)
    zone = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 1, 11, 23, tzinfo=zone)  # Sunday
    result = schedule_at(value, now, zone)
    assert result.next_change.at == datetime(2026, 1, 14, 7, tzinfo=zone)
    assert result.next_target == 21


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 1, 5, 23, tzinfo=UTC),
        datetime(2026, 3, 28, 23, tzinfo=UTC),
        datetime(2026, 10, 24, 23, tzinfo=UTC),
    ],
)
def test_constant_week_caps_override_at_seven_elapsed_days(now):
    value = weekly((Block("00:00", 18), Block("06:00", 18), Block("23:00", 18)))
    zone = ZoneInfo("Europe/Berlin")
    result = schedule_at(value, now, zone)
    assert result.next_change is None
    assert result.next_target is None
    assert result.until_next_change.astimezone(UTC) == now + timedelta(days=7)
    assert until_next_change(value, now, zone) == result.until_next_change


def test_next_change_ignores_overwritten_dst_collision_target():
    value = weekly((Block("00:00", 18), Block("02:30", 21), Block("03:00", 18), Block("07:00", 22)))
    zone = ZoneInfo("Europe/Berlin")
    result = schedule_at(value, datetime(2026, 3, 29, 0, 59, tzinfo=UTC), zone)
    assert result.next.block.start == "03:00"
    assert result.next_change.block.start == "07:00"
    assert result.next_target == 22


def test_next_change_uses_first_autumn_occurrence():
    value = weekly((Block("00:00", 18), Block("02:30", 21)))
    zone = ZoneInfo("Europe/Berlin")
    result = schedule_at(value, datetime(2026, 10, 25, 0, 29, tzinfo=UTC), zone)
    assert result.next_change.at.astimezone(UTC) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    repeated = schedule_at(value, datetime(2026, 10, 25, 1, 10, tzinfo=UTC), zone)
    assert repeated.next_change.at.isoformat() == "2026-10-26T00:00:00+01:00"


def test_skipped_date_uses_following_days_effective_block():
    zone = ZoneInfo("Pacific/Apia")
    value = Profile(
        "Profile A",
        tuple(Day(day, (Block("00:00", 18 + index / 2),)) for index, day in enumerate(WEEKDAYS)),
    )
    now = datetime(2011, 12, 29, 23, 59, tzinfo=zone)
    result = schedule_at(value, now, zone)
    assert result.current.at.date() == date(2011, 12, 29)
    assert result.next.at.isoformat() == "2011-12-31T00:00:00+14:00"
    assert result.next.block.target == 20.5  # Saturday wins over the skipped Friday.
    assert result.next_change == result.next
    assert schedule_at(value, result.next.at, zone).current.block.target == 20.5


def test_schedule_lookup_rejects_invalid_profile():
    value = replace(profile(), days=profile().days[:-1])
    with pytest.raises(ValueError, match="weekday"):
        schedule_at(value, datetime(2026, 1, 5, tzinfo=UTC), ZoneInfo("UTC"))


def test_nonconstant_week_next_change_survives_a_week_with_extra_dst_hour():
    days = tuple(Day(day, (Block("00:00", 18),)) for day in WEEKDAYS)
    days = (*days[:-1], Day("sun", (Block("00:00", 18), Block("03:00", 21), Block("03:05", 18))))
    value = Profile("Profile A", days)
    zone = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 10, 18, 3, 6, tzinfo=zone)
    result = schedule_at(value, now, zone)
    assert result.next_change.at == datetime(2026, 10, 25, 3, tzinfo=zone)
    assert result.until_next_change.astimezone(UTC) - now.astimezone(UTC) > timedelta(days=7)


def test_next_change_finds_the_week_after_a_dst_gap_hides_this_weeks_change():
    days = tuple(Day(day, (Block("00:00", 18),)) for day in WEEKDAYS)
    days = (*days[:-1], Day("sun", (Block("00:00", 18), Block("02:30", 21), Block("03:00", 18))))
    value = Profile("Profile A", days)
    zone = ZoneInfo("Europe/Berlin")
    now = datetime(2026, 3, 23, 12, tzinfo=zone)
    result = schedule_at(value, now, zone)
    assert result.next_change.at == datetime(2026, 4, 5, 2, 30, tzinfo=zone)
    assert result.next_target == 21
    assert result.until_next_change == result.next_change.at
