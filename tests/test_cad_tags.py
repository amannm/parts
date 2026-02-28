from __future__ import annotations

from simstack.cad.tags import TagRuleContext, evaluate_tag_rule, select_entities


def test_plane_at_min_and_max_with_context_bbox() -> None:
    global_bbox = (0.0, 0.0, 0.0, 1.0, 2.0, 3.0)
    left = {"tag": 1, "bbox": (0.0, 0.2, 0.3, 0.0, 1.8, 2.9), "dim": 2}
    right = {"tag": 2, "bbox": (1.0, 0.2, 0.3, 1.0, 1.8, 2.9), "dim": 2}
    ctx = TagRuleContext(global_bbox=global_bbox)

    assert evaluate_tag_rule("PlaneAtMin", {"axis": "x"}, left, context=ctx)
    assert evaluate_tag_rule("PlaneAtMax", {"axis": "x"}, right, context=ctx)
    assert not evaluate_tag_rule("PlaneAtMin", {"axis": "x"}, right, context=ctx)


def test_bbox_patch_and_all_volumes() -> None:
    entity = {"tag": 3, "bbox": (0.2, 0.2, 0.2, 0.8, 0.8, 0.8), "dim": 3}
    assert evaluate_tag_rule("BBoxPatch", {"xmin": 0.5, "xmax": 1.0}, entity)
    assert evaluate_tag_rule("AllVolumes", {}, entity)


def test_normal_approx_and_all_except() -> None:
    e1 = {"tag": 10, "bbox": (0, 0, 0, 0, 1, 1), "normal": (1.0, 0.0, 0.0)}
    e2 = {"tag": 11, "bbox": (1, 0, 0, 1, 1, 1), "normal": (-1.0, 0.0, 0.0)}
    assert evaluate_tag_rule("NormalApprox", {"nx": 1, "ny": 0, "nz": 0, "allow_flip": False, "tol": 1e-9}, e1)
    assert not evaluate_tag_rule("NormalApprox", {"nx": 1, "ny": 0, "nz": 0, "allow_flip": False, "tol": 1e-9}, e2)

    ctx = TagRuleContext(selected_tags={"left": {10}})
    assert not evaluate_tag_rule("AllExcept", {"names": ["left"]}, e1, context=ctx)
    assert evaluate_tag_rule("AllExcept", {"names": ["left"]}, e2, context=ctx)


def test_select_entities_computes_plane_context_automatically() -> None:
    entities = [
        {"tag": 1, "bbox": (0.0, 0.0, 0.0, 0.0, 1.0, 1.0), "dim": 2},
        {"tag": 2, "bbox": (1.0, 0.0, 0.0, 1.0, 1.0, 1.0), "dim": 2},
    ]
    selected = select_entities("PlaneAtMin", {"axis": "x"}, entities)
    assert [entity["tag"] for entity in selected] == [1]
