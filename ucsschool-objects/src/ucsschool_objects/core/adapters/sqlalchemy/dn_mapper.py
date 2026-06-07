import uuid
from typing import TYPE_CHECKING, Iterable, cast

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from ucsschool_objects.core.domain.ports.dn_mapper import DNIDMapper, ObjectType
from ucsschool_objects.database_models import GroupDNMapping, SchoolDNMapping, UserDNMapping

if TYPE_CHECKING:  # pragma: no cover
    from ucsschool_objects.core.domain.ports.unit_of_work import KelvinStorageSession


_DNMappingModel = type[SchoolDNMapping] | type[GroupDNMapping] | type[UserDNMapping]


class SQLAlchemyDNIDMapper:
    TYPE_TO_MODEL_MAPPING: dict[ObjectType, _DNMappingModel] = {
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
        return {public_id: dn for public_id, dn in result}

    async def set_mapping(self, object_type: ObjectType, dn: str, public_id: uuid.UUID | None) -> None:
        model = self.TYPE_TO_MODEL_MAPPING[object_type]
        if public_id is None:
            await self._session.execute(delete(model).where(model.dn == dn))
            return
        # The mapping is a bijection: setting (dn, public_id) must displace
        # both any row holding the dn and any row holding the public_id — an
        # object rename keeps its public_id but changes its dn.
        await self._session.execute(
            delete(model).where(or_(model.dn == dn, model.public_id == public_id))
        )
        self._session.add(model(public_id=public_id, dn=dn))


def sqlalchemy_mapper_factory(storage: "KelvinStorageSession") -> DNIDMapper:
    from ucsschool_objects.core.adapters.sqlalchemy.session import KelvinSqlAlchemySession

    return SQLAlchemyDNIDMapper(cast(KelvinSqlAlchemySession, storage).session)
