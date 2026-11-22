"""Generic immutable whole-house schedule fixtures."""

from custom_components.central_heating.storage import RoomWeek, Schedule


def seed(week, rooms, *, id="winter"):
    return Schedule(
        "Winter" if id == "winter" else week.name,
        tuple(RoomWeek(room.id, week.days) for room in rooms),
        id=id,
    )
