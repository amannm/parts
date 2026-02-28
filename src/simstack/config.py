"""Configuration schema and loader for SimStack."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, Dict, List, Literal, Optional

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
    model_validator,
)


class BCSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["dirichlet", "neumann", "robin"]
    tag: str
    value: Any = None
    component: Optional[int] = None
    alpha: Optional[float] = None
    params: Dict[str, Any] = Field(default_factory=dict)


class BCsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: List[BCSpec] = Field(default_factory=list)


class TimeParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t0: float | None = None
    start: float | None = None
    dt: float | None = None
    default_dt: float | None = None
    steps: int | None = None
    num_steps: int | None = None
    t_end: float | None = None
    end: float | None = None
    max_steps: int | None = None
    initial: float | None = None
    T0: float | None = None

    @model_validator(mode="after")
    def _validate_dt(self) -> "TimeParameters":
        dt = self.dt if self.dt is not None else self.default_dt
        if dt is not None and dt <= 0:
            raise ValueError("Time step dt must be positive")
        return self


class TargetSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    tag: str
    temperature: float
    mode: Literal["avg", "min", "max"] = "avg"
    direction: Literal["above", "below"] = "above"


class PhaseChangeParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latent_heat: float = 0.0
    delta_T: float | None = None
    mushy_delta: float | None = None
    transition_temp: float = 373.15


class PoissonParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree: int = 1
    kappa: float = 1.0
    source: float = 0.0


class HeatParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree: int = 1
    kappa: float = 1.0
    source: float = 0.0


class HeatTransientParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree: int = 1
    kappa: float = 1.0
    rho: float = 1.0
    cp: float = 1.0
    source: float = 0.0
    initial: float | None = None
    T0: float | None = None
    time: TimeParameters | None = None
    phase_change: PhaseChangeParameters | None = None
    targets: List[TargetSpec] = Field(default_factory=list)
    bcs: List[BCSpec] | None = None

    @field_validator("targets", mode="before")
    @classmethod
    def _normalize_targets(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, dict):
            return [value]
        return value


class ElectricACParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree: int = 1
    sigma: float | None = None
    conductivity: float | None = None
    source: float = 0.0
    include_joule_heat: bool = True
    joule_scale: float = 1.0
    derived: List[str] = Field(default_factory=list)
    bcs: List[BCSpec] | None = None


class MagnetostaticTorqueParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str
    axis: List[float] | None = None
    origin: List[float] | None = None


class MagnetostaticParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree: int = 1
    mu0: float | None = None
    mu_r: float | None = None
    mu: float | None = None
    current_density: float | List[float] | None = None
    J: float | List[float] | None = None
    magnetization: float | List[float] | None = None
    M: float | List[float] | None = None
    include_B: bool = True
    include_H: bool = True
    derived: List[str] = Field(default_factory=list)
    torque: MagnetostaticTorqueParameters | None = None


class ElasticityParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    degree: int = 1
    lambda_: float | None = Field(default=None, alias="lambda")
    mu: float | None = None
    E: float | None = None
    nu: float | None = None
    body_force: float | List[float] | None = None
    derived: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_lame(self) -> "ElasticityParameters":
        has_lame = self.lambda_ is not None and self.mu is not None
        has_enu = self.E is not None and self.nu is not None
        if not (has_lame or has_enu):
            raise ValueError("Elasticity requires either (lambda, mu) or (E, nu)")
        return self


class ElectroThermalParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    electric: ElectricACParameters = Field(default_factory=ElectricACParameters)
    heat: HeatTransientParameters = Field(default_factory=HeatTransientParameters)
    time: TimeParameters | None = None
    phase_change: PhaseChangeParameters | None = None
    targets: List[TargetSpec] = Field(default_factory=list)

    @field_validator("targets", mode="before")
    @classmethod
    def _normalize_targets(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, dict):
            return [value]
        return value


_PHYSICS_PARAMETER_MODELS: Dict[str, type[BaseModel]] = {}


def register_physics_parameter_model(model_name: str, params_model: type[BaseModel] | None) -> None:
    if params_model is None:
        _PHYSICS_PARAMETER_MODELS.pop(model_name, None)
        return
    _PHYSICS_PARAMETER_MODELS[model_name] = params_model


def get_physics_parameter_model(model_name: str) -> type[BaseModel] | None:
    return _PHYSICS_PARAMETER_MODELS.get(model_name)


class GeometryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    builder: str
    params: Dict[str, Any] = Field(default_factory=dict)
    units: Optional[str] = None

    @model_validator(mode="after")
    def _validate_builder_params(self) -> "GeometryConfig":
        try:
            from simstack.cad.build import get_builder_params_model
        except Exception:
            return self

        model_cls = get_builder_params_model(self.builder)
        if model_cls is None:
            return self

        validated = model_cls.model_validate(self.params)
        self.params = validated.model_dump(mode="json", by_alias=True, exclude_none=True)
        return self


class TagRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    rule: str
    params: Dict[str, Any] = Field(default_factory=dict)


class TagsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facets: List[TagRule] = Field(default_factory=list)
    cells: List[TagRule] = Field(default_factory=list)
    id_overrides: Dict[str, int] = Field(default_factory=dict)


class MeshingQAConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_quality: Optional[float] = None
    quality_bins: int = 10
    require_all_facets_tagged: bool = True
    allow_overlaps: bool = False


class MeshingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_size: Optional[float] = None
    curvature_refine: bool = True
    distance_refine: List[Dict[str, Any]] = Field(default_factory=list)
    boundary_layers: List[Dict[str, Any]] = Field(default_factory=list)
    gmsh_options: Dict[str, Any] = Field(default_factory=dict)
    qa: MeshingQAConfig = Field(default_factory=MeshingQAConfig)


class MaterialsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by_tag: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class _PhysicsConfigBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    parameters: Any = Field(default_factory=dict)

    def parameters_dict(self) -> Dict[str, Any]:
        raw = self.parameters
        if isinstance(raw, BaseModel):
            return raw.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(raw, dict):
            return raw
        raise TypeError("physics.parameters must be a dict or pydantic model")


class PoissonPhysicsConfig(_PhysicsConfigBase):
    model: Literal["poisson"]
    parameters: PoissonParameters = Field(default_factory=PoissonParameters)


class HeatPhysicsConfig(_PhysicsConfigBase):
    model: Literal["heat"]
    parameters: HeatParameters = Field(default_factory=HeatParameters)


class HeatTransientPhysicsConfig(_PhysicsConfigBase):
    model: Literal["heat_transient"]
    parameters: HeatTransientParameters = Field(default_factory=HeatTransientParameters)


class ElasticityPhysicsConfig(_PhysicsConfigBase):
    model: Literal["elasticity"]
    parameters: ElasticityParameters


class ElectricACPhysicsConfig(_PhysicsConfigBase):
    model: Literal["electric_ac"]
    parameters: ElectricACParameters = Field(default_factory=ElectricACParameters)


class MagnetostaticPhysicsConfig(_PhysicsConfigBase):
    model: Literal["magnetostatic"]
    parameters: MagnetostaticParameters = Field(default_factory=MagnetostaticParameters)


class ElectroThermalPhysicsConfig(_PhysicsConfigBase):
    model: Literal["electro_thermal"]
    parameters: ElectroThermalParameters = Field(default_factory=ElectroThermalParameters)


BuiltinPhysicsConfig = Annotated[
    PoissonPhysicsConfig
    | HeatPhysicsConfig
    | HeatTransientPhysicsConfig
    | ElasticityPhysicsConfig
    | ElectricACPhysicsConfig
    | MagnetostaticPhysicsConfig
    | ElectroThermalPhysicsConfig,
    Field(discriminator="model"),
]


_BUILTIN_PHYSICS_MODELS = {
    "poisson",
    "heat",
    "heat_transient",
    "elasticity",
    "electric_ac",
    "magnetostatic",
    "electro_thermal",
}
_BUILTIN_PHYSICS_ADAPTER = TypeAdapter(BuiltinPhysicsConfig)


class PluginPhysicsConfig(_PhysicsConfigBase):
    model: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_plugin_parameters(self) -> "PluginPhysicsConfig":
        params_model = get_physics_parameter_model(self.model)
        if params_model is not None and self.model not in _BUILTIN_PHYSICS_MODELS:
            validated = params_model.model_validate(self.parameters)
            self.parameters = validated.model_dump(mode="json", by_alias=True, exclude_none=True)
        return self


class PhysicsConfig(BaseModel):
    """Physics config wrapper around discriminated builtin configs + plugin fallback."""

    model_config = ConfigDict(extra="forbid")

    spec: BuiltinPhysicsConfig | PluginPhysicsConfig

    @model_validator(mode="before")
    @classmethod
    def _coerce_spec(cls, value: Any) -> Any:
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            raise TypeError("physics config must be an object")
        if "spec" in value:
            return value

        model_name = value.get("model")
        if not isinstance(model_name, str) or not model_name:
            raise ValueError("physics.model must be a non-empty string")

        if model_name in _BUILTIN_PHYSICS_MODELS:
            spec = _BUILTIN_PHYSICS_ADAPTER.validate_python(value)
        else:
            spec = PluginPhysicsConfig.model_validate(value)

        return {"spec": spec}

    @property
    def model(self) -> str:
        return self.spec.model

    @property
    def parameters(self) -> Any:
        return self.spec.parameters

    def parameters_dict(self) -> Dict[str, Any]:
        return self.spec.parameters_dict()

    def model_dump_external(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "parameters": self.parameters_dict(),
        }


class SolverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: str = "linear_default"
    options: Dict[str, Any] = Field(default_factory=dict)


class OutputsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    directory: str = "out"
    format: Literal["vtx", "xdmf", "both"] = "vtx"
    write_mesh: bool = True
    write_reports: bool = True
    reuse: bool = True
    write_tag_fields: bool = True
    write_boundary_mesh: bool = True
    write_paraview_state: bool = True
    paraview_state_name: str = "latest.pvsm"


class SimStackConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry: GeometryConfig
    tags: TagsConfig = Field(default_factory=TagsConfig)
    meshing: MeshingConfig = Field(default_factory=MeshingConfig)
    materials: MaterialsConfig = Field(default_factory=MaterialsConfig)
    physics: PhysicsConfig
    bcs: BCsConfig = Field(default_factory=BCsConfig)
    solver: SolverConfig = Field(default_factory=SolverConfig)
    outputs: OutputsConfig = Field(default_factory=OutputsConfig)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SweepParameterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | List[str]
    values: List[Any] = Field(default_factory=list)
    name: Optional[str] = None
    labels: Optional[List[str]] = None
    transform: Optional[Literal["deg2rad", "rad2deg"]] = None
    scale: Optional[float] = None
    offset: Optional[float] = None
    fmt: Optional[str] = None

    @field_validator("values")
    @classmethod
    def _validate_values(cls, value: List[Any]) -> List[Any]:
        if not value:
            raise ValueError("sweep parameter values must be non-empty")
        return value

    @field_validator("labels")
    @classmethod
    def _validate_labels(cls, value: Optional[List[str]], info) -> Optional[List[str]]:
        if value is None:
            return value
        values = info.data.get("values") or []
        if len(value) != len(values):
            raise ValueError("sweep parameter labels must match values length")
        return value


class SweepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base: str
    parameters: List[SweepParameterConfig] = Field(default_factory=list)
    name: Optional[str] = None
    output_directory: str = "out/sweeps"
    mode: Literal["cartesian", "zip"] = "cartesian"

    @field_validator("parameters")
    @classmethod
    def _validate_parameters(cls, value: List[SweepParameterConfig]) -> List[SweepParameterConfig]:
        if not value:
            raise ValueError("sweep requires at least one parameter")
        return value


def _register_builtin_parameter_models() -> None:
    register_physics_parameter_model("poisson", PoissonParameters)
    register_physics_parameter_model("heat", HeatParameters)
    register_physics_parameter_model("heat_transient", HeatTransientParameters)
    register_physics_parameter_model("elasticity", ElasticityParameters)
    register_physics_parameter_model("electric_ac", ElectricACParameters)
    register_physics_parameter_model("magnetostatic", MagnetostaticParameters)
    register_physics_parameter_model("electro_thermal", ElectroThermalParameters)


_register_builtin_parameter_models()


def load_config(path: str | Path) -> SimStackConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    data = yaml.safe_load(path.read_text())
    if data is None:
        raise ValueError(f"Config is empty: {path}")
    return SimStackConfig.model_validate(data)


def load_sweep_config(path: str | Path) -> SweepConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Sweep config not found: {path}")
    data = yaml.safe_load(path.read_text())
    if data is None:
        raise ValueError(f"Sweep config is empty: {path}")
    return SweepConfig.model_validate(data)


def config_to_dict(config: SimStackConfig) -> Dict[str, Any]:
    data = config.model_dump(mode="json", by_alias=True, exclude_none=True)
    data["physics"] = config.physics.model_dump_external()
    return data
