"""Sweep and design exploration utilities."""

from __future__ import annotations

import copy
import itertools
import json
import math
import random
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from simstack.config import SweepConfig, SweepParameterConfig, SimStackConfig, config_to_dict, load_config
from simstack.core.project import Project


def _slugify(text: str) -> str:
    safe = []
    for ch in text:
        if ch.isalnum() or ch in "-_=.":
            safe.append(ch)
        else:
            safe.append("-")
    return "".join(safe).strip("-")


def _set_path(data: Dict[str, Any], path: str, value: Any) -> None:
    parts = [p for p in path.split(".") if p]
    if not parts:
        raise ValueError("Empty sweep path")
    target: Any = data
    for key in parts[:-1]:
        if not isinstance(target, dict):
            raise TypeError(f"Cannot set path '{path}': parent '{key}' is not a dict")
        if key not in target or target[key] is None:
            target[key] = {}
        target = target[key]
    if not isinstance(target, dict):
        raise TypeError(f"Cannot set path '{path}': parent is not a dict")
    target[parts[-1]] = value


def _apply_paths(data: Dict[str, Any], paths: str | List[str], value: Any) -> None:
    if isinstance(paths, list):
        if not isinstance(value, (list, tuple)) or len(value) != len(paths):
            raise ValueError("Sweep value must be a list/tuple matching path list length")
        for subpath, subvalue in zip(paths, value):
            _set_path(data, subpath, subvalue)
        return
    _set_path(data, paths, value)


def _transform_scalar(value: float, param: SweepParameterConfig) -> float:
    out = float(value)
    if param.scale is not None:
        out *= float(param.scale)
    if param.offset is not None:
        out += float(param.offset)
    if param.transform == "deg2rad":
        out = math.radians(out)
    elif param.transform == "rad2deg":
        out = math.degrees(out)
    return out


def _apply_transform(value: Any, param: SweepParameterConfig) -> Any:
    if isinstance(value, (int, float)):
        return _transform_scalar(float(value), param)
    if isinstance(value, (list, tuple)) and value and all(isinstance(v, (int, float)) for v in value):
        return [_transform_scalar(float(v), param) for v in value]
    return value


def _param_name(param: SweepParameterConfig, index: int) -> str:
    if param.name:
        return param.name
    path = param.path
    if isinstance(path, list):
        return f"param_{index + 1}"
    return path.split(".")[-1] or f"param_{index + 1}"


def _label_value(param: SweepParameterConfig, raw: Any, idx: int) -> str:
    if param.labels is not None:
        return str(param.labels[idx])
    value = raw
    if isinstance(raw, (list, tuple)) and raw:
        value = raw[0]
    if param.fmt and isinstance(value, (int, float)):
        try:
            return format(float(value), param.fmt)
        except ValueError:
            return str(value)
    return str(value)


def _build_param_entries(param: SweepParameterConfig) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for idx, raw in enumerate(param.values):
        value = _apply_transform(raw, param)
        label = _label_value(param, raw, idx)
        entries.append({"raw": raw, "value": value, "label": label})
    return entries


def _lhs_unit(samples: int, dim: int, seed: int) -> List[List[float]]:
    rng = random.Random(seed)
    matrix = [[0.0] * dim for _ in range(samples)]
    for j in range(dim):
        points = [(i + rng.random()) / samples for i in range(samples)]
        rng.shuffle(points)
        for i in range(samples):
            matrix[i][j] = points[i]
    return matrix


def _sobol_unit(samples: int, dim: int, seed: int) -> List[List[float]]:
    try:
        from scipy.stats import qmc

        sampler = qmc.Sobol(d=dim, scramble=True, seed=seed)
        return sampler.random(n=samples).tolist()
    except Exception:
        return _lhs_unit(samples, dim, seed)


def _scale_bounds(point: Sequence[float], params: Sequence[SweepParameterConfig]) -> List[Any]:
    out: List[Any] = []
    for value, param in zip(point, params):
        if param.bounds is None:
            raise ValueError(f"Parameter '{param.name or param.path}' is missing bounds")
        lo, hi = float(param.bounds[0]), float(param.bounds[1])
        raw = lo + (hi - lo) * float(value)
        out.append(_apply_transform(raw, param))
    return out


def _iter_combinations(
    params: Sequence[SweepParameterConfig],
    mode: str,
    *,
    samples: int | None,
    seed: int,
) -> Iterable[List[Dict[str, Any]]]:
    if mode in {"cartesian", "zip"}:
        param_entries = [_build_param_entries(param) for param in params]
        if mode == "zip":
            length = len(param_entries[0])
            if any(len(entries) != length for entries in param_entries):
                raise ValueError("Zip sweep mode requires equal-length value lists")
            for idx in range(length):
                yield [entries[idx] for entries in param_entries]
            return
        for combo in itertools.product(*param_entries):
            yield list(combo)
        return

    if samples is None:
        raise ValueError(f"Sweep mode '{mode}' requires samples")

    dim = len(params)
    if mode == "lhs":
        points = _lhs_unit(samples, dim, seed)
    elif mode in {"sobol", "optuna"}:
        points = _sobol_unit(samples, dim, seed)
    else:
        raise ValueError(f"Unsupported sweep mode: {mode}")

    for idx, point in enumerate(points):
        scaled = _scale_bounds(point, params)
        entries: List[Dict[str, Any]] = []
        for p_idx, (param, value) in enumerate(zip(params, scaled)):
            name = _param_name(param, p_idx)
            entries.append(
                {
                    "raw": value,
                    "value": value,
                    "label": format(float(value), param.fmt) if param.fmt and isinstance(value, (int, float)) else str(value),
                    "name": name,
                    "sample_index": idx,
                }
            )
        yield entries


def _extract_path(data: Dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in [p for p in path.split(".") if p]:
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _constraints_ok(report: Dict[str, Any], constraints: List[Any]) -> bool:
    for spec in constraints:
        value = _extract_path(report, spec.path)
        if not isinstance(value, (int, float)):
            return False
        rhs = float(spec.value)
        lhs = float(value)
        if spec.op == "<=" and not (lhs <= rhs):
            return False
        if spec.op == ">=" and not (lhs >= rhs):
            return False
        if spec.op == "<" and not (lhs < rhs):
            return False
        if spec.op == ">" and not (lhs > rhs):
            return False
        if spec.op == "==" and not (lhs == rhs):
            return False
    return True


def _load_solve_report(result: Dict[str, Any]) -> Dict[str, Any]:
    out_dir = result.get("out_dir")
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


def _run_case(
    run_dict: Dict[str, Any],
    repo_root: str,
    *,
    dry_run: bool,
) -> Dict[str, Any]:
    run_config = SimStackConfig.model_validate(run_dict)
    project = Project(run_config, repo_root=Path(repo_root))

    if dry_run:
        out_root = project.output_root()
        report_path = project.write_dry_run_report(out_root / "reports")
        if run_config.outputs.write_reports:
            project.write_provenance(out_root / "reports")
        return {
            "run_hash": project.run_hash(),
            "out_dir": str(out_root),
            "dry_run_report": report_path,
            "cached": False,
        }

    return project.run()


def run_sweep(
    sweep: SweepConfig,
    repo_root: str | Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    out_dir: str | None = None,
) -> Dict[str, Any]:
    base_config = load_config(sweep.base)
    base_dict = config_to_dict(base_config)
    sweep_root = Path(out_dir) if out_dir else Path(sweep.output_directory)
    if sweep.name:
        sweep_root = sweep_root / sweep.name

    pending: List[Tuple[str, Dict[str, Any], Dict[str, Any]]] = []
    seen_labels: Dict[str, int] = {}

    for idx, entries in enumerate(
        _iter_combinations(
            sweep.parameters,
            sweep.mode,
            samples=sweep.samples,
            seed=int(sweep.seed),
        ),
        start=1,
    ):
        run_dict = copy.deepcopy(base_dict)
        labels: List[str] = []
        sweep_meta: Dict[str, Any] = {"index": idx, "parameters": {}}

        for p_idx, (param, entry) in enumerate(zip(sweep.parameters, entries)):
            raw = entry["raw"]
            value = entry["value"]
            _apply_paths(run_dict, param.path, value)

            name = _param_name(param, p_idx)
            label_val = entry["label"]
            labels.append(f"{name}={label_val}")
            sweep_meta["parameters"][name] = {
                "path": param.path,
                "raw": raw,
                "value": value,
            }

        label = _slugify("_".join(labels))
        if not label:
            label = f"run_{idx:03d}"
        if label in seen_labels:
            seen_labels[label] += 1
            label = f"{label}_{seen_labels[label]:03d}"
        else:
            seen_labels[label] = 1

        outputs = run_dict.get("outputs") or {}
        outputs["directory"] = str(sweep_root / label)
        if force:
            outputs["reuse"] = False
        run_dict["outputs"] = outputs

        metadata = run_dict.get("metadata") or {}
        sweep_meta["label"] = label
        if sweep.name:
            sweep_meta["name"] = sweep.name
        metadata["sweep"] = sweep_meta
        run_dict["metadata"] = metadata

        pending.append((label, run_dict, sweep_meta))

    runs: List[Dict[str, Any]] = []
    workers = sweep.parallel.workers
    if workers is None:
        workers = min(8, max(1, len(pending)))

    if workers > 1 and len(pending) > 1:
        try:
            with ProcessPoolExecutor(max_workers=workers) as pool:
                fut_map = {
                    pool.submit(_run_case, run_dict, str(repo_root), dry_run=dry_run): (label, meta)
                    for label, run_dict, meta in pending
                }
                for fut in as_completed(fut_map):
                    label, _meta = fut_map[fut]
                    result = fut.result()
                    result["label"] = label
                    runs.append(result)
        except Exception:
            runs = []

    if not runs:
        for label, run_dict, _meta in pending:
            result = _run_case(run_dict, str(repo_root), dry_run=dry_run)
            result["label"] = label
            runs.append(result)

    runs.sort(key=lambda item: str(item.get("label", "")))

    best: Dict[str, Any] | None = None
    if sweep.objective is not None and not dry_run:
        scored: List[Dict[str, Any]] = []
        for run in runs:
            solve_report = _load_solve_report(run)
            if not solve_report:
                continue
            if not _constraints_ok(solve_report, sweep.constraints):
                continue
            value = _extract_path(solve_report, sweep.objective.path)
            if not isinstance(value, (int, float)):
                continue
            scored.append({"label": run["label"], "objective": float(value), "out_dir": run.get("out_dir")})

        if scored:
            reverse = sweep.objective.goal == "max"
            best = sorted(scored, key=lambda item: item["objective"], reverse=reverse)[0]

    summary: Dict[str, Any] = {
        "sweep": sweep.model_dump(mode="json", exclude_none=True),
        "count": len(runs),
        "output_root": str(sweep_root),
        "runs": runs,
        "best": best,
    }

    sweep_root.mkdir(parents=True, exist_ok=True)
    report_path = sweep_root / "sweep_report.json"
    report_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    summary["report_path"] = str(report_path)

    return summary
