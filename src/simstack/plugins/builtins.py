"""Built-in plugin registrations backed by current in-repo modules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from simstack.cad.build import (
    get_builder_params_model,
    list_builders,
    build_geometry,
    load_part_catalog,
)
from simstack.core.registry import DEFAULT_REGISTRY
from simstack.plugins.protocols import CadBuildContext
from simstack.plugins.registry import PluginRegistry


@dataclass
class _BuiltinCadPlugin:
    name: str
    params_model: type[Any] | None

    def build(self, params: Dict[str, Any] | None, ctx: CadBuildContext) -> Any:
        geometry = type(
            "GeometryPayload",
            (),
            {
                "builder": self.name,
                "params": params or {},
                "units": None,
                "dimension": 3,
                "coordinate_system": "cartesian",
            },
        )()
        return build_geometry(geometry, out_dir=ctx.out_dir)


@dataclass
class _BuiltinPhysicsPlugin:
    model: str
    params_model: type[Any] | None = None

    def plan(self, ctx: Any) -> Dict[str, Any]:
        return {"model": self.model}


@dataclass
class _BuiltinPartPlugin:
    name: str
    _entry: Dict[str, Any]

    def descriptor(self) -> Dict[str, Any]:
        return dict(self._entry)


def register_builtin_plugins(registry: PluginRegistry) -> None:
    for builder_name in list_builders():
        registry.register_cad_builder(
            _BuiltinCadPlugin(name=builder_name, params_model=get_builder_params_model(builder_name))
        )

    for model in sorted(DEFAULT_REGISTRY.physics.keys()):
        registry.register_physics(_BuiltinPhysicsPlugin(model=model))

    for entry in load_part_catalog():
        name = str(entry.get("name", ""))
        if not name:
            continue
        registry.register_part(_BuiltinPartPlugin(name=name, _entry=entry))
