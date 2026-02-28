"""Stage graph execution primitives for SimStack."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Sequence

from simstack.config import SimStackConfig
from simstack.core.provenance import stable_hash


@dataclass
class StageRecord:
    name: str
    deps: List[str]
    fingerprint: str
    status: str
    outputs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RunContext:
    config: SimStackConfig
    repo_root: Any
    out_root: Any
    comm: Any
    rank: int
    state: Dict[str, Any] = field(default_factory=dict)
    records: List[StageRecord] = field(default_factory=list)

    def set(self, key: str, value: Any) -> None:
        self.state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.state.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self.state:
            raise KeyError(f"Missing stage state value: {key}")
        return self.state[key]


class Stage(ABC):
    name: str
    deps: Sequence[str] = ()

    @abstractmethod
    def fingerprint_payload(self, ctx: RunContext) -> Dict[str, Any]:
        """Return a deterministic payload used to fingerprint this stage."""

    def fingerprint(self, ctx: RunContext) -> str:
        return stable_hash(self.fingerprint_payload(ctx))

    @abstractmethod
    def run(self, ctx: RunContext) -> None:
        """Execute the stage and mutate context state."""

    def outputs(self, ctx: RunContext) -> Dict[str, Any]:
        """Return small, JSON-serializable stage metadata."""
        return {}


class StagePipeline:
    def __init__(self, stages: Iterable[Stage]) -> None:
        self._stages = list(stages)
        if not self._stages:
            raise ValueError("Stage pipeline must include at least one stage")
        self._by_name = self._index_stages(self._stages)
        self._ordered = self._toposort()

    def stage_names(self) -> List[str]:
        return [stage.name for stage in self._ordered]

    def run(self, ctx: RunContext) -> List[StageRecord]:
        records: List[StageRecord] = []
        for stage in self._ordered:
            fingerprint = stage.fingerprint(ctx)
            record = StageRecord(
                name=stage.name,
                deps=list(stage.deps),
                fingerprint=fingerprint,
                status="ok",
                outputs={},
            )
            try:
                stage.run(ctx)
                record.outputs = stage.outputs(ctx)
            except Exception:
                record.status = "failed"
                records.append(record)
                ctx.records = records
                raise
            records.append(record)

        ctx.records = records
        return records

    @staticmethod
    def _index_stages(stages: Sequence[Stage]) -> Dict[str, Stage]:
        by_name: Dict[str, Stage] = {}
        for stage in stages:
            if stage.name in by_name:
                raise ValueError(f"Duplicate stage name: {stage.name}")
            by_name[stage.name] = stage
        return by_name

    def _toposort(self) -> List[Stage]:
        visited: set[str] = set()
        visiting: set[str] = set()
        ordered: List[Stage] = []

        def visit(name: str) -> None:
            if name in visited:
                return
            if name in visiting:
                raise ValueError(f"Cycle detected in stage dependencies at '{name}'")
            if name not in self._by_name:
                raise ValueError(f"Unknown stage dependency: {name}")

            visiting.add(name)
            stage = self._by_name[name]
            for dep in stage.deps:
                visit(dep)
            visiting.remove(name)

            visited.add(name)
            ordered.append(stage)

        for stage in self._stages:
            visit(stage.name)

        return ordered
