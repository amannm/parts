"""Gmsh mesh generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from simstack.config import MeshingConfig, TagsConfig
from simstack.mesh.tag_transfer import TagTransferResult, apply_tag_rules


@dataclass
class GmshBuildResult:
    model: Any
    tag_result: TagTransferResult


class GmshSession:
    """Context manager to ensure Gmsh is finalized."""

    def __init__(self) -> None:
        self._initialized_here = False

    def __enter__(self) -> None:
        import gmsh  # local import to avoid hard dependency for dry-run

        if not gmsh.isInitialized():
            gmsh.initialize()
            self._initialized_here = True
        return None

    def __exit__(self, exc_type, exc, tb) -> None:
        import gmsh

        if self._initialized_here:
            gmsh.finalize()


def _apply_mesh_options(config: MeshingConfig) -> None:
    import gmsh

    if config.global_size is not None:
        gmsh.option.setNumber("Mesh.MeshSizeMin", float(config.global_size))
        gmsh.option.setNumber("Mesh.MeshSizeMax", float(config.global_size))

    for key, value in config.gmsh_options.items():
        if isinstance(value, (int, float)):
            gmsh.option.setNumber(str(key), float(value))
        else:
            gmsh.option.setString(str(key), str(value))


def _check_tag_coverage(
    tag_result: TagTransferResult,
    facet_entities: list[tuple[int, int]],
    require_all_facets: bool,
    allow_overlaps: bool,
) -> None:
    if not require_all_facets and allow_overlaps:
        return

    counts: Dict[int, int] = {tag: 0 for _dim, tag in facet_entities}
    for selected in tag_result.facet_entities.values():
        for tag in selected:
            counts[tag] = counts.get(tag, 0) + 1

    if require_all_facets:
        missing = [tag for tag, count in counts.items() if count == 0]
        if missing:
            raise ValueError(f"Facet coverage incomplete; missing {len(missing)} facets")

    if not allow_overlaps:
        overlaps = [tag for tag, count in counts.items() if count > 1]
        if overlaps:
            raise ValueError(f"Facet overlap detected for {len(overlaps)} facets")


def build_gmsh_model(step_path: str | Path, tags: TagsConfig, config: MeshingConfig) -> GmshBuildResult:
    import gmsh

    gmsh.model.reset()
    gmsh.model.add("simstack")

    step_path = Path(step_path)
    if not step_path.exists():
        raise FileNotFoundError(f"STEP file not found: {step_path}")

    gmsh.model.occ.importShapes(str(step_path))
    gmsh.model.occ.synchronize()

    _apply_mesh_options(config)

    tag_result = apply_tag_rules(gmsh.model, tags)

    facet_entities = gmsh.model.getEntities(2)
    _check_tag_coverage(
        tag_result,
        facet_entities,
        require_all_facets=config.qa.require_all_facets_tagged,
        allow_overlaps=config.qa.allow_overlaps,
    )

    gmsh.model.mesh.generate(3)

    return GmshBuildResult(model=gmsh.model, tag_result=tag_result)
