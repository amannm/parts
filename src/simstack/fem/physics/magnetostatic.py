"""Magnetostatic vector potential (A-formulation)."""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

MU0_DEFAULT = 4.0e-7 * math.pi


def _with_aliases(by_id: Dict[int, Dict[str, Any]]) -> Dict[int, Dict[str, Any]]:
    mapped: Dict[int, Dict[str, Any]] = {}
    for tag_id, props in by_id.items():
        data = dict(props)
        if "mu_r" not in data:
            if "mu" in data:
                data["mu_r"] = data["mu"]
            elif "relative_permeability" in data:
                data["mu_r"] = data["relative_permeability"]
            elif "permeability" in data:
                data["mu_r"] = data["permeability"]
        if "current_density" not in data:
            if "J" in data:
                data["current_density"] = data["J"]
            elif "source" in data:
                data["current_density"] = data["source"]
        if "magnetization" not in data:
            if "M" in data:
                data["magnetization"] = data["M"]
        mapped[tag_id] = data
    return mapped


class MagnetostaticModel:
    def declare_fields(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        degree = int(config.get("degree", 1))
        return [{"name": "A", "family": "N1curl", "degree": degree}]

    def build_spaces(self, mesh: Any, field_spec: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        from dolfinx import fem

        spec = field_spec[0]
        V = fem.FunctionSpace(mesh, (spec["family"], spec["degree"]))
        return {"V": V}

    def build_coefficients(self, mesh: Any, cell_tags: Any, matdb: Any, config: Dict[str, Any]) -> Dict[str, Any]:
        from dolfinx import fem
        from petsc4py import PETSc
        import numpy as np

        from simstack.fem.coeffs import _coerce_vector, build_dg0_field, build_dg0_vector_field

        gdim = mesh.geometry.dim
        mu0 = float(config.get("mu0", MU0_DEFAULT))
        mu_r_default = float(config.get("mu_r", config.get("mu", 1.0)))
        J_default = _coerce_vector(config.get("current_density", config.get("J", 0.0)), gdim, "current_density")
        M_default = _coerce_vector(config.get("magnetization", config.get("M", 0.0)), gdim, "magnetization")

        if matdb and matdb.get("by_id"):
            by_id = _with_aliases(matdb["by_id"])
            mu_r = build_dg0_field(mesh, cell_tags, by_id, "mu_r", mu_r_default)
            J = build_dg0_vector_field(mesh, cell_tags, by_id, "current_density", J_default)
            M = build_dg0_vector_field(mesh, cell_tags, by_id, "magnetization", M_default)
        else:
            mu_r = fem.Constant(mesh, PETSc.ScalarType(mu_r_default))
            J = fem.Constant(mesh, np.array(J_default, dtype=PETSc.ScalarType))
            M = fem.Constant(mesh, np.array(M_default, dtype=PETSc.ScalarType))

        nu = 1.0 / (mu0 * mu_r)

        return {
            "mu0": mu0,
            "mu_r": mu_r,
            "nu": nu,
            "J": J,
            "M": M,
        }

    def build_bcs(
        self,
        V: Any,
        facet_tags: Any,
        config: Dict[str, Any],
    ) -> Tuple[List[Any], List[Any], List[Any]]:
        from dolfinx import fem
        from petsc4py import PETSc
        import numpy as np

        bcs: List[Any] = []
        a_terms: List[Any] = []
        L_terms: List[Any] = []

        gdim = V.mesh.geometry.dim
        for bc in config.get("bcs", []):
            tag_id = config["tag_map"]["facets"].get(bc["tag"])
            if tag_id is None:
                raise KeyError(f"Unknown facet tag for BC: {bc['tag']}")

            if bc["type"] != "dirichlet":
                raise ValueError(f"Unsupported BC type for magnetostatics: {bc['type']}")

            if bc.get("component") is not None:
                raise ValueError("Magnetostatics Dirichlet BC does not support component targeting")

            value = bc.get("value", [0.0] * gdim)
            if isinstance(value, (int, float)):
                value = [float(value)] * gdim
            if len(value) != gdim:
                raise ValueError(f"Dirichlet value must have length {gdim}")
            const = fem.Constant(V.mesh, np.array(value, dtype=PETSc.ScalarType))
            facets = facet_tags.find(tag_id)
            dofs = fem.locate_dofs_topological(V, facet_tags.dim, facets)
            bcs.append(fem.dirichletbc(const, dofs, V))

        return bcs, a_terms, L_terms

    def build_forms(self, spaces: Dict[str, Any], coeffs: Dict[str, Any], measures: Dict[str, Any], config: Dict[str, Any]):
        from ufl import TestFunction, TrialFunction, curl, inner

        V = spaces["V"]
        u = TrialFunction(V)
        v = TestFunction(V)
        dx = measures["dx"]

        nu = coeffs["nu"]
        J = coeffs["J"]
        M = coeffs["M"]
        mu0 = coeffs["mu0"]

        a = inner(nu * curl(u), curl(v)) * dx
        L = inner(J, v) * dx
        if M is not None:
            L += inner(nu * mu0 * M, curl(v)) * dx
        return a, L

    def outputs(self, fields: Dict[str, Any], coeffs: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        from dolfinx import fem
        from ufl import curl, inner, sqrt

        derived: List[Dict[str, Any]] = []
        mu_r = coeffs.get("mu_r")
        if mu_r is not None and hasattr(mu_r, "function_space"):
            derived.append({"name": "mu_r", "field": mu_r})
        J = coeffs.get("J")
        if J is not None and hasattr(J, "function_space"):
            derived.append({"name": "current_density", "field": J})
        M = coeffs.get("M")
        if M is not None and hasattr(M, "function_space"):
            derived.append({"name": "magnetization", "field": M})

        requested = config.get("derived")
        if requested is None:
            requested = []
        include_B = bool(config.get("include_B", True))
        include_H = bool(config.get("include_H", True))
        if include_B and "B" not in requested:
            requested = list(requested) + ["B"]
        if include_H and "H" not in requested:
            requested = list(requested) + ["H"]

        A_field = fields.get("A")
        if A_field is None or not requested:
            return derived

        mesh = A_field.function_space.mesh
        V_vec = fem.VectorFunctionSpace(mesh, ("DG", 0))
        V0 = fem.FunctionSpace(mesh, ("DG", 0))

        def _project(expr, V):
            f = fem.Function(V)
            f.interpolate(fem.Expression(expr, V.element.interpolation_points()))
            return f

        nu = coeffs["nu"]
        B_expr = curl(A_field)
        H_expr = nu * B_expr
        if M is not None:
            H_expr = H_expr - M

        if "B" in requested:
            derived.append({"name": "B", "field": _project(B_expr, V_vec)})
        if "H" in requested:
            derived.append({"name": "H", "field": _project(H_expr, V_vec)})
        if "B_mag" in requested:
            derived.append({"name": "B_mag", "field": _project(sqrt(inner(B_expr, B_expr)), V0)})
        if "energy_density" in requested:
            derived.append({"name": "energy_density", "field": _project(0.5 * inner(B_expr, H_expr), V0)})

        return derived

    def metrics(
        self,
        fields: Dict[str, Any],
        coeffs: Dict[str, Any],
        measures: Dict[str, Any],
        config: Dict[str, Any],
        *,
        tag_map: Dict[str, Dict[str, int]] | None = None,
        facet_tags: Any | None = None,
    ) -> Dict[str, Any]:
        torque_cfg = config.get("torque")
        if not torque_cfg:
            return {}
        if facet_tags is None or tag_map is None:
            raise ValueError("Torque computation requires facet tags and tag map")

        tag_name = torque_cfg.get("tag")
        if not tag_name:
            raise KeyError("Torque configuration missing 'tag'")
        tag_id = tag_map.get("facets", {}).get(tag_name)
        if tag_id is None:
            raise KeyError(f"Torque tag not found in facet tags: {tag_name}")

        A_field = fields.get("A")
        if A_field is None:
            raise RuntimeError("Torque computation requires magnetic potential field 'A'")

        mesh = A_field.function_space.mesh
        gdim = mesh.geometry.dim
        if gdim != 3:
            raise ValueError("Torque computation currently supports 3D meshes only")

        from dolfinx import fem
        from mpi4py import MPI
        from ufl import Identity, SpatialCoordinate, FacetNormal, as_vector, cross, dot, inner, outer, curl

        def _axis(value, name, default):
            from simstack.fem.coeffs import _coerce_vector

            vec = _coerce_vector(value, gdim, name) if value is not None else default
            norm = math.sqrt(sum(v * v for v in vec))
            if norm <= 0.0:
                raise ValueError(f"{name} must be non-zero")
            return [v / norm for v in vec]

        axis = _axis(torque_cfg.get("axis"), "torque.axis", [0.0, 0.0, 1.0])
        origin = torque_cfg.get("origin")
        if origin is None:
            origin = [0.0, 0.0, 0.0]
        from simstack.fem.coeffs import _coerce_vector

        origin_vec = _coerce_vector(origin, gdim, "torque.origin")

        B = curl(A_field)
        mu0 = coeffs["mu0"]
        n = FacetNormal(mesh)
        r = SpatialCoordinate(mesh) - as_vector(origin_vec)

        T = (1.0 / mu0) * (outer(B, B) - 0.5 * inner(B, B) * Identity(gdim))
        traction = dot(T, n)
        torque_density = cross(r, traction)
        ds = measures["ds"]

        torque_form = fem.form(dot(torque_density, as_vector(axis)) * ds(tag_id))
        torque_value = fem.assemble_scalar(torque_form)
        torque_value = mesh.comm.allreduce(torque_value, op=MPI.SUM)

        return {
            "torque": float(torque_value),
            "torque_tag": tag_name,
        }
