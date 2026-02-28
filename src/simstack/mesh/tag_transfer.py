"""Typed tag rule evaluation and transfer to Gmsh physical groups."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import re
import time
from typing import Any, Dict, Iterable, List, Tuple

from simstack.config import (
    CellAllVolumesRule,
    CellBBoxPatchRule,
    CellByNameRegexRule,
    CellByVolumeRangeRule,
    CellConnectedToFacetTagRule,
    CellRule,
    FacetAdjacentToCellTagRule,
    FacetBBoxPatchRule,
    FacetByAreaRangeRule,
    FacetByNameRegexRule,
    FacetNormalApproxRule,
    FacetPlaneAtMaxRule,
    FacetPlaneAtMinRule,
    FacetRule,
    TagComposite,
    TagsConfig,
)

_AXIS_MAP = {"x": 0, "y": 1, "z": 2, 0: 0, 1: 1, 2: 2}


@dataclass
class TagTransferResult:
    tag_map: Dict[str, Dict[str, int]]
    facet_entities: Dict[str, List[int]]
    cell_entities: Dict[str, List[int]]
    debug: Dict[str, Any]


def _axis_index(axis: Any) -> int:
    if axis not in _AXIS_MAP:
        raise ValueError(f"Invalid axis: {axis}")
    return _AXIS_MAP[axis]


def _stable_tag_id(name: str, kind: str, overrides: Dict[str, int], used: set[int]) -> int:
    if name in overrides:
        tag_id = overrides[name]
        if tag_id <= 0:
            raise ValueError(f"Override ID must be positive for tag '{name}'")
        if tag_id in used:
            raise ValueError(f"Override ID collision for tag '{name}'")
        used.add(tag_id)
        return tag_id

    digest = hashlib.sha256(f"{kind}:{name}".encode("utf-8")).hexdigest()
    tag_id = int(digest[:8], 16) % (2**31 - 1)
    if tag_id == 0:
        tag_id = 1
    while tag_id in used:
        tag_id = (tag_id + 1) % (2**31 - 1)
        if tag_id == 0:
            tag_id = 1
    used.add(tag_id)
    return tag_id


def _collect_bbox(model: Any, entities: Iterable[Tuple[int, int]]) -> Tuple[float, float, float, float, float, float]:
    bbox = None
    for dim, tag in entities:
        entity_bbox = model.getBoundingBox(dim, tag)
        if bbox is None:
            bbox = list(entity_bbox)
        else:
            bbox[0] = min(bbox[0], entity_bbox[0])
            bbox[1] = min(bbox[1], entity_bbox[1])
            bbox[2] = min(bbox[2], entity_bbox[2])
            bbox[3] = max(bbox[3], entity_bbox[3])
            bbox[4] = max(bbox[4], entity_bbox[4])
            bbox[5] = max(bbox[5], entity_bbox[5])
    if bbox is None:
        raise ValueError("No entities available to compute a bounding box")
    return tuple(bbox)


def _matches_plane(
    entity_bbox: Tuple[float, float, float, float, float, float],
    global_bbox: Tuple[float, float, float, float, float, float],
    axis: int,
    which: str,
    tol: float,
) -> bool:
    axis_min = entity_bbox[axis]
    axis_max = entity_bbox[axis + 3]
    target = global_bbox[axis] if which == "min" else global_bbox[axis + 3]
    return abs(axis_min - target) <= tol and abs(axis_max - target) <= tol


def _rule_plane(model: Any, entities: List[Tuple[int, int]], axis: Any, which: str, tol: float | None) -> List[int]:
    axis_idx = _axis_index(axis)
    global_bbox = _collect_bbox(model, entities)
    span = global_bbox[axis_idx + 3] - global_bbox[axis_idx]
    eff_tol = float(tol if tol is not None else max(span * 1e-6, 1e-9))

    selected: List[int] = []
    for dim, tag in entities:
        bbox = model.getBoundingBox(dim, tag)
        if _matches_plane(bbox, global_bbox, axis_idx, which, eff_tol):
            selected.append(tag)
    return selected


def _rule_bbox_patch(
    model: Any,
    entities: List[Tuple[int, int]],
    *,
    xmin: float | None,
    xmax: float | None,
    ymin: float | None,
    ymax: float | None,
    zmin: float | None,
    zmax: float | None,
) -> List[int]:
    xmin_v = float(xmin) if xmin is not None else -math.inf
    xmax_v = float(xmax) if xmax is not None else math.inf
    ymin_v = float(ymin) if ymin is not None else -math.inf
    ymax_v = float(ymax) if ymax is not None else math.inf
    zmin_v = float(zmin) if zmin is not None else -math.inf
    zmax_v = float(zmax) if zmax is not None else math.inf

    selected: List[int] = []
    for dim, tag in entities:
        bbox = model.getBoundingBox(dim, tag)
        if bbox[3] < xmin_v or bbox[0] > xmax_v:
            continue
        if bbox[4] < ymin_v or bbox[1] > ymax_v:
            continue
        if bbox[5] < zmin_v or bbox[2] > zmax_v:
            continue
        selected.append(tag)
    return selected


def _try_get_normal(model: Any, dim: int, tag: int) -> Tuple[float, float, float] | None:
    try:
        bounds = model.getParametrizationBounds(dim, tag)
        if not bounds or len(bounds) < 4:
            return None
        umin, umax, vmin, vmax = bounds[:4]
        u = 0.5 * (umin + umax)
        v = 0.5 * (vmin + vmax)
        normal = model.getNormal(dim, tag, [u, v])
        return float(normal[0]), float(normal[1]), float(normal[2])
    except Exception:
        return None


def _bbox_normal(bbox: Tuple[float, float, float, float, float, float]) -> Tuple[float, float, float]:
    spans = [bbox[3] - bbox[0], bbox[4] - bbox[1], bbox[5] - bbox[2]]
    axis = spans.index(min(spans))
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0
    return normal[0], normal[1], normal[2]


def _rule_normal_approx(model: Any, entities: List[Tuple[int, int]], rule: FacetNormalApproxRule) -> List[int]:
    nx = float(rule.nx)
    ny = float(rule.ny)
    nz = float(rule.nz)
    tol = float(rule.tol)

    norm = math.sqrt(nx * nx + ny * ny + nz * nz)
    if norm == 0:
        raise ValueError("NormalApprox requires non-zero normal")
    ref = (nx / norm, ny / norm, nz / norm)

    selected: List[int] = []
    for dim, tag in entities:
        normal = _try_get_normal(model, dim, tag)
        if normal is None:
            normal = _bbox_normal(model.getBoundingBox(dim, tag))
        n_norm = math.sqrt(normal[0] ** 2 + normal[1] ** 2 + normal[2] ** 2)
        if n_norm == 0:
            continue
        unit = (normal[0] / n_norm, normal[1] / n_norm, normal[2] / n_norm)
        dot = ref[0] * unit[0] + ref[1] * unit[1] + ref[2] * unit[2]
        if rule.allow_flip:
            dot = abs(dot)
        if dot >= 1.0 - tol:
            selected.append(tag)
    return selected


def _entity_name(model: Any, dim: int, tag: int) -> str:
    try:
        name = model.getEntityName(dim, tag)
        if isinstance(name, str) and name:
            return name
    except Exception:
        pass
    return f"{dim}:{tag}"


def _rule_by_name_regex(model: Any, entities: List[Tuple[int, int]], pattern: str) -> List[int]:
    compiled = re.compile(pattern)
    out: List[int] = []
    for dim, tag in entities:
        if compiled.search(_entity_name(model, dim, tag)):
            out.append(tag)
    return out


def _entity_mass(model: Any, dim: int, tag: int) -> float:
    try:
        return float(model.occ.getMass(dim, tag))
    except Exception:
        return 0.0


def _rule_by_mass_range(
    model: Any,
    entities: List[Tuple[int, int]],
    *,
    min_mass: float | None,
    max_mass: float | None,
) -> List[int]:
    lo = float(min_mass) if min_mass is not None else -math.inf
    hi = float(max_mass) if max_mass is not None else math.inf
    out: List[int] = []
    for dim, tag in entities:
        mass = _entity_mass(model, dim, tag)
        if lo <= mass <= hi:
            out.append(tag)
    return out


def _boundaries(model: Any, dim: int, tag: int) -> List[int]:
    try:
        boundary = model.getBoundary([(dim, tag)], oriented=False, recursive=False)
    except Exception:
        return []
    return [btag for _bdim, btag in boundary]


def _add_physical_group(
    model: Any,
    *,
    dim: int,
    name: str,
    selected: List[int],
    overrides: Dict[str, int],
    used_ids: set[int],
    kind: str,
    tag_map: Dict[str, int],
) -> None:
    if not selected:
        raise ValueError(f"Tag '{name}' matched no entities")
    tag_id = _stable_tag_id(name, kind, overrides, used_ids)
    model.addPhysicalGroup(dim, selected, tag_id)
    model.setPhysicalName(dim, tag_id, name)
    tag_map[name] = tag_id


def _record_debug(debug_entries: List[Dict[str, Any]], *, name: str, entity: str, rule_type: str, selected: List[int], t0: float) -> None:
    debug_entries.append(
        {
            "name": name,
            "entity": entity,
            "rule": rule_type,
            "selected_count": len(selected),
            "selected_entities": sorted(int(tag) for tag in selected),
            "duration_ms": round((time.perf_counter() - t0) * 1000.0, 3),
        }
    )


def _apply_composites(
    *,
    model: Any,
    composites: List[TagComposite],
    facet_dim: int,
    cell_dim: int,
    facet_map: Dict[str, List[int]],
    cell_map: Dict[str, List[int]],
    facet_tag_map: Dict[str, int],
    cell_tag_map: Dict[str, int],
    id_overrides: Dict[str, int],
    used_facet_ids: set[int],
    used_cell_ids: set[int],
    debug_entries: List[Dict[str, Any]],
) -> None:
    for comp in composites:
        t0 = time.perf_counter()
        maps = facet_map if comp.entity == "facets" else cell_map
        if comp.entity == "facets":
            dim = facet_dim
            kind = "facet"
            tag_map = facet_tag_map
            used = used_facet_ids
        else:
            dim = cell_dim
            kind = "cell"
            tag_map = cell_tag_map
            used = used_cell_ids

        sets: List[set[int]] = []
        for name in comp.inputs:
            if name not in maps:
                raise KeyError(f"Composite '{comp.name}' references unknown {comp.entity[:-1]} tag: {name}")
            sets.append(set(maps[name]))

        if comp.op == "union":
            out = set().union(*sets)
        elif comp.op == "intersection":
            out = set(sets[0])
            for s in sets[1:]:
                out &= s
        elif comp.op == "difference":
            out = set(sets[0])
            for s in sets[1:]:
                out -= s
        else:
            raise ValueError(f"Unsupported composite op: {comp.op}")

        selected = sorted(out)
        _add_physical_group(
            model,
            dim=dim,
            name=comp.name,
            selected=selected,
            overrides=id_overrides,
            used_ids=used,
            kind=kind,
            tag_map=tag_map,
        )
        maps[comp.name] = selected
        _record_debug(
            debug_entries,
            name=comp.name,
            entity=comp.entity,
            rule_type=f"Composite:{comp.op}",
            selected=selected,
            t0=t0,
        )


def apply_tag_rules(model: Any, tags: TagsConfig, *, geometry_dim: int = 3) -> TagTransferResult:
    facet_dim = 2 if geometry_dim == 3 else 1
    cell_dim = 3 if geometry_dim == 3 else 2

    facet_entities = model.getEntities(facet_dim)
    cell_entities = model.getEntities(cell_dim)

    facet_map: Dict[str, List[int]] = {}
    cell_map: Dict[str, List[int]] = {}
    tag_map: Dict[str, Dict[str, int]] = {"facets": {}, "cells": {}}

    used_facet_ids: set[int] = set()
    used_cell_ids: set[int] = set()

    debug_entries: List[Dict[str, Any]] = []

    # Pass 1: non-cross facet rules.
    deferred_facet: List[FacetAdjacentToCellTagRule] = []
    for rule in tags.facets:
        if isinstance(rule, FacetAdjacentToCellTagRule):
            deferred_facet.append(rule)
            continue

        t0 = time.perf_counter()
        if isinstance(rule, FacetPlaneAtMinRule):
            selected = _rule_plane(model, facet_entities, rule.axis, "min", rule.tol)
        elif isinstance(rule, FacetPlaneAtMaxRule):
            selected = _rule_plane(model, facet_entities, rule.axis, "max", rule.tol)
        elif isinstance(rule, FacetBBoxPatchRule):
            selected = _rule_bbox_patch(
                model,
                facet_entities,
                xmin=rule.xmin,
                xmax=rule.xmax,
                ymin=rule.ymin,
                ymax=rule.ymax,
                zmin=rule.zmin,
                zmax=rule.zmax,
            )
        elif isinstance(rule, FacetNormalApproxRule):
            selected = _rule_normal_approx(model, facet_entities, rule)
        elif isinstance(rule, FacetByNameRegexRule):
            selected = _rule_by_name_regex(model, facet_entities, rule.pattern)
        elif isinstance(rule, FacetByAreaRangeRule):
            selected = _rule_by_mass_range(model, facet_entities, min_mass=rule.min_area, max_mass=rule.max_area)
        else:
            raise TypeError(f"Unsupported facet rule type: {type(rule)!r}")

        _add_physical_group(
            model,
            dim=facet_dim,
            name=rule.name,
            selected=selected,
            overrides=tags.id_overrides,
            used_ids=used_facet_ids,
            kind="facet",
            tag_map=tag_map["facets"],
        )
        facet_map[rule.name] = sorted(selected)
        _record_debug(
            debug_entries,
            name=rule.name,
            entity="facets",
            rule_type=rule.type,
            selected=selected,
            t0=t0,
        )

    # Pass 1: non-cross cell rules.
    deferred_cell: List[CellConnectedToFacetTagRule] = []
    for rule in tags.cells:
        if isinstance(rule, CellConnectedToFacetTagRule):
            deferred_cell.append(rule)
            continue

        t0 = time.perf_counter()
        if isinstance(rule, CellAllVolumesRule):
            selected = [tag for _dim, tag in cell_entities]
        elif isinstance(rule, CellBBoxPatchRule):
            selected = _rule_bbox_patch(
                model,
                cell_entities,
                xmin=rule.xmin,
                xmax=rule.xmax,
                ymin=rule.ymin,
                ymax=rule.ymax,
                zmin=rule.zmin,
                zmax=rule.zmax,
            )
        elif isinstance(rule, CellByNameRegexRule):
            selected = _rule_by_name_regex(model, cell_entities, rule.pattern)
        elif isinstance(rule, CellByVolumeRangeRule):
            selected = _rule_by_mass_range(model, cell_entities, min_mass=rule.min_volume, max_mass=rule.max_volume)
        else:
            raise TypeError(f"Unsupported cell rule type: {type(rule)!r}")

        _add_physical_group(
            model,
            dim=cell_dim,
            name=rule.name,
            selected=selected,
            overrides=tags.id_overrides,
            used_ids=used_cell_ids,
            kind="cell",
            tag_map=tag_map["cells"],
        )
        cell_map[rule.name] = sorted(selected)
        _record_debug(
            debug_entries,
            name=rule.name,
            entity="cells",
            rule_type=rule.type,
            selected=selected,
            t0=t0,
        )

    # Pass 2: cross-entity rules.
    for rule in deferred_facet:
        t0 = time.perf_counter()
        if rule.cell_tag not in cell_map:
            raise KeyError(f"AdjacentToCellTag references unknown cell tag: {rule.cell_tag}")
        cell_set = set(cell_map[rule.cell_tag])
        adjacent: set[int] = set()
        for dim, tag in cell_entities:
            if tag not in cell_set:
                continue
            for btag in _boundaries(model, dim, tag):
                adjacent.add(int(btag))
        selected = sorted(adjacent)
        _add_physical_group(
            model,
            dim=facet_dim,
            name=rule.name,
            selected=selected,
            overrides=tags.id_overrides,
            used_ids=used_facet_ids,
            kind="facet",
            tag_map=tag_map["facets"],
        )
        facet_map[rule.name] = selected
        _record_debug(
            debug_entries,
            name=rule.name,
            entity="facets",
            rule_type=rule.type,
            selected=selected,
            t0=t0,
        )

    for rule in deferred_cell:
        t0 = time.perf_counter()
        if rule.facet_tag not in facet_map:
            raise KeyError(f"ConnectedToFacetTag references unknown facet tag: {rule.facet_tag}")
        facet_set = set(facet_map[rule.facet_tag])
        connected: List[int] = []
        for dim, ctag in cell_entities:
            boundary = _boundaries(model, dim, ctag)
            if any(btag in facet_set for btag in boundary):
                connected.append(int(ctag))
        selected = sorted(set(connected))
        _add_physical_group(
            model,
            dim=cell_dim,
            name=rule.name,
            selected=selected,
            overrides=tags.id_overrides,
            used_ids=used_cell_ids,
            kind="cell",
            tag_map=tag_map["cells"],
        )
        cell_map[rule.name] = selected
        _record_debug(
            debug_entries,
            name=rule.name,
            entity="cells",
            rule_type=rule.type,
            selected=selected,
            t0=t0,
        )

    _apply_composites(
        model=model,
        composites=tags.composites,
        facet_dim=facet_dim,
        cell_dim=cell_dim,
        facet_map=facet_map,
        cell_map=cell_map,
        facet_tag_map=tag_map["facets"],
        cell_tag_map=tag_map["cells"],
        id_overrides=tags.id_overrides,
        used_facet_ids=used_facet_ids,
        used_cell_ids=used_cell_ids,
        debug_entries=debug_entries,
    )

    debug_payload = {
        "geometry_dimension": geometry_dim,
        "facet_dimension": facet_dim,
        "cell_dimension": cell_dim,
        "rules": debug_entries,
    }

    return TagTransferResult(tag_map=tag_map, facet_entities=facet_map, cell_entities=cell_map, debug=debug_payload)
