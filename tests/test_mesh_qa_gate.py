from __future__ import annotations

import pytest

from simstack.mesh.mesh_build import _check_tag_coverage
from simstack.mesh.tag_transfer import TagTransferResult


def _base_tag_result() -> TagTransferResult:
    return TagTransferResult(
        tag_map={"facets": {}, "cells": {}},
        facet_entities={},
        cell_entities={},
    )


def test_check_tag_coverage_fails_on_missing_required_facets() -> None:
    tag_result = _base_tag_result()
    tag_result.facet_entities = {"left": [1]}
    facets = [(2, 1), (2, 2)]

    with pytest.raises(ValueError, match="coverage incomplete"):
        _check_tag_coverage(
            tag_result,
            facets,
            require_all_facets=True,
            allow_overlaps=True,
        )


def test_check_tag_coverage_fails_on_overlap_when_disallowed() -> None:
    tag_result = _base_tag_result()
    tag_result.facet_entities = {"a": [1, 2], "b": [2]}
    facets = [(2, 1), (2, 2)]

    with pytest.raises(ValueError, match="overlap detected"):
        _check_tag_coverage(
            tag_result,
            facets,
            require_all_facets=True,
            allow_overlaps=False,
        )


def test_check_tag_coverage_reports_counts_when_valid() -> None:
    tag_result = _base_tag_result()
    tag_result.facet_entities = {"left": [1], "right": [2]}
    facets = [(2, 1), (2, 2), (2, 3)]

    report = _check_tag_coverage(
        tag_result,
        facets,
        require_all_facets=False,
        allow_overlaps=False,
    )

    assert report["total_entities"] == 3
    assert report["tagged_entities"] == 2
    assert report["missing_entities"] == [3]
    assert report["overlap_entities"] == []
