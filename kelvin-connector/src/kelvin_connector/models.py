import enum
from dataclasses import dataclass
from enum import auto
from typing import Any


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
