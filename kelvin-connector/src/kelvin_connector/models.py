import enum
from dataclasses import dataclass
from enum import auto
from typing import Any

from pydantic import BaseModel


class UDMEventBody(BaseModel):
    old: None | dict[str, Any]
    new: None | dict[str, Any]


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
