"""Exercise HA's real migration callback using the representative generic Store."""

import json

import pytest

from custom_components.central_heating.storage import STORE_MINOR, HeatingStore, to_json
from tests.test_schedule_model import legacy

pytestmark = pytest.mark.integration


async def test_ha_store_minor_migration_preserves_nine_room_fixture(hass, hass_storage):
    key = "central_heating.generic_entry"
    raw = legacy()
    hass_storage[key] = {"version": 1, "minor_version": 3, "key": key, "data": raw}
    store = HeatingStore(hass, "generic_entry")
    await store.async_load()
    current = to_json(store.data)
    assert current["overrides"] == raw["overrides"]
    assert current["settings"] == raw["settings"]
    assert hass_storage[key]["minor_version"] == STORE_MINOR
    assert hass_storage[key]["data"] == current
    for room_id, room in raw["rooms"].items():
        assert (
            current["schedules"]["winter"]["rooms"][room_id]["days"]
            == raw["profiles"][room["profile_id"]]["days"]
        )
    reloaded = HeatingStore(hass, "generic_entry")
    await reloaded.async_load()
    assert to_json(reloaded.data) == current


async def test_read_only_old_real_file_converts_only_in_memory(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    path = tmp_path / ".storage" / "central_heating.generic_entry"
    text = json.dumps({"version": 1, "minor_version": 3, "data": legacy()})
    await hass.async_add_executor_job(lambda: path.parent.mkdir())
    await hass.async_add_executor_job(path.write_text, text)
    before = await hass.async_add_executor_job(path.stat)
    data = await HeatingStore.async_read_only(hass, "generic_entry")
    assert len(data.rooms) == 9 and len(data.schedules) == 1
    assert await hass.async_add_executor_job(path.read_text) == text
    assert (await hass.async_add_executor_job(path.stat)).st_mtime_ns == before.st_mtime_ns


async def test_native_migration_rejects_future_minor_without_save(hass, hass_storage):
    key = "central_heating.generic_entry"
    hass_storage[key] = {
        "version": 1,
        "minor_version": STORE_MINOR + 1,
        "key": key,
        "data": legacy(),
    }
    before = json.dumps(hass_storage[key], sort_keys=True)
    store = HeatingStore(hass, "generic_entry")
    with pytest.raises(ValueError, match="Unsupported"):
        await store.async_load()
    assert json.dumps(hass_storage[key], sort_keys=True) == before
