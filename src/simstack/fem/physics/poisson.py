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

        from simstack.fem.coeffs import build_dg0_field

        kappa_default = float(config.get("kappa", 1.0))
        source = float(config.get("source", 0.0))
        kappa = None

        if matdb and matdb.get("by_id"):
            kappa = build_dg0_field(mesh, cell_tags, matdb["by_id"], "kappa", kappa_default)
        else:
            kappa = fem.Constant(mesh, PETSc.ScalarType(kappa_default))

        return {
            "kappa": kappa,
            "source": fem.Constant(mesh, PETSc.ScalarType(source)),
        }

    def build_bcs(
        self,
        V: Any,
        facet_tags: Any,
        config: Dict[str, Any],
    ) -> Tuple[List[Any], List[Any], List[Any]]:
        from dolfinx import fem
        from petsc4py import PETSc
        import math
        from ufl import SpatialCoordinate, TestFunction, TrialFunction

        bcs: List[Any] = []
        a_terms: List[Any] = []
        L_terms: List[Any] = []
        ds = config.get("ds")
        if ds is None:
            raise ValueError("Poisson build_bcs requires 'ds' measure in config")

        v = TestFunction(V)
        u = TrialFunction(V)
        params = config.get("params") or {}
        axisymmetric = (
            str(params.get("runtime_coordinate_system", "cartesian")) == "axisymmetric"
            and int(params.get("runtime_dimension", 3)) == 2
        )
        axis_weight = 2.0 * math.pi * SpatialCoordinate(V.mesh)[0] if axisymmetric else 1.0
        for bc in config.get("bcs", []):
            tag_id = config["tag_map"]["facets"].get(bc["tag"])
            if tag_id is None:
                raise KeyError(f"Unknown facet tag for BC: {bc['tag']}")

            if bc["type"] == "dirichlet":
                facets = facet_tags.find(tag_id)
                dofs = fem.locate_dofs_topological(V, facet_tags.dim, facets)
                value = fem.Constant(V.mesh, PETSc.ScalarType(bc["value"]))
                bcs.append(fem.dirichletbc(value, dofs, V))
            elif bc["type"] == "neumann":
                g = PETSc.ScalarType(bc["value"])
                L_terms.append(axis_weight * g * v * ds(tag_id))
            elif bc["type"] == "robin":
                params = bc.get("params") or {}
                alpha = PETSc.ScalarType(params.get("alpha", bc.get("alpha", 1.0)))
                u0 = PETSc.ScalarType(bc.get("value", 0.0))
                a_terms.append(axis_weight * alpha * u * v * ds(tag_id))
                L_terms.append(axis_weight * alpha * u0 * v * ds(tag_id))
            else:
                raise ValueError(f"Unsupported BC type: {bc['type']}")

        return bcs, a_terms, L_terms

    def build_forms(self, spaces: Dict[str, Any], coeffs: Dict[str, Any], measures: Dict[str, Any], config: Dict[str, Any]):
        from ufl import TestFunction, TrialFunction, inner, grad

        V = spaces["V"]
        u = TrialFunction(V)
        v = TestFunction(V)
        dx = measures["dx"]
        ds = measures["ds"]

        kappa = coeffs["kappa"]
        source = coeffs["source"]

        a = inner(kappa * grad(u), grad(v)) * dx
        L = source * v * dx

        sources = config.get("sources") or {}
        facet_map = config.get("runtime_tag_map_facets", {}) if isinstance(config, dict) else {}
        if isinstance(sources, dict) and isinstance(facet_map, dict):
            for group in ("surface", "line"):
                for spec in sources.get(group, []) or []:
                    if not isinstance(spec, dict):
                        continue
                    tag_name = spec.get("tag")
                    tag_id = facet_map.get(tag_name)
                    if tag_id is None:
                        raise KeyError(f"Unknown facet tag for poisson source: {tag_name}")
                    value = float(spec.get("value", 0.0))
                    L += value * v * ds(tag_id)
        return a, L

    def outputs(self, fields: Dict[str, Any], coeffs: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        derived = []
        kappa = coeffs.get("kappa")
        if kappa is not None and hasattr(kappa, "function_space"):
            derived.append({"name": "kappa", "field": kappa})
        return derived
