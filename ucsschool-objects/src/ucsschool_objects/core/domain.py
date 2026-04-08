from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Final
from uuid import UUID


class UnloadedType:
    """Sentinel used for optional relationship fields that were intentionally not loaded."""


UNLOADED: Final[UnloadedType] = UnloadedType()


@dataclass(frozen=True, slots=True)
class LoadSpec:
    """Controls which relationship fields should be loaded by a reader."""

    fields: frozenset[str] = frozenset()

    @classmethod
    def only(cls, *fields: str) -> LoadSpec:
        return cls(fields=frozenset(fields))

    def includes(self, field: str) -> bool:
        return field in self.fields


@dataclass(frozen=True, slots=True)
class School:
    public_id: UUID
    record_uid: str
    source_uid: str
    name: str
    display_name: dict[str, str]
    educational_servers: tuple[str, ...]
    administrative_servers: tuple[str, ...]
    class_share_file_server: str | None
    home_share_file_server: str | None


@dataclass(frozen=True, slots=True)
class Group:
    public_id: UUID
    record_uid: str
    source_uid: str
    name: str
    display_name: dict[str, str]
    has_share: bool
    email: str | None
    school: School | None | UnloadedType = UNLOADED


@dataclass(frozen=True, slots=True)
class User:
    public_id: UUID
    record_uid: str
    source_uid: str
    name: str
    firstname: str
    lastname: str
    email: str | None
    birthday: date | None
    expiration_date: date | None
    active: bool
    school: School | None | UnloadedType = UNLOADED
    groups: tuple[Group, ...] | UnloadedType = field(default=UNLOADED)
