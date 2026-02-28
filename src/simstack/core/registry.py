"""Registries for physics modules and solver presets."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import metadata
from typing import Any, Callable, Dict, Iterable, Protocol

from simstack.config import (
    ElasticityParameters,
    ElectricACParameters,
    HeatParameters,
    HeatTransientParameters,
    MagnetostaticParameters,
    PoissonParameters,
    register_physics_parameter_model,
)


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

    def register_physics(
        self,
        name: str,
        factory: Callable[[], PhysicsModule],
        *,
        parameters_model: type[Any] | None = None,
    ) -> None:
        if name in self.physics:
            raise ValueError(f"Physics model already registered: {name}")
        self.physics[name] = factory
        if parameters_model is not None:
            register_physics_parameter_model(name, parameters_model)

    def get_physics(self, name: str) -> Callable[[], PhysicsModule]:
        if name not in self.physics:
            raise KeyError(f"Physics model not found: {name}")
        return self.physics[name]

    def add_solver_preset(self, name: str, options: Dict[str, Any]) -> None:
        self.solver_presets[name] = options


def _entry_points(group: str) -> Iterable[metadata.EntryPoint]:
    all_eps = metadata.entry_points()
    if hasattr(all_eps, "select"):
        return list(all_eps.select(group=group))
    return list(all_eps.get(group, []))


def _load_physics_plugins(registry: Registry) -> None:
    for ep in _entry_points("simstack.physics"):
        plugin = ep.load()
        if not callable(plugin):
            continue
        try:
            plugin(registry)
        except TypeError:
            # Fallback: entry point directly provides a PhysicsModule factory.
            registry.register_physics(ep.name, plugin)


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
    from simstack.fem.physics.heat_transient import HeatTransientModel
    from simstack.fem.physics.elasticity import ElasticityModel
    from simstack.fem.physics.electric_ac import ElectricACModel
    from simstack.fem.physics.magnetostatic import MagnetostaticModel

    DEFAULT_REGISTRY.register_physics("poisson", PoissonModel, parameters_model=PoissonParameters)
    DEFAULT_REGISTRY.register_physics("heat", HeatModel, parameters_model=HeatParameters)
    DEFAULT_REGISTRY.register_physics("heat_transient", HeatTransientModel, parameters_model=HeatTransientParameters)
    DEFAULT_REGISTRY.register_physics("elasticity", ElasticityModel, parameters_model=ElasticityParameters)
    DEFAULT_REGISTRY.register_physics("electric_ac", ElectricACModel, parameters_model=ElectricACParameters)
    DEFAULT_REGISTRY.register_physics("magnetostatic", MagnetostaticModel, parameters_model=MagnetostaticParameters)


_register_defaults()
_load_physics_plugins(DEFAULT_REGISTRY)
