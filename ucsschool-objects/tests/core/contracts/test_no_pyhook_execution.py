import builtins

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemorySchoolReader


@pytest.mark.asyncio
async def test_readers_do_not_import_pyhooks(monkeypatch, db_session, school_factory) -> None:
    school = school_factory(name="hook-safe")
    original_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if "pyhook" in name.lower() or "kelvin-hooks" in name.lower():
            raise AssertionError("Corelib must not import PyHook modules")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    reader = SqliteMemorySchoolReader(db_session)
    fetched = await reader.get(school.public_id)
    assert fetched is not None
    assert fetched.name == "hook-safe"
