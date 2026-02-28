from __future__ import annotations

from pathlib import Path

import pytest

from simstack.config import load_config, load_sweep_config


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "examples" / "configs"


def _regular_config_paths() -> list[Path]:
    return sorted(path for path in EXAMPLES_DIR.glob("*.yaml") if "sweep" not in path.name)


def _sweep_config_paths() -> list[Path]:
    return sorted(path for path in EXAMPLES_DIR.glob("*sweep*.yaml"))


@pytest.mark.parametrize("path", _regular_config_paths(), ids=lambda p: p.name)
def test_example_config_loads(path: Path) -> None:
    cfg = load_config(path)
    assert cfg.physics.model


@pytest.mark.parametrize("path", _sweep_config_paths(), ids=lambda p: p.name)
def test_sweep_config_loads_and_base_loads(path: Path) -> None:
    sweep_cfg = load_sweep_config(path)
    base_cfg = load_config(REPO_ROOT / sweep_cfg.base)
    assert base_cfg.geometry.builder
