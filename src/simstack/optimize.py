"""Optimization entrypoints built on sweep infrastructure."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import Any, Dict

from simstack.config import SweepConfig, SimStackConfig, config_to_dict, load_config
from simstack.core.project import Project
from simstack.sweep import run_sweep


def _set_path(data: Dict[str, Any], path: str, value: Any) -> None:
    parts = [p for p in path.split(".") if p]
    if not parts:
        raise ValueError("Empty path")
    cur: Any = data
    for part in parts[:-1]:
        if not isinstance(cur, dict):
            raise TypeError(f"Cannot set path '{path}'")
        if part not in cur or cur[part] is None:
            cur[part] = {}
        cur = cur[part]
    if not isinstance(cur, dict):
        raise TypeError(f"Cannot set path '{path}'")
    cur[parts[-1]] = value


def _apply_paths(data: Dict[str, Any], paths: str | list[str], value: Any) -> None:
    if isinstance(paths, list):
        if not isinstance(value, (list, tuple)):
            raise ValueError("List path requires list/tuple value")
        if len(value) != len(paths):
            raise ValueError("List path length mismatch")
        for p, v in zip(paths, value):
            _set_path(data, p, v)
        return
    _set_path(data, paths, value)


def _extract_path(data: Dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in [p for p in path.split(".") if p]:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _load_solve_report(out_dir: str | None) -> Dict[str, Any]:
    if not out_dir:
        return {}
    report = Path(out_dir) / "reports" / "solve_report.json"
    if not report.exists():
        return {}
    try:
        data = json.loads(report.read_text())
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _constraints_ok(report: Dict[str, Any], constraints: list[Any]) -> bool:
    for spec in constraints:
        lhs = _extract_path(report, spec.path)
        if not isinstance(lhs, (int, float)):
            return False
        rhs = float(spec.value)
        lhs_v = float(lhs)
        if spec.op == "<=" and not (lhs_v <= rhs):
            return False
        if spec.op == ">=" and not (lhs_v >= rhs):
            return False
        if spec.op == "<" and not (lhs_v < rhs):
            return False
        if spec.op == ">" and not (lhs_v > rhs):
            return False
        if spec.op == "==" and not (lhs_v == rhs):
            return False
    return True


def _run_case(run_dict: Dict[str, Any], repo_root: str, *, dry_run: bool) -> Dict[str, Any]:
    cfg = SimStackConfig.model_validate(run_dict)
    project = Project(cfg, repo_root=Path(repo_root))
    if dry_run:
        out_root = project.output_root()
        report_path = project.write_dry_run_report(out_root / "reports")
        if cfg.outputs.write_reports:
            project.write_provenance(out_root / "reports")
        return {
            "run_hash": project.run_hash(),
            "out_dir": str(out_root),
            "dry_run_report": report_path,
            "cached": False,
        }
    return project.run()


def run_optimize(
    sweep: SweepConfig,
    repo_root: str | Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    out_dir: str | None = None,
) -> Dict[str, Any]:
    # Fallback when no objective provided.
    if sweep.objective is None:
        fallback = sweep.model_copy(update={"mode": "optuna"})
        return run_sweep(fallback, repo_root=repo_root, dry_run=dry_run, force=force, out_dir=out_dir)

    try:
        import optuna
    except Exception:
        fallback = sweep.model_copy(update={"mode": "optuna"})
        return run_sweep(fallback, repo_root=repo_root, dry_run=dry_run, force=force, out_dir=out_dir)

    base_cfg = load_config(sweep.base)
    base_dict = config_to_dict(base_cfg)
    root = Path(out_dir) if out_dir else Path(sweep.output_directory)
    if sweep.name:
        root = root / sweep.name

    direction = "maximize" if sweep.objective.goal == "max" else "minimize"
    study = optuna.create_study(
        direction=direction,
        sampler=optuna.samplers.TPESampler(seed=int(sweep.seed)),
        pruner=optuna.pruners.MedianPruner(),
    )

    records: list[dict[str, Any]] = []
    n_trials = int(sweep.samples or 20)

    def objective(trial: Any) -> float:
        run_dict = copy.deepcopy(base_dict)
        label_bits = []

        for idx, param in enumerate(sweep.parameters):
            if param.bounds is None:
                raise ValueError(f"Optimization parameter missing bounds: {param.name or param.path}")
            lo, hi = float(param.bounds[0]), float(param.bounds[1])
            name = param.name or (param.path if isinstance(param.path, str) else f"param_{idx+1}")
            value = trial.suggest_float(name, lo, hi)
            if param.scale is not None:
                value *= float(param.scale)
            if param.offset is not None:
                value += float(param.offset)
            if param.transform == "deg2rad":
                value = math.radians(value)
            elif param.transform == "rad2deg":
                value = math.degrees(value)
            _apply_paths(run_dict, param.path, value)
            label_bits.append(f"{name}={value:.6g}")

        label = "_".join(label_bits).replace(" ", "")
        outputs = run_dict.get("outputs") or {}
        outputs["directory"] = str(root / f"trial_{trial.number:04d}")
        if force:
            outputs["reuse"] = False
        run_dict["outputs"] = outputs

        metadata = run_dict.get("metadata") or {}
        metadata["optimization"] = {"trial": trial.number, "label": label}
        run_dict["metadata"] = metadata

        result = _run_case(run_dict, str(repo_root), dry_run=dry_run)
        report = _load_solve_report(result.get("out_dir"))

        obj_val = 0.0
        if report:
            extracted = _extract_path(report, sweep.objective.path)
            if isinstance(extracted, (int, float)):
                obj_val = float(extracted)

        feasible = True if dry_run else _constraints_ok(report, sweep.constraints)
        if not feasible:
            # Penalize infeasible points according to direction.
            obj_val = obj_val + 1e12 if direction == "minimize" else obj_val - 1e12

        records.append(
            {
                "trial": trial.number,
                "label": label,
                "objective": obj_val,
                "feasible": feasible,
                "out_dir": result.get("out_dir"),
                "result": result,
            }
        )
        return obj_val

    study.optimize(objective, n_trials=n_trials)

    root.mkdir(parents=True, exist_ok=True)
    summary = {
        "mode": "optuna",
        "count": len(records),
        "output_root": str(root),
        "best": {
            "trial": study.best_trial.number,
            "objective": study.best_value,
            "params": study.best_trial.params,
        }
        if records
        else None,
        "runs": [r["result"] | {"label": r["label"], "objective": r["objective"], "feasible": r["feasible"]} for r in records],
    }

    report_path = root / "sweep_report.json"
    report_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    summary["report_path"] = str(report_path)
    return summary
