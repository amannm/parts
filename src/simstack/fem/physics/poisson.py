"""Poisson physics module (stub)."""

from __future__ import annotations

from typing import Any, Dict, List


class PoissonModel:
    def declare_fields(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise NotImplementedError("Poisson model not implemented yet.")

    def build_spaces(self, mesh: Any, field_spec: List[Dict[str, Any]], config: Dict[str, Any]) -> Any:
        raise NotImplementedError("Poisson model not implemented yet.")

    def build_coefficients(self, mesh: Any, cell_tags: Any, matdb: Any, config: Dict[str, Any]) -> Any:
        raise NotImplementedError("Poisson model not implemented yet.")

    def build_bcs(self, V: Any, facet_tags: Any, config: Dict[str, Any]) -> Any:
        raise NotImplementedError("Poisson model not implemented yet.")

    def build_forms(self, spaces: Any, coeffs: Any, measures: Any, config: Dict[str, Any]) -> Any:
        raise NotImplementedError("Poisson model not implemented yet.")

    def outputs(self, fields: Any, coeffs: Any, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        raise NotImplementedError("Poisson model not implemented yet.")
