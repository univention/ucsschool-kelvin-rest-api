"""Internal SQLAlchemy ORM models.

.. warning::
    This module is **internal**.  It is consumed by the SQLAlchemy adapter
    layer (``ucsschool_objects.core.adapters.sqlalchemy``) and is **not** part
    of the public API.  Its contents may change between releases without
    deprecation notice.  Use the domain dataclasses exposed via the top-level
    ``ucsschool_objects`` package instead.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    BOOLEAN,
    DATE,
    INTEGER,
    JSON,
    UUID,
    Boolean,
    ForeignKey,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.engine import Connection
    from sqlalchemy.orm import Mapper


class Base(DeclarativeBase):
    ...


##########################
##### School objects #####
##########################


class School(Base):
    __tablename__ = "school"
    __table_args__ = (UniqueConstraint("record_uid", "source_uid", name="uq_school_record_source_uid"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        unique=True,
        index=True,
        default=uuid.uuid4,
        nullable=False,
        info={"udm_attr": "univentionObjectIdentifier"},
    )
    record_uid: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        info={
            "doc": (
                "The ``record_uid`` is the ID for record of this school of an external source,"
                " which is itself identified by the source_uid"
            ),
            "udm_attr": "ucsschoolRecordUID",
        },
    )
    source_uid: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        info={
            "doc": (
                "The ``source_uid`` is the ID of the source of this school,"
                " which could be an external database."
            ),
            "udm_attr": "ucsschoolSourceUID",
        },
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", info={"udm_attr": "displayName"}
    )
    educational_servers: Mapped[list[str]] = mapped_column(JSON(), nullable=False, default=list)
    administrative_servers: Mapped[list[str]] = mapped_column(JSON(), nullable=False, default=list)
    class_share_file_server: Mapped[str | None] = mapped_column(String(255), nullable=True)
    home_share_file_server: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Group(Base):
    __tablename__ = "group"
    __table_args__ = (UniqueConstraint("record_uid", "source_uid", name="uq_group_record_source_uid"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID, unique=True, index=True, default=uuid.uuid4, nullable=False
    )
    record_uid: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        info={
            "doc": (
                "The ``record_uid`` is the ID for record of this group of an external source,"
                " which is itself identified by the ``source_uid``"
            ),
            "udm_attr": "ucsschoolRecordUID",
        },
    )
    source_uid: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        info={
            "doc": (
                "The ``source_uid`` is the ID of the source of this group,"
                " which could be an external database."
            ),
            "udm_attr": "ucsschoolSourceUID",
        },
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, info={"udm_attr": "name"}
    )
    display_name: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", info={"udm_attr": "displayName"}
    )
    has_share: Mapped[bool] = mapped_column(BOOLEAN, nullable=False, default=False)
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, info={"udm_attr": "mailAddress"}
    )

    roles: Mapped[list["Role"]] = relationship("Role", secondary="group_role_association", lazy="raise")

    school_id: Mapped[int] = mapped_column(ForeignKey("school.id", ondelete="NO ACTION"), nullable=False)
    school: Mapped["School"] = relationship("School", lazy="selectin")

    members: Mapped[list["SchoolMembership"]] = relationship(
        "SchoolMembership", secondary="group_member_association", lazy="raise", back_populates="groups"
    )

    allowed_email_senders_users: Mapped[list["User"]] = relationship(
        secondary="group_user_email_senders_association",
        lazy="raise",
    )

    allowed_email_senders_groups: Mapped[list["Group"]] = relationship(
        secondary="group_group_email_senders_association",
        lazy="raise",
        primaryjoin="Group.id == group_group_email_senders_association.c.parent_group_id",
        secondaryjoin="Group.id == group_group_email_senders_association.c.child_group_id",
    )

    member_roles: Mapped[list["Role"]] = relationship(
        "Role", secondary="group_member_role_association", lazy="raise"
    )


class User(Base):
    __tablename__ = "user"
    __table_args__ = (UniqueConstraint("record_uid", "source_uid", name="uq_user_record_source_uid"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID,
        unique=True,
        index=True,
        default=uuid.uuid4,
        nullable=False,
        info={"udm_attr": "univentionObjectIdentifier"},
    )
    record_uid: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        info={
            "doc": (
                "The ``record_uid`` is the ID for record of this user of an external source"
                " which is itself identified by the source_uid"
            ),
            "udm_attr": "ucsschoolRecordUID",
        },
    )
    source_uid: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        info={
            "doc": (
                "The ``source_uid`` is the ID of the source of this user,"
                " which could be an external database."
            ),
            "udm_attr": "ucsschoolSourceUID",
        },
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, info={"udm_attr": "username"}
    )
    firstname: Mapped[str] = mapped_column(String(255), nullable=False, info={"udm_attr": "firstname"})
    lastname: Mapped[str] = mapped_column(String(255), nullable=False, info={"udm_attr": "lastname"})
    email: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True, info={"udm_attr": "mailPrimaryAddress"}
    )
    birthday: Mapped[date | None] = mapped_column(DATE, nullable=True, info={"udm_attr": "birthday"})
    expiration_date: Mapped[date | None] = mapped_column(
        DATE, nullable=True, info={"udm_attr": "userexpiry"}
    )
    active: Mapped[bool] = mapped_column(
        BOOLEAN, nullable=False, default=True, info={"udm_attr": "disabled"}
    )

    legal_wards: Mapped[list["User"]] = relationship(
        secondary="legal_guardian_association",
        lazy="raise",
        primaryjoin="User.id == legal_guardian_association.c.legal_guardian_id",
        secondaryjoin="User.id == legal_guardian_association.c.legal_ward_id",
        back_populates="legal_guardians",
    )
    legal_guardians: Mapped[list["User"]] = relationship(
        secondary="legal_guardian_association",
        lazy="raise",
        primaryjoin="User.id == legal_guardian_association.c.legal_ward_id",
        secondaryjoin="User.id == legal_guardian_association.c.legal_guardian_id",
        back_populates="legal_wards",
    )

    school_memberships: Mapped[list["SchoolMembership"]] = relationship(
        "SchoolMembership", lazy="raise", back_populates="user"
    )


class Role(Base):
    __tablename__ = "role"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID, unique=True, index=True, default=uuid.uuid4, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    display_name: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)


#############################
##### Auxiliary objects #####
#############################


class SchoolMembership(Base):
    __tablename__ = "school_membership"
    __table_args__ = (UniqueConstraint("user_id", "school_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # This is a column for putting a unique constraint on it.
    # In combination with a hook that sets it to the user_id,
    # if is_primary=True, we can enforce at most one primary school per user.
    primary_user_constraint: Mapped[int | None] = mapped_column(
        INTEGER,
        nullable=True,
        unique=True,
        info={
            "doc": "This is an internally managed field only, "
            "to ensure at most one primary school per user."
        },
    )

    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    user: Mapped["User"] = relationship("User", lazy="selectin")

    school_id: Mapped[int] = mapped_column(ForeignKey("school.id", ondelete="CASCADE"), nullable=False)
    school: Mapped["School"] = relationship("School", lazy="selectin")

    groups: Mapped[list["Group"]] = relationship(
        "Group", secondary="group_member_association", lazy="raise", back_populates="members"
    )

    roles: Mapped[list["Role"]] = relationship(
        "Role", secondary="school_membership_role_association", lazy="raise"
    )


@event.listens_for(SchoolMembership, "before_insert")
@event.listens_for(SchoolMembership, "before_update")
def sync_primary_user_constraint(
    mapper: Mapper[SchoolMembership], connection: Connection, target: SchoolMembership
) -> None:
    target.primary_user_constraint = target.user_id if target.is_primary else None


###############################
##### Association objects #####
###############################


class GroupMemberAssociation(Base):
    __tablename__ = "group_member_association"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("group.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    school_membership_id: Mapped[int] = mapped_column(
        ForeignKey("school_membership.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )


class GroupMemberRoleAssociation(Base):
    __tablename__ = "group_member_role_association"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("group.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )


class GroupRoleAssociation(Base):
    __tablename__ = "group_role_association"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("group.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )


class SchoolMembershipRoleAssociation(Base):
    __tablename__ = "school_membership_role_association"

    school_membership_id: Mapped[int] = mapped_column(
        ForeignKey("school_membership.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    role_id: Mapped[int] = mapped_column(
        ForeignKey("role.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )


class GroupUserEmailSendersAssociation(Base):
    __tablename__ = "group_user_email_senders_association"

    group_id: Mapped[int] = mapped_column(
        ForeignKey("group.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False, primary_key=True
    )


class GroupGroupEmailSendersAssociation(Base):
    __tablename__ = "group_group_email_senders_association"

    parent_group_id: Mapped[int] = mapped_column(
        ForeignKey("group.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )
    child_group_id: Mapped[int] = mapped_column(
        ForeignKey("group.id", ondelete="CASCADE"), primary_key=True, nullable=False
    )


class LegalGuardianAssociation(Base):
    __tablename__ = "legal_guardian_association"

    legal_guardian_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="cascade"), primary_key=True, nullable=False
    )
    legal_ward_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="cascade"), primary_key=True, nullable=False
    )


#############################
##### DN mapping tables #####
#############################


class SchoolDNMapping(Base):
    __tablename__ = "school_dn_public_id_mapping"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("school.public_id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )
    dn: Mapped[str] = mapped_column(String(4096), nullable=False, index=True, unique=True)


class GroupDNMapping(Base):
    __tablename__ = "group_dn_public_id_mapping"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("group.public_id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )
    dn: Mapped[str] = mapped_column(String(4096), nullable=False, index=True, unique=True)


class UserDNMapping(Base):
    __tablename__ = "user_dn_public_id_mapping"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.public_id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )
    dn: Mapped[str] = mapped_column(String(4096), nullable=False, index=True, unique=True)
