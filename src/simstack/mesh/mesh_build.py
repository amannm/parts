"""Gmsh mesh generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from simstack.domain.config import BoundaryLayerConfig, DistanceRefineConfig, MeshSpec, TaggingSpec
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


def _apply_mesh_options(config: MeshSpec) -> None:
    import gmsh

    if config.global_size is not None:
        gmsh.option.setNumber("Mesh.MeshSizeMin", float(config.global_size))
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(config.global_size))

    for key, value in config.gmsh_options.items():
        if isinstance(value, (int, float)):
            gmsh.option.setNumber(str(key), float(value))
        else:
            gmsh.option.setString(str(key), str(value))

    if config.curvature_refine.enabled:
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 1)
        if config.curvature_refine.min_size is not None:
            gmsh.option.setNumber("Mesh.MeshSizeMin", float(config.curvature_refine.min_size))
        if config.curvature_refine.max_size is not None:
            gmsh.option.setNumber("Mesh.MeshSizeMax", float(config.curvature_refine.max_size))


def _collect_target_entities(
    model: Any,
    *,
    names: List[str],
    tag_result: TagTransferResult,
    facet_dim: int,
    cell_dim: int,
) -> List[int]:
    """Resolve named tags into facet entities for meshing field controls."""
    selected: set[int] = set()

    for name in names:
        if name in tag_result.facet_entities:
            selected.update(int(tag) for tag in tag_result.facet_entities[name])
            continue

        if name in tag_result.cell_entities:
            for cell_tag in tag_result.cell_entities[name]:
                try:
                    boundary = model.getBoundary([(cell_dim, int(cell_tag))], oriented=False, recursive=False)
                except Exception:
                    boundary = []
                for bdim, btag in boundary:
                    if bdim == facet_dim:
                        selected.add(int(btag))
            continue

        raise KeyError(f"Unknown tag in meshing control: {name}")

    return sorted(selected)


def _apply_distance_refine_fields(
    model: Any,
    *,
    geometry_dim: int,
    tag_result: TagTransferResult,
    controls: List[DistanceRefineConfig],
) -> List[Dict[str, Any]]:
    import gmsh

    if not controls:
        return []

    facet_dim = 2 if geometry_dim == 3 else 1
    cell_dim = 3 if geometry_dim == 3 else 2

    field_ids: List[int] = []
    stats: List[Dict[str, Any]] = []

    for idx, ctrl in enumerate(controls, start=1):
        targets = _collect_target_entities(
            model,
            names=ctrl.tags,
            tag_result=tag_result,
            facet_dim=facet_dim,
            cell_dim=cell_dim,
        )

        dist_field = gmsh.model.mesh.field.add("Distance")
        if geometry_dim == 3:
            gmsh.model.mesh.field.setNumbers(dist_field, "FacesList", targets)
        else:
            gmsh.model.mesh.field.setNumbers(dist_field, "CurvesList", targets)

        thresh_field = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(thresh_field, "InField", dist_field)
        gmsh.model.mesh.field.setNumber(thresh_field, "SizeMin", float(ctrl.size_min))
        gmsh.model.mesh.field.setNumber(thresh_field, "SizeMax", float(ctrl.size_max))
        gmsh.model.mesh.field.setNumber(thresh_field, "DistMin", float(ctrl.dist_min))
        gmsh.model.mesh.field.setNumber(thresh_field, "DistMax", float(ctrl.dist_max))

        field_ids.append(thresh_field)
        stats.append(
            {
                "control_index": idx,
                "type": "distance_refine",
                "tags": list(ctrl.tags),
                "target_entities": targets,
                "distance_field": dist_field,
                "threshold_field": thresh_field,
                "size_min": float(ctrl.size_min),
                "size_max": float(ctrl.size_max),
                "dist_min": float(ctrl.dist_min),
                "dist_max": float(ctrl.dist_max),
            }
        )

    if len(field_ids) == 1:
        gmsh.model.mesh.field.setAsBackgroundMesh(field_ids[0])
    elif len(field_ids) > 1:
        min_field = gmsh.model.mesh.field.add("Min")
        gmsh.model.mesh.field.setNumbers(min_field, "FieldsList", field_ids)
        gmsh.model.mesh.field.setAsBackgroundMesh(min_field)
        stats.append({"type": "distance_refine_combine", "field": min_field, "inputs": field_ids})

    return stats


def _apply_boundary_layers(
    model: Any,
    *,
    geometry_dim: int,
    tag_result: TagTransferResult,
    layers: List[BoundaryLayerConfig],
) -> List[Dict[str, Any]]:
    import gmsh

    if not layers:
        return []

    facet_dim = 2 if geometry_dim == 3 else 1
    cell_dim = 3 if geometry_dim == 3 else 2

    stats: List[Dict[str, Any]] = []
    for idx, ctrl in enumerate(layers, start=1):
        targets = _collect_target_entities(
            model,
            names=ctrl.tags,
            tag_result=tag_result,
            facet_dim=facet_dim,
            cell_dim=cell_dim,
        )

        bl_field = gmsh.model.mesh.field.add("BoundaryLayer")
        if geometry_dim == 3:
            gmsh.model.mesh.field.setNumbers(bl_field, "FacesList", targets)
        else:
            gmsh.model.mesh.field.setNumbers(bl_field, "CurvesList", targets)

        first = float(ctrl.first_layer)
        ratio = float(ctrl.growth_rate)
        n_layers = int(ctrl.n_layers)
        thickness = first * sum(ratio ** i for i in range(max(n_layers, 1)))

        gmsh.model.mesh.field.setNumber(bl_field, "hwall_n", first)
        gmsh.model.mesh.field.setNumber(bl_field, "ratio", ratio)
        gmsh.model.mesh.field.setNumber(bl_field, "thickness", thickness)

        try:
            gmsh.model.mesh.field.setAsBoundaryLayer(bl_field)
        except Exception:
            # Older Gmsh versions may not expose setAsBoundaryLayer; keep field settings only.
            pass

        stats.append(
            {
                "control_index": idx,
                "type": "boundary_layer",
                "tags": list(ctrl.tags),
                "target_entities": targets,
                "field": bl_field,
                "first_layer": first,
                "growth_rate": ratio,
                "n_layers": n_layers,
                "thickness": thickness,
            }
        )

    return stats


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


def build_gmsh_model(
    step_path: str | Path,
    tags: TaggingSpec,
    config: MeshSpec,
    *,
    geometry_dim: int = 3,
) -> GmshBuildResult:
    import gmsh

    gmsh.model.reset()
    gmsh.model.add("simstack")

    step_path = Path(step_path)
    if not step_path.exists():
        raise FileNotFoundError(f"STEP file not found: {step_path}")

    gmsh.model.occ.importShapes(str(step_path))
    gmsh.model.occ.synchronize()

    _apply_mesh_options(config)

    tag_result = apply_tag_rules(gmsh.model, tags, geometry_dim=geometry_dim)

    facet_dim = 2 if geometry_dim == 3 else 1
    cell_dim = 3 if geometry_dim == 3 else 2

    field_stats: List[Dict[str, Any]] = []
    field_stats.extend(
        _apply_distance_refine_fields(
            gmsh.model,
            geometry_dim=geometry_dim,
            tag_result=tag_result,
            controls=config.distance_refine,
        )
    )
    field_stats.extend(
        _apply_boundary_layers(
            gmsh.model,
            geometry_dim=geometry_dim,
            tag_result=tag_result,
            layers=config.boundary_layers,
        )
    )

    facet_entities = gmsh.model.getEntities(facet_dim)
    facet_coverage = _check_tag_coverage(
        tag_result,
        facet_entities,
        require_all_facets=config.qa.require_all_facets_tagged,
        allow_overlaps=config.qa.allow_overlaps,
    )

    gmsh.model.mesh.generate(geometry_dim)

    mesh_stats = _mesh_quality_stats(config.qa.quality_bins)
    cell_entities = gmsh.model.getEntities(cell_dim)
    cell_coverage = _coverage_report(cell_entities, tag_result.cell_entities)
    mesh_stats["tag_coverage"] = {"facets": facet_coverage, "cells": cell_coverage}
    mesh_stats["field_controls"] = field_stats
    mesh_stats["tag_debug"] = tag_result.debug
    mesh_stats["geometry_dimension"] = geometry_dim

    if config.qa.min_quality is not None:
        min_quality = mesh_stats.get("min_quality")
        if min_quality is not None and min_quality < config.qa.min_quality:
            raise ValueError(
                f"Mesh quality below threshold: min {min_quality:.4g} < {config.qa.min_quality:.4g}"
            )

    return GmshBuildResult(model=gmsh.model, tag_result=tag_result, mesh_stats=mesh_stats)
