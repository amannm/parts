"""Configuration schema and loader for SimStack."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field


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


def load_config(path: str | Path) -> SimStackConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    data = yaml.safe_load(path.read_text())
    if data is None:
        raise ValueError(f"Config is empty: {path}")
    return SimStackConfig.model_validate(data)


def config_to_dict(config: SimStackConfig) -> Dict[str, Any]:
    return config.model_dump(mode="json", by_alias=True, exclude_none=True)
