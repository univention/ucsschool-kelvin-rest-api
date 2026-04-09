from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class UnloadedType:
    """Sentinel value for intentionally unloaded relationships."""


UNLOADED = UnloadedType()


@dataclass(frozen=True)
class Group:
    public_id: UUID
    record_uid: str
    source_uid: str
    name: str
    display_name: dict[str, str]
    has_share: bool
    email: str | None
    school: School | None | UnloadedType = UNLOADED


@dataclass(frozen=True)
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
    groups: tuple[Group, ...] | UnloadedType = UNLOADED
