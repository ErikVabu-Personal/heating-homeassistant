"""Lossless generic migration and whole-house configuration invariants."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from custom_components.central_heating.migration import migrate_store
from custom_components.central_heating.schedule_config import affected_rooms, edit
from custom_components.central_heating.storage import HeatingData, from_json, to_json, validate_data


def legacy():
    return json.loads(
        (Path(__file__).parent / "fixtures/legacy_four_profiles_nine_rooms.json").read_text()
    )


def migrated():
    return from_json(migrate_store(legacy()))


@pytest.mark.parametrize(
    "old,new", [("auto", "schedule"), ("summer", "off"), ("manual", "manual"), ("away", "away")]
)
def test_lossless_four_profiles_nine_rooms_migration(old, new):
    raw = legacy()
    raw["mode"]["value"] = old
    before = deepcopy(raw)
    current = to_json(from_json(migrate_store(raw)))
    assert raw == before
    assert current["mode"] == {"value": new, "until": None}
    assert current["settings"] == raw["settings"] and current["shadow"] == raw["shadow"]
    assert current["overrides"] == raw["overrides"]
    assert current["active_schedule_id"] == "winter"
    schedule = current["schedules"]["winter"]
    assert schedule["name"] == "Winter" and len(schedule["rooms"]) == 9
    assert "profiles" not in current
    for id, room in raw["rooms"].items():
        assert current["rooms"][id] == {
            key: value for key, value in room.items() if key != "profile_id"
        }
        assert schedule["rooms"][id]["days"] == raw["profiles"][room["profile_id"]]["days"]
    assert migrate_store(current) == current
    assert to_json(from_json(current)) == current


def test_room_week_copies_are_independent_and_empty_install_has_winter():
    raw = migrate_store(legacy())
    raw["schedules"]["winter"]["rooms"]["room_0"]["days"]["mon"][0]["target"] = 30
    assert raw["schedules"]["winter"]["rooms"]["room_4"]["days"]["mon"][0]["target"] != 30
    empty = from_json(migrate_store({}))
    assert empty == HeatingData()
    assert to_json(empty)["schedules"] == {"winter": {"name": "Winter", "rooms": {}}}


@pytest.mark.parametrize(
    "broken", ["missing_profile", "missing_day", "bad_target", "duplicate_trv", "unknown_field"]
)
def test_bad_legacy_data_is_not_repaired_or_partly_changed(broken):
    raw = legacy()
    if broken == "missing_profile":
        raw["rooms"]["room_0"]["profile_id"] = "absent"
    if broken == "missing_day":
        del raw["profiles"]["legacy_0"]["days"]["sun"]
    if broken == "bad_target":
        raw["profiles"]["legacy_0"]["days"]["mon"][0]["target"] = 20.25
    if broken == "duplicate_trv":
        raw["rooms"]["room_1"]["trvs"] = raw["rooms"]["room_0"]["trvs"]
    if broken == "unknown_field":
        raw["unexpected"] = True
    before = deepcopy(raw)
    with pytest.raises((ValueError, KeyError)):
        from_json(migrate_store(raw))
    assert raw == before


def test_schedules_default_complete_room_weeks_unique_names_and_atomic_validation():
    data = migrated()
    second, id = edit(data, "schedule/save", {"schedule": {"name": "Autumn"}})
    assert len(second.schedules[1].rooms) == 9
    assert all(
        all(b.target == 18 for b in day.blocks)
        for week in second.schedules[1].rooms
        for day in week.days
    )
    for payload in (
        {"name": " "},
        {"name": " winter "},
        {"name": "Autumn", "rooms": {"missing": {"days": {}}}},
    ):
        with pytest.raises(ValueError):
            edit(second, "schedule/save", {"schedule": payload})
    raw = to_json(data)
    del raw["schedules"]["winter"]["rooms"]["room_0"]
    with pytest.raises(ValueError):
        from_json(raw)
    with pytest.raises(ValueError):
        validate_data(replace(data, schedules=()))
    with pytest.raises(ValueError):
        validate_data(replace(data, active_schedule_id="absent"))


def test_room_create_seeds_each_schedule_from_its_own_source_and_delete_removes_weeks():
    data = migrated()
    data, id = edit(data, "schedule/save", {"schedule": {"name": "Autumn"}})
    changed, id = edit(
        data,
        "room/save",
        {
            "room": {
                "name": "Room J",
                "trvs": ["climate.trv_j"],
                "area_id": None,
                "enabled": True,
                "copy_week_from_room": "room_0",
            }
        },
    )
    for schedule in changed.schedules:
        weeks = {week.room_id: week.days for week in schedule.rooms}
        assert weeks[id] == weeks["room_0"]
    changed, _ = edit(changed, "room/delete", {"room_id": id})
    assert all(
        id not in {week.room_id for week in schedule.rooms} for schedule in changed.schedules
    )
    assert len(changed.rooms) == 9
    with pytest.raises(ValueError):
        edit(
            data,
            "room/save",
            {"room": {"name": "Bad", "trvs": ["climate.new"], "copy_week_from_room": "missing"}},
        )


def test_protected_deletion_activation_and_affected_rooms():
    data = migrated()
    with pytest.raises(ValueError, match="last"):
        edit(data, "schedule/delete", {"schedule_id": "winter"})
    second, key = edit(data, "schedule/save", {"schedule": {"name": "Autumn"}})
    with pytest.raises(ValueError, match="active"):
        edit(second, "schedule/delete", {"schedule_id": "winter"})
    renamed, _ = edit(
        second, "schedule/save", {"schedule": {"id": "winter", "name": "Winter renamed"}}
    )
    assert not affected_rooms(second, renamed)
    activated, _ = edit(second, "schedule/activate", {"schedule_id": key})
    assert affected_rooms(second, activated) == {room.id for room in data.rooms}
    deleted, _ = edit(activated, "schedule/delete", {"schedule_id": "winter"})
    assert deleted.active_schedule_id == key and len(deleted.schedules) == 1


@pytest.mark.parametrize("where", ["schedule", "week"])
def test_unknown_schedule_fields_are_rejected_instead_of_dropped(where):
    raw = to_json(migrated())
    target = (
        raw["schedules"]["winter"]
        if where == "schedule"
        else raw["schedules"]["winter"]["rooms"]["room_0"]
    )
    target["unexpected"] = True
    with pytest.raises(ValueError, match="Unexpected"):
        from_json(raw)
