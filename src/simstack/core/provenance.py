"""Provenance capture and hashing helpers."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import platform
import subprocess
import sys
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, Iterable, Optional


def _json_dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, default=str, separators=(",", ":"))


def stable_hash(data: Any) -> str:
    payload = _json_dumps(data).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_git_revision(root: str | Path) -> Optional[str]:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return None
    return completed.stdout.strip() or None


def collect_versions(packages: Iterable[str]) -> Dict[str, Optional[str]]:
    versions: Dict[str, Optional[str]] = {}
    for name in packages:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def build_stage_hashes(config_dict: Dict[str, Any]) -> Dict[str, str]:
    geometry = config_dict.get("geometry", {})
    tags = config_dict.get("tags", {})
    meshing = config_dict.get("meshing", {})
    physics = config_dict.get("physics", {})
    materials = config_dict.get("materials", {})
    bcs = config_dict.get("bcs", {})
    solver = config_dict.get("solver", {})
    workflow = config_dict.get("workflow", {})
    units = config_dict.get("units", {})
    outputs = config_dict.get("outputs", {})

    cad_payload = {"geometry": geometry}
    cad_hash = stable_hash(cad_payload)

    mesh_payload = {
        "cad_hash": cad_hash,
        "tags": tags,
        "meshing": meshing,
    }
    mesh_hash = stable_hash(mesh_payload)

    solve_payload = {
        "mesh_hash": mesh_hash,
        "physics": physics,
        "materials": materials,
        "bcs": bcs,
        "solver": solver,
        "workflow": workflow,
        "units": units,
    }
    solve_hash = stable_hash(solve_payload)

    post_payload = {
        "solve_hash": solve_hash,
        "outputs": outputs,
    }
    post_hash = stable_hash(post_payload)

    return {
        "cad": cad_hash,
        "mesh": mesh_hash,
        "solve": solve_hash,
        "post": post_hash,
    }


def build_provenance(
    config_dict: Dict[str, Any],
    repo_root: str | Path,
    *,
    tag_map: Optional[Dict[str, Dict[str, int]]] = None,
    mesh_stats: Optional[Dict[str, Any]] = None,
    tag_legend_path: Optional[str] = None,
    stage_hashes: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    timestamp = _dt.datetime.now(_dt.timezone.utc).isoformat()
    packages = [
        "cadquery",
        "gmsh",
        "dolfinx",
        "ufl",
        "petsc4py",
        "mpi4py",
        "pyyaml",
        "pydantic",
    ]
    provenance: Dict[str, Any] = {
        "timestamp": timestamp,
        "python": sys.version,
        "platform": platform.platform(),
        "git_revision": get_git_revision(repo_root),
        "package_versions": collect_versions(packages),
        "config_hash": stable_hash(config_dict),
        "stage_hashes": stage_hashes or build_stage_hashes(config_dict),
        "config": config_dict,
    }
    if tag_map is not None:
        provenance["tag_map"] = tag_map
    if mesh_stats is not None:
        provenance["mesh_stats"] = mesh_stats
    if tag_legend_path is not None:
        provenance["tag_legend"] = tag_legend_path
    return provenance
