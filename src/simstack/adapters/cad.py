"""CAD node adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from simstack.cad.build import build_geometry


def run_cad(ctx: Any) -> Dict[str, Any]:
    step_path = None
    cad_provenance: Dict[str, Any] | None = None

    if ctx.rank == 0:
        artifact = build_geometry(ctx.config.geometry, out_dir=Path(ctx.out_root) / "cad")
        step_path = artifact.step_path
        cad_provenance = artifact.cad_provenance
        if step_path is None:
            raise RuntimeError("CAD builder did not produce a STEP path")

    step_path = ctx.comm.bcast(step_path, root=0)
    cad_provenance = ctx.comm.bcast(cad_provenance, root=0)

    state_updates = {
        "cad_step_path": step_path,
        "cad_provenance": cad_provenance or {},
    }
    return {
        "state_updates": state_updates,
        "cache_payload": state_updates,
        "outputs": {"step": step_path},
    }


def hydrate_cad(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "cad_step_path": payload.get("cad_step_path"),
        "cad_provenance": payload.get("cad_provenance", {}),
    }
