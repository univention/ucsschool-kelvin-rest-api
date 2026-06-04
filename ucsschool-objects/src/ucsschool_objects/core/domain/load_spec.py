from __future__ import annotations

from dataclasses import dataclass, field, fields


@dataclass(frozen=True)
class LoadSpec:
    includes_set: frozenset[str] = field(default_factory=frozenset)

    def includes(self, attribute: str) -> bool:
        return attribute in self.includes_set

    @classmethod
    def from_attributes(cls, *attributes: str) -> LoadSpec:
        return cls(includes_set=frozenset(attributes))

    @classmethod
    def from_model(cls, model: type) -> "LoadSpec":
        """Return a LoadSpec covering every field of the given domain model.

        Use this when the loaded object serves as a change-detection baseline
        (e.g. with ``track_changes``): unloaded fields would otherwise diff as
        changed against their newly assigned values.
        """
        # Domain models store their fields privately (``_name``) behind public
        # properties; LoadSpec attributes use the public names (see domain_asdict).
        return cls(includes_set=frozenset(f.name.removeprefix("_") for f in fields(model)))
