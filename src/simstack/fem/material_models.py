"""Material property model evaluation helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def evaluate_property(value: Any, variables: Dict[str, float] | None = None) -> float | Any:
    """Evaluate a property value.

    - Scalars are returned unchanged.
    - Dict models support: constant, polynomial, table.
    """
    if variables is None:
        variables = {}

    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, dict):
        return value

    model = str(value.get("model", "")).strip().lower()
    if model == "constant":
        return float(value.get("value", 0.0))

    if model == "polynomial":
        var_name = str(value.get("variable", "T"))
        x = _as_float(variables.get(var_name), _as_float(value.get("reference", 0.0)))
        x0 = _as_float(value.get("reference", 0.0))
        coeffs = value.get("coefficients", [])
        if not isinstance(coeffs, Iterable):
            return 0.0
        total = 0.0
        dx = x - x0
        for idx, coeff in enumerate(coeffs):
            total += _as_float(coeff) * (dx ** idx)
        return total

    if model == "table":
        var_name = str(value.get("variable", "T"))
        x = _as_float(variables.get(var_name), 0.0)
        points_raw = value.get("points", [])
        points = []
        for item in points_raw:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            points.append((float(item[0]), float(item[1])))
        if not points:
            return 0.0
        points.sort(key=lambda p: p[0])
        if x <= points[0][0]:
            return points[0][1]
        if x >= points[-1][0]:
            return points[-1][1]
        for i in range(len(points) - 1):
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            if x0 <= x <= x1:
                if x1 == x0:
                    return y0
                t = (x - x0) / (x1 - x0)
                return y0 + t * (y1 - y0)
        return points[-1][1]

    # Unknown model: keep old behavior by returning as-is.
    return value


def evaluate_material_map(props: Dict[str, Any], variables: Dict[str, float] | None = None) -> Dict[str, Any]:
    resolved: Dict[str, Any] = {}
    for key, value in props.items():
        resolved[key] = evaluate_property(value, variables)
    return resolved
