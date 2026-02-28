"""Workflow execution engine for single and coupled solves."""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, List

from simstack.core.artifacts import SolveArtifact
from simstack.fem.solve import solve_problem


def _set_nested(data: Dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in path.split(".") if part]
    if not parts:
        raise ValueError("Empty coupling target path")
    cur: Any = data
    for part in parts[:-1]:
        if not isinstance(cur, dict):
            raise TypeError(f"Cannot set path '{path}': '{part}' parent is not dict")
        if part not in cur or cur[part] is None:
            cur[part] = {}
        cur = cur[part]
    if not isinstance(cur, dict):
        raise TypeError(f"Cannot set path '{path}': parent is not dict")
    cur[parts[-1]] = value


def _field_reduction(field: Any, mode: str) -> float | None:
    if field is None or not hasattr(field, "x") or not hasattr(field.x, "array"):
        return None
    values = field.x.array
    if values.size == 0:
        return None
    if mode == "min":
        return float(values.min())
    if mode == "max":
        return float(values.max())
    return float(values.mean())


def _field_delta(prev: Any, cur: Any) -> float:
    if prev is None or cur is None:
        return math.inf
    if not hasattr(prev, "x") or not hasattr(cur, "x"):
        return math.inf
    if not hasattr(prev.x, "array") or not hasattr(cur.x, "array"):
        return math.inf
    a = prev.x.array
    b = cur.x.array
    if a.shape != b.shape:
        return math.inf
    if a.size == 0:
        return 0.0
    diff = b - a
    denom = float((a * a).sum())
    num = float((diff * diff).sum())
    if denom <= 0:
        return math.sqrt(max(num, 0.0))
    return math.sqrt(max(num, 0.0) / denom)


def _primary_field_name(artifact: SolveArtifact) -> str | None:
    if not artifact.fields:
        return None
    return next(iter(artifact.fields.keys()))


def _merge_fields(stage_results: Dict[str, SolveArtifact]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for stage_id, artifact in stage_results.items():
        for name, field in artifact.fields.items():
            prefixed = f"{stage_id}.{name}"
            merged[prefixed] = field
            if name not in merged:
                merged[name] = field
    return merged


def _runtime_params(config: Any, params: Dict[str, Any], runtime_vars: Dict[str, float] | None = None) -> Dict[str, Any]:
    out = dict(params)
    out["runtime_dimension"] = int(config.geometry.dimension)
    out["runtime_coordinate_system"] = str(config.geometry.coordinate_system)
    if runtime_vars:
        out["runtime_material_variables"] = dict(runtime_vars)
    return out


def run_workflow(
    mesh: Any,
    cell_tags: Any,
    facet_tags: Any,
    config: Any,
    tag_map: Dict[str, Dict[str, int]],
) -> SolveArtifact:
    workflow = config.workflow

    if workflow.mode == "single":
        if not workflow.nodes:
            raise ValueError("workflow.mode='single' requires one workflow node")
        node = workflow.nodes[0]
        physics_cfg = {
            "model": node.physics.model,
            "parameters": _runtime_params(config, node.physics.parameters),
        }
        return solve_problem(
            mesh,
            cell_tags,
            facet_tags,
            physics_cfg,
            list(node.bcs),
            config.materials,
            config.solver,
            tag_map,
        )

    stages = workflow.nodes
    couplings = workflow.couplings
    max_iters = int(workflow.solver.max_iters)
    relax_default = float(workflow.solver.relaxation)
    rtol = float(workflow.solver.rtol)
    atol = float(workflow.solver.atol)

    previous_results: Dict[str, SolveArtifact] = {}
    previous_scalars: Dict[str, float] = {}

    converged = False
    stop_reason = "max_iters"
    iteration_reports: List[Dict[str, Any]] = []
    current_results: Dict[str, SolveArtifact] = {}

    for it in range(1, max_iters + 1):
        current_results = {}

        stage_params: Dict[str, Dict[str, Any]] = {}
        for stage in stages:
            stage_params[stage.id] = _runtime_params(config, stage.physics.parameters)

        for coupling in couplings:
            source_artifact = previous_results.get(coupling.from_node)
            if source_artifact is None:
                continue
            source_field = source_artifact.fields.get(coupling.field)
            if source_field is None:
                continue

            if coupling.operator == "field":
                _set_nested(stage_params[coupling.to_node], coupling.target, source_field)
                continue

            raw = _field_reduction(source_field, coupling.reduction)
            if raw is None:
                continue

            if coupling.operator == "scalar-reduction":
                _set_nested(stage_params[coupling.to_node], coupling.target, raw)
                continue

            if coupling.operator == "relaxed-scalar":
                key = f"{coupling.from_node}:{coupling.field}->{coupling.to_node}:{coupling.target}"
                prev = previous_scalars.get(key, raw)
                relax = float(coupling.relaxation) if coupling.relaxation is not None else relax_default
                mixed = relax * raw + (1.0 - relax) * prev
                previous_scalars[key] = mixed
                _set_nested(stage_params[coupling.to_node], coupling.target, mixed)
                continue

            raise ValueError(f"Unsupported coupling operator: {coupling.operator}")

        stage_reports: Dict[str, Any] = {}
        for stage in stages:
            stage_cfg = {
                "model": stage.physics.model,
                "parameters": copy.deepcopy(stage_params[stage.id]),
            }
            artifact = solve_problem(
                mesh,
                cell_tags,
                facet_tags,
                stage_cfg,
                list(stage.bcs),
                config.materials,
                config.solver,
                tag_map,
            )
            current_results[stage.id] = artifact
            stage_reports[stage.id] = artifact.solver_report

        max_delta = 0.0
        for stage in stages:
            prev = previous_results.get(stage.id)
            cur = current_results.get(stage.id)
            if prev is None or cur is None:
                max_delta = math.inf
                continue
            prev_name = _primary_field_name(prev)
            cur_name = _primary_field_name(cur)
            if prev_name is None or cur_name is None:
                continue
            delta = _field_delta(prev.fields.get(prev_name), cur.fields.get(cur_name))
            max_delta = max(max_delta, delta)

        if math.isfinite(max_delta) and (max_delta <= atol or max_delta <= rtol):
            converged = True
            stop_reason = "converged"

        iteration_reports.append(
            {
                "iteration": it,
                "field_delta": None if not math.isfinite(max_delta) else max_delta,
                "stage_reports": stage_reports,
            }
        )

        previous_results = current_results
        if converged:
            break

    if not current_results:
        raise RuntimeError("Coupled workflow produced no stage results")

    final_fields = _merge_fields(current_results)
    solver_report = {
        "workflow": {
            "mode": "coupled",
            "scheme": workflow.solver.scheme,
            "iterations": len(iteration_reports),
            "max_iters": max_iters,
            "rtol": rtol,
            "atol": atol,
            "relaxation": relax_default,
            "converged": converged,
            "stop_reason": stop_reason,
            "history": iteration_reports,
        }
    }

    return SolveArtifact(fields=final_fields, derived_fields={}, solver_report=solver_report, timings={})
