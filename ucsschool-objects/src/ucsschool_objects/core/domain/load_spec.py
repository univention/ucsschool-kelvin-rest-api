from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING

from ucsschool_objects.core.domain.models import get_properties

if TYPE_CHECKING:
    from ucsschool_objects.core.domain.models import DomainObjectType


@dataclass(frozen=True)
class LoadSpec:
    includes_set: frozenset[str] = field(default_factory=frozenset)

    def includes(self, attribute: str) -> bool:
        return attribute in self.includes_set

    @classmethod
    def from_attributes(cls, *attributes: str) -> LoadSpec:
        return cls(includes_set=frozenset(attributes))

    @classmethod
    @lru_cache(maxsize=None)
    def from_model(cls, model: DomainObjectType) -> "LoadSpec":
        """Return a LoadSpec covering every field of the given domain model.

        Use this when the loaded object serves as a change-detection baseline
        (e.g. with ``track_changes``): unloaded fields would otherwise diff as
        changed against their newly assigned values.

        NOTE The cache size is set to unlimited, but the type limits the number
        of distinct models (=the 5 SerializableDomainObject types) that can be cached.
        """
        return cls(includes_set=frozenset(get_properties(model)))
