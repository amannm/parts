"""Deterministic DAG execution runtime with artifact caching."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List

from simstack.cache.store import ArtifactStore
from simstack.engine.types import EngineContext, NodeExecutionRecord, NodeSpec


@dataclass
class EngineRunResult:
    records: List[NodeExecutionRecord]
    node_digests: Dict[str, str]
    state: Dict[str, Any]


class DAGEngine:
    def __init__(
        self,
        nodes: List[NodeSpec],
        *,
        store: ArtifactStore,
        plugin_versions: Dict[str, str | None],
        resumable: bool = False,
    ) -> None:
        if not nodes:
            raise ValueError("DAG requires at least one node")
        self._nodes = list(nodes)
        self._by_id = self._index(nodes)
        self._ordered = self._toposort()
        self._store = store
        self._plugin_versions = dict(plugin_versions)
        self._resumable = resumable

    @staticmethod
    def _index(nodes: List[NodeSpec]) -> Dict[str, NodeSpec]:
        out: Dict[str, NodeSpec] = {}
        for node in nodes:
            if node.id in out:
                raise ValueError(f"Duplicate DAG node id: {node.id}")
            out[node.id] = node
        return out

    def _toposort(self) -> List[NodeSpec]:
        visited: set[str] = set()
        visiting: set[str] = set()
        ordered: List[NodeSpec] = []

        def visit(node_id: str) -> None:
            if node_id in visited:
                return
            if node_id in visiting:
                raise ValueError(f"Cycle detected at node '{node_id}'")
            if node_id not in self._by_id:
                raise ValueError(f"Unknown dependency: '{node_id}'")

            visiting.add(node_id)
            node = self._by_id[node_id]
            for dep in node.deps:
                visit(dep)
            visiting.remove(node_id)
            visited.add(node_id)
            ordered.append(node)

        for node in self._nodes:
            visit(node.id)

        return ordered

    def _digest_for(self, node: NodeSpec, node_digests: Dict[str, str]) -> str:
        normalized_inputs = {
            "deps": {dep: node_digests.get(dep) for dep in node.deps},
        }
        return self._store.artifact_digest(
            node_kind=node.kind,
            node_version=node.version,
            normalized_inputs=normalized_inputs,
            plugin_versions=self._plugin_versions,
            config_slice=node.config_slice,
        )

    def run(self, ctx: EngineContext) -> EngineRunResult:
        records: List[NodeExecutionRecord] = []
        node_digests: Dict[str, str] = {}

        for node in self._ordered:
            t0 = time.perf_counter()
            digest = self._digest_for(node, node_digests)
            node_digests[node.id] = digest

            reuse_enabled = bool(getattr(ctx.config.outputs, "reuse", True))
            cached_payload = self._store.load(digest) if node.cacheable and reuse_enabled else None
            if cached_payload is not None:
                updates = node.hydrate_updates(ctx, cached_payload)
                ctx.state.update(updates)
                records.append(
                    NodeExecutionRecord(
                        id=node.id,
                        kind=node.kind,
                        fingerprint=digest,
                        status="ok",
                        cache_hit=True,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                        deps=list(node.deps),
                        outputs={"cache": "hit"},
                    )
                )
                continue

            try:
                result = node.execute(ctx)
            except Exception:
                records.append(
                    NodeExecutionRecord(
                        id=node.id,
                        kind=node.kind,
                        fingerprint=digest,
                        status="failed",
                        cache_hit=False,
                        duration_ms=(time.perf_counter() - t0) * 1000.0,
                        deps=list(node.deps),
                        outputs={},
                    )
                )
                if not self._resumable:
                    raise
                continue

            ctx.state.update(result.state_updates)
            if node.cacheable and reuse_enabled:
                self._store.store(
                    digest,
                    result.cache_payload,
                    metadata={
                        "node": node.id,
                        "kind": node.kind,
                        "deps": list(node.deps),
                    },
                )

            records.append(
                NodeExecutionRecord(
                    id=node.id,
                    kind=node.kind,
                    fingerprint=digest,
                    status="ok",
                    cache_hit=False,
                    duration_ms=(time.perf_counter() - t0) * 1000.0,
                    deps=list(node.deps),
                    outputs={"cache": "miss"},
                )
            )

        return EngineRunResult(records=records, node_digests=node_digests, state=ctx.state)
