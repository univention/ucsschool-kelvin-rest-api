import uuid
from collections.abc import Iterable
from enum import StrEnum
from typing import Protocol


class ObjectType(StrEnum):
    SCHOOL = "school"
    GROUP = "group"
    USER = "user"


class DNIDMapper(Protocol):
    """Maps LDAP DNs to public UUIDs and vice versa."""

    async def dns_to_public_ids(
        self, object_type: ObjectType, dns: Iterable[str]
    ) -> dict[str, uuid.UUID]:  # pragma: no cover
        ...

    async def public_ids_to_dns(
        self, object_type: ObjectType, public_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, str]:  # pragma: no cover
        ...

    async def set_mapping(
        self, object_type: ObjectType, dn: str, public_id: uuid.UUID | None
    ) -> None:  # pragma: no cover
        ...
