"""AC electric conduction physics module (quasi-static)."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _with_sigma_aliases(by_id: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    mapped: Dict[int, Dict[str, Any]] = {}
    for tag_id, props in by_id.items():
        data = dict(props)
        if "sigma" not in data:
            if "conductivity" in data:
                data["sigma"] = data["conductivity"]
            elif "electric_conductivity" in data:
                data["sigma"] = data["electric_conductivity"]
        mapped[tag_id] = data
    return mapped


class ElectricACModel:
    def declare_fields(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        degree = int(config.get("degree", 1))
        return [{"name": "V", "family": "CG", "degree": degree}]

    def build_spaces(self, mesh: Any, field_spec: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        from dolfinx import fem

        spec = field_spec[0]
        V = fem.FunctionSpace(mesh, (spec["family"], spec["degree"]))
        return {"V": V}

    def build_coefficients(self, mesh: Any, cell_tags: Any, matdb: Any, config: Dict[str, Any]) -> Dict[str, Any]:
        from dolfinx import fem
        from petsc4py import PETSc

        from simstack.fem.coeffs import build_dg0_field

        sigma_default = float(config.get("sigma", config.get("conductivity", 1.0)))
        source = float(config.get("source", 0.0))

        if matdb and matdb.get("by_id"):
            by_id = _with_sigma_aliases(matdb["by_id"])
            sigma = build_dg0_field(mesh, cell_tags, by_id, "sigma", sigma_default)
        else:
            sigma = fem.Constant(mesh, PETSc.ScalarType(sigma_default))

        return {
            "sigma": sigma,
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
        from ufl import TestFunction, TrialFunction

        bcs: List[Any] = []
        a_terms: List[Any] = []
        L_terms: List[Any] = []
        ds = config.get("ds")
        if ds is None:
            raise ValueError("ElectricAC build_bcs requires 'ds' measure in config")

        v = TestFunction(V)
        u = TrialFunction(V)

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
                jn = PETSc.ScalarType(bc["value"])
                L_terms.append(jn * v * ds(tag_id))
            elif bc["type"] == "robin":
                params = bc.get("params") or {}
                alpha = PETSc.ScalarType(params.get("alpha", bc.get("alpha", 1.0)))
                v0 = PETSc.ScalarType(bc.get("value", 0.0))
                a_terms.append(alpha * u * v * ds(tag_id))
                L_terms.append(alpha * v0 * v * ds(tag_id))
            else:
                raise ValueError(f"Unsupported BC type: {bc['type']}")

        return bcs, a_terms, L_terms

    def build_forms(self, spaces: Dict[str, Any], coeffs: Dict[str, Any], measures: Dict[str, Any], config: Dict[str, Any]):
        from ufl import TestFunction, TrialFunction, inner, grad

        V = spaces["V"]
        u = TrialFunction(V)
        v = TestFunction(V)
        dx = measures["dx"]

        sigma = coeffs["sigma"]
        source = coeffs["source"]

        a = inner(sigma * grad(u), grad(v)) * dx
        L = source * v * dx
        return a, L

    def outputs(self, fields: Dict[str, Any], coeffs: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        from dolfinx import fem
        from ufl import grad, inner

        derived: List[Dict[str, Any]] = []

        sigma = coeffs.get("sigma")
        if sigma is not None and hasattr(sigma, "function_space"):
            derived.append({"name": "sigma", "field": sigma})

        requested = config.get("derived")
        if requested is None:
            requested = []
        include_joule = bool(config.get("include_joule_heat", True))
        if include_joule and "joule_heat" not in requested:
            requested = list(requested) + ["joule_heat"]

        V_field = fields.get("V")
        if V_field is None or not requested:
            return derived

        mesh = V_field.function_space.mesh

        def _project(expr, V):
            f = fem.Function(V)
            f.interpolate(fem.Expression(expr, V.element.interpolation_points()))
            return f

        E_expr = -grad(V_field)
        if "E" in requested:
            V_vec = fem.VectorFunctionSpace(mesh, ("DG", 0))
            derived.append({"name": "E", "field": _project(E_expr, V_vec)})
        if "J" in requested:
            V_vec = fem.VectorFunctionSpace(mesh, ("DG", 0))
            derived.append({"name": "J", "field": _project(sigma * E_expr, V_vec)})
        if "joule_heat" in requested:
            heat_scale = float(config.get("joule_scale", 1.0))
            V0 = fem.FunctionSpace(mesh, ("DG", 0))
            q_expr = heat_scale * sigma * inner(E_expr, E_expr)
            derived.append({"name": "joule_heat", "field": _project(q_expr, V0)})

        return derived
