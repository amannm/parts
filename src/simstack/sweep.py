"""Exploration entrypoints backed by the unified runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from simstack.domain import StudyConfig, load_study_config
from simstack.runner import ExplorationRunner


def _load_study(config_or_path: StudyConfig | str | Path) -> StudyConfig:
    if isinstance(config_or_path, StudyConfig):
        return config_or_path
    return load_study_config(config_or_path)


def run_sweep(
    study: StudyConfig | str | Path,
    repo_root: str | Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    out_dir: str | None = None,
) -> Dict[str, Any]:
    loaded = _load_study(study)
    if out_dir:
        exploration = loaded.exploration
        if exploration is None:
            raise ValueError("Study config does not define exploration")
        loaded = loaded.model_copy(
            update={
                "exploration": exploration.model_copy(update={"output_directory": out_dir}),
            }
        )
    return ExplorationRunner(loaded, repo_root=repo_root).run(optimize=False, force=force, dry_run=dry_run)
