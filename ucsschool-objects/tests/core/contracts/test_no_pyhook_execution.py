import builtins
from typing import TYPE_CHECKING, Any

import pytest
from ucsschool_objects.core.adapters.sqlite_memory.readers import SqliteMemorySchoolReader

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from tests.test_types import SchoolFactory


@pytest.mark.asyncio
async def test_readers_do_not_import_pyhooks(
    monkeypatch: pytest.MonkeyPatch,
    db_session: Session,
    school_factory: SchoolFactory,
) -> None:
    school = school_factory(name="hook-safe")
    original_import = builtins.__import__

    def guarded_import(
        name: str,
        globals: Any = None,
        locals: Any = None,
        fromlist: tuple[str, ...] = (),
        level: int = 0,
    ) -> Any:
        if "pyhook" in name.lower() or "kelvin-hooks" in name.lower():
            raise AssertionError("Corelib must not import PyHook modules")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    reader = SqliteMemorySchoolReader(db_session)
    fetched = await reader.get(school.public_id)
    assert fetched is not None
    assert fetched.name == "hook-safe"
