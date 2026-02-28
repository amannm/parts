from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import pytest

from simstack.config import TagRule, TagsConfig
from simstack.mesh.tag_transfer import apply_tag_rules


@dataclass
class FakeModel:
    facets: Dict[int, Tuple[float, float, float, float, float, float]]
    cells: Dict[int, Tuple[float, float, float, float, float, float]]
    normals: Dict[Tuple[int, int], Tuple[float, float, float]] = field(default_factory=dict)
    physical_groups: List[Tuple[int, Tuple[int, ...], int]] = field(default_factory=list)
    physical_names: List[Tuple[int, int, str]] = field(default_factory=list)

    def getEntities(self, dim: int) -> List[Tuple[int, int]]:
        if dim == 2:
            return [(2, tag) for tag in sorted(self.facets)]
        if dim == 3:
            return [(3, tag) for tag in sorted(self.cells)]
        return []

    def getBoundingBox(self, dim: int, tag: int) -> Tuple[float, float, float, float, float, float]:
        if dim == 2:
            return self.facets[tag]
        if dim == 3:
            return self.cells[tag]
        raise KeyError(dim)

    def addPhysicalGroup(self, dim: int, tags: List[int], tag_id: int) -> None:
        self.physical_groups.append((dim, tuple(tags), tag_id))

    def setPhysicalName(self, dim: int, tag_id: int, name: str) -> None:
        self.physical_names.append((dim, tag_id, name))

    def getParametrizationBounds(self, dim: int, tag: int) -> List[float]:
        if dim != 2:
            raise RuntimeError("Only surfaces are supported in this fake model")
        return [0.0, 1.0, 0.0, 1.0]

    def getNormal(self, dim: int, tag: int, _uv: List[float]) -> Tuple[float, float, float]:
        normal = self.normals.get((dim, tag))
        if normal is None:
            raise RuntimeError("No normal available")
        return normal


def _make_model() -> FakeModel:
    return FakeModel(
        facets={
            1: (0.0, 0.0, 0.0, 0.0, 0.4, 1.0),
            2: (0.0, 0.6, 0.0, 0.0, 1.0, 1.0),
            3: (1.0, 0.0, 0.0, 1.0, 0.4, 1.0),
            4: (1.0, 0.6, 0.0, 1.0, 1.0, 1.0),
        },
        cells={
            10: (0.0, 0.0, 0.0, 0.5, 1.0, 1.0),
            11: (0.5, 0.0, 0.0, 1.0, 1.0, 1.0),
        },
    )


def test_tag_ids_are_stable_across_runs() -> None:
    tags = TagsConfig(
        facets=[
            TagRule(name="left", rule="PlaneAtMin", params={"axis": "x"}),
            TagRule(name="right", rule="PlaneAtMax", params={"axis": "x"}),
        ],
        cells=[TagRule(name="solid", rule="AllVolumes", params={})],
    )

    result_1 = apply_tag_rules(_make_model(), tags)
    result_2 = apply_tag_rules(_make_model(), tags)

    assert result_1.tag_map == result_2.tag_map
    assert result_1.tag_map["facets"]["left"] != result_1.tag_map["facets"]["right"]
    assert result_1.tag_map["cells"]["solid"] > 0


def test_override_id_collision_raises() -> None:
    tags = TagsConfig(
        facets=[
            TagRule(name="left", rule="PlaneAtMin", params={"axis": "x"}),
            TagRule(name="right", rule="PlaneAtMax", params={"axis": "x"}),
        ],
        cells=[TagRule(name="solid", rule="AllVolumes", params={})],
        id_overrides={"left": 100, "right": 100},
    )

    with pytest.raises(ValueError, match="collision"):
        apply_tag_rules(_make_model(), tags)
