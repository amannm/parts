from __future__ import annotations

from pathlib import Path

from simstack.core.provenance import build_provenance, build_stage_hashes, stable_hash


def test_stable_hash_is_order_invariant_for_mappings() -> None:
    left = {"a": 1, "b": {"x": 2, "y": [3, 4]}}
    right = {"b": {"y": [3, 4], "x": 2}, "a": 1}
    assert stable_hash(left) == stable_hash(right)


def test_build_provenance_carries_tag_and_mesh_metadata(tmp_path: Path) -> None:
    config = {"geometry": {"builder": "block_with_hole", "params": {"length": 1.0}}}
    tag_map = {"facets": {"left": 1}, "cells": {"solid": 2}}
    mesh_stats = {"min_quality": 0.42, "count": 100}
    legend_path = str(tmp_path / "mesh" / "tag_legend.json")

    provenance = build_provenance(
        config,
        repo_root=tmp_path,
        tag_map=tag_map,
        mesh_stats=mesh_stats,
        tag_legend_path=legend_path,
    )

    assert provenance["config"] == config
    assert provenance["tag_map"] == tag_map
    assert provenance["mesh_stats"] == mesh_stats
    assert provenance["tag_legend"] == legend_path
    assert provenance["config_hash"] == stable_hash(config)
    assert set(provenance["stage_hashes"]) == {"cad", "mesh", "solve", "post"}


def test_stage_hashes_change_with_expected_stage_inputs() -> None:
    base = {
        "geometry": {"builder": "block_with_hole", "params": {"length": 1.0}},
        "tags": {"facets": [], "cells": []},
        "meshing": {"global_size": 0.2},
        "physics": {"model": "poisson", "parameters": {"source": 0.0}},
        "materials": {"by_tag": {}},
        "bcs": {"items": []},
        "solver": {"preset": "linear_default", "options": {}},
        "outputs": {"format": "vtx"},
    }
    base_hashes = build_stage_hashes(base)

    changed_geometry = {
        **base,
        "geometry": {"builder": "block_with_hole", "params": {"length": 2.0}},
    }
    geom_hashes = build_stage_hashes(changed_geometry)
    assert geom_hashes["cad"] != base_hashes["cad"]
    assert geom_hashes["mesh"] != base_hashes["mesh"]
    assert geom_hashes["solve"] != base_hashes["solve"]
    assert geom_hashes["post"] != base_hashes["post"]

    changed_meshing = {
        **base,
        "meshing": {"global_size": 0.5},
    }
    mesh_hashes = build_stage_hashes(changed_meshing)
    assert mesh_hashes["cad"] == base_hashes["cad"]
    assert mesh_hashes["mesh"] != base_hashes["mesh"]
    assert mesh_hashes["solve"] != base_hashes["solve"]
    assert mesh_hashes["post"] != base_hashes["post"]

    changed_physics = {
        **base,
        "physics": {"model": "poisson", "parameters": {"source": 1.0}},
    }
    phys_hashes = build_stage_hashes(changed_physics)
    assert phys_hashes["cad"] == base_hashes["cad"]
    assert phys_hashes["mesh"] == base_hashes["mesh"]
    assert phys_hashes["solve"] != base_hashes["solve"]
    assert phys_hashes["post"] != base_hashes["post"]
