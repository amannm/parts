"""Compile validated study configs into runtime IR."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, ConfigDict, Field

from simstack.domain.config import StudyConfig, study_to_dict


class RuntimeContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    geometry_dimension: int
    coordinate_system: str
    runtime_material_variables: Dict[str, float] = Field(default_factory=dict)


class NodeIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    deps: List[str] = Field(default_factory=list)
    version: str = "1"
    config_slice: Dict[str, Any] = Field(default_factory=dict)


class RunIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: List[NodeIR]
    runtime: RuntimeContext
    config_hash_payload: Dict[str, Any]


def _material_variables(config_dict: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    workflow = config_dict.get("workflow", {})
    nodes = workflow.get("nodes", []) if isinstance(workflow, dict) else []
    for node in nodes:
        physics = node.get("physics", {}) if isinstance(node, dict) else {}
        params = physics.get("parameters", {}) if isinstance(physics, dict) else {}
        if not isinstance(params, dict):
            continue
        temp = params.get("temperature")
        freq = params.get("frequency")
        if isinstance(temp, (int, float)):
            out.setdefault("T", float(temp))
        if isinstance(freq, (int, float)):
            out.setdefault("f", float(freq))
    return out


def compile_run_ir(config: StudyConfig) -> RunIR:
    payload = study_to_dict(config)

    nodes = [
        NodeIR(
            id="cad",
            kind="cad",
            deps=[],
            config_slice={"geometry": payload.get("geometry", {})},
        ),
        NodeIR(
            id="mesh",
            kind="mesh",
            deps=["cad"],
            config_slice={
                "geometry": payload.get("geometry", {}),
                "tagging": payload.get("tagging", {}),
                "mesh": payload.get("mesh", {}),
            },
        ),
        NodeIR(
            id="solve",
            kind="solve",
            deps=["mesh"],
            config_slice={
                "workflow": payload.get("workflow", {}),
                "materials": payload.get("materials", {}),
                "solver": payload.get("solver", {}),
                "outputs": {
                    "format": payload.get("outputs", {}).get("format"),
                    "write_tag_fields": payload.get("outputs", {}).get("write_tag_fields"),
                },
            },
        ),
        NodeIR(
            id="post",
            kind="post",
            deps=["solve"],
            config_slice={"outputs": payload.get("outputs", {})},
        ),
    ]

    runtime = RuntimeContext(
        geometry_dimension=int(config.geometry.dimension),
        coordinate_system=str(config.geometry.coordinate_system),
        runtime_material_variables=_material_variables(payload),
    )

    return RunIR(nodes=nodes, runtime=runtime, config_hash_payload=payload)
