"""Configuration schema and loader for SimStack."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class GeometryConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    builder: str
    params: Dict[str, Any] = Field(default_factory=dict)
    units: Optional[str] = None


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


class PhysicsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    parameters: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("parameters")
    @classmethod
    def _validate_targets(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(value, dict):
            raise TypeError("physics.parameters must be a dict")

        time_cfg = value.get("time")
        if isinstance(time_cfg, dict) and "targets" in time_cfg:
            raise ValueError("time.targets is not supported; move targets to physics.parameters.targets")

        raw = value.get("targets")
        if raw is None:
            return value
        if isinstance(raw, dict):
            raw_list = [raw]
        elif isinstance(raw, list):
            raw_list = raw
        else:
            raise TypeError("physics.parameters.targets must be a dict or list of dicts")

        for idx, spec in enumerate(raw_list):
            if not isinstance(spec, dict):
                raise TypeError(f"targets[{idx}] must be a dict")
            if "tag" not in spec:
                raise ValueError(f"targets[{idx}] missing 'tag'")
            if "temperature" not in spec:
                raise ValueError(f"targets[{idx}] missing 'temperature'")
            mode = spec.get("mode", "avg")
            if mode not in {"avg", "min", "max"}:
                raise ValueError(f"targets[{idx}] invalid mode '{mode}'")
            direction = spec.get("direction", "above")
            if direction not in {"above", "below"}:
                raise ValueError(f"targets[{idx}] invalid direction '{direction}'")

        return value


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
    return config.model_dump(mode="json", by_alias=True, exclude_none=True)
