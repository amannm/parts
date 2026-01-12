"""Sweep runner utilities."""

from __future__ import annotations

import copy
import itertools
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

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


def _iter_combinations(params: Sequence[SweepParameterConfig], mode: str) -> Iterable[List[Dict[str, Any]]]:
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

    runs: List[Dict[str, Any]] = []
    seen_labels: Dict[str, int] = {}

    for idx, entries in enumerate(_iter_combinations(sweep.parameters, sweep.mode), start=1):
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

        run_config = SimStackConfig.model_validate(run_dict)
        project = Project(run_config, repo_root=Path(repo_root))

        if dry_run:
            out_root = project.output_root()
            report_path = project.write_dry_run_report(out_root / "reports")
            if run_config.outputs.write_reports:
                project.write_provenance(out_root / "reports")
            result = {
                "label": label,
                "run_hash": project.run_hash(),
                "out_dir": str(out_root),
                "dry_run_report": report_path,
                "cached": False,
            }
        else:
            result = project.run()
            result["label"] = label

        runs.append(result)

    summary: Dict[str, Any] = {
        "sweep": sweep.model_dump(mode="json", exclude_none=True),
        "count": len(runs),
        "output_root": str(sweep_root),
        "runs": runs,
    }

    sweep_root.mkdir(parents=True, exist_ok=True)
    report_path = sweep_root / "sweep_report.json"
    report_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    summary["report_path"] = str(report_path)

    return summary
