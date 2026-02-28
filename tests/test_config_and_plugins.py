from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from simstack.cad.build import build_geometry, register_builder
from simstack.config import (
    GeometryConfig,
    HeatTransientParameters,
    PhysicsConfig,
    register_physics_parameter_model,
)
from simstack.core.registry import Registry


def test_builtin_physics_parameters_are_typed() -> None:
    cfg = PhysicsConfig.model_validate(
        {
            "model": "heat_transient",
            "parameters": {
                "time": {"dt": 0.1, "t_end": 1.0},
                "targets": {"tag": "solid", "temperature": 350.0},
            },
        }
    )
    assert isinstance(cfg.parameters, HeatTransientParameters)
    params = cfg.parameters_dict()
    assert params["targets"][0]["tag"] == "solid"
    assert params["time"]["dt"] == 0.1


def test_typed_physics_validation_rejects_invalid_target_mode() -> None:
    with pytest.raises(ValidationError):
        PhysicsConfig.model_validate(
            {
                "model": "heat_transient",
                "parameters": {
                    "targets": {"tag": "solid", "temperature": 350.0, "mode": "peak"},
                },
            }
        )


def test_registry_registers_plugin_parameter_schema() -> None:
    class DummyParams(BaseModel):
        model_config = ConfigDict(extra="forbid")
        alpha: float

    registry = Registry()
    model_name = f"dummy_{uuid4().hex}"
    try:
        registry.register_physics(model_name, lambda: object(), parameters_model=DummyParams)
        cfg = PhysicsConfig.model_validate({"model": model_name, "parameters": {"alpha": 3.5}})
        assert isinstance(cfg.parameters, DummyParams)
        assert cfg.parameters.alpha == 3.5
    finally:
        register_physics_parameter_model(model_name, None)


def test_custom_builder_registration_supports_parameter_schema() -> None:
    class BuilderParams(BaseModel):
        model_config = ConfigDict(extra="forbid")
        radius: float

    builder_name = f"unit_builder_{uuid4().hex}"

    @register_builder(builder_name, params_model=BuilderParams)
    def _build(params):
        return {"shape": "dummy", "params": params}

    cfg = GeometryConfig.model_validate({"builder": builder_name, "params": {"radius": 2.0}})
    artifact = build_geometry(cfg, out_dir=None)
    assert artifact.cad_provenance["builder"] == builder_name
    assert artifact.shape_ref["params"]["radius"] == 2.0

    with pytest.raises(ValidationError):
        GeometryConfig.model_validate({"builder": builder_name, "params": {"diameter": 4.0}})
