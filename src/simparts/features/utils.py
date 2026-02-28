from __future__ import annotations

import cadquery as cq


def color_from(
    value: str | tuple[float, float, float] | tuple[float, float, float, float] | None,
    fallback: tuple[float, float, float, float],
) -> cq.Color:
    if value is None:
        value = fallback
    if isinstance(value, str):
        return cq.Color(value)
    if isinstance(value, (list, tuple)):
        if len(value) == 3:
            return cq.Color(*value)
        if len(value) == 4:
            return cq.Color(*value)
    return cq.Color(*fallback)


def validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive.")


def validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")
