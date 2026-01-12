"""Material database helpers."""

from __future__ import annotations

from typing import Any, Dict

from simstack.config import MaterialsConfig


def build_matdb(materials: MaterialsConfig, tag_map: Dict[str, Dict[str, int]]) -> Dict[str, Any]:
    """Build a material database keyed by tag name and ID."""
    by_name = materials.by_tag
    by_id: Dict[int, Dict[str, Any]] = {}

    cell_map = tag_map.get("cells", {})
    for name, props in by_name.items():
        if name not in cell_map:
            raise KeyError(f"Material tag not found in cell tags: {name}")
        by_id[cell_map[name]] = props

    return {"by_name": by_name, "by_id": by_id}
