"""Solver orchestration."""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from simstack.core.registry import DEFAULT_REGISTRY
from simstack.core.artifacts import SolveArtifact
from simstack.fem.materials import build_matdb


SolvePlan = Callable[
    [Any, Any, Any, Any, Any, Any, Any, Dict[str, Dict[str, int]]],
    SolveArtifact,
]
_SOLVE_PLANS: Dict[str, SolvePlan] = {}


def register_solve_plan(model_name: str) -> Callable[[SolvePlan], SolvePlan]:
    def decorator(func: SolvePlan) -> SolvePlan:
        if model_name in _SOLVE_PLANS:
            raise ValueError(f"Solve plan already registered for model '{model_name}'")
        _SOLVE_PLANS[model_name] = func
        return func

    return decorator


def _obj_get(data: Any, key: str, default: Any = None) -> Any:
    if isinstance(data, dict):
        return data.get(key, default)
    return getattr(data, key, default)


def _physics_model(physics: Any) -> str:
    model = _obj_get(physics, "model")
    if not isinstance(model, str) or not model:
        raise ValueError("Physics object must define non-empty 'model'")
    return model


def _merge_solver_options(solver: Any) -> Dict[str, Any]:
    options: Dict[str, Any] = {}
    preset_name = _obj_get(solver, "preset", "linear_default")
    preset = DEFAULT_REGISTRY.solver_presets.get(str(preset_name), {})
    options.update(preset)
    raw = _obj_get(solver, "options", {})
    if isinstance(raw, dict):
        options.update(raw)
    return options


def _physics_params(physics: Any) -> Dict[str, Any]:
    if hasattr(physics, "parameters_dict"):
        return dict(physics.parameters_dict())
    params = _obj_get(physics, "parameters", {})
    if isinstance(params, dict):
        return dict(params)
    return {}


def _dump_bcs(bcs: Any) -> List[Dict[str, Any]]:
    raw = _obj_get(bcs, "items", bcs)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise TypeError("BCs must be a list or object exposing .items list")
    out: List[Dict[str, Any]] = []
    for item in raw:
        if hasattr(item, "model_dump"):
            out.append(item.model_dump(mode="json"))
        elif isinstance(item, dict):
            out.append(dict(item))
        else:
            raise TypeError("BC entries must be dicts or pydantic models")
    return out


def _ensure_bcs_list(items: Any) -> List[Dict[str, Any]]:
    return _dump_bcs(items)


def _runtime_material_variables(params: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    raw = params.get("runtime_material_variables")
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, (int, float)):
                out[str(key)] = float(value)
    temp = params.get("temperature")
    if isinstance(temp, (int, float)):
        out.setdefault("T", float(temp))
    freq = params.get("frequency")
    if isinstance(freq, (int, float)):
        out.setdefault("f", float(freq))
    return out


def _is_axisymmetric(params: Dict[str, Any]) -> bool:
    return (
        str(params.get("runtime_coordinate_system", "cartesian")) == "axisymmetric"
        and int(params.get("runtime_dimension", 3)) == 2
    )


def _axisymmetric_weight(mesh: Any, params: Dict[str, Any]) -> Any | None:
    if not _is_axisymmetric(params):
        return None
    from ufl import SpatialCoordinate

    x = SpatialCoordinate(mesh)
    return 2.0 * math.pi * x[0]


def _parse_time_config(params: Dict[str, Any]) -> Tuple[float, float, float, int]:
    time_cfg = params.get("time", {}) if isinstance(params, dict) else {}
    t0 = float(time_cfg.get("t0", time_cfg.get("start", 0.0)))

    dt = time_cfg.get("dt")
    if dt is None:
        dt = float(time_cfg.get("default_dt", 1.0))
    else:
        dt = float(dt)
    if dt <= 0:
        raise ValueError("Time step dt must be positive")

    steps = time_cfg.get("steps") or time_cfg.get("num_steps")
    t_end = time_cfg.get("t_end", time_cfg.get("end"))
    if steps is None:
        if t_end is None:
            steps = 1
            t_end = t0 + dt
        else:
            t_end = float(t_end)
            span = max(t_end - t0, 0.0)
            steps = max(1, int(math.ceil(span / dt))) if dt > 0 else 1
    else:
        steps = max(int(steps), 1)
        if t_end is None:
            t_end = t0 + steps * dt
        else:
            t_end = float(t_end)
            span = max(t_end - t0, 0.0)
            dt = span / steps if steps > 0 else dt

    max_steps = int(time_cfg.get("max_steps", steps))
    if steps > max_steps:
        steps = max_steps
        t_end = t0 + steps * dt

    return t0, t_end, dt, steps


def _domain_average(field: Any, dx: Any, tag_id: int, comm: Any) -> Optional[float]:
    from dolfinx import fem
    from mpi4py import MPI

    value = fem.assemble_scalar(fem.form(field * dx(tag_id)))
    volume = fem.assemble_scalar(fem.form(1.0 * dx(tag_id)))
    value = comm.allreduce(value, op=MPI.SUM)
    volume = comm.allreduce(volume, op=MPI.SUM)
    if volume <= 0:
        return None
    return float(value / volume)


def _domain_min_max(field: Any, cell_tags: Any, tag_id: int, comm: Any) -> Optional[Tuple[float, float]]:
    from dolfinx import fem
    from mpi4py import MPI

    cells = cell_tags.find(tag_id)
    if len(cells) == 0:
        return None
    V = field.function_space
    dofs = fem.locate_dofs_topological(V, V.mesh.topology.dim, cells)
    if dofs.size == 0:
        local_min = math.inf
        local_max = -math.inf
    else:
        values = field.x.array[dofs]
        local_min = float(values.min()) if values.size else math.inf
        local_max = float(values.max()) if values.size else -math.inf
    global_min = comm.allreduce(local_min, op=MPI.MIN)
    global_max = comm.allreduce(local_max, op=MPI.MAX)
    if not math.isfinite(global_min) or not math.isfinite(global_max):
        return None
    return global_min, global_max


def _build_targets(params: Dict[str, Any], tag_map: Dict[str, Dict[str, int]]) -> List[Dict[str, Any]]:
    targets: List[Dict[str, Any]] = []
    raw = params.get("targets")
    if isinstance(raw, dict):
        raw = [raw]
    if isinstance(raw, list):
        for idx, spec in enumerate(raw):
            if not isinstance(spec, dict):
                continue
            name = spec.get("name") or f"target_{idx + 1}"
            tag = spec.get("tag")
            if not tag:
                raise KeyError("Target spec missing 'tag'")
            tag_id = tag_map.get("cells", {}).get(tag)
            if tag_id is None:
                raise KeyError(f"Target tag not found in cell tags: {tag}")
            threshold = spec.get("temperature")
            if threshold is None:
                raise KeyError(f"Target '{name}' missing temperature")
            mode = spec.get("mode", "avg")
            direction = spec.get("direction", "above")
            targets.append(
                {
                    "name": name,
                    "tag": tag,
                    "tag_id": tag_id,
                    "threshold": float(threshold),
                    "mode": mode,
                    "direction": direction,
                }
            )
    return targets


def _target_reached(value: float, threshold: float, direction: str) -> bool:
    if direction == "below":
        return value <= threshold
    return value >= threshold


def _target_value(
    field: Any,
    dx: Any,
    cell_tags: Any,
    tag_id: int,
    comm: Any,
    mode: str,
) -> Optional[float]:
    if mode == "avg":
        return _domain_average(field, dx, tag_id, comm)
    if mode in {"min", "max"}:
        values = _domain_min_max(field, cell_tags, tag_id, comm)
        if values is None:
            return None
        return values[0] if mode == "min" else values[1]
    raise ValueError(f"Unsupported target mode: {mode}")


def _update_rho_cp(
    rho_cp: Any,
    rho: Any,
    cp: Any,
    T_prev: Any,
    phase_cfg: Optional[Dict[str, Any]],
) -> None:
    from dolfinx import fem
    from ufl import tanh

    expr = rho * cp
    if phase_cfg:
        latent = float(phase_cfg.get("latent_heat", 0.0))
        delta = float(phase_cfg.get("delta_T", phase_cfg.get("mushy_delta", 1.0)))
        if latent > 0.0 and delta > 0.0:
            t_transition = float(phase_cfg.get("transition_temp", 373.15))
            smooth = 0.5 * (1.0 + tanh((T_prev - t_transition) / delta))
            expr = rho * (cp + latent / max(delta, 1e-12) * smooth)

    rho_cp.interpolate(fem.Expression(expr, rho_cp.function_space.element.interpolation_points()))


def solve_linear_problem(
    mesh: Any,
    cell_tags: Any,
    facet_tags: Any,
    physics: Any,
    bcs: Any,
    materials: Any,
    solver: Any,
    tag_map: Dict[str, Dict[str, int]],
) -> SolveArtifact:
    from dolfinx.fem import petsc
    from ufl import Measure

    params = _physics_params(physics)
    params["runtime_tag_map_facets"] = tag_map.get("facets", {})
    params["runtime_tag_map_cells"] = tag_map.get("cells", {})

    physics_model = _physics_model(physics)
    model_factory = DEFAULT_REGISTRY.get_physics(physics_model)
    model = model_factory()

    field_spec = model.declare_fields(params)
    spaces = model.build_spaces(mesh, field_spec, params)

    matdb = build_matdb(materials, tag_map, variables=_runtime_material_variables(params))
    coeffs = model.build_coefficients(mesh, cell_tags, matdb, params)
    measures = {
        "dx": Measure("dx", domain=mesh, subdomain_data=cell_tags),
        "ds": Measure("ds", domain=mesh, subdomain_data=facet_tags),
    }

    bc_payload = {
        "bcs": _dump_bcs(bcs),
        "tag_map": tag_map,
        "ds": measures["ds"],
        "params": params,
    }
    dirichlet_bcs, a_terms, L_terms = model.build_bcs(spaces["V"], facet_tags, bc_payload)

    a, L = model.build_forms(spaces, coeffs, measures, params)
    for term in a_terms:
        a += term
    for term in L_terms:
        L += term

    weight = _axisymmetric_weight(mesh, params)
    if weight is not None and physics_model in {"poisson", "heat", "heat_transient", "electric_ac"}:
        a = weight * a
        L = weight * L

    options = _merge_solver_options(solver)

    nonlinear_cfg = params.get("nonlinear")
    if isinstance(nonlinear_cfg, dict) and bool(nonlinear_cfg.get("enabled", False)):
        # Lightweight nonlinear path: repeated assembly/solve with convergence on field delta.
        max_iters = int(nonlinear_cfg.get("max_iters", 15))
        tol = float(nonlinear_cfg.get("tol", 1e-6))
        last = None
        uh = None
        iter_count = 0
        for i in range(1, max_iters + 1):
            problem = petsc.LinearProblem(a, L, bcs=dirichlet_bcs, petsc_options=options)
            uh = problem.solve()
            iter_count = i
            if last is not None:
                diff = uh.x.array - last
                denom = float((last * last).sum())
                delta = math.sqrt(float((diff * diff).sum()) / max(denom, 1e-30))
                if delta <= tol:
                    break
            last = uh.x.array.copy()

        solver_info = {
            "nonlinear": True,
            "iterations": iter_count,
            "converged_reason": 1 if iter_count < max_iters else 0,
        }
    else:
        problem = petsc.LinearProblem(a, L, bcs=dirichlet_bcs, petsc_options=options)
        uh = problem.solve()
        solver_info = {
            "nonlinear": False,
            "converged_reason": problem.solver.getConvergedReason(),
            "iterations": problem.solver.getIterationNumber(),
        }

    primary_name = field_spec[0]["name"] if field_spec else "u"
    uh.name = primary_name
    fields = {primary_name: uh}
    for derived in model.outputs(fields, coeffs, params):
        name = derived.get("name")
        field = derived.get("field")
        if name and field is not None:
            fields[name] = field
    metrics_fn = getattr(model, "metrics", None)
    if callable(metrics_fn):
        extra = metrics_fn(
            fields,
            coeffs,
            measures,
            params,
            tag_map=tag_map,
            facet_tags=facet_tags,
        )
        if isinstance(extra, dict):
            solver_info.update(extra)

    return SolveArtifact(fields=fields, derived_fields={}, solver_report=solver_info, timings={})


@register_solve_plan("heat_transient")
def solve_transient_heat(
    mesh: Any,
    cell_tags: Any,
    facet_tags: Any,
    physics: Any,
    bcs: Any,
    materials: Any,
    solver: Any,
    tag_map: Dict[str, Dict[str, int]],
    *,
    source_field: Any | None = None,
) -> SolveArtifact:
    from dolfinx import fem
    from dolfinx.fem import petsc
    from ufl import Measure, TestFunction, TrialFunction

    params = _physics_params(physics)
    params["runtime_tag_map_facets"] = tag_map.get("facets", {})
    params["runtime_tag_map_cells"] = tag_map.get("cells", {})

    physics_model = _physics_model(physics)
    model_factory = DEFAULT_REGISTRY.get_physics(physics_model)
    model = model_factory()

    field_spec = model.declare_fields(params)
    spaces = model.build_spaces(mesh, field_spec, params)

    matdb = build_matdb(materials, tag_map, variables=_runtime_material_variables(params))
    coeffs = model.build_coefficients(mesh, cell_tags, matdb, params)

    if source_field is None:
        source_field = params.get("source_field")
    if source_field is not None:
        coeffs["source"] = source_field

    measures = {
        "dx": Measure("dx", domain=mesh, subdomain_data=cell_tags),
        "ds": Measure("ds", domain=mesh, subdomain_data=facet_tags),
    }

    bc_payload = {
        "bcs": _dump_bcs(bcs),
        "tag_map": tag_map,
        "ds": measures["ds"],
        "params": params,
    }
    dirichlet_bcs, a_terms, L_terms = model.build_bcs(spaces["V"], facet_tags, bc_payload)

    a_base, L_base = model.build_forms(spaces, coeffs, measures, params)

    V = spaces["V"]
    T = TrialFunction(V)
    v = TestFunction(V)
    dx = measures["dx"]

    rho = coeffs.get("rho")
    cp = coeffs.get("cp")
    if rho is None or cp is None:
        raise ValueError("Transient heat requires 'rho' and 'cp' coefficients")

    V0 = fem.FunctionSpace(mesh, ("DG", 0))
    rho_cp = fem.Function(V0)

    time_params = params or {}
    t0, t_end, dt, steps = _parse_time_config(time_params)
    initial_raw = time_params.get("initial", time_params.get("T0"))
    if initial_raw is None:
        time_cfg = time_params.get("time", {})
        if isinstance(time_cfg, dict):
            initial_raw = time_cfg.get("initial", time_cfg.get("T0"))
    if initial_raw is None:
        initial_raw = 293.15
    initial = float(initial_raw)

    T_prev = fem.Function(V)
    T_prev.x.array[:] = initial
    T_prev.x.scatter_forward()

    phase_cfg = None
    if isinstance(time_params, dict):
        phase_cfg = time_params.get("phase_change")

    targets = _build_targets(time_params, tag_map)
    target_state: Dict[str, Dict[str, Any]] = {}
    for spec in targets:
        target_state[spec["name"]] = {
            "time": None,
            "reached": False,
            "value": None,
            "threshold": spec["threshold"],
            "mode": spec["mode"],
            "direction": spec["direction"],
            "tag": spec["tag"],
        }

    options = _merge_solver_options(solver)

    weight = _axisymmetric_weight(mesh, params)

    for step in range(1, steps + 1):
        t = t0 + step * dt
        _update_rho_cp(rho_cp, rho, cp, T_prev, phase_cfg)

        a = (rho_cp / dt) * T * v * dx + a_base
        L = (rho_cp / dt) * T_prev * v * dx + L_base
        for term in a_terms:
            a += term
        for term in L_terms:
            L += term

        if weight is not None:
            a = weight * a
            L = weight * L

        problem = petsc.LinearProblem(a, L, bcs=dirichlet_bcs, petsc_options=options)
        T_new = problem.solve()

        if targets:
            for spec in targets:
                name = spec["name"]
                value = _target_value(T_new, dx, cell_tags, spec["tag_id"], mesh.comm, spec["mode"])
                state = target_state[name]
                state["value"] = value
                if value is not None and not state["reached"]:
                    if _target_reached(value, spec["threshold"], spec["direction"]):
                        state["reached"] = True
                        state["time"] = t

        T_prev.x.array[:] = T_new.x.array
        T_prev.x.scatter_forward()

    T_new.name = field_spec[0]["name"] if field_spec else "T"
    fields = {T_new.name: T_new}
    for derived in model.outputs(fields, coeffs, params):
        name = derived.get("name")
        field = derived.get("field")
        if name and field is not None:
            fields[name] = field

    solver_info = {
        "t0": t0,
        "t_end": t_end,
        "dt": dt,
        "steps": steps,
        "targets": target_state,
    }

    return SolveArtifact(fields=fields, derived_fields={}, solver_report=solver_info, timings={})


@register_solve_plan("electro_thermal")
def solve_electro_thermal(
    mesh: Any,
    cell_tags: Any,
    facet_tags: Any,
    physics: Any,
    bcs: Any,
    materials: Any,
    solver: Any,
    tag_map: Dict[str, Dict[str, int]],
) -> SolveArtifact:
    params = _physics_params(physics)
    electric_params = dict(params.get("electric", {}))
    heat_params = dict(params.get("heat", {}))
    if "time" in params and "time" not in heat_params:
        heat_params["time"] = params["time"]
    if "targets" in params and "targets" not in heat_params:
        heat_params["targets"] = params["targets"]
    if "phase_change" in params and "phase_change" not in heat_params:
        heat_params["phase_change"] = params["phase_change"]

    for key in ("runtime_dimension", "runtime_coordinate_system", "runtime_material_variables"):
        if key in params and key not in electric_params:
            electric_params[key] = params[key]
        if key in params and key not in heat_params:
            heat_params[key] = params[key]

    if "include_joule_heat" not in electric_params:
        electric_params["include_joule_heat"] = True

    default_bcs = _dump_bcs(bcs)
    electric_bcs = _ensure_bcs_list(electric_params.get("bcs", default_bcs))
    heat_bcs = _ensure_bcs_list(heat_params.get("bcs", default_bcs))

    electric_cfg = {"model": "electric_ac", "parameters": electric_params}
    electric_artifact = solve_linear_problem(
        mesh,
        cell_tags,
        facet_tags,
        electric_cfg,
        electric_bcs,
        materials,
        solver,
        tag_map,
    )

    joule_heat = electric_artifact.fields.get("joule_heat")
    if joule_heat is None:
        raise RuntimeError("Electric solve did not produce 'joule_heat' field")

    heat_params["source_field"] = joule_heat
    heat_cfg = {"model": "heat_transient", "parameters": heat_params}
    heat_artifact = solve_transient_heat(
        mesh,
        cell_tags,
        facet_tags,
        heat_cfg,
        heat_bcs,
        materials,
        solver,
        tag_map,
        source_field=joule_heat,
    )

    fields: Dict[str, Any] = {}
    fields.update(electric_artifact.fields)
    fields.update(heat_artifact.fields)

    solver_info = {
        "electric": electric_artifact.solver_report,
        "heat": heat_artifact.solver_report,
    }

    return SolveArtifact(fields=fields, derived_fields={}, solver_report=solver_info, timings={})


def solve_problem(
    mesh: Any,
    cell_tags: Any,
    facet_tags: Any,
    physics: Any,
    bcs: Any,
    materials: Any,
    solver: Any,
    tag_map: Dict[str, Dict[str, int]],
) -> SolveArtifact:
    plan = _SOLVE_PLANS.get(_physics_model(physics), solve_linear_problem)
    return plan(mesh, cell_tags, facet_tags, physics, bcs, materials, solver, tag_map)
