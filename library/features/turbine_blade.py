from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import cadquery as cq

from features.utils import color_from, validate_non_negative, validate_positive


# -----------------------------------------------------------------------------
# Dataclasses
# -----------------------------------------------------------------------------


@dataclass(frozen=True)
class AirfoilSectionSpec:
    """2D airfoil section at a specific span location."""

    eta: float  # Span location [0=hub, 1=tip]
    chord: float  # Chord length
    stagger_angle_deg: float  # Chord line vs axial (gamma)
    inlet_metal_angle_deg: float  # beta_1,m
    outlet_metal_angle_deg: float  # beta_2,m
    max_thickness: float  # t_max (absolute, not % chord)
    le_radius: float  # R_LE
    te_thickness: float  # t_TE
    max_thickness_location: float = 0.3  # u_tmax in [0, 1]
    te_wedge_angle_deg: float = 10.0  # delta_TE
    camber_control_points: tuple[tuple[float, float], ...] | None = None
    thickness_control_points: tuple[tuple[float, float], ...] | None = None
    suction_side_bias: float = 0.0  # Asymmetric thickness (0 = symmetric)
    stacking_axis_x: float = 0.0  # Fraction of chord from LE


@dataclass(frozen=True)
class SpanwiseLawSpec:
    """Spanwise distribution laws for twist, sweep, and lean."""

    # Control points as (eta, value) pairs
    twist_control_points: tuple[tuple[float, float], ...] = ((0.0, 0.0), (1.0, 0.0))
    sweep_control_points: tuple[tuple[float, float], ...] = ((0.0, 0.0), (1.0, 0.0))
    lean_control_points: tuple[tuple[float, float], ...] = ((0.0, 0.0), (1.0, 0.0))
    stacking_axis_control_points: tuple[tuple[float, float], ...] | None = None


@dataclass(frozen=True)
class PlatformSpec:
    """Hub platform geometry at blade root."""

    axial_width: float  # Total axial extent
    circumferential_width: float  # Angular extent in degrees
    height: float  # Radial thickness below blade root
    fillet_radius: float = 0.0
    axial_upstream: float | None = None  # If None, symmetric
    axial_downstream: float | None = None


@dataclass(frozen=True)
class ShroudSpec:
    """Tip shroud geometry for shrouded blades."""

    axial_width: float
    circumferential_width: float  # Angular extent in degrees
    height: float  # Radial thickness above blade tip
    fillet_radius: float = 0.0
    axial_upstream: float | None = None
    axial_downstream: float | None = None
    knife_seal_count: int = 0
    knife_seal_height: float = 0.0
    knife_seal_width: float = 0.0
    knife_seal_spacing: float = 0.0


@dataclass(frozen=True)
class TurbineBladeSpec:
    """Complete turbine blade specification for axial turbine."""

    hub_radius: float  # r_hub
    tip_radius: float  # r_tip (span H = tip_radius - hub_radius)
    sections: tuple[AirfoilSectionSpec, ...]  # Minimum 2: hub and tip
    spanwise_laws: SpanwiseLawSpec = SpanwiseLawSpec()
    platform: PlatformSpec | None = None
    shroud: ShroudSpec | None = None
    airfoil_points_per_side: int = 50  # Points for airfoil discretization
    span_interpolation_points: int = 20  # Intermediate loft sections
    loft_ruled: bool = False  # True for ruled surface, False for smooth
    axial_axis: Literal["X", "Y", "Z"] = "Z"  # Flow direction
    radial_axis: Literal["X", "Y", "Z"] = "Y"  # Span direction
    blade_color: str | tuple[float, float, float, float] | None = None
    platform_color: str | tuple[float, float, float, float] | None = None
    shroud_color: str | tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class TurbineBladeGeometry:
    """Resolved/computed turbine blade geometry."""

    span: float
    hub_radius: float
    tip_radius: float
    section_count: int
    eta_values: tuple[float, ...]
    chord_distribution: tuple[float, ...]
    stagger_distribution: tuple[float, ...]
    sweep_distribution: tuple[float, ...]
    lean_distribution: tuple[float, ...]


# -----------------------------------------------------------------------------
# Validation Functions
# -----------------------------------------------------------------------------


def _validate_control_points(points: tuple, name: str) -> None:
    """Validate NURBS control point sequence."""
    if len(points) < 2:
        raise ValueError(f"{name} control points must have at least 2 points.")

    prev_u = -1.0
    for u, v in points:
        if not 0.0 <= u <= 1.0:
            raise ValueError(f"{name} control point u must be in [0, 1].")
        if u <= prev_u:
            raise ValueError(f"{name} control points must be ordered by u.")
        prev_u = u


def _validate_section(section: AirfoilSectionSpec, index: int) -> None:
    """Validate a single airfoil section."""
    prefix = f"Section {index}"

    if not 0.0 <= section.eta <= 1.0:
        raise ValueError(f"{prefix} eta must be in [0, 1].")

    validate_positive(f"{prefix} chord", section.chord)
    validate_positive(f"{prefix} max_thickness", section.max_thickness)
    validate_positive(f"{prefix} le_radius", section.le_radius)
    validate_non_negative(f"{prefix} te_thickness", section.te_thickness)

    if not 0.0 < section.max_thickness_location < 1.0:
        raise ValueError(f"{prefix} max_thickness_location must be in (0, 1).")

    if section.max_thickness > section.chord * 0.5:
        raise ValueError(f"{prefix} max_thickness exceeds 50% of chord.")

    if section.le_radius > section.max_thickness / 2:
        raise ValueError(f"{prefix} le_radius too large for max_thickness.")

    if not 0.0 <= section.stacking_axis_x <= 1.0:
        raise ValueError(f"{prefix} stacking_axis_x must be in [0, 1].")

    if section.camber_control_points:
        _validate_control_points(section.camber_control_points, f"{prefix} camber")
    if section.thickness_control_points:
        _validate_control_points(
            section.thickness_control_points, f"{prefix} thickness"
        )


def _validate_spanwise_laws(laws: SpanwiseLawSpec) -> None:
    """Validate spanwise distribution laws."""
    _validate_control_points(laws.twist_control_points, "Twist")
    _validate_control_points(laws.sweep_control_points, "Sweep")
    _validate_control_points(laws.lean_control_points, "Lean")

    if laws.stacking_axis_control_points:
        _validate_control_points(laws.stacking_axis_control_points, "Stacking axis")


def _validate_platform(platform: PlatformSpec) -> None:
    """Validate platform specification."""
    validate_positive("Platform axial_width", platform.axial_width)
    validate_positive("Platform circumferential_width", platform.circumferential_width)
    validate_positive("Platform height", platform.height)
    validate_non_negative("Platform fillet_radius", platform.fillet_radius)


def _validate_shroud(shroud: ShroudSpec) -> None:
    """Validate shroud specification."""
    validate_positive("Shroud axial_width", shroud.axial_width)
    validate_positive("Shroud circumferential_width", shroud.circumferential_width)
    validate_positive("Shroud height", shroud.height)
    validate_non_negative("Shroud fillet_radius", shroud.fillet_radius)

    if shroud.knife_seal_count > 0:
        validate_positive("Shroud knife_seal_height", shroud.knife_seal_height)
        validate_positive("Shroud knife_seal_width", shroud.knife_seal_width)


def _validate_spec(spec: TurbineBladeSpec) -> None:
    """Validate turbine blade specification."""
    validate_positive("hub_radius", spec.hub_radius)
    validate_positive("tip_radius", spec.tip_radius)
    if spec.tip_radius <= spec.hub_radius:
        raise ValueError("tip_radius must be greater than hub_radius.")

    if len(spec.sections) < 2:
        raise ValueError("At least 2 airfoil sections required (hub and tip).")

    prev_eta = -1.0
    for i, section in enumerate(spec.sections):
        _validate_section(section, i)
        if section.eta <= prev_eta:
            raise ValueError(f"Section {i} eta must be greater than previous section.")
        prev_eta = section.eta

    if spec.sections[0].eta != 0.0:
        raise ValueError("First section must have eta = 0.0 (hub).")
    if spec.sections[-1].eta != 1.0:
        raise ValueError("Last section must have eta = 1.0 (tip).")

    _validate_spanwise_laws(spec.spanwise_laws)

    if spec.platform is not None:
        _validate_platform(spec.platform)

    if spec.shroud is not None:
        _validate_shroud(spec.shroud)

    if spec.airfoil_points_per_side < 10:
        raise ValueError("airfoil_points_per_side must be at least 10.")
    if spec.span_interpolation_points < 2:
        raise ValueError("span_interpolation_points must be at least 2.")


# -----------------------------------------------------------------------------
# Utility Functions
# -----------------------------------------------------------------------------


def _eval_spline_law(
    control_points: tuple[tuple[float, float], ...],
    eta: float,
) -> float:
    """Evaluate spanwise law at given eta using linear interpolation."""
    points = sorted(control_points, key=lambda p: p[0])

    if eta <= points[0][0]:
        return points[0][1]
    if eta >= points[-1][0]:
        return points[-1][1]

    for i in range(len(points) - 1):
        if points[i][0] <= eta <= points[i + 1][0]:
            t = (eta - points[i][0]) / (points[i + 1][0] - points[i][0])
            return points[i][1] + t * (points[i + 1][1] - points[i][1])

    return points[-1][1]


def _interp_section_param(
    sections: tuple[AirfoilSectionSpec, ...],
    eta: float,
    param_name: str,
) -> float:
    """Linearly interpolate a section parameter at given eta."""
    for i in range(len(sections) - 1):
        if sections[i].eta <= eta <= sections[i + 1].eta:
            s0, s1 = sections[i], sections[i + 1]
            t = (eta - s0.eta) / (s1.eta - s0.eta) if s1.eta != s0.eta else 0
            v0 = getattr(s0, param_name)
            v1 = getattr(s1, param_name)
            return v0 + t * (v1 - v0)

    if eta <= sections[0].eta:
        return getattr(sections[0], param_name)
    return getattr(sections[-1], param_name)


def _interpolate_section_at_eta(
    sections: tuple[AirfoilSectionSpec, ...],
    eta: float,
) -> AirfoilSectionSpec:
    """Create an interpolated section at given eta."""
    for i in range(len(sections) - 1):
        if sections[i].eta <= eta <= sections[i + 1].eta:
            s0, s1 = sections[i], sections[i + 1]
            t = (eta - s0.eta) / (s1.eta - s0.eta) if s1.eta != s0.eta else 0

            return AirfoilSectionSpec(
                eta=eta,
                chord=s0.chord + t * (s1.chord - s0.chord),
                stagger_angle_deg=s0.stagger_angle_deg
                + t * (s1.stagger_angle_deg - s0.stagger_angle_deg),
                inlet_metal_angle_deg=s0.inlet_metal_angle_deg
                + t * (s1.inlet_metal_angle_deg - s0.inlet_metal_angle_deg),
                outlet_metal_angle_deg=s0.outlet_metal_angle_deg
                + t * (s1.outlet_metal_angle_deg - s0.outlet_metal_angle_deg),
                max_thickness=s0.max_thickness
                + t * (s1.max_thickness - s0.max_thickness),
                max_thickness_location=s0.max_thickness_location
                + t * (s1.max_thickness_location - s0.max_thickness_location),
                le_radius=s0.le_radius + t * (s1.le_radius - s0.le_radius),
                te_thickness=s0.te_thickness + t * (s1.te_thickness - s0.te_thickness),
                te_wedge_angle_deg=s0.te_wedge_angle_deg
                + t * (s1.te_wedge_angle_deg - s0.te_wedge_angle_deg),
                stacking_axis_x=s0.stacking_axis_x
                + t * (s1.stacking_axis_x - s0.stacking_axis_x),
                suction_side_bias=s0.suction_side_bias
                + t * (s1.suction_side_bias - s0.suction_side_bias),
                camber_control_points=(
                    s0.camber_control_points if t < 0.5 else s1.camber_control_points
                ),
                thickness_control_points=(
                    s0.thickness_control_points
                    if t < 0.5
                    else s1.thickness_control_points
                ),
            )

    if eta <= sections[0].eta:
        return sections[0]
    return sections[-1]


# -----------------------------------------------------------------------------
# Geometry Resolution
# -----------------------------------------------------------------------------


def _generate_eta_values(spec: TurbineBladeSpec) -> list[float]:
    """Generate eta values including user sections and interpolated points."""
    user_etas = {s.eta for s in spec.sections}
    all_etas = set()
    for i in range(spec.span_interpolation_points + 1):
        eta = i / spec.span_interpolation_points
        all_etas.add(eta)
    all_etas.update(user_etas)
    return sorted(all_etas)


def _blade_geometry(spec: TurbineBladeSpec) -> TurbineBladeGeometry:
    """Resolve turbine blade geometry from specification."""
    _validate_spec(spec)

    span = spec.tip_radius - spec.hub_radius
    eta_values = _generate_eta_values(spec)
    section_count = len(eta_values)

    chord_dist = tuple(
        _interp_section_param(spec.sections, eta, "chord") for eta in eta_values
    )

    base_stagger = [
        _interp_section_param(spec.sections, eta, "stagger_angle_deg")
        for eta in eta_values
    ]
    twist_offset = [
        _eval_spline_law(spec.spanwise_laws.twist_control_points, eta)
        for eta in eta_values
    ]
    stagger_dist = tuple(bs + tw for bs, tw in zip(base_stagger, twist_offset))

    sweep_dist = tuple(
        _eval_spline_law(spec.spanwise_laws.sweep_control_points, eta)
        for eta in eta_values
    )
    lean_dist = tuple(
        _eval_spline_law(spec.spanwise_laws.lean_control_points, eta)
        for eta in eta_values
    )

    return TurbineBladeGeometry(
        span=span,
        hub_radius=spec.hub_radius,
        tip_radius=spec.tip_radius,
        section_count=section_count,
        eta_values=tuple(eta_values),
        chord_distribution=chord_dist,
        stagger_distribution=stagger_dist,
        sweep_distribution=sweep_dist,
        lean_distribution=lean_dist,
    )


# -----------------------------------------------------------------------------
# Airfoil Construction
# -----------------------------------------------------------------------------


def _build_camber_line(
    section: AirfoilSectionSpec,
    num_points: int,
) -> list[tuple[float, float]]:
    """Build camber line as list of (x, y) points."""
    chord = section.chord
    gamma = math.radians(section.stagger_angle_deg)
    beta1 = math.radians(section.inlet_metal_angle_deg)
    beta2 = math.radians(section.outlet_metal_angle_deg)

    tan_le = math.tan(beta1 - gamma)
    tan_te = math.tan(beta2 - gamma)

    u_values = [i / (num_points - 1) for i in range(num_points)]

    if section.camber_control_points:
        points = []
        for u in u_values:
            x = u * chord
            y_base = _eval_spline_law(section.camber_control_points, u)
            h10 = u**3 - 2 * u**2 + u
            h11 = u**3 - u**2
            y_hermite = h10 * (tan_le * chord) + h11 * (tan_te * chord)
            y = y_base * chord + y_hermite
            points.append((x, y))
    else:
        points = []
        for u in u_values:
            x = u * chord
            h00 = 2 * u**3 - 3 * u**2 + 1
            h10 = u**3 - 2 * u**2 + u
            h01 = -2 * u**3 + 3 * u**2
            h11 = u**3 - u**2
            y = h10 * (tan_le * chord) + h11 * (tan_te * chord)
            points.append((x, y))

    return points


def _naca_thickness_blend(
    u: float,
    t_max: float,
    u_tmax: float,
    r_le: float,
    t_te: float,
) -> float:
    """NACA-style thickness distribution with custom parameters."""
    if u <= 0.001:
        return 2 * math.sqrt(2 * r_le * max(u, 0.0001))

    if u <= u_tmax:
        blend = u / u_tmax
        t_le_contrib = 2 * math.sqrt(2 * r_le * u) * (1 - blend)
        t_max_contrib = t_max * math.sin(blend * math.pi / 2)
        return t_le_contrib + t_max_contrib
    else:
        blend = (u - u_tmax) / (1.0 - u_tmax)
        return t_max * (1 - blend) + t_te * blend


def _build_thickness_distribution(
    section: AirfoilSectionSpec,
    u_values: list[float],
) -> list[float]:
    """Build thickness distribution t(u) for normalized chord positions."""
    t_max = section.max_thickness
    u_tmax = section.max_thickness_location
    t_te = section.te_thickness
    r_le = section.le_radius

    if section.thickness_control_points:
        thicknesses = [
            _eval_spline_law(section.thickness_control_points, u) for u in u_values
        ]
    else:
        thicknesses = []
        for u in u_values:
            t = _naca_thickness_blend(u, t_max, u_tmax, r_le, t_te)
            thicknesses.append(max(0, t))

    return thicknesses


def _compute_camber_tangents(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Compute tangent vectors at each camber line point."""
    tangents = []
    n = len(points)

    for i in range(n):
        if i == 0:
            dx = points[1][0] - points[0][0]
            dy = points[1][1] - points[0][1]
        elif i == n - 1:
            dx = points[-1][0] - points[-2][0]
            dy = points[-1][1] - points[-2][1]
        else:
            dx = points[i + 1][0] - points[i - 1][0]
            dy = points[i + 1][1] - points[i - 1][1]

        tangents.append((dx, dy))

    return tangents


def _build_airfoil_wire(
    section: AirfoilSectionSpec,
    num_points: int,
) -> cq.Wire:
    """Build complete airfoil as a closed CadQuery Wire."""
    camber_points = _build_camber_line(section, num_points)
    u_values = [i / (num_points - 1) for i in range(num_points)]
    thicknesses = _build_thickness_distribution(section, u_values)
    tangents = _compute_camber_tangents(camber_points)

    upper_points = []
    lower_points = []
    suction_bias = section.suction_side_bias

    for (x, y), t, (dx, dy) in zip(camber_points, thicknesses, tangents):
        mag = math.sqrt(dx**2 + dy**2)
        if mag > 1e-10:
            nx, ny = -dy / mag, dx / mag
        else:
            nx, ny = 0, 1

        t_upper = t / 2 * (1 + suction_bias)
        t_lower = t / 2 * (1 - suction_bias)

        upper_points.append((x + nx * t_upper, y + ny * t_upper))
        lower_points.append((x - nx * t_lower, y - ny * t_lower))

    edges = []

    upper_vectors = [cq.Vector(x, y, 0) for x, y in upper_points]
    upper_edge = cq.Edge.makeSpline(upper_vectors)
    edges.append(upper_edge)

    if section.te_thickness > 1e-6:
        te_edge = cq.Edge.makeLine(
            cq.Vector(*upper_points[-1], 0),
            cq.Vector(*lower_points[-1], 0),
        )
        edges.append(te_edge)

    lower_vectors = [cq.Vector(x, y, 0) for x, y in reversed(lower_points)]
    lower_edge = cq.Edge.makeSpline(lower_vectors)
    edges.append(lower_edge)

    le_upper = upper_points[0]
    le_lower = lower_points[0]
    le_mid = camber_points[0]

    # Calculate distance between upper and lower LE points
    le_dist = math.sqrt(
        (le_upper[0] - le_lower[0]) ** 2 + (le_upper[1] - le_lower[1]) ** 2
    )

    # If the LE points are very close (nearly coincident), skip the LE edge
    if le_dist < 1e-6:
        # Points coincide, no edge needed - the splines already connect
        pass
    elif le_dist < section.le_radius * 0.1:
        # Very small gap, use a line instead of arc
        try:
            le_edge = cq.Edge.makeLine(
                cq.Vector(*le_lower, 0),
                cq.Vector(*le_upper, 0),
            )
            edges.append(le_edge)
        except Exception:
            pass  # Skip if line also fails
    else:
        # Normal case: create an arc
        le_x = le_mid[0] - section.le_radius
        le_y = le_mid[1]

        try:
            le_edge = cq.Edge.makeThreePointArc(
                cq.Vector(*le_lower, 0),
                cq.Vector(le_x, le_y, 0),
                cq.Vector(*le_upper, 0),
            )
            edges.append(le_edge)
        except Exception:
            # Fallback to line if arc fails
            try:
                le_edge = cq.Edge.makeLine(
                    cq.Vector(*le_lower, 0),
                    cq.Vector(*le_upper, 0),
                )
                edges.append(le_edge)
            except Exception:
                pass  # Skip if line also fails

    wire = cq.Wire.assembleEdges(edges)
    return wire


# -----------------------------------------------------------------------------
# 3D Blade Surface Construction
# -----------------------------------------------------------------------------


def _transform_airfoil_to_3d(
    wire: cq.Wire,
    stacking_x: float,
    stagger_deg: float,
    radius: float,
    sweep: float,
    lean_deg: float,
    axial_axis: str,
    radial_axis: str,
) -> cq.Wire:
    """Transform 2D airfoil wire to 3D blade position."""
    wire = wire.translate(cq.Vector(-stacking_x, 0, 0))
    wire = wire.rotate(
        cq.Vector(0, 0, 0),
        cq.Vector(0, 0, 1),
        stagger_deg,
    )

    if radial_axis == "Y" and axial_axis == "Z":
        wire = wire.rotate(
            cq.Vector(0, 0, 0),
            cq.Vector(1, 0, 0),
            90,
        )
        radial_vector = cq.Vector(0, radius, 0)
        sweep_vector = cq.Vector(0, 0, sweep)
        lean_axis_vec = cq.Vector(0, 1, 0)
    elif radial_axis == "Z" and axial_axis == "X":
        wire = wire.rotate(
            cq.Vector(0, 0, 0),
            cq.Vector(0, 1, 0),
            -90,
        )
        radial_vector = cq.Vector(0, 0, radius)
        sweep_vector = cq.Vector(sweep, 0, 0)
        lean_axis_vec = cq.Vector(0, 0, 1)
    else:
        radial_vector = cq.Vector(0, radius, 0)
        sweep_vector = cq.Vector(0, 0, sweep)
        lean_axis_vec = cq.Vector(0, 1, 0)

    wire = wire.translate(radial_vector)
    wire = wire.translate(sweep_vector)

    if abs(lean_deg) > 1e-6:
        wire = wire.rotate(
            cq.Vector(0, 0, 0),
            lean_axis_vec,
            lean_deg,
        )

    return wire


def _build_blade_surface(
    spec: TurbineBladeSpec,
    geom: TurbineBladeGeometry,
) -> cq.Solid:
    """Build 3D blade surface by lofting transformed airfoil sections."""
    span = geom.span
    section_wires = []

    for i, eta in enumerate(geom.eta_values):
        section = _interpolate_section_at_eta(spec.sections, eta)
        wire_2d = _build_airfoil_wire(section, spec.airfoil_points_per_side)

        stagger = geom.stagger_distribution[i]
        sweep = geom.sweep_distribution[i]
        lean = geom.lean_distribution[i]

        if spec.spanwise_laws.stacking_axis_control_points:
            x_stack = _eval_spline_law(
                spec.spanwise_laws.stacking_axis_control_points, eta
            )
        else:
            x_stack = section.stacking_axis_x

        stacking_x = x_stack * section.chord
        r = spec.hub_radius + eta * span

        wire_3d = _transform_airfoil_to_3d(
            wire_2d,
            stacking_x=stacking_x,
            stagger_deg=stagger,
            radius=r,
            sweep=sweep,
            lean_deg=lean,
            axial_axis=spec.axial_axis,
            radial_axis=spec.radial_axis,
        )

        section_wires.append(wire_3d)

    faces = [cq.Face.makeFromWires(w) for w in section_wires]
    wp = cq.Workplane("XY")
    for face in faces:
        wp = wp.add(face)

    blade_solid = wp.loft(ruled=spec.loft_ruled)

    return blade_solid.val()


# -----------------------------------------------------------------------------
# Platform and Shroud Construction
# -----------------------------------------------------------------------------


def _build_platform(
    spec: TurbineBladeSpec,
    blade_solid: cq.Solid,
) -> cq.Solid | None:
    """Build hub platform geometry."""
    if spec.platform is None:
        return None

    platform = spec.platform
    hub_section = spec.sections[0]
    chord = hub_section.chord

    axial_up = platform.axial_upstream or platform.axial_width / 2
    axial_down = platform.axial_downstream or platform.axial_width / 2

    r_hub = spec.hub_radius
    r_platform = r_hub - platform.height

    theta_half = math.radians(platform.circumferential_width / 2)

    wp = cq.Workplane("XY")

    pts = [
        (r_hub * math.cos(-theta_half), r_hub * math.sin(-theta_half)),
        (r_hub, 0),
        (r_hub * math.cos(theta_half), r_hub * math.sin(theta_half)),
    ]

    platform_sketch = (
        wp.moveTo(pts[0][0], pts[0][1])
        .threePointArc(pts[1], pts[2])
        .lineTo(r_platform * math.cos(theta_half), r_platform * math.sin(theta_half))
        .threePointArc(
            (r_platform, 0),
            (r_platform * math.cos(-theta_half), r_platform * math.sin(-theta_half)),
        )
        .close()
    )

    platform_solid = platform_sketch.extrude(axial_up + axial_down)

    if spec.axial_axis == "Z":
        platform_solid = platform_solid.translate((0, 0, -axial_up))
    elif spec.axial_axis == "X":
        platform_solid = platform_solid.rotate(
            (0, 0, 0), (0, 1, 0), 90
        ).translate((- axial_up, 0, 0))

    if platform.fillet_radius > 0:
        try:
            platform_solid = platform_solid.edges().fillet(platform.fillet_radius)
        except Exception:
            print("WARN: Platform fillet failed (try smaller radius).")

    return platform_solid.val()


def _build_shroud(
    spec: TurbineBladeSpec,
    blade_solid: cq.Solid,
) -> cq.Solid | None:
    """Build tip shroud geometry."""
    if spec.shroud is None:
        return None

    shroud = spec.shroud
    tip_section = spec.sections[-1]

    axial_up = shroud.axial_upstream or shroud.axial_width / 2
    axial_down = shroud.axial_downstream or shroud.axial_width / 2

    r_tip = spec.tip_radius
    r_shroud = r_tip + shroud.height

    theta_half = math.radians(shroud.circumferential_width / 2)

    wp = cq.Workplane("XY")

    pts = [
        (r_shroud * math.cos(-theta_half), r_shroud * math.sin(-theta_half)),
        (r_shroud, 0),
        (r_shroud * math.cos(theta_half), r_shroud * math.sin(theta_half)),
    ]

    shroud_sketch = (
        wp.moveTo(pts[0][0], pts[0][1])
        .threePointArc(pts[1], pts[2])
        .lineTo(r_tip * math.cos(theta_half), r_tip * math.sin(theta_half))
        .threePointArc(
            (r_tip, 0),
            (r_tip * math.cos(-theta_half), r_tip * math.sin(-theta_half)),
        )
        .close()
    )

    shroud_solid = shroud_sketch.extrude(axial_up + axial_down)

    if spec.axial_axis == "Z":
        shroud_solid = shroud_solid.translate((0, 0, -axial_up))
    elif spec.axial_axis == "X":
        shroud_solid = shroud_solid.rotate(
            (0, 0, 0), (0, 1, 0), 90
        ).translate((-axial_up, 0, 0))

    if shroud.knife_seal_count > 0:
        shroud_solid = _add_knife_seals(shroud_solid, shroud, r_shroud, spec.axial_axis)

    if shroud.fillet_radius > 0:
        try:
            shroud_solid = shroud_solid.edges().fillet(shroud.fillet_radius)
        except Exception:
            print("WARN: Shroud fillet failed (try smaller radius).")

    return shroud_solid.val()


def _add_knife_seals(
    shroud_solid: cq.Workplane,
    shroud: ShroudSpec,
    r_outer: float,
    axial_axis: str,
) -> cq.Workplane:
    """Add knife seal features to shroud."""
    h = shroud.knife_seal_height
    w = shroud.knife_seal_width
    spacing = shroud.knife_seal_spacing

    total_span = (shroud.knife_seal_count - 1) * spacing
    start_pos = -total_span / 2

    for i in range(shroud.knife_seal_count):
        pos = start_pos + i * spacing

        seal = cq.Workplane("XY").circle(r_outer + h).circle(r_outer).extrude(w)
        seal = seal.translate((0, 0, -w / 2))

        if axial_axis == "Z":
            seal = seal.translate((0, 0, pos))
        elif axial_axis == "X":
            seal = seal.rotate((0, 0, 0), (0, 1, 0), 90).translate((pos, 0, 0))

        shroud_solid = shroud_solid.union(seal)

    return shroud_solid


# -----------------------------------------------------------------------------
# Main Build Function
# -----------------------------------------------------------------------------


def build_turbine_blade(spec: TurbineBladeSpec) -> cq.Assembly:
    """
    Build complete turbine blade assembly.

    Returns an assembly with named parts:
    - "{name}_blade": The main blade airfoil surface
    - "{name}_platform": Hub platform (if specified)
    - "{name}_shroud": Tip shroud (if specified)
    """
    geom = _blade_geometry(spec)
    blade_solid = _build_blade_surface(spec, geom)
    platform_solid = _build_platform(spec, blade_solid)
    shroud_solid = _build_shroud(spec, blade_solid)

    assembly = cq.Assembly()

    blade_color = color_from(spec.blade_color, (0.7, 0.7, 0.75, 1.0))
    assembly.add(blade_solid, name="blade", color=blade_color)

    if platform_solid is not None:
        platform_color = color_from(spec.platform_color, (0.6, 0.6, 0.65, 1.0))
        assembly.add(platform_solid, name="platform", color=platform_color)

    if shroud_solid is not None:
        shroud_color = color_from(spec.shroud_color, (0.6, 0.6, 0.65, 1.0))
        assembly.add(shroud_solid, name="shroud", color=shroud_color)

    return assembly
