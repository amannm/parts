"""Gmsh mesh generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from simstack.config import MeshingConfig, TagsConfig
from simstack.mesh.tag_transfer import TagTransferResult, apply_tag_rules


@dataclass
class GmshBuildResult:
    model: Any
    tag_result: TagTransferResult
    mesh_stats: Dict[str, Any]


class GmshSession:
    """Context manager to ensure Gmsh is finalized."""

    def __init__(self) -> None:
        self._initialized_here = False

    def __enter__(self) -> None:
        import gmsh  # local import to avoid hard dependency for dry-run

        if not gmsh.isInitialized():
            gmsh.initialize()
            self._initialized_here = True
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        import gmsh

        if self._initialized_here:
            gmsh.finalize()


def _apply_mesh_options(config: MeshingConfig) -> None:
    import gmsh

    if config.global_size is not None:
        gmsh.option.setNumber("Mesh.MeshSizeMin", float(config.global_size))
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(config.global_size))

    for key, value in config.gmsh_options.items():
        if isinstance(value, (int, float)):
            gmsh.option.setNumber(str(key), float(value))
        else:
            gmsh.option.setString(str(key), str(value))


def _coverage_report(
    entities: list[tuple[int, int]],
    tag_map: Dict[str, List[int]],
) -> Dict[str, Any]:
    counts: Dict[int, int] = {tag: 0 for _dim, tag in entities}
    per_tag_counts: Dict[str, int] = {}
    for name, selected in tag_map.items():
        per_tag_counts[name] = len(selected)
        for tag in selected:
            counts[tag] = counts.get(tag, 0) + 1

    missing = [tag for tag, count in counts.items() if count == 0]
    overlaps = [tag for tag, count in counts.items() if count > 1]

    return {
        "total_entities": len(entities),
        "tagged_entities": len([tag for tag, count in counts.items() if count > 0]),
        "missing_entities": missing,
        "overlap_entities": overlaps,
        "per_tag_counts": per_tag_counts,
    }


def _check_tag_coverage(
    tag_result: TagTransferResult,
    facet_entities: list[tuple[int, int]],
    require_all_facets: bool,
    allow_overlaps: bool,
) -> Dict[str, Any]:
    report = _coverage_report(facet_entities, tag_result.facet_entities)

    if require_all_facets and report["missing_entities"]:
        raise ValueError(f"Facet coverage incomplete; missing {len(report['missing_entities'])} facets")

    if not allow_overlaps and report["overlap_entities"]:
        raise ValueError(f"Facet overlap detected for {len(report['overlap_entities'])} facets")

    return report


def _mesh_quality_histogram(values: list[float], bins: int) -> Dict[str, Any]:
    if not values:
        return {}
    if bins <= 0:
        bins = 10
    vmin = min(values)
    vmax = max(values)
    if vmax == vmin:
        return {"bins": [vmin, vmax], "counts": [len(values)]}
    step = (vmax - vmin) / bins
    edges = [vmin + i * step for i in range(bins + 1)]
    counts = [0 for _ in range(bins)]
    for v in values:
        idx = min(int((v - vmin) / step), bins - 1)
        counts[idx] += 1
    return {"bins": edges, "counts": counts}


def _mesh_quality_stats(bins: int) -> Dict[str, Any]:
    import gmsh

    try:
        qualities = gmsh.model.mesh.getElementQualities()
    except Exception:
        return {}
    if not qualities:
        return {}
    qmin = min(qualities)
    qmax = max(qualities)
    qavg = sum(qualities) / len(qualities)
    hist = _mesh_quality_histogram(list(qualities), bins)
    return {
        "min_quality": qmin,
        "max_quality": qmax,
        "avg_quality": qavg,
        "count": len(qualities),
        "histogram": hist,
    }


def build_gmsh_model(step_path: str | Path, tags: TagsConfig, config: MeshingConfig) -> GmshBuildResult:
    import gmsh

    gmsh.model.reset()
    gmsh.model.add("simstack")

    step_path = Path(step_path)
    if not step_path.exists():
        raise FileNotFoundError(f"STEP file not found: {step_path}")

    gmsh.model.occ.importShapes(str(step_path))
    gmsh.model.occ.synchronize()

    _apply_mesh_options(config)

    tag_result = apply_tag_rules(gmsh.model, tags)

    facet_entities = gmsh.model.getEntities(2)
    facet_coverage = _check_tag_coverage(
        tag_result,
        facet_entities,
        require_all_facets=config.qa.require_all_facets_tagged,
        allow_overlaps=config.qa.allow_overlaps,
    )

    gmsh.model.mesh.generate(3)

    mesh_stats = _mesh_quality_stats(config.qa.quality_bins)
    cell_entities = gmsh.model.getEntities(3)
    cell_coverage = _coverage_report(cell_entities, tag_result.cell_entities)
    mesh_stats["tag_coverage"] = {"facets": facet_coverage, "cells": cell_coverage}
    if config.qa.min_quality is not None:
        min_quality = mesh_stats.get("min_quality")
        if min_quality is not None and min_quality < config.qa.min_quality:
            raise ValueError(
                f"Mesh quality below threshold: min {min_quality:.4g} < {config.qa.min_quality:.4g}"
            )

    return GmshBuildResult(model=gmsh.model, tag_result=tag_result, mesh_stats=mesh_stats)
