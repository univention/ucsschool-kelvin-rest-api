from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LoadSpec:
    includes_set: frozenset[str] = field(default_factory=frozenset)

    def includes(self, attribute: str) -> bool:
        return attribute in self.includes_set

    @classmethod
    def from_attributes(cls, *attributes: str) -> "LoadSpec":
        return cls(includes_set=frozenset(attributes))
