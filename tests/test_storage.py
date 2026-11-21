"""Storage codecs and validation use invented, generic records only."""

import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from custom_components.central_heating.schedule import WEEKDAYS, Block, Day, Profile, Room
from custom_components.central_heating.storage import (
    HeatingData,
    Mode,
    Override,
    from_json,
    to_json,
    validate_data,
)


def example():
    profile = Profile("Profile A", tuple(Day(day, (Block("00:00", 18),)) for day in WEEKDAYS))
    room = Room("Room A", ("climate.trv_a",), profile.id)
    override = Override(room.id, 21, datetime(2027, 1, 1, tzinfo=UTC), "card")
    return HeatingData(profiles=(profile,), rooms=(room,), overrides=(override,))


def test_new_entry_is_manual_and_shadow():
    data = from_json({})
    assert data.mode == Mode("manual") and data.shadow is True


def test_json_roundtrip_and_detached_containers():
    data = example()
    serialized = to_json(data)
    assert from_json(json.loads(json.dumps(serialized))) == data
    serialized["rooms"][data.rooms[0].id]["trvs"].append("climate.trv_b")
    assert data.rooms[0].trvs == ("climate.trv_a",)


@pytest.mark.parametrize(
    "field,value",
    [
        ("hysteresis", 0),
        ("hysteresis", 1.1),
        ("hysteresis", 0.15),
        ("frost_temperature", 4.5),
        ("frost_temperature", 18.5),
        ("frost_temperature", 16.2),
        ("away_temperature", 4.9),
        ("away_temperature", 30.1),
        ("away_temperature", float("nan")),
        ("override_default", "other"),
        ("override_minutes", 0),
        ("override_minutes", 1.5),
        ("sync_rooms_on_knob_change", 1),
        ("retry_seconds", 0),
        ("retry_seconds", float("inf")),
        ("hysteresis", True),
        ("frost_temperature", "16"),
    ],
)
def test_invalid_settings_rejected(field, value):
    data = HeatingData()
    with pytest.raises(ValueError):
        validate_data(replace(data, settings=replace(data.settings, **{field: value})))


@pytest.mark.parametrize("hysteresis", [0.1, 0.3, 1.0])
@pytest.mark.parametrize("frost", [5, 16, 18])
@pytest.mark.parametrize("away", [5, 15.25, 30])
def test_settings_boundaries_and_float_steps(hysteresis, frost, away):
    data = HeatingData()
    validate_data(
        replace(
            data,
            settings=replace(
                data.settings, hysteresis=hysteresis, frost_temperature=frost, away_temperature=away
            ),
        )
    )


@pytest.mark.parametrize(
    "trv", ["sensor.trv_a", "climate.", "climate.trv_a/other", "climate.TRV_A", None]
)
def test_trv_id_domain_and_syntax(trv):
    data = example()
    with pytest.raises(ValueError):
        validate_data(replace(data, rooms=(replace(data.rooms[0], trvs=(trv,)),)))


def test_used_profile_cannot_be_removed():
    with pytest.raises(ValueError):
        validate_data(replace(example(), profiles=()))


def test_trv_cannot_be_assigned_to_two_rooms():
    data = example()
    with pytest.raises(ValueError):
        validate_data(replace(data, rooms=(*data.rooms, replace(data.rooms[0], id="room_b"))))


@pytest.mark.parametrize(
    "mode",
    [
        Mode("other"),
        Mode("auto", datetime(2027, 1, 1, tzinfo=UTC)),
        Mode("away", datetime(2027, 1, 1)),
    ],
)
def test_invalid_mode_or_expiration_rejected(mode):
    with pytest.raises(ValueError):
        validate_data(replace(HeatingData(), mode=mode))


@pytest.mark.parametrize(
    "raw",
    [
        {"unexpected": True},
        {"mode": None},
        {"profiles": []},
        {"rooms": {"room_a": {}}},
        {"shadow": 1},
        {"settings": {"other": 1}},
    ],
)
def test_malformed_json_rejected(raw):
    with pytest.raises(ValueError):
        from_json(raw)
