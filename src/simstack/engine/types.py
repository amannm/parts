"""Typed DAG runtime primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Sequence


@dataclass
class NodeResult:
    state_updates: Dict[str, Any] = field(default_factory=dict)
    cache_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeExecutionRecord:
    id: str
    kind: str
    fingerprint: str
    status: str
    cache_hit: bool
    duration_ms: float
    deps: List[str] = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineContext:
    config: Any
    ir: Any
    repo_root: Path
    out_root: Path
    comm: Any
    rank: int
    state: Dict[str, Any] = field(default_factory=dict)


ExecuteFn = Callable[[EngineContext], NodeResult]
HydrateFn = Callable[[EngineContext, Dict[str, Any]], Dict[str, Any]]


@dataclass
class NodeSpec:
    id: str
    kind: str
    deps: Sequence[str]
    version: str
    config_slice: Dict[str, Any]
    execute: ExecuteFn
    hydrate: HydrateFn | None = None
    cacheable: bool = True

    def hydrate_updates(self, ctx: EngineContext, payload: Dict[str, Any]) -> Dict[str, Any]:
        if self.hydrate is None:
            return dict(payload)
        return self.hydrate(ctx, payload)
