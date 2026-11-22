"""Pure, detached conversion of version-1 legacy data to whole-house schedules."""

from copy import deepcopy

from .schedule import Block, Day, Week, validate_week


def migrate_store(raw):
    """Keep settings, room identities/TRVs and overrides; never write or repair bad data."""
    if not isinstance(raw, dict):
        raise ValueError("Invalid heating Store")
    result = deepcopy(raw)
    if "schedules" in result:
        if "profiles" in result:
            raise ValueError("Mixed legacy and schedule Store")
        return result
    if set(result) - {"settings", "mode", "profiles", "rooms", "overrides", "shadow"}:
        raise ValueError("Unexpected legacy Store fields")
    profiles = result.pop("profiles", {})
    for profile in profiles.values():
        validate_week(
            Week(
                profile["name"],
                tuple(
                    Day(day, tuple(Block(**block) for block in blocks))
                    for day, blocks in profile["days"].items()
                ),
            )
        )
    weeks = {}
    for key, room in result.get("rooms", {}).items():
        profile_id = room.pop("profile_id", None)
        if profile_id not in profiles:
            raise ValueError("Legacy room has no valid profile")
        weeks[key] = {"days": deepcopy(profiles[profile_id]["days"])}
    result["schedules"] = {"winter": {"name": "Winter", "rooms": weeks}}
    result["active_schedule_id"] = "winter"
    mode = result.get("mode", {"value": "manual", "until": None})
    mode["value"] = {"auto": "schedule", "summer": "off"}.get(mode["value"], mode["value"])
    result["mode"] = mode
    return result
