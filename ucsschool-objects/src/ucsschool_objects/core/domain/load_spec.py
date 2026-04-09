from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class LoadSpec:
    includes_set: frozenset[str] = field(default_factory=frozenset)

    def includes(self, relation: str) -> bool:
        return relation in self.includes_set

    @classmethod
    def from_relations(cls, *relations: str) -> "LoadSpec":
        return cls(includes_set=frozenset(relations))
