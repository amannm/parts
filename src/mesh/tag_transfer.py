"""TagSpec evaluation and transfer to Gmsh physical groups."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
from typing import Any, Dict, Iterable, List, Tuple

from simstack.config import TagsConfig, TagRule

_AXIS_MAP = {"x": 0, "y": 1, "z": 2, 0: 0, 1: 1, 2: 2}


@dataclass
class TagTransferResult:
    tag_map: Dict[str, Dict[str, int]]
    facet_entities: Dict[str, List[int]]
    cell_entities: Dict[str, List[int]]


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
    # Use a 31-bit positive range for Gmsh physical group tags.
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


def _rule_plane(model: Any, rule: TagRule, entities: List[Tuple[int, int]], which: str) -> List[int]:
    axis = _axis_index(rule.params.get("axis"))
    global_bbox = _collect_bbox(model, entities)
    span = global_bbox[axis + 3] - global_bbox[axis]
    tol = float(rule.params.get("tol", max(span * 1e-6, 1e-9)))

    selected: List[int] = []
    for dim, tag in entities:
        bbox = model.getBoundingBox(dim, tag)
        if _matches_plane(bbox, global_bbox, axis, which, tol):
            selected.append(tag)
    return selected


def _rule_bbox_patch(model: Any, rule: TagRule, entities: List[Tuple[int, int]]) -> List[int]:
    xmin = float(rule.params.get("xmin", -math.inf))
    xmax = float(rule.params.get("xmax", math.inf))
    ymin = float(rule.params.get("ymin", -math.inf))
    ymax = float(rule.params.get("ymax", math.inf))
    zmin = float(rule.params.get("zmin", -math.inf))
    zmax = float(rule.params.get("zmax", math.inf))

    selected: List[int] = []
    for dim, tag in entities:
        bbox = model.getBoundingBox(dim, tag)
        if bbox[3] < xmin or bbox[0] > xmax:
            continue
        if bbox[4] < ymin or bbox[1] > ymax:
            continue
        if bbox[5] < zmin or bbox[2] > zmax:
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
    min_span = min(spans)
    axis = spans.index(min_span)
    normal = [0.0, 0.0, 0.0]
    normal[axis] = 1.0
    return normal[0], normal[1], normal[2]


def _rule_normal_approx(model: Any, rule: TagRule, entities: List[Tuple[int, int]]) -> List[int]:
    nx = float(rule.params.get("nx", 0.0))
    ny = float(rule.params.get("ny", 0.0))
    nz = float(rule.params.get("nz", 0.0))
    tol = float(rule.params.get("tol", 0.05))
    allow_flip = bool(rule.params.get("allow_flip", True))

    ref = (nx, ny, nz)
    norm = math.sqrt(nx * nx + ny * ny + nz * nz)
    if norm == 0:
        raise ValueError("NormalApprox requires a non-zero (nx, ny, nz)")
    ref = (nx / norm, ny / norm, nz / norm)

    selected: List[int] = []
    for dim, tag in entities:
        normal = _try_get_normal(model, dim, tag)
        if normal is None:
            bbox = model.getBoundingBox(dim, tag)
            normal = _bbox_normal(bbox)
        n_norm = math.sqrt(normal[0] ** 2 + normal[1] ** 2 + normal[2] ** 2)
        if n_norm == 0:
            continue
        normal = (normal[0] / n_norm, normal[1] / n_norm, normal[2] / n_norm)
        dot = ref[0] * normal[0] + ref[1] * normal[1] + ref[2] * normal[2]
        if allow_flip:
            dot = abs(dot)
        if dot >= 1.0 - tol:
            selected.append(tag)
    return selected


def _rule_all_volumes(entities: List[Tuple[int, int]]) -> List[int]:
    return [tag for _dim, tag in entities]


def apply_tag_rules(model: Any, tags: TagsConfig) -> TagTransferResult:
    facet_entities = model.getEntities(2)
    cell_entities = model.getEntities(3)

    facet_map: Dict[str, List[int]] = {}
    cell_map: Dict[str, List[int]] = {}
    tag_map: Dict[str, Dict[str, int]] = {"facets": {}, "cells": {}}

    used_facet_ids: set[int] = set()
    used_cell_ids: set[int] = set()

    for rule in tags.facets:
        if rule.rule == "PlaneAtMin":
            selected = _rule_plane(model, rule, facet_entities, "min")
        elif rule.rule == "PlaneAtMax":
            selected = _rule_plane(model, rule, facet_entities, "max")
        elif rule.rule == "BBoxPatch":
            selected = _rule_bbox_patch(model, rule, facet_entities)
        elif rule.rule == "NormalApprox":
            selected = _rule_normal_approx(model, rule, facet_entities)
        elif rule.rule == "AllExcept":
            names = rule.params.get("names") or rule.params.get("tags") or []
            if not names:
                raise ValueError("AllExcept requires 'names' or 'tags' list")
            excluded: set[int] = set()
            for name in names:
                if name not in facet_map:
                    raise KeyError(f"AllExcept references unknown facet tag: {name}")
                excluded.update(facet_map[name])
            selected = [tag for _dim, tag in facet_entities if tag not in excluded]
        else:
            raise NotImplementedError(f"Facet rule not implemented: {rule.rule}")

        if not selected:
            raise ValueError(f"Facet tag '{rule.name}' matched no entities")

        tag_id = _stable_tag_id(rule.name, "facet", tags.id_overrides, used_facet_ids)
        model.addPhysicalGroup(2, selected, tag_id)
        model.setPhysicalName(2, tag_id, rule.name)
        facet_map[rule.name] = selected
        tag_map["facets"][rule.name] = tag_id

    for rule in tags.cells:
        if rule.rule == "AllVolumes":
            selected = _rule_all_volumes(cell_entities)
        elif rule.rule == "BBoxPatch":
            selected = _rule_bbox_patch(model, rule, cell_entities)
        elif rule.rule == "AllExcept":
            names = rule.params.get("names") or rule.params.get("tags") or []
            if not names:
                raise ValueError("AllExcept requires 'names' or 'tags' list")
            excluded: set[int] = set()
            for name in names:
                if name not in cell_map:
                    raise KeyError(f"AllExcept references unknown cell tag: {name}")
                excluded.update(cell_map[name])
            selected = [tag for _dim, tag in cell_entities if tag not in excluded]
        else:
            raise NotImplementedError(f"Cell rule not implemented: {rule.rule}")

        if not selected:
            raise ValueError(f"Cell tag '{rule.name}' matched no entities")

        tag_id = _stable_tag_id(rule.name, "cell", tags.id_overrides, used_cell_ids)
        model.addPhysicalGroup(3, selected, tag_id)
        model.setPhysicalName(3, tag_id, rule.name)
        cell_map[rule.name] = selected
        tag_map["cells"][rule.name] = tag_id

    return TagTransferResult(tag_map=tag_map, facet_entities=facet_map, cell_entities=cell_map)
