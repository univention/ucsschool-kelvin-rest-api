import uuid
from enum import StrEnum
from typing import Iterable, Protocol


class ObjectType(StrEnum):
    SCHOOL = "school"
    GROUP = "group"
    USER = "user"


class DNIDMapper(Protocol):
    """
    This protocol allows to map DNs to public ids and vice versa.

    This is relevant, since relationships in the Nubus source database
    are referenced via DNs.

    Since we do not want to use DNs within the school the connector needs to switch
    them out, before creating school objects.
    """

    async def dns_to_public_ids(
        self, object_type: ObjectType, dns: Iterable[str]
    ) -> dict[str, uuid.UUID | None]:
        """
        Returns the corresponding `public_id` for each given DN.

        If a DN is not known, `None` is returned instead.
        """
        ...

    async def public_ids_to_dns(
        self, object_type: ObjectType, public_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, str | None]:
        """
        Returns the corresponding DN for each given `public_id`.

        If a `public_id` is not known, `None` is returned instead.
        """
        ...

    async def set_mapping(self, object_type: ObjectType, dn: str, public_id: uuid.UUID | None) -> None:
        """
        Sets a mapping from a DN to a `public_id`.

        If the public_id is set to `None`, the mapping is deleted.

        Be aware that if a DN->public_id mapping exists and the object referenced
        by that `public_id` is deleted from the database, the mapping is also removed
        automatically.
        """
        ...
