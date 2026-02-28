from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import cadquery as cq

from simparts.features.utils import validate_non_negative, validate_positive


WireShape = Literal["round", "square", "rectangular", "custom"]
HelixHand = Literal["RH", "LH"]
SpringAxis = Literal["X", "Y", "Z"]

CompressionEndType = Literal[
    "plain",
    "plain_ground",
    "squared",
    "squared_ground",
    "closed",
    "closed_ground",
    "custom",
]

HookType = Literal["machine", "crossover_center", "side", "threaded_insert", "custom"]
HookPlane = Literal["in_plane", "out_of_plane"]

LegType = Literal["tangent", "radial", "axial", "custom"]
LegPlane = Literal["in_plane", "out_of_plane"]

DiameterProfile = Literal["linear", "parabolic", "custom"]
PitchProfile = Literal["constant", "linear", "parabolic", "custom"]

WaveForm = Literal["sinusoidal", "trapezoidal", "custom"]
SpiralLaw = Literal["archimedean", "custom"]
SpiralHand = Literal["CW", "CCW"]


@dataclass(frozen=True)
class WireSection:
    shape: WireShape = "round"
    diameter: float | None = None
    width: float | None = None
    thickness: float | None = None
    corner_radius: float = 0.0
    radial_thickness: float | None = None


@dataclass(frozen=True)
class HelicalBodySpec:
    wire: WireSection
    mean_diameter: float | None = None
    outer_diameter: float | None = None
    inner_diameter: float | None = None
    pitch: float | None = None
    helix_angle_deg: float | None = None
    free_length: float | None = None
    total_coils: float = 1.0
    active_coils: float | None = None
    end_coils: float | None = None
    hand: HelixHand = "RH"
    clocking_deg: float = 0.0
    axis: SpringAxis = "Z"
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class CompressionEndSpec:
    end_type: CompressionEndType = "plain"
    closed_turns: float = 0.0
    ground_length: float = 0.0
    ground_depth: float = 0.0
    ground_angle_deg: float = 0.0
    transition_turns: float = 0.0
    clocking_deg: float = 0.0


@dataclass(frozen=True)
class CompressionSpringSpec:
    body: HelicalBodySpec
    end_a: CompressionEndSpec | None = None
    end_b: CompressionEndSpec | None = None


@dataclass(frozen=True)
class HookSpec:
    hook_type: HookType = "machine"
    inside_diameter: float | None = None
    mean_diameter: float | None = None
    opening: float | None = None
    length: float | None = None
    bend_radius: float | None = None
    plane: HookPlane = "in_plane"
    angle_deg: float = 0.0
    clocking_deg: float = 0.0


@dataclass(frozen=True)
class ExtensionSpringSpec:
    body: HelicalBodySpec
    hook_a: HookSpec | None = None
    hook_b: HookSpec | None = None
    initial_tension_gap: float | None = None


@dataclass(frozen=True)
class TorsionLegSpec:
    leg_type: LegType = "tangent"
    length: float = 0.0
    bend_angle_deg: float = 0.0
    plane: LegPlane = "in_plane"
    bend_radius: float = 0.0
    end_feature: str | None = None
    clocking_deg: float = 0.0
    transition_turns: float = 0.0


@dataclass(frozen=True)
class TorsionSpringSpec:
    body: HelicalBodySpec
    leg_a: TorsionLegSpec | None = None
    leg_b: TorsionLegSpec | None = None
    included_angle_deg: float | None = None


@dataclass(frozen=True)
class VariableDiameterHelixSpec:
    wire: WireSection
    mean_diameter_small: float | None = None
    mean_diameter_large: float | None = None
    outer_diameter_small: float | None = None
    outer_diameter_large: float | None = None
    inner_diameter_small: float | None = None
    inner_diameter_large: float | None = None
    cone_angle_deg: float | None = None
    free_length: float | None = None
    total_coils: float = 1.0
    pitch: float | None = None
    pitch_small: float | None = None
    pitch_large: float | None = None
    diameter_profile: DiameterProfile = "linear"
    pitch_profile: PitchProfile = "constant"
    end_a: CompressionEndSpec | None = None
    end_b: CompressionEndSpec | None = None
    hand: HelixHand = "RH"
    clocking_deg: float = 0.0
    axis: SpringAxis = "Z"
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class WaveSpringSpec:
    thickness: float
    waves: int
    wave_height: float
    mean_diameter: float | None = None
    inner_diameter: float | None = None
    outer_diameter: float | None = None
    radial_width: float | None = None
    wave_form: WaveForm = "sinusoidal"
    turns: int = 1
    overlap: float = 0.0
    edge_radius: float = 0.0


@dataclass(frozen=True)
class FlatSpiralSpec:
    strip_thickness: float
    strip_width: float
    inner_diameter: float | None = None
    outer_diameter: float | None = None
    turns: float | None = None
    strip_length: float | None = None
    spiral_pitch: float | None = None
    spiral_law: SpiralLaw = "archimedean"
    handedness: SpiralHand = "CW"
    inner_attachment: str | None = None
    outer_attachment: str | None = None
    clearance: float = 0.0


@dataclass(frozen=True)
class HelicalSpringGeometry:
    mean_diameter: float
    outer_diameter: float
    inner_diameter: float
    pitch: float
    helix_angle_deg: float
    free_length: float
    total_coils: float
    active_coils: float
    end_coils: float
    spring_index: float
    solid_height: float
    coil_gap: float | None
    body_length: float
    wire_length: float


@dataclass(frozen=True)
class VariableDiameterGeometry:
    mean_diameter_small: float
    mean_diameter_large: float
    outer_diameter_small: float
    outer_diameter_large: float
    inner_diameter_small: float
    inner_diameter_large: float
    free_length: float | None
    total_coils: float
    pitch: float | None
    pitch_small: float | None
    pitch_large: float | None
    cone_angle_deg: float | None
    spring_index_small: float
    spring_index_large: float


@dataclass(frozen=True)
class WaveSpringGeometry:
    mean_diameter: float
    inner_diameter: float
    outer_diameter: float
    radial_width: float
    thickness: float
    waves: int
    wave_height: float
    turns: int


@dataclass(frozen=True)
class FlatSpiralGeometry:
    inner_diameter: float
    outer_diameter: float
    turns: float
    spiral_pitch: float
    strip_length: float | None


def _assert_close(name: str, a: float, b: float, tol: float = 1e-6) -> None:
    if abs(a - b) > tol * max(1.0, abs(a), abs(b)):
        raise ValueError(f"{name} values are inconsistent ({a:g} vs {b:g}).")


def _validate_wire_section(wire: WireSection) -> None:
    validate_non_negative("Wire corner_radius", wire.corner_radius)
    if wire.shape == "round":
        if wire.diameter is None:
            raise ValueError("Wire diameter is required for round wire.")
        validate_positive("Wire diameter", wire.diameter)
        return
    if wire.shape in ("square", "rectangular"):
        if wire.width is None or wire.thickness is None:
            raise ValueError("Wire width and thickness are required for non-round wire.")
        validate_positive("Wire width", wire.width)
        validate_positive("Wire thickness", wire.thickness)
        if wire.shape == "square":
            _assert_close("Square wire width/thickness", wire.width, wire.thickness)
        return
    if wire.shape == "custom":
        if wire.radial_thickness is None:
            raise ValueError("Wire radial_thickness is required for custom wire shapes.")
        validate_positive("Wire radial_thickness", wire.radial_thickness)
        return
    raise ValueError(f"Unsupported wire shape: {wire.shape}.")


def _wire_radial_thickness(wire: WireSection) -> float:
    if wire.shape == "round":
        if wire.diameter is None:
            raise ValueError("Wire diameter is required for round wire.")
        return wire.diameter
    if wire.shape in ("square", "rectangular"):
        if wire.thickness is None:
            raise ValueError("Wire thickness is required for non-round wire.")
        return wire.thickness
    if wire.radial_thickness is not None:
        return wire.radial_thickness
    if wire.thickness is not None:
        return wire.thickness
    if wire.diameter is not None:
        return wire.diameter
    raise ValueError("Wire radial thickness could not be resolved.")


def _resolve_diameters(
    mean: float | None,
    outer: float | None,
    inner: float | None,
    wire_thickness: float,
    *,
    label: str = "Helical",
) -> tuple[float, float, float]:
    if mean is None and outer is None and inner is None:
        raise ValueError(f"{label} spring must define mean, outer, or inner diameter.")
    if mean is None:
        if outer is not None and inner is not None:
            mean = (outer + inner) / 2.0
        elif outer is not None:
            mean = outer - wire_thickness
        else:
            mean = inner + wire_thickness
    if outer is None:
        outer = mean + wire_thickness
    if inner is None:
        inner = mean - wire_thickness
    validate_positive(f"{label} mean_diameter", mean)
    validate_positive(f"{label} outer_diameter", outer)
    validate_positive(f"{label} inner_diameter", inner)
    if outer <= inner:
        raise ValueError(f"{label} outer_diameter must be larger than inner_diameter.")
    if mean is not None:
        _assert_close(f"{label} outer_diameter", outer, mean + wire_thickness)
        _assert_close(f"{label} inner_diameter", inner, mean - wire_thickness)
    return mean, outer, inner


def _resolve_pitch(spec: HelicalBodySpec, mean_diameter: float) -> float:
    if spec.pitch is not None:
        validate_positive("Helical pitch", spec.pitch)
        return spec.pitch
    if spec.helix_angle_deg is not None:
        angle = abs(spec.helix_angle_deg)
        if angle >= 89.0:
            raise ValueError("Helix angle must be less than 89 degrees.")
        return math.tan(math.radians(spec.helix_angle_deg)) * math.pi * mean_diameter
    if spec.free_length is not None:
        validate_positive("Helical free_length", spec.free_length)
        if spec.total_coils <= 0:
            raise ValueError("Helical total_coils must be positive to resolve pitch.")
        return spec.free_length / spec.total_coils
    raise ValueError("Helical pitch, helix_angle_deg, or free_length must be provided.")


def _resolve_coil_counts(spec: HelicalBodySpec) -> tuple[float, float]:
    total = spec.total_coils
    validate_positive("Helical total_coils", total)
    active = spec.active_coils
    end = spec.end_coils
    if active is not None:
        validate_positive("Helical active_coils", active)
    if end is not None:
        validate_non_negative("Helical end_coils", end)
    if active is not None and end is not None:
        _assert_close("Helical coil count", active + end, total)
        return active, end
    if active is None and end is None:
        return total, 0.0
    if active is None:
        active = total - end
        if active <= 0:
            raise ValueError("Helical active_coils must be positive.")
        return active, end
    end = total - active
    if end < 0:
        raise ValueError("Helical end_coils cannot be negative.")
    return active, end


def resolve_helical_geometry(spec: HelicalBodySpec) -> HelicalSpringGeometry:
    _validate_wire_section(spec.wire)
    wire_thickness = _wire_radial_thickness(spec.wire)
    if wire_thickness <= 0:
        raise ValueError("Wire radial thickness must be positive.")
    mean, outer, inner = _resolve_diameters(
        spec.mean_diameter,
        spec.outer_diameter,
        spec.inner_diameter,
        wire_thickness,
    )
    pitch = _resolve_pitch(spec, mean)
    if pitch <= 0:
        raise ValueError("Helical pitch must be positive.")
    if spec.pitch is not None and spec.helix_angle_deg is not None:
        expected_pitch = math.tan(math.radians(spec.helix_angle_deg)) * math.pi * mean
        _assert_close("Helical pitch", spec.pitch, expected_pitch)
    helix_angle = spec.helix_angle_deg
    if helix_angle is None:
        helix_angle = math.degrees(math.atan(pitch / (math.pi * mean)))
    free_length = spec.free_length
    if free_length is None:
        free_length = pitch * spec.total_coils
    elif spec.pitch is not None:
        expected_length = spec.pitch * spec.total_coils
        _assert_close("Helical free_length", free_length, expected_length)
    validate_positive("Helical free_length", free_length)
    active, end = _resolve_coil_counts(spec)
    spring_index = mean / wire_thickness
    solid_height = wire_thickness * spec.total_coils
    coil_gap = None
    if spec.total_coils > 1:
        coil_gap = (free_length - solid_height) / (spec.total_coils - 1.0)
    turn_length = math.hypot(math.pi * mean, pitch)
    wire_length = turn_length * spec.total_coils
    return HelicalSpringGeometry(
        mean_diameter=mean,
        outer_diameter=outer,
        inner_diameter=inner,
        pitch=pitch,
        helix_angle_deg=helix_angle,
        free_length=free_length,
        total_coils=spec.total_coils,
        active_coils=active,
        end_coils=end,
        spring_index=spring_index,
        solid_height=solid_height,
        coil_gap=coil_gap,
        body_length=free_length,
        wire_length=wire_length,
    )


def _resolve_wave_diameters(spec: WaveSpringSpec) -> tuple[float, float, float, float]:
    mean = spec.mean_diameter
    inner = spec.inner_diameter
    outer = spec.outer_diameter
    radial_width = spec.radial_width
    if mean is None and inner is None and outer is None:
        raise ValueError("Wave spring must define mean, inner, or outer diameter.")
    if radial_width is not None:
        validate_positive("Wave spring radial_width", radial_width)
    if inner is not None:
        validate_positive("Wave spring inner_diameter", inner)
    if outer is not None:
        validate_positive("Wave spring outer_diameter", outer)
    if mean is None:
        if inner is not None and outer is not None:
            mean = (inner + outer) / 2.0
        elif inner is not None and radial_width is not None:
            outer = inner + radial_width
            mean = (inner + outer) / 2.0
        elif outer is not None and radial_width is not None:
            inner = outer - radial_width
            mean = (inner + outer) / 2.0
        else:
            raise ValueError("Wave spring mean diameter could not be resolved.")
    if radial_width is None:
        if inner is not None and outer is not None:
            radial_width = outer - inner
        else:
            raise ValueError("Wave spring radial_width could not be resolved.")
    if inner is None:
        inner = mean - radial_width / 2.0
    if outer is None:
        outer = mean + radial_width / 2.0
    validate_positive("Wave spring mean_diameter", mean)
    if outer <= inner:
        raise ValueError("Wave spring outer_diameter must be larger than inner_diameter.")
    return mean, inner, outer, radial_width


def resolve_wave_geometry(spec: WaveSpringSpec) -> WaveSpringGeometry:
    validate_positive("Wave spring thickness", spec.thickness)
    if spec.waves <= 0:
        raise ValueError("Wave spring waves must be positive.")
    validate_non_negative("Wave spring wave_height", spec.wave_height)
    if spec.turns <= 0:
        raise ValueError("Wave spring turns must be positive.")
    validate_non_negative("Wave spring overlap", spec.overlap)
    validate_non_negative("Wave spring edge_radius", spec.edge_radius)
    mean, inner, outer, radial_width = _resolve_wave_diameters(spec)
    return WaveSpringGeometry(
        mean_diameter=mean,
        inner_diameter=inner,
        outer_diameter=outer,
        radial_width=radial_width,
        thickness=spec.thickness,
        waves=spec.waves,
        wave_height=spec.wave_height,
        turns=spec.turns,
    )


def resolve_variable_diameter_geometry(spec: VariableDiameterHelixSpec) -> VariableDiameterGeometry:
    _validate_wire_section(spec.wire)
    wire_thickness = _wire_radial_thickness(spec.wire)
    validate_positive("Variable diameter total_coils", spec.total_coils)
    mean_small, outer_small, inner_small = _resolve_diameters(
        spec.mean_diameter_small,
        spec.outer_diameter_small,
        spec.inner_diameter_small,
        wire_thickness,
        label="Small end",
    )
    mean_large, outer_large, inner_large = _resolve_diameters(
        spec.mean_diameter_large,
        spec.outer_diameter_large,
        spec.inner_diameter_large,
        wire_thickness,
        label="Large end",
    )
    free_length = spec.free_length
    if free_length is not None:
        validate_positive("Variable diameter free_length", free_length)
    pitch = spec.pitch
    if pitch is not None:
        validate_positive("Variable diameter pitch", pitch)
    elif free_length is not None:
        pitch = free_length / spec.total_coils
    if pitch is not None and free_length is not None:
        expected_length = pitch * spec.total_coils
        _assert_close("Variable diameter free_length", free_length, expected_length)
    if spec.pitch_small is not None:
        validate_positive("Variable diameter pitch_small", spec.pitch_small)
    if spec.pitch_large is not None:
        validate_positive("Variable diameter pitch_large", spec.pitch_large)
    cone_angle = spec.cone_angle_deg
    if cone_angle is not None:
        validate_positive("Variable diameter cone_angle_deg", cone_angle)
    if cone_angle is None and free_length is not None:
        delta_r = (mean_large - mean_small) / 2.0
        if abs(delta_r) > 0:
            cone_angle = math.degrees(math.atan2(abs(delta_r), free_length))
    spring_index_small = mean_small / wire_thickness
    spring_index_large = mean_large / wire_thickness
    return VariableDiameterGeometry(
        mean_diameter_small=mean_small,
        mean_diameter_large=mean_large,
        outer_diameter_small=outer_small,
        outer_diameter_large=outer_large,
        inner_diameter_small=inner_small,
        inner_diameter_large=inner_large,
        free_length=free_length,
        total_coils=spec.total_coils,
        pitch=pitch,
        pitch_small=spec.pitch_small,
        pitch_large=spec.pitch_large,
        cone_angle_deg=cone_angle,
        spring_index_small=spring_index_small,
        spring_index_large=spring_index_large,
    )


def resolve_flat_spiral_geometry(spec: FlatSpiralSpec) -> FlatSpiralGeometry:
    validate_positive("Flat spiral strip_thickness", spec.strip_thickness)
    validate_positive("Flat spiral strip_width", spec.strip_width)
    validate_non_negative("Flat spiral clearance", spec.clearance)
    inner = spec.inner_diameter
    outer = spec.outer_diameter
    turns = spec.turns
    pitch = spec.spiral_pitch
    if inner is not None:
        validate_positive("Flat spiral inner_diameter", inner)
    if outer is not None:
        validate_positive("Flat spiral outer_diameter", outer)
    if turns is not None:
        validate_positive("Flat spiral turns", turns)
    if pitch is not None:
        validate_positive("Flat spiral spiral_pitch", pitch)
    if inner is None and outer is None:
        raise ValueError("Flat spiral must define inner_diameter or outer_diameter.")
    if pitch is None:
        if inner is not None and outer is not None and turns is not None:
            pitch = (outer - inner) / (2.0 * turns)
        else:
            raise ValueError("Flat spiral spiral_pitch could not be resolved.")
    if turns is None:
        if inner is not None and outer is not None:
            turns = (outer - inner) / (2.0 * pitch)
        else:
            raise ValueError("Flat spiral turns could not be resolved.")
    if inner is None:
        inner = outer - 2.0 * pitch * turns
    if outer is None:
        outer = inner + 2.0 * pitch * turns
    if outer <= inner:
        raise ValueError("Flat spiral outer_diameter must be larger than inner_diameter.")
    return FlatSpiralGeometry(
        inner_diameter=inner,
        outer_diameter=outer,
        turns=turns,
        spiral_pitch=pitch,
        strip_length=spec.strip_length,
    )


def _axis_rotation(axis: SpringAxis) -> tuple[tuple[float, float, float], float]:
    if axis == "X":
        return (0.0, 1.0, 0.0), -90.0
    if axis == "Y":
        return (1.0, 0.0, 0.0), 90.0
    return (0.0, 0.0, 1.0), 0.0


def _axis_vector(axis: SpringAxis) -> tuple[float, float, float]:
    if axis == "X":
        return (1.0, 0.0, 0.0)
    if axis == "Y":
        return (0.0, 1.0, 0.0)
    return (0.0, 0.0, 1.0)


def _wire_profile(wire: WireSection, *, mean_radius: float) -> cq.Workplane:
    if wire.shape == "round":
        if wire.diameter is None:
            raise ValueError("Wire diameter is required for round wire.")
        return cq.Workplane("XZ").center(mean_radius, 0).circle(wire.diameter / 2.0)
    if wire.shape in ("square", "rectangular"):
        if wire.width is None or wire.thickness is None:
            raise ValueError("Wire width and thickness are required for non-round wire.")
        profile = cq.Workplane("XZ").center(mean_radius, 0).rect(wire.thickness, wire.width)
        if wire.corner_radius > 0:
            max_corner = min(wire.thickness, wire.width) * 0.5 * 0.99
            corner = min(wire.corner_radius, max_corner)
            try:
                profile = profile.vertices().fillet(corner)
            except Exception:
                print("WARN: Spring wire corner fillet failed (try smaller corner_radius).")
        return profile
    raise NotImplementedError("Custom wire profiles are not supported in build_helical_body.")


def build_helical_body(spec: HelicalBodySpec, *, use_frenet: bool = True) -> cq.Workplane:
    geom = resolve_helical_geometry(spec)
    mean_radius = geom.mean_diameter / 2.0
    helix_wire = cq.Wire.makeHelix(
        pitch=geom.pitch,
        height=geom.free_length,
        radius=mean_radius,
        lefthand=spec.hand == "LH",
    )
    helix = cq.Workplane(obj=helix_wire)
    profile = _wire_profile(spec.wire, mean_radius=mean_radius)
    body = profile.sweep(helix, isFrenet=use_frenet)
    axis, angle = _axis_rotation(spec.axis)
    if angle != 0.0:
        body = body.rotate((0, 0, 0), axis, angle)
    if spec.clocking_deg:
        body = body.rotate((0, 0, 0), _axis_vector(spec.axis), spec.clocking_deg)
    if spec.origin != (0.0, 0.0, 0.0):
        body = body.translate(spec.origin)
    return body


def _parabolic_interp(u: float, v0: float, v_mid: float, v1: float) -> float:
    return (v0 * (2.0 * (u - 0.5) * (u - 1.0))) + (v_mid * (4.0 * u * (1.0 - u))) + (
        v1 * (u * (2.0 * u - 1.0))
    )


def _radius_profile(
    u: float,
    r0: float,
    r1: float,
    profile: DiameterProfile,
    *,
    r_mid: float | None = None,
    mean_diameter_fn: Callable[[float], float] | None = None,
) -> float:
    if profile == "linear":
        return r0 + (r1 - r0) * u
    if profile == "parabolic":
        if r_mid is None:
            raise ValueError("Parabolic diameter profile requires mean_diameter_mid.")
        return _parabolic_interp(u, r0, r_mid, r1)
    if profile == "custom":
        if mean_diameter_fn is None:
            raise ValueError("Custom diameter profile requires mean_diameter_fn.")
        radius = mean_diameter_fn(u) * 0.5
        validate_positive("Custom mean diameter", radius * 2.0)
        return radius
    raise ValueError(f"Unsupported diameter_profile: {profile}.")


def _pitch_profile(
    u: float,
    p0: float,
    p1: float,
    profile: PitchProfile,
    *,
    p_mid: float | None = None,
    pitch_fn: Callable[[float], float] | None = None,
) -> float:
    if profile == "constant":
        return p0
    if profile == "linear":
        return p0 + (p1 - p0) * u
    if profile == "parabolic":
        if p_mid is None:
            raise ValueError("Parabolic pitch profile requires pitch_mid.")
        return _parabolic_interp(u, p0, p_mid, p1)
    if profile == "custom":
        if pitch_fn is None:
            raise ValueError("Custom pitch profile requires pitch_fn.")
        value = pitch_fn(u)
        validate_positive("Custom pitch", value)
        return value
    raise ValueError(f"Unsupported pitch_profile: {profile}.")


def build_variable_diameter_body(
    spec: VariableDiameterHelixSpec,
    *,
    segments_per_turn: int = 48,
    mean_diameter_mid: float | None = None,
    pitch_mid: float | None = None,
    mean_diameter_fn: Callable[[float], float] | None = None,
    pitch_fn: Callable[[float], float] | None = None,
    use_frenet: bool = True,
) -> cq.Workplane:
    geom = resolve_variable_diameter_geometry(spec)
    if segments_per_turn <= 0:
        raise ValueError("segments_per_turn must be positive.")
    mean_radius_start = geom.mean_diameter_small / 2.0
    mean_radius_end = geom.mean_diameter_large / 2.0
    mean_radius_mid = None
    if mean_diameter_mid is not None:
        validate_positive("mean_diameter_mid", mean_diameter_mid)
        mean_radius_mid = mean_diameter_mid / 2.0

    pitch_profile = spec.pitch_profile
    if pitch_profile not in ("constant", "linear", "parabolic", "custom"):
        raise ValueError(f"Unsupported pitch_profile: {pitch_profile}.")
    diameter_profile = spec.diameter_profile
    if diameter_profile not in ("linear", "parabolic", "custom"):
        raise ValueError(f"Unsupported diameter_profile: {diameter_profile}.")
    if diameter_profile == "custom" and mean_diameter_fn is None:
        raise ValueError("Custom diameter profile requires mean_diameter_fn.")
    if diameter_profile == "custom" and mean_diameter_fn is not None:
        r_start = mean_diameter_fn(0.0) * 0.5
        r_end = mean_diameter_fn(1.0) * 0.5
        _assert_close("Custom mean diameter start", r_start, mean_radius_start)
        _assert_close("Custom mean diameter end", r_end, mean_radius_end)

    pitch = geom.pitch
    p0 = spec.pitch_small if spec.pitch_small is not None else pitch
    p1 = spec.pitch_large if spec.pitch_large is not None else pitch

    if pitch_profile == "constant":
        if p0 is None and geom.free_length is not None:
            p0 = geom.free_length / geom.total_coils
        if p1 is None:
            p1 = p0
        if p0 is None or p1 is None:
            raise ValueError("Variable diameter pitch could not be resolved.")
        _assert_close("Variable diameter pitch", p0, p1)

    if pitch_profile == "linear":
        if p0 is None and p1 is None and geom.free_length is not None:
            p0 = geom.free_length / geom.total_coils
            p1 = p0
        elif p0 is None and p1 is not None and geom.free_length is not None:
            p0 = (2.0 * geom.free_length / geom.total_coils) - p1
        elif p1 is None and p0 is not None and geom.free_length is not None:
            p1 = (2.0 * geom.free_length / geom.total_coils) - p0
    if pitch_profile == "parabolic":
        if p0 is None or p1 is None:
            raise ValueError("Parabolic pitch profile requires pitch_small/pitch_large.")
        if pitch_mid is None:
            raise ValueError("Parabolic pitch profile requires pitch_mid.")
        validate_positive("pitch_mid", pitch_mid)
    if pitch_profile == "custom":
        if pitch_fn is None:
            raise ValueError("Custom pitch profile requires pitch_fn.")
        p_start = spec.pitch_small if spec.pitch_small is not None else spec.pitch
        p_end = spec.pitch_large if spec.pitch_large is not None else spec.pitch
        if p_start is not None:
            _assert_close("Custom pitch start", pitch_fn(0.0), p_start)
        if p_end is not None:
            _assert_close("Custom pitch end", pitch_fn(1.0), p_end)
    if pitch_profile != "custom":
        if p0 is None or p1 is None:
            raise ValueError("Variable diameter pitch profile could not be resolved.")
        validate_positive("Variable diameter pitch_start", p0)
        validate_positive("Variable diameter pitch_end", p1)

    total_turns = geom.total_coils
    total_angle = 2.0 * math.pi * total_turns
    if total_turns <= 0:
        raise ValueError("Variable diameter total_coils must be positive.")
    segments = max(12, int(segments_per_turn * total_turns))
    sign = -1.0 if spec.hand == "LH" else 1.0
    points: list[cq.Vector] = []
    z = 0.0
    du = 1.0 / segments
    prev_pitch = None
    for i in range(segments + 1):
        u = i / segments
        theta = sign * total_angle * u
        radius = _radius_profile(
            u,
            mean_radius_start,
            mean_radius_end,
            diameter_profile,
            r_mid=mean_radius_mid,
            mean_diameter_fn=mean_diameter_fn,
        )
        if radius <= 0:
            raise ValueError("Variable diameter radius must be positive.")
        if pitch_profile == "custom":
            pitch_local = _pitch_profile(u, 0.0, 0.0, pitch_profile, pitch_fn=pitch_fn)
        else:
            pitch_local = _pitch_profile(u, p0, p1, pitch_profile, p_mid=pitch_mid)
        if pitch_local <= 0:
            raise ValueError("Variable diameter pitch must be positive.")
        if prev_pitch is None:
            prev_pitch = pitch_local
        else:
            z += total_turns * 0.5 * (prev_pitch + pitch_local) * du
            prev_pitch = pitch_local
        x = radius * math.cos(theta)
        y = radius * math.sin(theta)
        points.append(cq.Vector(x, y, z))
    if geom.free_length is not None:
        _assert_close("Variable diameter free_length", geom.free_length, z)
    edge = cq.Edge.makeSpline(points)
    wire = cq.Wire.assembleEdges([edge])
    path = cq.Workplane(obj=wire)

    profile = _wire_profile(spec.wire, mean_radius=mean_radius_start)
    body = profile.sweep(path, isFrenet=use_frenet)
    axis, angle = _axis_rotation(spec.axis)
    if angle != 0.0:
        body = body.rotate((0, 0, 0), axis, angle)
    if spec.clocking_deg:
        body = body.rotate((0, 0, 0), _axis_vector(spec.axis), spec.clocking_deg)
    if spec.origin != (0.0, 0.0, 0.0):
        body = body.translate(spec.origin)
    return body
