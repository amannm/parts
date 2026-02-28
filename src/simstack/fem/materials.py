"""Material database helpers."""

from __future__ import annotations

from typing import Any, Dict

from simstack.domain.config import MaterialsSpec
from simstack.fem.material_models import evaluate_material_map


def build_matdb(
    materials: MaterialsSpec,
    tag_map: Dict[str, Dict[str, int]],
    *,
    variables: Dict[str, float] | None = None,
) -> Dict[str, Any]:
    """Build a material database keyed by tag name and ID.

    Property-model dicts are evaluated to scalar values using runtime variables
    when provided.
    """
    by_name_raw = materials.by_tag
    by_name: Dict[str, Dict[str, Any]] = {}
    by_id: Dict[int, Dict[str, Any]] = {}

    cell_map = tag_map.get("cells", {})
    for name, props in by_name_raw.items():
        if name not in cell_map:
            raise KeyError(f"Material tag not found in cell tags: {name}")
        resolved = evaluate_material_map(props, variables)
        by_name[name] = resolved
        by_id[cell_map[name]] = resolved

    return {"by_name": by_name, "by_id": by_id}
