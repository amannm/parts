from __future__ import annotations

from pathlib import Path

import pytest

from simstack.config import SimStackConfig
from simstack.core.pipeline import RunContext, Stage, StagePipeline


class _FakeComm:
    def bcast(self, value, root=0):  # noqa: ARG002
        return value


def _minimal_config() -> SimStackConfig:
    return SimStackConfig.model_validate(
        {
            "geometry": {"builder": "block_with_hole", "params": {}},
            "physics": {"model": "poisson", "parameters": {}},
        }
    )


class _DummyStage(Stage):
    def __init__(self, name: str, deps: tuple[str, ...] = ()) -> None:
        self.name = name
        self.deps = deps

    def fingerprint_payload(self, ctx: RunContext):
        return {"stage": self.name, "deps": list(self.deps), "seed": ctx.get("seed", 0)}

    def run(self, ctx: RunContext) -> None:
        order = list(ctx.get("order", []))
        order.append(self.name)
        ctx.set("order", order)

    def outputs(self, ctx: RunContext):
        return {"index": len(ctx.get("order", []))}


def _ctx() -> RunContext:
    return RunContext(
        config=_minimal_config(),
        repo_root=Path.cwd(),
        out_root=Path.cwd() / "out",
        comm=_FakeComm(),
        rank=0,
    )


def test_pipeline_topologically_orders_stages() -> None:
    pipeline = StagePipeline(
        [
            _DummyStage("post", deps=("solve",)),
            _DummyStage("cad"),
            _DummyStage("solve", deps=("mesh",)),
            _DummyStage("mesh", deps=("cad",)),
        ]
    )
    ctx = _ctx()
    records = pipeline.run(ctx)

    assert ctx.get("order") == ["cad", "mesh", "solve", "post"]
    assert [record.name for record in records] == ["cad", "mesh", "solve", "post"]
    assert all(record.status == "ok" for record in records)


def test_pipeline_rejects_missing_dependency() -> None:
    with pytest.raises(ValueError, match="Unknown stage dependency"):
        StagePipeline([_DummyStage("solve", deps=("mesh",))])


def test_pipeline_rejects_duplicate_stage_names() -> None:
    with pytest.raises(ValueError, match="Duplicate stage name"):
        StagePipeline([_DummyStage("cad"), _DummyStage("cad")])
