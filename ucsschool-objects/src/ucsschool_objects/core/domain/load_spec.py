from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ucsschool_objects.core.domain.models import get_properties

if TYPE_CHECKING:
    from ucsschool_objects.core.domain.models import SerializableDomainObject


@dataclass(frozen=True)
class LoadSpec:
    includes_set: frozenset[str] = field(default_factory=frozenset)

    def includes(self, attribute: str) -> bool:
        return attribute in self.includes_set

    @classmethod
    def from_attributes(cls, *attributes: str) -> LoadSpec:
        return cls(includes_set=frozenset(attributes))

    @classmethod
    def from_model(cls, model: type[SerializableDomainObject]) -> "LoadSpec":
        """Return a LoadSpec covering every field of the given domain model.

        Use this when the loaded object serves as a change-detection baseline
        (e.g. with ``track_changes``): unloaded fields would otherwise diff as
        changed against their newly assigned values.
        """
        # get_properties already maps private field names (``_name``) to the
        # public property names that LoadSpec attributes use.
        return cls(includes_set=frozenset(get_properties(model)))
