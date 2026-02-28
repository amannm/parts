"""Configuration schema and loaders for SimStack v2."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple, Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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


class MixedSourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str
    value: float


class MixedSourcesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface: List[MixedSourceSpec] = Field(default_factory=list)
    line: List[MixedSourceSpec] = Field(default_factory=list)


class PoissonParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree: int = 1
    kappa: float = 1.0
    source: float = 0.0
    sources: MixedSourcesConfig = Field(default_factory=MixedSourcesConfig)
    runtime_dimension: int | None = None
    runtime_coordinate_system: Literal["cartesian", "axisymmetric"] | None = None
    runtime_material_variables: Dict[str, float] = Field(default_factory=dict)


class HeatParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree: int = 1
    kappa: float = 1.0
    source: float = 0.0
    sources: MixedSourcesConfig = Field(default_factory=MixedSourcesConfig)
    runtime_dimension: int | None = None
    runtime_coordinate_system: Literal["cartesian", "axisymmetric"] | None = None
    runtime_material_variables: Dict[str, float] = Field(default_factory=dict)


class HeatTransientParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    degree: int = 1
    kappa: float = 1.0
    rho: float = 1.0
    cp: float = 1.0
    source: float = 0.0
    sources: MixedSourcesConfig = Field(default_factory=MixedSourcesConfig)
    source_field: Any | None = None
    initial: float | None = None
    T0: float | None = None
    time: TimeParameters | None = None
    phase_change: PhaseChangeParameters | None = None
    targets: List[TargetSpec] = Field(default_factory=list)
    bcs: List[BCSpec] | None = None
    runtime_dimension: int | None = None
    runtime_coordinate_system: Literal["cartesian", "axisymmetric"] | None = None
    runtime_material_variables: Dict[str, float] = Field(default_factory=dict)

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
    sources: MixedSourcesConfig = Field(default_factory=MixedSourcesConfig)
    include_joule_heat: bool = True
    joule_scale: float = 1.0
    derived: List[str] = Field(default_factory=list)
    bcs: List[BCSpec] | None = None
    runtime_dimension: int | None = None
    runtime_coordinate_system: Literal["cartesian", "axisymmetric"] | None = None
    runtime_material_variables: Dict[str, float] = Field(default_factory=dict)


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
    runtime_dimension: int | None = None
    runtime_coordinate_system: Literal["cartesian", "axisymmetric"] | None = None
    runtime_material_variables: Dict[str, float] = Field(default_factory=dict)


class ElasticityParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    degree: int = 1
    lambda_: float | None = Field(default=None, alias="lambda")
    mu: float | None = None
    E: float | None = None
    nu: float | None = None
    body_force: float | List[float] | None = None
    derived: List[str] = Field(default_factory=list)
    runtime_dimension: int | None = None
    runtime_coordinate_system: Literal["cartesian", "axisymmetric"] | None = None
    runtime_material_variables: Dict[str, float] = Field(default_factory=dict)

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
    runtime_dimension: int | None = None
    runtime_coordinate_system: Literal["cartesian", "axisymmetric"] | None = None
    runtime_material_variables: Dict[str, float] = Field(default_factory=dict)

    @field_validator("targets", mode="before")
    @classmethod
    def _normalize_targets(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, dict):
            return [value]
        return value


PhysicsParameters = (
    PoissonParameters
    | HeatParameters
    | HeatTransientParameters
    | ElasticityParameters
    | ElectricACParameters
    | MagnetostaticParameters
    | ElectroThermalParameters
    | Dict[str, Any]
)


_PHYSICS_PARAMETER_MODELS: Dict[str, type[BaseModel]] = {}


def register_physics_parameter_model(model_name: str, params_model: type[BaseModel] | None) -> None:
    if params_model is None:
        _PHYSICS_PARAMETER_MODELS.pop(model_name, None)
        return
    _PHYSICS_PARAMETER_MODELS[model_name] = params_model


def get_physics_parameter_model(model_name: str) -> type[BaseModel] | None:
    return _PHYSICS_PARAMETER_MODELS.get(model_name)


class PhysicsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    parameters: PhysicsParameters = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_parameters(self) -> "PhysicsConfig":
        params_model = get_physics_parameter_model(self.model)
        raw = self.parameters

        if params_model is None:
            if isinstance(raw, BaseModel):
                self.parameters = raw.model_dump(mode="json", by_alias=True, exclude_none=True)
            elif not isinstance(raw, dict):
                raise TypeError("physics.parameters must be an object")
            return self

        if isinstance(raw, BaseModel):
            if isinstance(raw, params_model):
                return self
            raw = raw.model_dump(mode="json", by_alias=True, exclude_none=True)

        if not isinstance(raw, dict):
            raise TypeError("physics.parameters must be an object")

        self.parameters = params_model.model_validate(raw)
        return self

    def parameters_dict(self) -> Dict[str, Any]:
        raw = self.parameters
        if isinstance(raw, BaseModel):
            return raw.model_dump(mode="json", by_alias=True, exclude_none=True)
        if isinstance(raw, dict):
            return raw
        raise TypeError("physics.parameters must be a dict or pydantic model")


class GeometryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    builder: str
    params: Dict[str, Any] = Field(default_factory=dict)
    units: Optional[str] = None
    dimension: Literal[2, 3] = 3
    coordinate_system: Literal["cartesian", "axisymmetric"] = "cartesian"

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

    @model_validator(mode="after")
    def _validate_coordinate_system(self) -> "GeometryConfig":
        if self.coordinate_system == "axisymmetric" and self.dimension != 2:
            raise ValueError("axisymmetric coordinate system requires geometry.dimension = 2")
        return self


class FacetPlaneAtMinRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["PlaneAtMin"]
    name: str
    axis: Literal["x", "y", "z", 0, 1, 2]
    tol: float | None = None


class FacetPlaneAtMaxRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["PlaneAtMax"]
    name: str
    axis: Literal["x", "y", "z", 0, 1, 2]
    tol: float | None = None


class FacetBBoxPatchRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["BBoxPatch"]
    name: str
    xmin: float | None = None
    xmax: float | None = None
    ymin: float | None = None
    ymax: float | None = None
    zmin: float | None = None
    zmax: float | None = None


class FacetNormalApproxRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["NormalApprox"]
    name: str
    nx: float
    ny: float
    nz: float
    tol: float = 0.05
    allow_flip: bool = True


class FacetByNameRegexRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ByNameRegex"]
    name: str
    pattern: str


class FacetByAreaRangeRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ByAreaRange"]
    name: str
    min_area: float | None = None
    max_area: float | None = None


class FacetAdjacentToCellTagRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["AdjacentToCellTag"]
    name: str
    cell_tag: str


FacetRule = Annotated[
    FacetPlaneAtMinRule
    | FacetPlaneAtMaxRule
    | FacetBBoxPatchRule
    | FacetNormalApproxRule
    | FacetByNameRegexRule
    | FacetByAreaRangeRule
    | FacetAdjacentToCellTagRule,
    Field(discriminator="type"),
]


class CellAllVolumesRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["AllVolumes"]
    name: str


class CellBBoxPatchRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["BBoxPatch"]
    name: str
    xmin: float | None = None
    xmax: float | None = None
    ymin: float | None = None
    ymax: float | None = None
    zmin: float | None = None
    zmax: float | None = None


class CellByNameRegexRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ByNameRegex"]
    name: str
    pattern: str


class CellByVolumeRangeRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ByVolumeRange"]
    name: str
    min_volume: float | None = None
    max_volume: float | None = None


class CellConnectedToFacetTagRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["ConnectedToFacetTag"]
    name: str
    facet_tag: str


CellRule = Annotated[
    CellAllVolumesRule
    | CellBBoxPatchRule
    | CellByNameRegexRule
    | CellByVolumeRangeRule
    | CellConnectedToFacetTagRule,
    Field(discriminator="type"),
]


class TagComposite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    entity: Literal["facets", "cells"]
    op: Literal["union", "intersection", "difference"]
    inputs: List[str]

    @field_validator("inputs")
    @classmethod
    def _validate_inputs(cls, value: List[str]) -> List[str]:
        if len(value) < 2:
            raise ValueError("composite inputs must include at least two tags")
        return value


class TagsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facets: List[FacetRule] = Field(default_factory=list)
    cells: List[CellRule] = Field(default_factory=list)
    composites: List[TagComposite] = Field(default_factory=list)
    id_overrides: Dict[str, int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_uniques(self) -> "TagsConfig":
        facet_names = [rule.name for rule in self.facets]
        cell_names = [rule.name for rule in self.cells]
        if len(set(facet_names)) != len(facet_names):
            raise ValueError("Duplicate facet tag names are not allowed")
        if len(set(cell_names)) != len(cell_names):
            raise ValueError("Duplicate cell tag names are not allowed")
        composite_names = [rule.name for rule in self.composites]
        if len(set(composite_names)) != len(composite_names):
            raise ValueError("Duplicate composite tag names are not allowed")
        return self


class MeshingQAConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_quality: Optional[float] = None
    quality_bins: int = 10
    require_all_facets_tagged: bool = True
    allow_overlaps: bool = False


class CurvatureRefineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    min_size: float | None = None
    max_size: float | None = None


class DistanceRefineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: List[str]
    size_min: float
    size_max: float
    dist_min: float
    dist_max: float


class BoundaryLayerConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tags: List[str]
    first_layer: float
    growth_rate: float = 1.2
    n_layers: int = 5


class MeshingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_size: Optional[float] = None
    curvature_refine: CurvatureRefineConfig = Field(default_factory=CurvatureRefineConfig)
    distance_refine: List[DistanceRefineConfig] = Field(default_factory=list)
    boundary_layers: List[BoundaryLayerConfig] = Field(default_factory=list)
    gmsh_options: Dict[str, Any] = Field(default_factory=dict)
    qa: MeshingQAConfig = Field(default_factory=MeshingQAConfig)


class MaterialConstantModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Literal["constant"]
    value: float


class MaterialPolynomialModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Literal["polynomial"]
    variable: Literal["T", "f"]
    coefficients: List[float]
    reference: float = 0.0


class MaterialTableModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: Literal["table"]
    variable: Literal["T", "f"]
    points: List[Tuple[float, float]]
    interpolation: Literal["linear"] = "linear"

    @field_validator("points")
    @classmethod
    def _validate_points(cls, value: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        if len(value) < 2:
            raise ValueError("table model requires at least two points")
        return value


MaterialModel = Annotated[
    MaterialConstantModel | MaterialPolynomialModel | MaterialTableModel,
    Field(discriminator="model"),
]


class MaterialsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by_tag: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class SolverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: str = "linear_default"
    options: Dict[str, Any] = Field(default_factory=dict)


class WorkflowStageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    physics: PhysicsConfig
    bcs: BCsConfig = Field(default_factory=BCsConfig)


class CouplingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_stage: str
    field: str
    to_stage: str
    target: str
    mode: Literal["field", "avg"] = "field"
    reduction: Literal["avg", "min", "max"] = "avg"


class WorkflowSolverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme: Literal["fixed_point"] = "fixed_point"
    max_iters: int = 20
    rtol: float = 1e-4
    atol: float = 1e-8
    relaxation: float = 0.7


class WorkflowConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["single", "coupled"] = "single"
    stages: List[WorkflowStageConfig] = Field(default_factory=list)
    couplings: List[CouplingSpec] = Field(default_factory=list)
    solver: WorkflowSolverConfig = Field(default_factory=WorkflowSolverConfig)

    @model_validator(mode="after")
    def _validate_consistency(self) -> "WorkflowConfig":
        stage_ids = [stage.id for stage in self.stages]
        if len(set(stage_ids)) != len(stage_ids):
            raise ValueError("workflow stage IDs must be unique")
        if self.type == "coupled" and len(self.stages) < 2:
            raise ValueError("workflow.type='coupled' requires at least two stages")
        known = set(stage_ids)
        for coupling in self.couplings:
            if known and coupling.from_stage not in known:
                raise ValueError(f"workflow coupling references unknown from_stage: {coupling.from_stage}")
            if known and coupling.to_stage not in known:
                raise ValueError(f"workflow coupling references unknown to_stage: {coupling.to_stage}")
        return self


class UnitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    internal_system: Literal["SI"] = "SI"
    inputs: Dict[str, str] = Field(default_factory=dict)


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
    workflow: WorkflowConfig = Field(default_factory=WorkflowConfig)
    units: UnitsConfig = Field(default_factory=UnitsConfig)
    outputs: OutputsConfig = Field(default_factory=OutputsConfig)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_axisymmetric_support(self) -> "SimStackConfig":
        if self.geometry.coordinate_system != "axisymmetric":
            return self

        scalar_models = {"poisson", "heat", "heat_transient", "electric_ac"}
        if self.workflow.type == "single":
            if self.physics.model not in scalar_models:
                raise ValueError("axisymmetric mode currently supports scalar physics only")
            return self

        for stage in self.workflow.stages:
            if stage.physics.model not in scalar_models:
                raise ValueError("axisymmetric mode currently supports scalar workflow stages only")
        return self


class SweepObjectiveConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    goal: Literal["min", "max"] = "min"


class SweepConstraintConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    op: Literal["<=", ">=", "<", ">", "=="]
    value: float


class SweepParallelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workers: int | None = None


class SweepParameterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str | List[str]
    values: List[Any] = Field(default_factory=list)
    bounds: Tuple[float, float] | None = None
    name: Optional[str] = None
    labels: Optional[List[str]] = None
    transform: Optional[Literal["deg2rad", "rad2deg"]] = None
    scale: Optional[float] = None
    offset: Optional[float] = None
    fmt: Optional[str] = None

    @model_validator(mode="after")
    def _validate_parameter(self) -> "SweepParameterConfig":
        if not self.values and self.bounds is None:
            raise ValueError("sweep parameter requires either values or bounds")
        if self.labels is not None and self.values and len(self.labels) != len(self.values):
            raise ValueError("sweep parameter labels must match values length")
        if self.bounds is not None and self.bounds[0] >= self.bounds[1]:
            raise ValueError("sweep parameter bounds must satisfy min < max")
        return self


class SweepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base: str
    parameters: List[SweepParameterConfig] = Field(default_factory=list)
    name: Optional[str] = None
    output_directory: str = "out/sweeps"
    mode: Literal["cartesian", "zip", "lhs", "sobol", "optuna"] = "cartesian"
    samples: int | None = None
    seed: int = 42
    parallel: SweepParallelConfig = Field(default_factory=SweepParallelConfig)
    objective: SweepObjectiveConfig | None = None
    constraints: List[SweepConstraintConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_parameters(self) -> "SweepConfig":
        if not self.parameters:
            raise ValueError("sweep requires at least one parameter")
        if self.mode in {"lhs", "sobol", "optuna"}:
            for param in self.parameters:
                if param.bounds is None:
                    raise ValueError(f"sweep mode '{self.mode}' requires bounds for parameter '{param.name or param.path}'")
            if self.samples is None:
                raise ValueError(f"sweep mode '{self.mode}' requires samples")
        if self.mode == "optuna" and self.objective is None:
            raise ValueError("optuna sweep requires objective")
        return self


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
    config = SimStackConfig.model_validate(data)

    from simstack.fem.units import normalize_config_units, validate_config_units

    validate_config_units(config_to_dict(config))
    return normalize_config_units(config)


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
    data["physics"]["parameters"] = config.physics.parameters_dict()
    if "workflow" in data and config.workflow.stages:
        for idx, stage in enumerate(config.workflow.stages):
            data["workflow"]["stages"][idx]["physics"]["parameters"] = stage.physics.parameters_dict()
    return data
