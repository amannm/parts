"""TagSpec evaluation and transfer to Gmsh physical groups."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
