import uuid
from enum import StrEnum
from typing import Iterable, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database_models import GroupDNMapping, SchoolDNMapping, UserDNMapping


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
    ) -> dict[str, uuid.UUID]:
        """
        Returns the corresponding `public_id` for each given DN.

        If a DN is not known, it is not part of the result.
        """
        ...

    async def public_ids_to_dns(
        self, object_type: ObjectType, public_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        """
        Returns the corresponding DN for each given `public_id`.

        If a `public_id` is not known, it is not part of the result.
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


class SQLAlchemyDNIDMapper(DNIDMapper):
    TYPE_TO_MODEL_MAPPING = {
        ObjectType.SCHOOL: SchoolDNMapping,
        ObjectType.GROUP: GroupDNMapping,
        ObjectType.USER: UserDNMapping,
    }

    def __init__(self, session: AsyncSession):
        self._session = session

    async def dns_to_public_ids(
        self, object_type: ObjectType, dns: Iterable[str]
    ) -> dict[str, uuid.UUID]:
        model = self.TYPE_TO_MODEL_MAPPING[object_type]
        result = (
            await self._session.execute(select(model.dn, model.public_id).where(model.dn.in_(dns)))
        ).all()
        return {dn: public_id for dn, public_id in result}

    async def public_ids_to_dns(
        self, object_type: ObjectType, public_ids: Iterable[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        model = self.TYPE_TO_MODEL_MAPPING[object_type]
        result = (
            await self._session.execute(
                select(model.public_id, model.dn).where(model.public_id.in_(public_ids))
            )
        ).all()
        return {dn: public_id for dn, public_id in result}

    async def set_mapping(self, object_type: ObjectType, dn: str, public_id: uuid.UUID | None) -> None:
        model = self.TYPE_TO_MODEL_MAPPING[object_type]
        async with self._session.begin():
            existing_mapping = (
                await self._session.execute(select(model).where(model.dn == dn))
            ).scalar_one_or_none()
            if existing_mapping and public_id is None:
                await self._session.delete(existing_mapping)
            elif existing_mapping is None and public_id:
                model(public_id=public_id, dn=dn)
                self._session.add(model)
            elif existing_mapping and public_id:
                existing_mapping.public_id = public_id
                existing_mapping.dn = dn
                self._session.add(model)
            await self._session.commit()
