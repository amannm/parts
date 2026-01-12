"""Linear elasticity physics module."""

from __future__ import annotations

from typing import Any, Dict, List, Tuple


def _lame_from_E_nu(E: float, nu: float) -> Tuple[float, float]:
    mu = E / (2.0 * (1.0 + nu))
    lam = E * nu / ((1.0 + nu) * (1.0 - 2.0 * nu))
    return lam, mu


class ElasticityModel:
    def declare_fields(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        degree = int(config.get("degree", 1))
        return [{"name": "u", "family": "CG", "degree": degree}]

    def build_spaces(self, mesh: Any, field_spec: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[str, Any]:
        from dolfinx import fem

        spec = field_spec[0]
        V = fem.VectorFunctionSpace(mesh, (spec["family"], spec["degree"]))
        return {"V": V}

    def _default_lame(self, config: Dict[str, Any]) -> Tuple[float, float]:
        if "lambda" in config and "mu" in config:
            return float(config["lambda"]), float(config["mu"])
        if "E" in config and "nu" in config:
            return _lame_from_E_nu(float(config["E"]), float(config["nu"]))
        raise ValueError("Elasticity requires either (lambda, mu) or (E, nu) in parameters")

    def _resolve_lame(self, props: Dict[str, Any], default_lam: float, default_mu: float) -> Tuple[float, float]:
        if "lambda" in props or "mu" in props:
            return float(props.get("lambda", default_lam)), float(props.get("mu", default_mu))
        if "E" in props and "nu" in props:
            return _lame_from_E_nu(float(props["E"]), float(props["nu"]))
        return default_lam, default_mu

    def build_coefficients(self, mesh: Any, cell_tags: Any, matdb: Any, config: Dict[str, Any]) -> Dict[str, Any]:
        from dolfinx import fem
        from petsc4py import PETSc
        import numpy as np

        from simstack.fem.coeffs import build_dg0_field

        default_lam, default_mu = self._default_lame(config)

        lam_field = None
        mu_field = None
        if matdb and matdb.get("by_id"):
            by_id_lambda: Dict[int, Dict[str, Any]] = {}
            by_id_mu: Dict[int, Dict[str, Any]] = {}
            for tag_id, props in matdb["by_id"].items():
                lam, mu = self._resolve_lame(props, default_lam, default_mu)
                by_id_lambda[tag_id] = {"lambda": lam}
                by_id_mu[tag_id] = {"mu": mu}
            lam_field = build_dg0_field(mesh, cell_tags, by_id_lambda, "lambda", default_lam)
            mu_field = build_dg0_field(mesh, cell_tags, by_id_mu, "mu", default_mu)
        else:
            lam_field = fem.Constant(mesh, PETSc.ScalarType(default_lam))
            mu_field = fem.Constant(mesh, PETSc.ScalarType(default_mu))

        gdim = mesh.geometry.dim
        body_force = config.get("body_force", [0.0] * gdim)
        if isinstance(body_force, (int, float)):
            body_force = [float(body_force)] * gdim
        if len(body_force) != gdim:
            raise ValueError(f"body_force must have length {gdim}")

        f = fem.Constant(mesh, np.array(body_force, dtype=PETSc.ScalarType))

        return {
            "lambda": lam_field,
            "mu": mu_field,
            "body_force": f,
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
        from ufl import TestFunction, TrialFunction, dot

        bcs: List[Any] = []
        a_terms: List[Any] = []
        L_terms: List[Any] = []
        ds = config.get("ds")
        if ds is None:
            raise ValueError("Elasticity build_bcs requires 'ds' measure in config")

        v = TestFunction(V)
        u = TrialFunction(V)
        gdim = V.mesh.geometry.dim

        for bc in config.get("bcs", []):
            tag_id = config["tag_map"]["facets"].get(bc["tag"])
            if tag_id is None:
                raise KeyError(f"Unknown facet tag for BC: {bc['tag']}")

            if bc["type"] == "dirichlet":
                component = bc.get("component")
                if component is None:
                    value = bc.get("value", [0.0] * gdim)
                    if isinstance(value, (int, float)):
                        value = [float(value)] * gdim
                    if len(value) != gdim:
                        raise ValueError(f"Dirichlet value must have length {gdim}")
                    const = fem.Constant(V.mesh, np.array(value, dtype=PETSc.ScalarType))
                    facets = facet_tags.find(tag_id)
                    dofs = fem.locate_dofs_topological(V, facet_tags.dim, facets)
                    bcs.append(fem.dirichletbc(const, dofs, V))
                else:
                    if component < 0 or component >= gdim:
                        raise ValueError(f"Component {component} out of range for gdim={gdim}")
                    sub = V.sub(component)
                    facets = facet_tags.find(tag_id)
                    dofs = fem.locate_dofs_topological(sub, facet_tags.dim, facets)
                    value = fem.Constant(V.mesh, PETSc.ScalarType(bc.get("value", 0.0)))
                    bcs.append(fem.dirichletbc(value, dofs, sub))
            elif bc["type"] == "neumann":
                traction = bc.get("value", [0.0] * gdim)
                if isinstance(traction, (int, float)):
                    traction = [float(traction)] * gdim
                if len(traction) != gdim:
                    raise ValueError(f"Neumann traction must have length {gdim}")
                t = fem.Constant(V.mesh, np.array(traction, dtype=PETSc.ScalarType))
                L_terms.append(dot(t, v) * ds(tag_id))
            elif bc["type"] == "robin":
                params = bc.get("params") or {}
                alpha = PETSc.ScalarType(params.get("alpha", bc.get("alpha", 1.0)))
                u0 = bc.get("value", [0.0] * gdim)
                if isinstance(u0, (int, float)):
                    u0 = [float(u0)] * gdim
                if len(u0) != gdim:
                    raise ValueError(f"Robin value must have length {gdim}")
                u0_const = fem.Constant(V.mesh, np.array(u0, dtype=PETSc.ScalarType))
                a_terms.append(alpha * dot(u, v) * ds(tag_id))
                L_terms.append(alpha * dot(u0_const, v) * ds(tag_id))
            else:
                raise ValueError(f"Unsupported BC type: {bc['type']}")

        return bcs, a_terms, L_terms

    def build_forms(self, spaces: Dict[str, Any], coeffs: Dict[str, Any], measures: Dict[str, Any], config: Dict[str, Any]):
        from ufl import Identity, TestFunction, TrialFunction, grad, inner, sym, tr

        V = spaces["V"]
        u = TrialFunction(V)
        v = TestFunction(V)
        dx = measures["dx"]

        lam = coeffs["lambda"]
        mu = coeffs["mu"]
        f = coeffs["body_force"]

        def eps(w):
            return sym(grad(w))

        def sigma(w):
            return lam * tr(eps(w)) * Identity(V.mesh.geometry.dim) + 2.0 * mu * eps(w)

        a = inner(sigma(u), eps(v)) * dx
        L = inner(f, v) * dx
        return a, L

    def outputs(self, fields: Dict[str, Any], coeffs: Dict[str, Any], config: Dict[str, Any]) -> List[Dict[str, Any]]:
        from dolfinx import fem
        from ufl import Identity, sqrt, sym, grad, tr, inner

        derived: List[Dict[str, Any]] = []
        lam = coeffs.get("lambda")
        mu = coeffs.get("mu")
        if lam is not None and hasattr(lam, "function_space"):
            derived.append({"name": "lambda", "field": lam})
        if mu is not None and hasattr(mu, "function_space"):
            derived.append({"name": "mu", "field": mu})

        requested = config.get("derived", [])
        if not requested:
            return derived

        u = fields.get("u")
        if u is None:
            return derived

        mesh = u.function_space.mesh
        gdim = mesh.geometry.dim

        def _project(expr, V):
            f = fem.Function(V)
            f.interpolate(fem.Expression(expr, V.element.interpolation_points()))
            return f

        eps = sym(grad(u))
        sigma = lam * tr(eps) * Identity(gdim) + 2.0 * mu * eps

        if "strain" in requested:
            V_strain = fem.TensorFunctionSpace(mesh, ("DG", 0))
            derived.append({"name": "strain", "field": _project(eps, V_strain)})
        if "stress" in requested:
            V_stress = fem.TensorFunctionSpace(mesh, ("DG", 0))
            derived.append({"name": "stress", "field": _project(sigma, V_stress)})
        if "von_mises" in requested:
            dev = sigma - (tr(sigma) / 3.0) * Identity(gdim)
            von = sqrt(1.5 * inner(dev, dev))
            V_vm = fem.FunctionSpace(mesh, ("DG", 0))
            derived.append({"name": "von_mises", "field": _project(von, V_vm)})

        return derived
