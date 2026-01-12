"""Project orchestration and caching hooks (initial scaffolding)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from simstack.config import SimStackConfig, config_to_dict
from simstack.core.provenance import build_provenance


class Project:
    def __init__(self, config: SimStackConfig, repo_root: str | Path) -> None:
        self.config = config
        self.repo_root = Path(repo_root)

    def dry_run_plan(self) -> List[str]:
        return ["cad", "mesh", "solve", "post"]

    def write_provenance(self, out_dir: str | Path) -> str:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        provenance = build_provenance(config_to_dict(self.config), self.repo_root)
        path = out_dir / "provenance.json"
        path.write_text(json.dumps(provenance, indent=2, sort_keys=True))
        return str(path)

    def write_dry_run_report(self, out_dir: str | Path) -> str:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        report: Dict[str, Any] = {
            "stages": self.dry_run_plan(),
            "note": "dry run only; no CAD/mesh/solve executed",
        }
        path = out_dir / "dry_run.json"
        path.write_text(json.dumps(report, indent=2, sort_keys=True))
        return str(path)
