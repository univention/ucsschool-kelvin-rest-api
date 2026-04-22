import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    ...


class SchoolDNMapping(Base):
    __tablename__ = "school_dn_public_id_mapping"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("school.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )
    dn: Mapped[str] = mapped_column(String(4096), nullable=False, index=True, unique=True)


class GroupDNMapping(Base):
    __tablename__ = "group_dn_public_id_mapping"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("group.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )
    dn: Mapped[str] = mapped_column(String(4096), nullable=False, index=True, unique=True)


class UserDNMapping(Base):
    __tablename__ = "user_dn_public_id_mapping"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True, unique=True
    )
    dn: Mapped[str] = mapped_column(String(4096), nullable=False, index=True, unique=True)
