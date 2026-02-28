"""High-level study and exploration runners."""

from __future__ import annotations

import itertools
import json
import math
import random
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

from simstack.cache import ArtifactStore
from simstack.core.provenance import collect_versions, get_git_revision, stable_hash
from simstack.domain import StudyConfig, compile_run_ir, load_study_config, study_to_dict
from simstack.engine import DAGEngine, EngineContext
from simstack.nodes import build_nodes
from simstack.plugins import load_plugins


class StudyRunner:
    def __init__(self, config_or_path: StudyConfig | str | Path, *, repo_root: str | Path | None = None) -> None:
        if isinstance(config_or_path, StudyConfig):
            self.config = config_or_path
            self.config_path: Path | None = None
        else:
            self.config_path = Path(config_or_path)
            self.config = load_study_config(self.config_path)

        self.repo_root = Path(repo_root) if repo_root is not None else Path.cwd()

    def run_hash(self) -> str:
        return stable_hash(study_to_dict(self.config))

    def output_root(self) -> Path:
        base = Path(self.config.outputs.directory)
        run_hash = self.run_hash()
        if base.name == run_hash:
            return base
        return base / run_hash

    def _write_manifest(
        self,
        *,
        out_root: Path,
        records: List[Any],
        node_digests: Dict[str, str],
        plugin_versions: Dict[str, str | None],
        cache_root: Path,
    ) -> str:
        reports_dir = out_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        payload = {
            "run_hash": self.run_hash(),
            "config_hash": stable_hash(study_to_dict(self.config)),
            "config": study_to_dict(self.config),
            "git_revision": get_git_revision(self.repo_root),
            "package_versions": collect_versions(["cadquery", "gmsh", "dolfinx", "petsc4py", "mpi4py", "pydantic"]),
            "cache_root": str(cache_root),
            "plugin_versions": plugin_versions,
            "node_digests": node_digests,
            "nodes": [asdict(record) for record in records],
        }

        path = reports_dir / "run_manifest.json"
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return str(path)

    def _update_latest_pointer(self, out_root: Path) -> None:
        base = Path(self.config.outputs.directory)
        base.mkdir(parents=True, exist_ok=True)
        latest = base / "latest"
        if latest.exists() or latest.is_symlink():
            if latest.is_symlink() or latest.is_file():
                latest.unlink()
            else:
                return
        try:
            latest.symlink_to(out_root)
        except OSError:
            return

    def run(self, *, resumable: bool = False) -> Dict[str, Any]:
        out_root = self.output_root()
        out_root.mkdir(parents=True, exist_ok=True)

        ir = compile_run_ir(self.config)
        plugins = load_plugins()
        store = ArtifactStore(self.repo_root)
        nodes = build_nodes(ir)

        from mpi4py import MPI

        comm = MPI.COMM_WORLD
        rank = int(comm.rank)

        ctx = EngineContext(
            config=self.config,
            ir=ir,
            repo_root=self.repo_root,
            out_root=out_root,
            comm=comm,
            rank=rank,
        )

        engine = DAGEngine(
            nodes,
            store=store,
            plugin_versions=plugins.plugin_versions(),
            resumable=resumable,
        )
        result = engine.run(ctx)

        response: Dict[str, Any] | None = None
        if rank == 0:
            run_manifest = self._write_manifest(
                out_root=out_root,
                records=result.records,
                node_digests=result.node_digests,
                plugin_versions=plugins.plugin_versions(),
                cache_root=store.cache_root,
            )
            self._update_latest_pointer(out_root)

            response = {
                "run_hash": self.run_hash(),
                "out_dir": str(out_root),
                "run_manifest": run_manifest,
                "node_digests": result.node_digests,
                "outputs": result.state.get("output_paths", {}),
                "paraview_state": result.state.get("paraview_state_path"),
                "paraview_macro": result.state.get("paraview_macro_path"),
                "cache_hits": [record.id for record in result.records if record.cache_hit],
            }

        return comm.bcast(response, root=0)

    def dry_run(self) -> Dict[str, Any]:
        out_root = self.output_root()
        out_root.mkdir(parents=True, exist_ok=True)

        ir = compile_run_ir(self.config)
        plugins = load_plugins()
        store = ArtifactStore(self.repo_root)
        nodes = build_nodes(ir)

        node_digests: Dict[str, str] = {}
        records = []
        for node in nodes:
            normalized_inputs = {"deps": {dep: node_digests.get(dep) for dep in node.deps}}
            digest = store.artifact_digest(
                node_kind=node.kind,
                node_version=node.version,
                normalized_inputs=normalized_inputs,
                plugin_versions=plugins.plugin_versions(),
                config_slice=node.config_slice,
            )
            node_digests[node.id] = digest
            cache_hit = store.load(digest) is not None
            records.append(
                {
                    "id": node.id,
                    "kind": node.kind,
                    "fingerprint": digest,
                    "status": "dry-run",
                    "cache_hit": cache_hit,
                    "duration_ms": 0.0,
                    "deps": list(node.deps),
                    "outputs": {},
                }
            )

        reports_dir = out_root / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = reports_dir / "run_manifest.json"
        payload = {
            "run_hash": self.run_hash(),
            "config_hash": stable_hash(study_to_dict(self.config)),
            "config": study_to_dict(self.config),
            "git_revision": get_git_revision(self.repo_root),
            "package_versions": collect_versions(["cadquery", "gmsh", "dolfinx", "petsc4py", "mpi4py", "pydantic"]),
            "cache_root": str(store.cache_root),
            "plugin_versions": plugins.plugin_versions(),
            "node_digests": node_digests,
            "nodes": records,
            "note": "dry run only; no compute nodes executed",
        }
        manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True))

        return {
            "run_hash": self.run_hash(),
            "out_dir": str(out_root),
            "run_manifest": str(manifest_path),
            "node_digests": node_digests,
            "cache_hits": [record["id"] for record in records if record["cache_hit"]],
        }


def _set_path(data: Dict[str, Any], path: str, value: Any) -> None:
    parts = [p for p in path.split(".") if p]
    if not parts:
        raise ValueError("Empty path")
    cur: Any = data
    for idx_part, part in enumerate(parts[:-1]):
        next_part = parts[idx_part + 1]
        if isinstance(cur, list):
            try:
                idx = int(part)
            except ValueError as exc:
                raise TypeError(f"Cannot set path '{path}'") from exc
            if idx < 0:
                raise TypeError(f"Cannot set path '{path}'")
            while idx >= len(cur):
                cur.append({})
            if cur[idx] is None:
                cur[idx] = {}
            cur = cur[idx]
            continue

        if not isinstance(cur, dict):
            raise TypeError(f"Cannot set path '{path}'")
        if part not in cur or cur[part] is None:
            cur[part] = [] if next_part.isdigit() else {}
        cur = cur[part]

    leaf = parts[-1]
    if isinstance(cur, list):
        try:
            idx = int(leaf)
        except ValueError as exc:
            raise TypeError(f"Cannot set path '{path}'") from exc
        if idx < 0:
            raise TypeError(f"Cannot set path '{path}'")
        while idx >= len(cur):
            cur.append(None)
        cur[idx] = value
        return

    if not isinstance(cur, dict):
        raise TypeError(f"Cannot set path '{path}'")
    cur[leaf] = value


def _apply_paths(data: Dict[str, Any], paths: str | List[str], value: Any) -> None:
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


def _constraints_ok(report: Dict[str, Any], constraints: List[Any]) -> bool:
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


def _scale_bounds(point: Sequence[float], params: Sequence[Any]) -> List[Any]:
    out: List[Any] = []
    for value, param in zip(point, params):
        if param.bounds is None:
            raise ValueError(f"Parameter '{param.name or param.path}' is missing bounds")
        lo, hi = float(param.bounds[0]), float(param.bounds[1])
        raw = lo + (hi - lo) * float(value)
        if param.scale is not None:
            raw *= float(param.scale)
        if param.offset is not None:
            raw += float(param.offset)
        if param.transform == "deg2rad":
            raw = math.radians(raw)
        elif param.transform == "rad2deg":
            raw = math.degrees(raw)
        out.append(raw)
    return out


def _iter_exploration(params: Sequence[Any], mode: str, *, samples: int | None, seed: int) -> Iterable[List[Any]]:
    if mode in {"cartesian", "zip"}:
        value_lists = [list(param.values) for param in params]
        if mode == "zip":
            size = len(value_lists[0])
            if any(len(values) != size for values in value_lists):
                raise ValueError("zip mode requires equal-length value lists")
            for idx in range(size):
                yield [values[idx] for values in value_lists]
            return
        for combo in itertools.product(*value_lists):
            yield list(combo)
        return

    if samples is None:
        raise ValueError(f"mode '{mode}' requires samples")

    dim = len(params)
    points = _lhs_unit(samples, dim, seed) if mode == "lhs" else _sobol_unit(samples, dim, seed)
    for point in points:
        yield _scale_bounds(point, params)


class ExplorationRunner:
    def __init__(self, config_or_path: StudyConfig | str | Path, *, repo_root: str | Path | None = None) -> None:
        self.base_runner = StudyRunner(config_or_path, repo_root=repo_root)

    def run(self, *, optimize: bool = False, force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        config = self.base_runner.config
        exploration = config.exploration
        if exploration is None:
            raise ValueError("study config does not define exploration")

        base = study_to_dict(config)
        base.pop("exploration", None)
        runs: List[Dict[str, Any]] = []

        combos = _iter_exploration(
            exploration.parameters,
            exploration.mode if not optimize else "optuna",
            samples=exploration.samples,
            seed=int(exploration.seed),
        )

        for idx, values in enumerate(combos, start=1):
            run_dict = json.loads(json.dumps(base))
            labels: List[str] = []

            for param, value in zip(exploration.parameters, values):
                _apply_paths(run_dict, param.path, value)
                name = param.name or (param.path if isinstance(param.path, str) else f"param_{idx}")
                labels.append(f"{name}={value}")

            label = "_".join(labels).replace(" ", "") or f"run_{idx:03d}"
            outputs = run_dict.get("outputs") or {}
            outputs["directory"] = str(Path(exploration.output_directory) / (exploration.name or "study") / label)
            if force:
                outputs["reuse"] = False
            run_dict["outputs"] = outputs

            run_cfg = StudyConfig.model_validate(run_dict)
            if dry_run:
                runner = StudyRunner(run_cfg, repo_root=self.base_runner.repo_root)
                result = {
                    "run_hash": runner.run_hash(),
                    "out_dir": str(runner.output_root()),
                    "dry_run": True,
                }
            else:
                result = StudyRunner(run_cfg, repo_root=self.base_runner.repo_root).run()
            result["label"] = label
            runs.append(result)

            if optimize and exploration.objective is not None:
                # Optuna mode currently mapped to Sobol/LHS-like exploration.
                continue

        best: Dict[str, Any] | None = None
        if exploration.objective is not None:
            scored: List[Dict[str, Any]] = []
            for run in runs:
                report = _load_solve_report(run)
                if not report:
                    continue
                if not _constraints_ok(report, exploration.constraints):
                    continue
                value = _extract_path(report, exploration.objective.path)
                if not isinstance(value, (int, float)):
                    continue
                scored.append({"label": run["label"], "objective": float(value), "out_dir": run.get("out_dir")})

            if scored:
                reverse = exploration.objective.goal == "max"
                best = sorted(scored, key=lambda item: item["objective"], reverse=reverse)[0]

        summary = {
            "count": len(runs),
            "runs": runs,
            "best": best,
            "output_root": str(Path(exploration.output_directory) / (exploration.name or "study")),
            "dry_run": dry_run,
        }

        root = Path(summary["output_root"])
        root.mkdir(parents=True, exist_ok=True)
        report_path = root / "exploration_report.json"
        report_path.write_text(json.dumps(summary, indent=2, sort_keys=True))
        summary["report_path"] = str(report_path)
        return summary
