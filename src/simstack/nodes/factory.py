"""Node construction for the DAG runtime."""

from __future__ import annotations

from typing import Any, Dict, List

from simstack.adapters.cad import hydrate_cad, run_cad
from simstack.adapters.mesh import hydrate_mesh, run_mesh
from simstack.adapters.post import hydrate_post, run_post
from simstack.adapters.solve import hydrate_solve, run_solve
from simstack.engine.types import EngineContext, NodeResult, NodeSpec


def _execute_cad(ctx: EngineContext) -> NodeResult:
    result = run_cad(ctx)
    return NodeResult(state_updates=result["state_updates"], cache_payload=result["cache_payload"])


def _hydrate_cad(ctx: EngineContext, payload: Dict[str, Any]) -> Dict[str, Any]:
    return hydrate_cad(payload)


def _execute_mesh(ctx: EngineContext) -> NodeResult:
    result = run_mesh(ctx)
    return NodeResult(state_updates=result["state_updates"], cache_payload=result["cache_payload"])


def _hydrate_mesh(ctx: EngineContext, payload: Dict[str, Any]) -> Dict[str, Any]:
    return hydrate_mesh(ctx, payload)


def _execute_solve(ctx: EngineContext) -> NodeResult:
    result = run_solve(ctx)
    return NodeResult(state_updates=result["state_updates"], cache_payload=result["cache_payload"])


def _hydrate_solve(ctx: EngineContext, payload: Dict[str, Any]) -> Dict[str, Any]:
    return hydrate_solve(payload)


def _execute_post(ctx: EngineContext) -> NodeResult:
    result = run_post(ctx)
    return NodeResult(state_updates=result["state_updates"], cache_payload=result["cache_payload"])


def _hydrate_post(ctx: EngineContext, payload: Dict[str, Any]) -> Dict[str, Any]:
    return hydrate_post(payload)


_EXECUTORS = {
    "cad": (_execute_cad, _hydrate_cad),
    "mesh": (_execute_mesh, _hydrate_mesh),
    "solve": (_execute_solve, _hydrate_solve),
    "post": (_execute_post, _hydrate_post),
}


def build_nodes(ir: Any) -> List[NodeSpec]:
    specs: List[NodeSpec] = []
    for node in ir.nodes:
        if node.kind not in _EXECUTORS:
            raise KeyError(f"Unknown node kind: {node.kind}")
        execute, hydrate = _EXECUTORS[node.kind]
        specs.append(
            NodeSpec(
                id=node.id,
                kind=node.kind,
                deps=list(node.deps),
                version=node.version,
                config_slice=node.config_slice,
                execute=execute,
                hydrate=hydrate,
                cacheable=True,
            )
        )
    return specs
