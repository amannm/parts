"""Registries for physics modules and solver presets."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Protocol


class PhysicsModule(Protocol):
    def declare_fields(self, config: Dict[str, Any]) -> list[Dict[str, Any]]: ...
    def build_spaces(self, mesh: Any, field_spec: list[Dict[str, Any]], config: Dict[str, Any]) -> Any: ...
    def build_coefficients(self, mesh: Any, cell_tags: Any, matdb: Any, config: Dict[str, Any]) -> Any: ...
    def build_bcs(self, V: Any, facet_tags: Any, config: Dict[str, Any]) -> Any: ...
    def build_forms(self, spaces: Any, coeffs: Any, measures: Any, config: Dict[str, Any]) -> Any: ...
    def outputs(self, fields: Any, coeffs: Any, config: Dict[str, Any]) -> list[Dict[str, Any]]: ...


@dataclass
class Registry:
    physics: Dict[str, Callable[[], PhysicsModule]] = field(default_factory=dict)
    solver_presets: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def register_physics(self, name: str, factory: Callable[[], PhysicsModule]) -> None:
        if name in self.physics:
            raise ValueError(f"Physics model already registered: {name}")
        self.physics[name] = factory

    def get_physics(self, name: str) -> Callable[[], PhysicsModule]:
        if name not in self.physics:
            raise KeyError(f"Physics model not found: {name}")
        return self.physics[name]

    def add_solver_preset(self, name: str, options: Dict[str, Any]) -> None:
        self.solver_presets[name] = options


DEFAULT_REGISTRY = Registry(
    solver_presets={
        "linear_default": {
            "ksp_type": "cg",
            "pc_type": "hypre",
        }
    }
)


def _register_defaults() -> None:
    from simstack.fem.physics.poisson import PoissonModel
    from simstack.fem.physics.heat import HeatModel
    from simstack.fem.physics.elasticity import ElasticityModel

    DEFAULT_REGISTRY.register_physics("poisson", PoissonModel)
    DEFAULT_REGISTRY.register_physics("heat", HeatModel)
    DEFAULT_REGISTRY.register_physics("elasticity", ElasticityModel)


_register_defaults()
