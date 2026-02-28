"""CAD builder registry and CadQuery integration."""

from __future__ import annotations

import dataclasses as dc
from dataclasses import dataclass
import importlib
from importlib import metadata
from pathlib import Path
import sys
from typing import Any, Callable, Dict, Iterable

from pydantic import BaseModel

from simstack.config import GeometryConfig
from simstack.core.artifacts import CadArtifact
from simstack.cad.bridge import export_step


Builder = Callable[[Dict[str, Any]], Any]


@dataclass
class BuilderRegistration:
    factory: Builder
    params_model: type[BaseModel] | None = None


_BUILDERS: Dict[str, BuilderRegistration] = {}
_PLUGINS_LOADED = False
_LIBRARY_DIR = Path(__file__).resolve().parents[3] / "library"


def _entry_points(group: str) -> Iterable[metadata.EntryPoint]:
    all_eps = metadata.entry_points()
    if hasattr(all_eps, "select"):
        return list(all_eps.select(group=group))
    return list(all_eps.get(group, []))


def _register_builder(name: str, builder: Builder, params_model: type[BaseModel] | None = None) -> None:
    if name in _BUILDERS:
        raise ValueError(f"CAD builder already registered: {name}")
    _BUILDERS[name] = BuilderRegistration(factory=builder, params_model=params_model)


def register_builder(
    name: str,
    *,
    params_model: type[BaseModel] | None = None,
) -> Callable[[Builder], Builder]:
    def decorator(func: Builder) -> Builder:
        _register_builder(name, func, params_model=params_model)
        return func

    return decorator


def _load_builder_plugins() -> None:
    global _PLUGINS_LOADED
    if _PLUGINS_LOADED:
        return

    for ep in _entry_points("simstack.builders"):
        plugin = ep.load()
        if not callable(plugin):
            continue
        try:
            plugin(register_builder)
        except TypeError:
            # Fallback: entry point directly provides a builder function.
            _register_builder(ep.name, plugin)

    _PLUGINS_LOADED = True


def get_builder_params_model(name: str) -> type[BaseModel] | None:
    _load_builder_plugins()
    registration = _BUILDERS.get(name)
    if registration is None:
        return None
    return registration.params_model


def _import_library_module(module_name: str) -> Any:
    if not _LIBRARY_DIR.exists():
        raise FileNotFoundError(f"Library directory not found: {_LIBRARY_DIR}")

    path_str = str(_LIBRARY_DIR)
    inserted = False
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
        inserted = True
    try:
        return importlib.import_module(module_name)
    finally:
        if inserted:
            sys.path.remove(path_str)


def _patch_dataclass(default_obj: Any, overrides: Dict[str, Any]) -> Any:
    if not dc.is_dataclass(default_obj):
        raise TypeError(f"Expected dataclass instance, got {type(default_obj)!r}")

    updates: Dict[str, Any] = {}
    for key, value in overrides.items():
        if not hasattr(default_obj, key):
            raise KeyError(f"Unknown parameter for {type(default_obj).__name__}: {key}")
        current = getattr(default_obj, key)
        if dc.is_dataclass(current) and isinstance(value, dict):
            updates[key] = _patch_dataclass(current, value)
        else:
            updates[key] = value
    return dc.replace(default_obj, **updates)


@register_builder("block_with_hole")
def _build_block_with_hole(params: Dict[str, Any]) -> Any:
    import cadquery as cq

    length = float(params.get("length", 1.0))
    width = float(params.get("width", 1.0))
    height = float(params.get("height", 1.0))
    hole_radius = float(params.get("hole_radius", 0.0))

    wp = cq.Workplane("XY").box(length, width, height)
    if hole_radius > 0:
        wp = wp.faces(">Z").workplane().hole(2 * hole_radius)
    return wp


@register_builder("qfn")
def _build_qfn(params: Dict[str, Any]) -> Any:
    module = _import_library_module("qfn")
    model_params = module.QFNParams()
    if params:
        model_params = _patch_dataclass(model_params, params)
    return module.build_model(model_params)


@register_builder("rgy0020d")
def _build_rgy0020d(params: Dict[str, Any]) -> Any:
    module = _import_library_module("rgy0020d")
    model_params = module.RGY0020DParams()
    if params:
        model_params = _patch_dataclass(model_params, params)
    return module.build_model(model_params)


@register_builder("w61700")
def _build_w61700(params: Dict[str, Any]) -> Any:
    module = _import_library_module("W_61700")
    model_params = module.W61700Spec()
    if params:
        model_params = _patch_dataclass(model_params, params)
    return module.build_w61700(model_params)


@register_builder("ipmsm")
def _build_ipmsm(params: Dict[str, Any]) -> Any:
    module = _import_library_module("ipmsm")
    config = module.IPMSMConfig()
    if params:
        config = _patch_dataclass(config, params)
    stator, _stator_steel, _stator_varnish, rotor, _rotor_steel, _rotor_varnish, magnets = module.build_ipmsm(config)
    return module._build_combined_assembly(stator, rotor, magnets)


def build_geometry(geometry: GeometryConfig, out_dir: str | Path | None = None) -> CadArtifact:
    _load_builder_plugins()
    if geometry.builder not in _BUILDERS:
        available = ", ".join(sorted(_BUILDERS.keys()))
        raise KeyError(f"Unknown CAD builder: {geometry.builder}. Available: {available}")

    registration = _BUILDERS[geometry.builder]
    params = geometry.params
    if registration.params_model is not None:
        validated = registration.params_model.model_validate(params)
        params = validated.model_dump(mode="json", by_alias=True, exclude_none=True)

    shape = registration.factory(params)

    step_path: Path | None = None
    if out_dir is not None:
        step_path = export_step(shape, Path(out_dir), geometry.builder)

    return CadArtifact(
        shape_ref=shape,
        step_path=str(step_path) if step_path else None,
        tag_spec=None,
        bbox=None,
        units=geometry.units,
        cad_provenance={"builder": geometry.builder, "params": params},
    )
