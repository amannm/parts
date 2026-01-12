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


def build_provenance(
    config_dict: Dict[str, Any],
    repo_root: str | Path,
    *,
    tag_map: Optional[Dict[str, Dict[str, int]]] = None,
    mesh_stats: Optional[Dict[str, Any]] = None,
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
        "config": config_dict,
    }
    if tag_map is not None:
        provenance["tag_map"] = tag_map
    if mesh_stats is not None:
        provenance["mesh_stats"] = mesh_stats
    return provenance
