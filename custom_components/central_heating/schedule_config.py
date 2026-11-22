"""Atomic whole-house schedule edits, separate from HA control side effects."""

from uuid import uuid4

from .storage import active_schedule, default_days, from_json, to_json


def resolve_schedule(data, name_or_id):
    matches = [item for item in data.schedules if item.id == name_or_id]
    if not matches:
        matches = [item for item in data.schedules if item.name == name_or_id]
    if not matches:
        raise ValueError("Unknown schedule")
    return matches[0].id


def affected_rooms(before, after):
    if before.active_schedule_id != after.active_schedule_id:
        return {room.id for room in after.rooms}
    old = {week.room_id: week.days for week in active_schedule(before).rooms}
    return {
        week.room_id for week in active_schedule(after).rooms if old.get(week.room_id) != week.days
    }


def edit(data, command, msg):
    """Return a fully validated candidate plus saved identity. Never mutate the input."""
    raw = to_json(data)
    saved_id = None
    if command == "schedule/save":
        value = msg["schedule"]
        saved_id = value.get("id")
        if saved_id is not None and saved_id not in raw["schedules"]:
            raise ValueError("Unknown schedule")
        saved_id = saved_id or uuid4().hex
        baseline = raw["schedules"].get(
            saved_id,
            {
                "rooms": {
                    room.id: {
                        "days": {
                            day.weekday: [
                                {"start": block.start, "target": block.target}
                                for block in day.blocks
                            ]
                            for day in default_days()
                        }
                    }
                    for room in data.rooms
                }
            },
        )
        baseline["name"] = value["name"]
        baseline["rooms"].update(value.get("rooms", {}))
        raw["schedules"][saved_id] = baseline
    elif command == "schedule/activate":
        raw["active_schedule_id"] = resolve_schedule(data, msg["schedule_id"])
    elif command == "schedule/delete":
        key = msg["schedule_id"]
        if key not in raw["schedules"]:
            raise ValueError("Unknown schedule")
        if len(raw["schedules"]) == 1:
            raise ValueError("The last schedule cannot be deleted")
        if key == data.active_schedule_id:
            raise ValueError("The active schedule cannot be deleted")
        del raw["schedules"][key]
    elif command == "room/save":
        value = dict(msg["room"])
        saved_id = value.pop("id", None)
        source = value.pop("copy_week_from_room", None)
        if saved_id is not None:
            if saved_id not in raw["rooms"]:
                raise ValueError("Unknown room")
            if source is not None:
                raise ValueError("Copying weeks is only supported when creating a room")
        else:
            saved_id = uuid4().hex
            if source is not None and source not in raw["rooms"]:
                raise ValueError("Unknown room to copy weeks from")
            for schedule in raw["schedules"].values():
                schedule["rooms"][saved_id] = (
                    schedule["rooms"][source]
                    if source
                    else {
                        "days": {
                            day.weekday: [
                                {"start": block.start, "target": block.target}
                                for block in day.blocks
                            ]
                            for day in default_days()
                        }
                    }
                )
        raw["rooms"][saved_id] = value
    elif command == "room/delete":
        key = msg["room_id"]
        if key not in raw["rooms"]:
            raise ValueError("Unknown room")
        del raw["rooms"][key]
        raw["overrides"].pop(key, None)
        for schedule in raw["schedules"].values():
            del schedule["rooms"][key]
    elif command == "settings/save":
        if "settings" not in msg and "shadow" not in msg:
            raise ValueError("Provide settings or shadow")
        raw["settings"].update(msg.get("settings", {}))
        if "shadow" in msg:
            raw["shadow"] = msg["shadow"]
    else:
        raise ValueError("Unknown configuration command")
    return from_json(raw), saved_id
