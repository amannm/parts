"""Content-addressed artifact cache storage."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from simstack.core.provenance import stable_hash


class ArtifactStore:
    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)
        self.cache_root = self.repo_root / ".simstack" / "cache"
        self.cache_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def artifact_digest(
        *,
        node_kind: str,
        node_version: str,
        normalized_inputs: Dict[str, Any],
        plugin_versions: Dict[str, str | None],
        config_slice: Dict[str, Any],
    ) -> str:
        payload = {
            "node_kind": node_kind,
            "node_version": node_version,
            "normalized_inputs": normalized_inputs,
            "plugin_versions": plugin_versions,
            "config_slice": config_slice,
        }
        return stable_hash(payload)

    def _artifact_dir(self, digest: str) -> Path:
        return self.cache_root / digest

    def load(self, digest: str) -> Dict[str, Any] | None:
        payload_path = self._artifact_dir(digest) / "payload.json"
        if not payload_path.exists():
            return None
        try:
            data = json.loads(payload_path.read_text())
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def store(self, digest: str, payload: Dict[str, Any], metadata: Dict[str, Any] | None = None) -> Path:
        artifact_dir = self._artifact_dir(digest)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        payload_path = artifact_dir / "payload.json"
        payload_path.write_text(json.dumps(payload, indent=2, sort_keys=True))

        if metadata is not None:
            metadata_path = artifact_dir / "metadata.json"
            metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True))

        return artifact_dir

    def prune(self) -> int:
        removed = 0
        if not self.cache_root.exists():
            return 0
        for child in self.cache_root.iterdir():
            if child.is_dir():
                for nested in child.rglob("*"):
                    if nested.is_file():
                        nested.unlink()
                for nested_dir in sorted([d for d in child.rglob("*") if d.is_dir()], reverse=True):
                    nested_dir.rmdir()
                child.rmdir()
                removed += 1
        return removed
