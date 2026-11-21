"""Stored configuration and computed commands; no connection credentials."""

from dataclasses import asdict

from .storage import to_json


async def async_get_config_entry_diagnostics(hass, entry):
    engine = entry.runtime_data
    return {
        "configuration": to_json(engine.store.data),
        "command": asdict(engine.command),
        "last_sent": engine.last_sent.isoformat() if engine.last_sent else None,
        "shadow": engine.store.data.shadow,
        "sync_problems": sorted(engine.rooms.problems),
        "last_commanded": {
            trv: {"target": value[0], "at": value[1].isoformat()}
            for trv, value in engine.rooms.last_commanded.items()
        },
    }
