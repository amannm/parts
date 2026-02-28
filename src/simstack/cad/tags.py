"""TagSpec helpers for CAD-side rule evaluation.

These utilities are intentionally lightweight and dependency-free so they can
be reused by pre-mesh geometry workflows and tests.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence

_AXIS_MAP = {"x": 0, "y": 1, "z": 2, 0: 0, 1: 1, 2: 2}


@dataclass(frozen=True)
class TagRuleContext:
    global_bbox: tuple[float, float, float, float, float, float] | None = None
    selected_tags: Mapping[str, set[int]] | None = None


def _axis_index(axis: Any) -> int:
    if axis not in _AXIS_MAP:
        raise ValueError(f"Invalid axis: {axis}")
    return _AXIS_MAP[axis]


def _entity_value(entity: Any, key: str) -> Any:
    if isinstance(entity, Mapping):
        return entity.get(key)
    return getattr(entity, key, None)


def _entity_bbox(entity: Any) -> tuple[float, float, float, float, float, float]:
    bbox = _entity_value(entity, "bbox")
    if bbox is None:
        bbox = _entity_value(entity, "bounds")
    if bbox is None and isinstance(entity, Sequence) and len(entity) == 6:
        bbox = entity
    if bbox is None or len(bbox) != 6:
        raise ValueError("Entity must expose a 6-value bbox/bounds")
    return tuple(float(v) for v in bbox)


def _entity_id(entity: Any) -> int | None:
    for key in ("tag", "id", "entity_id"):
        value = _entity_value(entity, key)
        if value is not None:
            return int(value)
    return None


def _entity_dim(entity: Any) -> int | None:
    value = _entity_value(entity, "dim")
    if value is None:
        return None
    return int(value)


def _entity_normal(entity: Any) -> tuple[float, float, float] | None:
    normal = _entity_value(entity, "normal")
    if normal is None:
        return None
    if len(normal) != 3:
        raise ValueError("Entity normal must have three components")
    return float(normal[0]), float(normal[1]), float(normal[2])


def _bbox_union(entities: Sequence[Any]) -> tuple[float, float, float, float, float, float]:
    if not entities:
        raise ValueError("Cannot compute a global bbox from an empty entity sequence")
    bboxes = [_entity_bbox(entity) for entity in entities]
    mins = [min(values) for values in zip(*(bbox[:3] for bbox in bboxes))]
    maxs = [max(values) for values in zip(*(bbox[3:] for bbox in bboxes))]
    return mins[0], mins[1], mins[2], maxs[0], maxs[1], maxs[2]


def _norm3(vec: tuple[float, float, float]) -> float:
    return math.sqrt(vec[0] ** 2 + vec[1] ** 2 + vec[2] ** 2)


def _bbox_intersects(
    bbox: tuple[float, float, float, float, float, float],
    *,
    xmin: float,
    xmax: float,
    ymin: float,
    ymax: float,
    zmin: float,
    zmax: float,
) -> bool:
    if bbox[3] < xmin or bbox[0] > xmax:
        return False
    if bbox[4] < ymin or bbox[1] > ymax:
        return False
    if bbox[5] < zmin or bbox[2] > zmax:
        return False
    return True


def evaluate_tag_rule(
    rule: str,
    params: dict[str, Any],
    entity: Any,
    *,
    context: TagRuleContext | None = None,
) -> bool:
    """Evaluate a TagSpec rule for a single CAD entity."""
    context = context or TagRuleContext()
    rule_name = rule.strip()

    if rule_name in {"PlaneAtMin", "PlaneAtMax"}:
        axis = _axis_index(params.get("axis"))
        bbox = _entity_bbox(entity)
        global_bbox = params.get("global_bbox") or context.global_bbox
        if global_bbox is None:
            raise ValueError(f"{rule_name} requires a global_bbox in params or context")
        span = float(global_bbox[axis + 3] - global_bbox[axis])
        tol = float(params.get("tol", max(span * 1e-6, 1e-9)))
        target = float(global_bbox[axis] if rule_name == "PlaneAtMin" else global_bbox[axis + 3])
        return abs(bbox[axis] - target) <= tol and abs(bbox[axis + 3] - target) <= tol

    if rule_name == "BBoxPatch":
        bbox = _entity_bbox(entity)
        return _bbox_intersects(
            bbox,
            xmin=float(params.get("xmin", -math.inf)),
            xmax=float(params.get("xmax", math.inf)),
            ymin=float(params.get("ymin", -math.inf)),
            ymax=float(params.get("ymax", math.inf)),
            zmin=float(params.get("zmin", -math.inf)),
            zmax=float(params.get("zmax", math.inf)),
        )

    if rule_name == "NormalApprox":
        normal = _entity_normal(entity)
        if normal is None:
            raise ValueError("NormalApprox requires entity.normal to be provided")
        ref = (
            float(params.get("nx", 0.0)),
            float(params.get("ny", 0.0)),
            float(params.get("nz", 0.0)),
        )
        ref_norm = _norm3(ref)
        if ref_norm == 0.0:
            raise ValueError("NormalApprox requires non-zero (nx, ny, nz)")
        n_norm = _norm3(normal)
        if n_norm == 0.0:
            return False
        unit_ref = (ref[0] / ref_norm, ref[1] / ref_norm, ref[2] / ref_norm)
        unit_n = (normal[0] / n_norm, normal[1] / n_norm, normal[2] / n_norm)
        dot = unit_ref[0] * unit_n[0] + unit_ref[1] * unit_n[1] + unit_ref[2] * unit_n[2]
        if bool(params.get("allow_flip", True)):
            dot = abs(dot)
        tol = float(params.get("tol", 0.05))
        return dot >= 1.0 - tol

    if rule_name == "AllVolumes":
        dim = _entity_dim(entity)
        return dim == 3 if dim is not None else True

    if rule_name == "AllExcept":
        excluded_ids = {int(v) for v in params.get("excluded_ids", [])}
        names = params.get("names") or params.get("tags") or []
        if names:
            if context.selected_tags is None:
                raise ValueError("AllExcept with names requires context.selected_tags")
            for name in names:
                if name not in context.selected_tags:
                    raise KeyError(f"AllExcept references unknown tag name: {name}")
                excluded_ids.update(context.selected_tags[name])
        entity_id = _entity_id(entity)
        if entity_id is None:
            raise ValueError("AllExcept requires entities with tag/id/entity_id")
        return entity_id not in excluded_ids

    raise NotImplementedError(f"Unsupported CAD tag rule: {rule_name}")


def select_entities(
    rule: str,
    params: dict[str, Any],
    entities: Sequence[Any],
    *,
    context: TagRuleContext | None = None,
) -> list[Any]:
    """Filter entities using a TagSpec rule."""
    if not entities:
        return []

    context = context or TagRuleContext()
    if rule in {"PlaneAtMin", "PlaneAtMax"} and context.global_bbox is None and "global_bbox" not in params:
        context = TagRuleContext(global_bbox=_bbox_union(entities), selected_tags=context.selected_tags)

    return [
        entity
        for entity in entities
        if evaluate_tag_rule(rule, params, entity, context=context)
    ]
