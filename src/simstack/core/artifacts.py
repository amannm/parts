"""Typed artifacts for pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class CadArtifact:
    shape_ref: Any
    step_path: Optional[str]
    tag_spec: Any
    bbox: Optional[tuple[float, float, float, float, float, float]]
    units: Optional[str]
    cad_provenance: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MeshArtifact:
    gmsh_model_ref: Any
    dolfinx_mesh: Any
    cell_tags: Any
    facet_tags: Any
    tag_map: Dict[str, Dict[str, int]]
    mesh_stats: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SolveArtifact:
    fields: Dict[str, Any]
    derived_fields: Dict[str, Any]
    solver_report: Dict[str, Any]
    timings: Dict[str, float] = field(default_factory=dict)


@dataclass
class PostArtifact:
    vtx_paths: Dict[str, str]
    xdmf_paths: Dict[str, str]
    provenance_json: str
    pvsm_path: Optional[str] = None
