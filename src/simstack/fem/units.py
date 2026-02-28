"""Unit validation and normalization helpers."""

from __future__ import annotations

from typing import Any, Dict

from simstack.config import SimStackConfig


def _get_ureg():
    try:
        import pint
    except Exception:
        return None
    return pint.UnitRegistry()


def validate_config_units(config: Dict[str, Any]) -> None:
    """Validate unit strings in config.units.inputs.

    This intentionally validates syntax and convertibility, but leaves
    dimension-specific physical checks to dedicated validators.
    """
    units_cfg = config.get("units") or {}
    if not isinstance(units_cfg, dict):
        return
    inputs = units_cfg.get("inputs") or {}
    if not isinstance(inputs, dict) or not inputs:
        return

    ureg = _get_ureg()
    if ureg is None:
        return

    for path, unit in inputs.items():
        if not isinstance(path, str) or not isinstance(unit, str):
            raise ValueError("units.inputs must map path strings to unit strings")
        try:
            q = 1.0 * ureg(unit)
            _ = q.to_base_units()
        except Exception as exc:
            raise ValueError(f"Invalid unit for '{path}': {unit}") from exc


def normalize_config_units(config: SimStackConfig) -> SimStackConfig:
    """Normalize unit metadata.

    In v2, internal units are SI; for now this preserves config and acts as
    a stable hook for future numerical conversion at load time.
    """
    if config.units.internal_system != "SI":
        raise ValueError("Only SI internal system is currently supported")
    return config


def extract_material_variables(config_dict: Dict[str, Any]) -> Dict[str, float]:
    """Extract common runtime variables for material model evaluation."""
    out: Dict[str, float] = {}

    physics = config_dict.get("physics") or {}
    params = physics.get("parameters") if isinstance(physics, dict) else {}
    if isinstance(params, dict):
        temp = params.get("temperature")
        freq = params.get("frequency")
        if isinstance(temp, (int, float)):
            out["T"] = float(temp)
        if isinstance(freq, (int, float)):
            out["f"] = float(freq)

    return out
