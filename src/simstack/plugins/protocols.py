"""Plugin protocols and context objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Protocol

from pydantic import BaseModel


@dataclass
class CadBuildContext:
    out_dir: Path
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SolvePlanContext:
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TagRuleContext:
    metadata: Dict[str, Any] = field(default_factory=dict)


class CadBuilderPlugin(Protocol):
    name: str
    params_model: type[BaseModel] | None

    def build(self, params: BaseModel | Dict[str, Any] | None, ctx: CadBuildContext) -> Any: ...


class PhysicsPlugin(Protocol):
    model: str
    params_model: type[BaseModel] | None

    def plan(self, ctx: SolvePlanContext) -> Any: ...


class TagRulePlugin(Protocol):
    rule_type: str
    params_model: type[BaseModel] | None

    def select(self, entities: Any, params: BaseModel | Dict[str, Any] | None, ctx: TagRuleContext) -> Any: ...


class PostprocessorPlugin(Protocol):
    name: str

    def run(self, payload: Dict[str, Any]) -> Dict[str, Any] | None: ...


class PartPlugin(Protocol):
    name: str

    def descriptor(self) -> Dict[str, Any]: ...
