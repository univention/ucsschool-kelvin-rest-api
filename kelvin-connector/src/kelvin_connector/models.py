import enum
from dataclasses import dataclass
from enum import auto
from typing import Any, Union

from pydantic import BaseModel, Extra, Field, root_validator


class UDMPayload(BaseModel):
    dn: str = Field(..., min_length=1)
    objectType: str = Field(..., min_length=1)
    id: str = Field(..., min_length=1)

    class Config:
        extra = Extra.allow


class EmptyDict(BaseModel):
    class Config:
        extra = Extra.forbid


class UDMEventBody(BaseModel):
    old: Union[UDMPayload, EmptyDict]
    new: Union[UDMPayload, EmptyDict]

    @root_validator
    def at_least_one_non_empty(cls, values):
        old, new = values.get("old"), values.get("new")
        if isinstance(old, EmptyDict) and isinstance(new, EmptyDict):
            raise ValueError("at least one of 'old' or 'new' must be non-empty")
        return values


class UDMEventObject(BaseModel):
    publisher_name: str
    ts: str
    realm: str
    topic: str
    body: UDMEventBody
    sequence_number: int
    num_delivered: int


class EventType(enum.Enum):
    CREATE = auto()
    MODIFY = auto()
    DELETE = auto()


@dataclass
class Event:
    timestamp: str
    sequence_number: int
    event_type: EventType
    old: None | dict[str, Any]
    new: None | dict[str, Any]


@dataclass
class UserEvent(Event):
    pass


@dataclass
class GroupEvent(Event):
    pass


@dataclass
class SchoolEvent(Event):
    pass
