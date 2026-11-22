"""Exercise HA's real migration callback using the representative generic Store."""

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

import pytest

from custom_components.central_heating.storage import STORE_MINOR, HeatingStore, to_json
from tests.test_schedule_model import legacy

pytestmark = pytest.mark.integration


async def test_ha_store_minor_migration_preserves_nine_room_fixture(hass, hass_storage, tmp_path):
    key = "central_heating.generic_entry"
    raw = legacy()
    hass_storage[key] = {"version": 1, "minor_version": 3, "key": key, "data": raw}
    hass.config.config_dir = str(tmp_path)
    path = tmp_path / ".storage" / key
    original = json.dumps(hass_storage[key], indent=3).encode() + b"\n"

    def write_original():
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(original)

    await hass.async_add_executor_job(write_original)
    store = HeatingStore(hass, "generic_entry")
    await store.async_load()
    assert (
        await hass.async_add_executor_job(Path(str(path) + ".pre_schedules").read_bytes) == original
    )
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


async def seed_original(hass, hass_storage, tmp_path, raw):
    hass.config.config_dir = str(tmp_path)
    key = "central_heating.generic_entry"
    hass_storage[key] = {"version": 1, "minor_version": 3, "key": key, "data": raw}
    original = json.dumps(hass_storage[key], indent=3, ensure_ascii=False).encode() + b"\n"
    path = tmp_path / ".storage" / key

    def write():
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(original)

    await hass.async_add_executor_job(write)
    return path, original


async def test_unused_profile_warning_and_original_bytes_backup(
    hass, hass_storage, tmp_path, caplog
):
    raw = legacy()
    raw["profiles"]["unused_generic"] = deepcopy(next(iter(raw["profiles"].values())))
    raw["profiles"]["unused_generic"]["name"] = "Unused holiday plan"
    path, original = await seed_original(hass, hass_storage, tmp_path, raw)
    store = HeatingStore(hass, "generic_entry")
    await store.async_load()
    assert (
        await hass.async_add_executor_job(Path(str(path) + ".pre_schedules").read_bytes) == original
    )
    assert "Unused holiday plan (unused_generic)" in caplog.text
    assert store._store._atomic_writes
    # Loading again cannot replace the original backup with the new model.
    await HeatingStore(hass, "generic_entry").async_load()
    assert (
        await hass.async_add_executor_job(Path(str(path) + ".pre_schedules").read_bytes) == original
    )


async def test_backup_failure_aborts_before_original_store_rewrite(hass, hass_storage, tmp_path):
    from homeassistant.util.file import WriteError

    path, original = await seed_original(hass, hass_storage, tmp_path, legacy())
    before = deepcopy(hass_storage)
    with patch(
        "homeassistant.util.file.write_utf8_file_atomic", side_effect=WriteError("disk full")
    ) as write:
        with pytest.raises(
            ValueError, match="Cannot back up original heating Store; schedules migration stopped"
        ):
            await HeatingStore(hass, "generic_entry").async_load()
    assert write.call_args.kwargs == {"private": True, "mode": "wb"}
    assert hass_storage == before
    assert await hass.async_add_executor_job(path.read_bytes) == original
    assert not await hass.async_add_executor_job(Path(str(path) + ".pre_schedules").exists)


async def test_different_backup_is_never_overwritten(hass, hass_storage, tmp_path):
    path, original = await seed_original(hass, hass_storage, tmp_path, legacy())
    backup = Path(str(path) + ".pre_schedules")
    await hass.async_add_executor_job(backup.write_bytes, b"earlier backup")
    with pytest.raises(ValueError, match="Cannot back up original"):
        await HeatingStore(hass, "generic_entry").async_load()
    assert await hass.async_add_executor_job(backup.read_bytes) == b"earlier backup"
    assert await hass.async_add_executor_job(path.read_bytes) == original


async def test_missing_store_creates_no_migration_backup(hass, tmp_path):
    hass.config.config_dir = str(tmp_path)
    await HeatingStore(hass, "missing_entry").async_load()
    assert not await hass.async_add_executor_job(
        (tmp_path / ".storage" / "central_heating.missing_entry.pre_schedules").exists
    )


async def test_invalid_legacy_store_does_not_create_backup_or_rewrite(hass, hass_storage, tmp_path):
    raw = legacy()
    next(iter(raw["rooms"].values()))["profile_id"] = "absent"
    path, original = await seed_original(hass, hass_storage, tmp_path, raw)
    before = deepcopy(hass_storage)
    with pytest.raises(ValueError, match="no valid profile"):
        await HeatingStore(hass, "generic_entry").async_load()
    assert hass_storage == before
    assert await hass.async_add_executor_job(path.read_bytes) == original
    assert not await hass.async_add_executor_job(Path(str(path) + ".pre_schedules").exists)
