"""Typed study configuration schema."""

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


class PhysicsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_runtime_keys(self) -> "PhysicsSpec":
        runtime_keys = [key for key in self.parameters.keys() if key.startswith("runtime_")]
        if runtime_keys:
            joined = ", ".join(sorted(runtime_keys))
            raise ValueError(
                f"runtime_* fields are internal and must not appear in config (found: {joined})"
            )
        return self


class WorkflowNodeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    physics: PhysicsSpec
    bcs: List[BCSpec] = Field(default_factory=list)


class CouplingEdgeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_node: str
    field: str
    to_node: str
    target: str
    operator: Literal["field", "scalar-reduction", "relaxed-scalar"] = "field"
    reduction: Literal["avg", "min", "max"] = "avg"
    relaxation: float | None = None


class WorkflowSolverSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme: Literal["fixed_point"] = "fixed_point"
    max_iters: int = 20
    rtol: float = 1e-4
    atol: float = 1e-8
    relaxation: float = 0.7


class WorkflowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["single", "coupled"] = "single"
    nodes: List[WorkflowNodeSpec] = Field(default_factory=list)
    couplings: List[CouplingEdgeSpec] = Field(default_factory=list)
    solver: WorkflowSolverSpec = Field(default_factory=WorkflowSolverSpec)

    @model_validator(mode="after")
    def _validate_nodes(self) -> "WorkflowSpec":
        ids = [node.id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("workflow node IDs must be unique")
        if self.mode == "coupled" and len(self.nodes) < 2:
            raise ValueError("workflow.mode='coupled' requires at least two nodes")
        known = set(ids)
        for edge in self.couplings:
            if edge.from_node not in known:
                raise ValueError(f"unknown coupling from_node: {edge.from_node}")
            if edge.to_node not in known:
                raise ValueError(f"unknown coupling to_node: {edge.to_node}")
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


class TaggingSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facets: List[FacetRule] = Field(default_factory=list)
    cells: List[CellRule] = Field(default_factory=list)
    composites: List[TagComposite] = Field(default_factory=list)
    id_overrides: Dict[str, int] = Field(default_factory=dict)


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


class MeshSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    global_size: Optional[float] = None
    curvature_refine: CurvatureRefineConfig = Field(default_factory=CurvatureRefineConfig)
    distance_refine: List[DistanceRefineConfig] = Field(default_factory=list)
    boundary_layers: List[BoundaryLayerConfig] = Field(default_factory=list)
    gmsh_options: Dict[str, Any] = Field(default_factory=dict)
    qa: MeshingQAConfig = Field(default_factory=MeshingQAConfig)


class GeometrySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    builder: str
    params: Dict[str, Any] = Field(default_factory=dict)
    units: str | None = None
    dimension: Literal[2, 3] = 3
    coordinate_system: Literal["cartesian", "axisymmetric"] = "cartesian"

    @model_validator(mode="after")
    def _validate_coordinate_system(self) -> "GeometrySpec":
        if self.coordinate_system == "axisymmetric" and self.dimension != 2:
            raise ValueError("axisymmetric coordinate system requires geometry.dimension = 2")
        return self


class MaterialsSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    by_tag: Dict[str, Dict[str, Any]] = Field(default_factory=dict)


class SolverSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: str = "linear_default"
    options: Dict[str, Any] = Field(default_factory=dict)


class OutputsSpec(BaseModel):
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


class ExplorationObjectiveSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    goal: Literal["min", "max"] = "min"


class ExplorationConstraintSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    op: Literal["<=", ">=", "<", ">", "=="]
    value: float


class ExplorationParallelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workers: int | None = None


class ExplorationParameterSpec(BaseModel):
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
    def _validate_parameter(self) -> "ExplorationParameterSpec":
        if not self.values and self.bounds is None:
            raise ValueError("exploration parameter requires either values or bounds")
        if self.labels is not None and self.values and len(self.labels) != len(self.values):
            raise ValueError("exploration parameter labels must match values length")
        if self.bounds is not None and self.bounds[0] >= self.bounds[1]:
            raise ValueError("exploration parameter bounds must satisfy min < max")
        return self


class ExplorationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["cartesian", "zip", "lhs", "sobol", "optuna"] = "cartesian"
    name: str | None = None
    output_directory: str = "out/sweeps"
    samples: int | None = None
    seed: int = 42
    parameters: List[ExplorationParameterSpec] = Field(default_factory=list)
    objective: ExplorationObjectiveSpec | None = None
    constraints: List[ExplorationConstraintSpec] = Field(default_factory=list)
    parallel: ExplorationParallelSpec = Field(default_factory=ExplorationParallelSpec)

    @model_validator(mode="after")
    def _validate(self) -> "ExplorationSpec":
        if self.parameters and self.mode in {"lhs", "sobol", "optuna"}:
            for param in self.parameters:
                if param.bounds is None:
                    raise ValueError(
                        f"exploration mode '{self.mode}' requires bounds for '{param.name or param.path}'"
                    )
            if self.samples is None:
                raise ValueError(f"exploration mode '{self.mode}' requires samples")
        if self.mode == "optuna" and self.objective is None:
            raise ValueError("exploration mode 'optuna' requires objective")
        return self


class StudyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry: GeometrySpec
    tagging: TaggingSpec = Field(default_factory=TaggingSpec)
    mesh: MeshSpec = Field(default_factory=MeshSpec)
    workflow: WorkflowSpec
    materials: MaterialsSpec = Field(default_factory=MaterialsSpec)
    solver: SolverSpec = Field(default_factory=SolverSpec)
    outputs: OutputsSpec = Field(default_factory=OutputsSpec)
    exploration: ExplorationSpec | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def study_to_dict(config: StudyConfig) -> Dict[str, Any]:
    return config.model_dump(mode="json", exclude_none=True)


def load_study_config(path: str | Path) -> StudyConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Study config not found: {config_path}")
    data = yaml.safe_load(config_path.read_text())
    if data is None:
        raise ValueError(f"Study config is empty: {config_path}")
    return StudyConfig.model_validate(data)
