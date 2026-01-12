"""TagSpec evaluation helpers.

Tag rules are currently defined in the config schema.
"""

from __future__ import annotations

from typing import Any


def evaluate_tag_rule(rule: str, params: dict[str, Any], entity: Any) -> bool:
    """Evaluate a tag rule against a CAD/Gmsh entity (stub)."""
    raise NotImplementedError("Tag rule evaluation is not implemented yet.")
