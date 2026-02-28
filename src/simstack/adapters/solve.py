"""Solve node adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from simstack.io.write import build_tag_fields, write_outputs
from simstack.workflow.engine import run_workflow


def run_solve(ctx: Any) -> Dict[str, Any]:
    mesh = ctx.state.get("mesh")
    cell_tags = ctx.state.get("cell_tags")
    facet_tags = ctx.state.get("facet_tags")
    tag_map = ctx.state.get("tag_map")

    if mesh is None or cell_tags is None or facet_tags is None or tag_map is None:
        raise RuntimeError("Missing mesh state required for solve")

    solve_artifact = run_workflow(
        mesh,
        cell_tags,
        facet_tags,
        ctx.config,
        tag_map,
    )

    fields = dict(solve_artifact.fields)
    if ctx.config.outputs.write_tag_fields:
        fields.update(build_tag_fields(mesh, cell_tags))

    output_paths = write_outputs(
        mesh,
        fields,
        out_dir=ctx.out_root,
        fmt=ctx.config.outputs.format,
    )
    field_names = sorted(fields.keys())

    solve_report_path = None
    if ctx.rank == 0 and ctx.config.outputs.write_reports:
        report_dir = Path(ctx.out_root) / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "solve_report.json"
        report_path.write_text(json.dumps(solve_artifact.solver_report, indent=2, sort_keys=True))
        solve_report_path = str(report_path)

    solve_report_path = ctx.comm.bcast(solve_report_path, root=0)

    state_updates = {
        "output_paths": output_paths,
        "field_names": field_names,
        "solve_report_path": solve_report_path,
    }

    outputs = {
        "formats": [fmt for fmt, data in output_paths.items() if data],
        "field_count": len(field_names),
        "solve_report": solve_report_path,
    }

    return {
        "state_updates": state_updates,
        "cache_payload": state_updates,
        "outputs": outputs,
    }


def hydrate_solve(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "output_paths": payload.get("output_paths", {}),
        "field_names": payload.get("field_names", []),
        "solve_report_path": payload.get("solve_report_path"),
    }
