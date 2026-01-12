"""Transient heat conduction physics module."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _with_thermal_aliases(by_id: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    mapped: Dict[int, Dict[str, Any]] = {}
    for tag_id, props in by_id.items():
        data = dict(props)
        if "kappa" not in data:
            if "k" in data:
                data["kappa"] = data["k"]
            elif "thermal_conductivity" in data:
                data["kappa"] = data["thermal_conductivity"]
        if "rho" not in data:
            if "density" in data:
                data["rho"] = data["density"]
        if "cp" not in data:
            if "heat_capacity" in data:
                data["cp"] = data["heat_capacity"]
        mapped[tag_id] = data
    return mapped


class HeatTransientModel:
    def declare_fields(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        degree = int(config.get("degree", 1))
        return [{"name": "T", "family": "CG", "degree": degree}]

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
        rho_default = float(config.get("rho", 1.0))
        cp_default = float(config.get("cp", 1.0))

        source_field = config.get("_source_field") or config.get("source_field")
        source_value = float(config.get("source", 0.0))

        if matdb and matdb.get("by_id"):
            by_id = _with_thermal_aliases(matdb["by_id"])
            kappa = build_dg0_field(mesh, cell_tags, by_id, "kappa", kappa_default)
            rho = build_dg0_field(mesh, cell_tags, by_id, "rho", rho_default)
            cp = build_dg0_field(mesh, cell_tags, by_id, "cp", cp_default)
        else:
            kappa = fem.Constant(mesh, PETSc.ScalarType(kappa_default))
            rho = fem.Constant(mesh, PETSc.ScalarType(rho_default))
            cp = fem.Constant(mesh, PETSc.ScalarType(cp_default))

        if source_field is None:
            source = fem.Constant(mesh, PETSc.ScalarType(source_value))
        else:
            source = source_field

        return {
            "kappa": kappa,
            "rho": rho,
            "cp": cp,
            "source": source,
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
            raise ValueError("HeatTransient build_bcs requires 'ds' measure in config")

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
                q = PETSc.ScalarType(bc["value"])
                L_terms.append(q * v * ds(tag_id))
            elif bc["type"] == "robin":
                params = bc.get("params") or {}
                alpha = PETSc.ScalarType(params.get("alpha", bc.get("alpha", 1.0)))
                t_inf = PETSc.ScalarType(bc.get("value", 0.0))
                a_terms.append(alpha * u * v * ds(tag_id))
                L_terms.append(alpha * t_inf * v * ds(tag_id))
            else:
                raise ValueError(f"Unsupported BC type: {bc['type']}")

        return bcs, a_terms, L_terms

    def build_forms(self, spaces: Dict[str, Any], coeffs: Dict[str, Any], measures: Dict[str, Any], config: Dict[str, Any]):
        from ufl import TestFunction, TrialFunction, inner, grad

        V = spaces["V"]
        T = TrialFunction(V)
        v = TestFunction(V)
        dx = measures["dx"]

        kappa = coeffs["kappa"]
        source = coeffs["source"]

        a = inner(kappa * grad(T), grad(v)) * dx
        L = source * v * dx
        return a, L

    def outputs(self, fields: Dict[str, Any], coeffs: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        derived: List[Dict[str, Any]] = []
        for name in ("kappa", "rho", "cp"):
            field = coeffs.get(name)
            if field is not None and hasattr(field, "function_space"):
                derived.append({"name": name, "field": field})
        return derived
