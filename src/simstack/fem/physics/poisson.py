"""Poisson physics module."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


class PoissonModel:
    def declare_fields(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        degree = int(config.get("degree", 1))
        return [{"name": "u", "family": "CG", "degree": degree}]

    def build_spaces(self, mesh: Any, field_spec: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        from dolfinx import fem

        spec = field_spec[0]
        V = fem.FunctionSpace(mesh, (spec["family"], spec["degree"]))
        return {"V": V}

    def build_coefficients(self, mesh: Any, cell_tags: Any, matdb: Any, config: Dict[str, Any]) -> Dict[str, Any]:
        from dolfinx import fem
        from petsc4py import PETSc

        kappa = float(config.get("kappa", 1.0))
        source = float(config.get("source", 0.0))
        return {
            "kappa": fem.Constant(mesh, PETSc.ScalarType(kappa)),
            "source": fem.Constant(mesh, PETSc.ScalarType(source)),
        }

    def build_bcs(
        self,
        V: Any,
        facet_tags: Any,
        config: Dict[str, Any],
    ) -> Tuple[List[Any], List[Any]]:
        from dolfinx import fem
        from petsc4py import PETSc

        bcs: List[Any] = []
        for bc in config.get("bcs", []):
            if bc["type"] != "dirichlet":
                continue
            tag_id = config["tag_map"]["facets"].get(bc["tag"])
            if tag_id is None:
                raise KeyError(f"Unknown facet tag for BC: {bc['tag']}")
            facets = facet_tags.find(tag_id)
            dofs = fem.locate_dofs_topological(V, facet_tags.dim, facets)
            value = fem.Constant(V.mesh, PETSc.ScalarType(bc["value"]))
            bcs.append(fem.dirichletbc(value, dofs, V))
        return bcs, []

    def build_forms(self, spaces: Dict[str, Any], coeffs: Dict[str, Any], measures: Dict[str, Any], config: Dict[str, Any]):
        from ufl import TestFunction, TrialFunction, inner, grad

        V = spaces["V"]
        u = TrialFunction(V)
        v = TestFunction(V)
        dx = measures["dx"]

        kappa = coeffs["kappa"]
        source = coeffs["source"]

        a = inner(kappa * grad(u), grad(v)) * dx
        L = source * v * dx
        return a, L

    def outputs(self, fields: Dict[str, Any], coeffs: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        return []
