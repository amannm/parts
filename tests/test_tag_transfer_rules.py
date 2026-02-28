from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from simstack.config import TagRule, TagsConfig
from simstack.mesh.tag_transfer import apply_tag_rules


@dataclass
class FakeModel:
    facets: Dict[int, Tuple[float, float, float, float, float, float]]
    cells: Dict[int, Tuple[float, float, float, float, float, float]]
    normals: Dict[Tuple[int, int], Tuple[float, float, float]] = field(default_factory=dict)

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

    def addPhysicalGroup(self, _dim: int, _tags: List[int], _tag_id: int) -> None:
        return None

    def setPhysicalName(self, _dim: int, _tag_id: int, _name: str) -> None:
        return None

    def getParametrizationBounds(self, dim: int, tag: int) -> List[float]:
        if dim != 2:
            raise RuntimeError("Only surfaces are supported in this fake model")
        return [0.0, 1.0, 0.0, 1.0]

    def getNormal(self, dim: int, tag: int, _uv: List[float]) -> Tuple[float, float, float]:
        normal = self.normals.get((dim, tag))
        if normal is None:
            raise RuntimeError("No normal available")
        return normal


def test_bbox_patch_and_all_except_facets() -> None:
    model = FakeModel(
        facets={
            1: (0.0, 0.0, 0.0, 0.0, 0.4, 1.0),
            2: (0.0, 0.6, 0.0, 0.0, 1.0, 1.0),
            3: (1.0, 0.0, 0.0, 1.0, 0.4, 1.0),
            4: (1.0, 0.6, 0.0, 1.0, 1.0, 1.0),
        },
        cells={10: (0.0, 0.0, 0.0, 1.0, 1.0, 1.0)},
    )
    tags = TagsConfig(
        facets=[
            TagRule(name="left", rule="PlaneAtMin", params={"axis": "x"}),
            TagRule(name="upper", rule="BBoxPatch", params={"ymin": 0.5}),
            TagRule(name="other", rule="AllExcept", params={"names": ["left", "upper"]}),
        ],
        cells=[TagRule(name="solid", rule="AllVolumes", params={})],
    )

    result = apply_tag_rules(model, tags)

    assert set(result.facet_entities["left"]) == {1, 2}
    assert set(result.facet_entities["upper"]) == {2, 4}
    assert set(result.facet_entities["other"]) == {3}


def test_bbox_patch_cells_selects_expected_volume() -> None:
    model = FakeModel(
        facets={
            1: (0.0, 0.0, 0.0, 0.0, 1.0, 1.0),
            2: (1.0, 0.0, 0.0, 1.0, 1.0, 1.0),
        },
        cells={
            10: (0.0, 0.0, 0.0, 0.5, 1.0, 1.0),
            11: (0.6, 0.0, 0.0, 1.0, 1.0, 1.0),
        },
    )
    tags = TagsConfig(
        facets=[TagRule(name="left", rule="PlaneAtMin", params={"axis": "x"})],
        cells=[TagRule(name="right_half", rule="BBoxPatch", params={"xmin": 0.55})],
    )

    result = apply_tag_rules(model, tags)
    assert set(result.cell_entities["right_half"]) == {11}


def test_normal_approx_respects_allow_flip() -> None:
    model = FakeModel(
        facets={
            1: (0.0, 0.0, 0.0, 0.0, 0.2, 0.2),
            2: (1.0, 0.0, 0.0, 1.0, 0.2, 0.2),
            3: (0.5, 0.5, 0.0, 0.7, 0.7, 0.2),
        },
        cells={10: (0.0, 0.0, 0.0, 1.0, 1.0, 1.0)},
        normals={
            (2, 1): (1.0, 0.0, 0.0),
            (2, 2): (-1.0, 0.0, 0.0),
            (2, 3): (0.0, 1.0, 0.0),
        },
    )
    tags = TagsConfig(
        facets=[
            TagRule(
                name="x_plus",
                rule="NormalApprox",
                params={"nx": 1, "ny": 0, "nz": 0, "tol": 1e-6, "allow_flip": False},
            ),
            TagRule(
                name="x_any",
                rule="NormalApprox",
                params={"nx": 1, "ny": 0, "nz": 0, "tol": 1e-6, "allow_flip": True},
            ),
        ],
        cells=[TagRule(name="solid", rule="AllVolumes", params={})],
    )

    result = apply_tag_rules(model, tags)

    assert set(result.facet_entities["x_plus"]) == {1}
    assert set(result.facet_entities["x_any"]) == {1, 2}
