from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import cadquery as cq

from features.package import union_solids
from features.utils import validate_non_negative, validate_positive


ThreadHand = Literal["RH", "LH"]
ThreadSide = Literal["internal", "external"]
ThreadUnits = Literal["mm", "inch"]
ThreadReferenceDiameter = Literal["major", "pitch", "minor"]


@dataclass(frozen=True)
class ThreadProfile:
    form: str
    included_angle_deg: float
    flank_angle_deg: tuple[float, float] | None = None
    crest_shape: str = "flat"
    root_shape: str = "flat"
    crest_radius: float | None = None
    root_radius: float | None = None
    crest_truncation: float | None = None
    root_truncation: float | None = None


@dataclass(frozen=True)
class ThreadEngagement:
    length: float | None = None
    depth: float | None = None
    min_engagement: float | None = None
    thru: bool = False
    runout: float | None = None


@dataclass(frozen=True)
class ThreadDiameters:
    major_min: float | None = None
    major_max: float | None = None
    pitch_min: float | None = None
    pitch_max: float | None = None
    minor_min: float | None = None
    minor_max: float | None = None


@dataclass(frozen=True)
class ThreadTaper:
    taper_per_length: float | None = None
    taper_angle_deg: float | None = None
    reference_diameter: ThreadReferenceDiameter = "pitch"
    gage_plane: float | None = None
    direction: Literal["+Z", "-Z"] = "+Z"


@dataclass(frozen=True)
class ThreadFinish:
    material_condition: str | None = None
    coating: str | None = None
    surface_finish_ra: float | None = None
    gaging: str | None = None


@dataclass(frozen=True)
class ThreadSpec:
    system: str
    profile: ThreadProfile
    side: ThreadSide
    nominal_diameter: float | None = None
    nominal_designation: str | None = None
    pitch: float | None = None
    tpi: float | None = None
    hand: ThreadHand = "RH"
    series: str | None = None
    tolerance_class: str | None = None
    starts: int = 1
    lead: float | None = None
    engagement: ThreadEngagement | None = None
    diameters: ThreadDiameters | None = None
    taper: ThreadTaper | None = None
    sealing: str | None = None
    special_form: str | None = None
    finish: ThreadFinish | None = None
    units: ThreadUnits = "mm"


@dataclass(frozen=True)
class ThreadDerived:
    pitch: float
    lead: float
    tpi: float | None


@dataclass(frozen=True)
class _ThreadProfileGeometry:
    pitch: float
    full_height: float
    height: float
    crest_x: float
    root_x: float
    crest_t: float
    root_t: float
    crest_radius: float | None
    root_radius: float | None
    crest_delta: float
    root_delta: float
    angle_pos: float
    angle_neg: float
    slope_pos: float
    slope_neg: float
    pitch_pos: float
    pitch_neg: float


def _is_iso_metric_form(form: str) -> bool:
    token = form.strip().lower()
    if token in {"iso", "iso metric", "iso-m", "iso 68", "iso68", "iso 68-1", "iso68-1", "m", "metric"}:
        return True
    return "iso" in token and "metric" in token


def _format_value(value: float) -> str:
    return f"{value:g}"


def _validate_profile(profile: ThreadProfile) -> None:
    if not profile.form:
        raise ValueError("Thread profile form must be provided.")
    validate_positive("Thread profile included_angle_deg", profile.included_angle_deg)
    allowed_shapes = {"flat", "sharp", "rounded"}
    if profile.crest_shape not in allowed_shapes:
        raise ValueError("Thread crest shape must be flat, sharp, or rounded.")
    if profile.root_shape not in allowed_shapes:
        raise ValueError("Thread root shape must be flat, sharp, or rounded.")
    if profile.flank_angle_deg is not None:
        if len(profile.flank_angle_deg) != 2:
            raise ValueError("Thread flank_angle_deg must contain two angles.")
        for idx, angle in enumerate(profile.flank_angle_deg, start=1):
            validate_positive(f"Thread flank_angle_deg[{idx}]", angle)
            if angle >= 89.0:
                raise ValueError("Thread flank angles must be less than 89 degrees.")
    for name, value in (
        ("Thread profile crest_radius", profile.crest_radius),
        ("Thread profile root_radius", profile.root_radius),
    ):
        if value is not None and value < 0:
            raise ValueError(f"{name} must be non-negative.")
    for name, value in (
        ("Thread profile crest_truncation", profile.crest_truncation),
        ("Thread profile root_truncation", profile.root_truncation),
    ):
        if value is not None:
            validate_non_negative(name, value)


def _validate_engagement(engagement: ThreadEngagement) -> None:
    if engagement.length is not None:
        validate_positive("Thread length", engagement.length)
    if engagement.depth is not None:
        validate_positive("Thread depth", engagement.depth)
    if engagement.min_engagement is not None:
        validate_positive("Thread min engagement", engagement.min_engagement)
    if engagement.runout is not None:
        validate_non_negative("Thread runout", engagement.runout)
    if engagement.length is not None and engagement.depth is not None:
        raise ValueError("Thread engagement cannot set both length and depth.")


def _validate_diameters(diameters: ThreadDiameters) -> None:
    for name, value in (
        ("Major diameter min", diameters.major_min),
        ("Major diameter max", diameters.major_max),
        ("Pitch diameter min", diameters.pitch_min),
        ("Pitch diameter max", diameters.pitch_max),
        ("Minor diameter min", diameters.minor_min),
        ("Minor diameter max", diameters.minor_max),
    ):
        if value is not None:
            validate_positive(name, value)
    if diameters.major_min is not None and diameters.major_max is not None:
        if diameters.major_min > diameters.major_max:
            raise ValueError("Major diameter min must be <= max.")
    if diameters.pitch_min is not None and diameters.pitch_max is not None:
        if diameters.pitch_min > diameters.pitch_max:
            raise ValueError("Pitch diameter min must be <= max.")
    if diameters.minor_min is not None and diameters.minor_max is not None:
        if diameters.minor_min > diameters.minor_max:
            raise ValueError("Minor diameter min must be <= max.")


def _validate_taper(taper: ThreadTaper) -> None:
    if taper.taper_per_length is None and taper.taper_angle_deg is None:
        raise ValueError("Thread taper must define taper_per_length or taper_angle_deg.")
    if taper.taper_per_length is not None:
        validate_positive("Thread taper_per_length", taper.taper_per_length)
    if taper.taper_angle_deg is not None:
        validate_positive("Thread taper_angle_deg", taper.taper_angle_deg)
    if taper.gage_plane is not None:
        validate_non_negative("Thread gage_plane", taper.gage_plane)
    if taper.direction not in ("+Z", "-Z"):
        raise ValueError("Thread taper direction must be '+Z' or '-Z'.")


def _validate_finish(finish: ThreadFinish) -> None:
    if finish.surface_finish_ra is not None:
        validate_non_negative("Thread surface_finish_ra", finish.surface_finish_ra)


def _resolve_pitch_from_tpi(tpi: float, units: ThreadUnits) -> float:
    pitch_inch = 1.0 / tpi
    if units == "mm":
        return pitch_inch * 25.4
    return pitch_inch


def resolve_pitch(spec: ThreadSpec) -> float:
    if spec.pitch is not None and spec.tpi is not None:
        raise ValueError("Thread spec cannot define both pitch and tpi.")
    if spec.pitch is not None:
        validate_positive("Thread pitch", spec.pitch)
        return spec.pitch
    if spec.tpi is not None:
        validate_positive("Thread tpi", spec.tpi)
        return _resolve_pitch_from_tpi(spec.tpi, spec.units)
    raise ValueError("Thread spec must define pitch or tpi.")


def resolve_tpi(spec: ThreadSpec) -> float | None:
    if spec.tpi is not None:
        validate_positive("Thread tpi", spec.tpi)
        return spec.tpi
    if spec.pitch is None:
        return None
    validate_positive("Thread pitch", spec.pitch)
    if spec.units == "mm":
        return 25.4 / spec.pitch
    return 1.0 / spec.pitch


def resolve_lead(spec: ThreadSpec) -> float:
    pitch = resolve_pitch(spec)
    expected = pitch * spec.starts
    if spec.lead is None:
        return expected
    validate_positive("Thread lead", spec.lead)
    if abs(spec.lead - expected) > 1e-6 * max(1.0, expected):
        raise ValueError("Thread lead must equal pitch * starts.")
    return spec.lead


def derive_thread(spec: ThreadSpec) -> ThreadDerived:
    _validate_thread(spec)
    pitch = resolve_pitch(spec)
    lead = resolve_lead(spec)
    return ThreadDerived(pitch=pitch, lead=lead, tpi=resolve_tpi(spec))


def _validate_thread(spec: ThreadSpec) -> None:
    if not spec.system:
        raise ValueError("Thread system must be provided.")
    if spec.nominal_diameter is None and not spec.nominal_designation:
        raise ValueError("Thread nominal size or designation must be provided.")
    if spec.nominal_diameter is not None:
        validate_positive("Thread nominal_diameter", spec.nominal_diameter)
    if spec.pitch is not None and spec.tpi is not None:
        raise ValueError("Thread spec cannot define both pitch and tpi.")
    if spec.pitch is not None:
        validate_positive("Thread pitch", spec.pitch)
    if spec.tpi is not None:
        validate_positive("Thread tpi", spec.tpi)
    if spec.starts <= 0:
        raise ValueError("Thread starts must be positive.")
    if spec.lead is not None:
        validate_positive("Thread lead", spec.lead)
    _validate_profile(spec.profile)
    if spec.engagement is not None:
        _validate_engagement(spec.engagement)
    if spec.diameters is not None:
        _validate_diameters(spec.diameters)
    if spec.taper is not None:
        _validate_taper(spec.taper)
    if spec.finish is not None:
        _validate_finish(spec.finish)
    if spec.pitch is None and spec.tpi is None:
        raise ValueError("Thread spec must define pitch or tpi.")


def _thread_length_segment(engagement: ThreadEngagement | None) -> str | None:
    if engagement is None:
        return None
    if engagement.thru:
        return "THRU"
    if engagement.depth is not None:
        return f"thread depth {_format_value(engagement.depth)}"
    if engagement.length is not None:
        return f"thread length {_format_value(engagement.length)}"
    if engagement.min_engagement is not None:
        return f"min engagement {_format_value(engagement.min_engagement)}"
    return None


def _metric_nominal(spec: ThreadSpec) -> str:
    if spec.nominal_designation:
        designation = spec.nominal_designation
        return designation if designation.upper().startswith("M") else f"M{designation}"
    if spec.nominal_diameter is None:
        raise ValueError("Metric callout requires nominal diameter or designation.")
    return f"M{_format_value(spec.nominal_diameter)}"


def _unified_nominal(spec: ThreadSpec) -> str:
    if spec.nominal_designation:
        return spec.nominal_designation
    if spec.nominal_diameter is None:
        raise ValueError("Unified callout requires nominal diameter or designation.")
    return _format_value(spec.nominal_diameter)


def metric_callout(spec: ThreadSpec) -> str:
    _validate_thread(spec)
    pitch = resolve_pitch(spec)
    base = f"{_metric_nominal(spec)}x{_format_value(pitch)}"
    segments = [base]
    if spec.tolerance_class:
        segments.append(spec.tolerance_class)
    if spec.hand == "LH":
        segments.append("LH")
    length_segment = _thread_length_segment(spec.engagement)
    if length_segment:
        segments.append(length_segment)
    return " - ".join(segments)


def unified_callout(spec: ThreadSpec) -> str:
    _validate_thread(spec)
    tpi = resolve_tpi(spec)
    if tpi is None:
        raise ValueError("Unified callout requires tpi or pitch.")
    base = f"{_unified_nominal(spec)}-{_format_value(tpi)}"
    if spec.series:
        base = f"{base} {spec.series}"
    segments = [base]
    if spec.tolerance_class:
        segments.append(spec.tolerance_class)
    if spec.hand == "LH":
        segments.append("LH")
    length_segment = _thread_length_segment(spec.engagement)
    if length_segment:
        segments.append(length_segment)
    return " - ".join(segments)


def thread_callout(spec: ThreadSpec) -> str:
    system = spec.system.lower()
    series = (spec.series or "").upper()
    if "un" in system or series.startswith("UN") or spec.units == "inch" or spec.tpi is not None:
        return unified_callout(spec)
    if "iso" in system or "metric" in system or spec.units == "mm":
        return metric_callout(spec)
    return metric_callout(spec)


def thread_envelope_diameter(spec: ThreadSpec) -> float:
    _validate_thread(spec)
    if spec.diameters is not None:
        if spec.side == "external":
            diameter = (
                spec.diameters.major_max
                or spec.diameters.major_min
                or spec.nominal_diameter
            )
        else:
            diameter = (
                spec.diameters.minor_max
                or spec.diameters.minor_min
                or spec.nominal_diameter
            )
        if diameter is None:
            raise ValueError("Thread envelope diameter needs major/minor or nominal diameter.")
        return diameter
    if spec.nominal_diameter is None:
        raise ValueError("Thread envelope diameter needs nominal_diameter or diameters.")
    return spec.nominal_diameter


def _resolve_thread_length(spec: ThreadSpec, length: float | None) -> float:
    if length is not None:
        validate_positive("Thread length", length)
        return length
    if spec.engagement is None:
        raise ValueError("Thread length must be provided or defined in engagement.")
    if spec.engagement.length is not None:
        return spec.engagement.length
    if spec.engagement.depth is not None:
        return spec.engagement.depth
    if spec.engagement.min_engagement is not None:
        return spec.engagement.min_engagement
    raise ValueError("Thread length must be provided when engagement has no length/depth.")


def _taper_half_angle(taper: ThreadTaper) -> float:
    if taper.taper_angle_deg is not None:
        validate_positive("Thread taper_angle_deg", taper.taper_angle_deg)
        return math.radians(taper.taper_angle_deg)
    if taper.taper_per_length is None:
        raise ValueError("Thread taper must define taper_per_length or taper_angle_deg.")
    validate_positive("Thread taper_per_length", taper.taper_per_length)
    slope = taper.taper_per_length / 2.0
    return math.atan(slope)


def _taper_radii(
    taper: ThreadTaper,
    *,
    pitch_radius: float,
    length: float,
) -> tuple[float, float]:
    angle = _taper_half_angle(taper)
    slope = math.tan(angle)
    gage_plane = taper.gage_plane or 0.0
    validate_non_negative("Thread gage_plane", gage_plane)
    r_start = pitch_radius - gage_plane * slope
    r_end = r_start + length * slope
    if r_start <= 0 or r_end <= 0:
        raise ValueError("Thread taper results in non-positive radius.")
    return r_start, r_end


def _cone_between_radii(
    radius_start: float,
    radius_end: float,
    length: float,
    *,
    centered: bool,
    direction: Literal["+Z", "-Z"],
) -> cq.Workplane:
    if radius_start <= 0 or radius_end <= 0:
        raise ValueError("Cone radii must be positive.")
    z1 = length if direction == "+Z" else -length
    solid = (
        cq.Workplane("XY")
        .workplane(offset=0.0)
        .circle(radius_start)
        .workplane(offset=z1)
        .circle(radius_end)
        .loft(combine=True)
    )
    if centered:
        offset = -length / 2.0 if direction == "+Z" else length / 2.0
        solid = solid.translate((0, 0, offset))
    return solid


def _rounded_truncation_from_radius(radius: float, half_angle: float) -> float:
    sin_a = math.sin(half_angle)
    cos_a = math.cos(half_angle)
    if sin_a <= 0 or cos_a <= 0:
        raise ValueError("Thread included angle must be between 0 and 180 degrees.")
    return radius * (cos_a * cos_a) / sin_a


def _rounded_radius_from_truncation(truncation: float, half_angle: float) -> float:
    sin_a = math.sin(half_angle)
    cos_a = math.cos(half_angle)
    if sin_a <= 0 or cos_a <= 0:
        raise ValueError("Thread included angle must be between 0 and 180 degrees.")
    return truncation * sin_a / (cos_a * cos_a)


def _resolve_end_geometry(
    *,
    shape: str,
    truncation: float | None,
    radius: float | None,
    half_angle: float | None,
    label: str,
) -> tuple[float, float, float | None]:
    if shape == "sharp":
        if truncation not in (None, 0.0):
            raise ValueError(f"{label} truncation must be 0 for sharp threads.")
        if radius not in (None, 0.0):
            raise ValueError(f"{label} radius must be 0 for sharp threads.")
        return 0.0, 0.0, None
    if shape == "flat":
        if radius not in (None, 0.0):
            raise ValueError(f"{label} radius cannot be set for flat threads.")
        trunc = truncation or 0.0
        if trunc < 0:
            raise ValueError(f"{label} truncation must be non-negative.")
        return trunc, trunc, None
    if shape != "rounded":
        raise ValueError(f"{label} shape must be flat, sharp, or rounded.")
    if radius is None and truncation is None:
        raise ValueError(f"{label} rounded threads require a radius or truncation.")
    if half_angle is None:
        raise NotImplementedError(f"{label} rounded threads require symmetric flank angles.")
    if radius is None:
        trunc = truncation or 0.0
        if trunc <= 0:
            raise ValueError(f"{label} truncation must be positive for rounded threads.")
        radius = _rounded_radius_from_truncation(trunc, half_angle)
    else:
        if radius <= 0:
            raise ValueError(f"{label} radius must be positive for rounded threads.")
        trunc = _rounded_truncation_from_radius(radius, half_angle)
    if truncation is not None:
        tol = 1e-6 * max(1.0, trunc)
        if abs(truncation - trunc) > tol:
            raise ValueError(f"{label} truncation and radius are inconsistent.")
        trunc = truncation
    delta = radius / math.sin(half_angle) - radius
    return trunc, delta, radius


def _profile_geometry(profile: ThreadProfile, pitch: float) -> _ThreadProfileGeometry:
    if profile.flank_angle_deg is not None:
        angle_pos = math.radians(profile.flank_angle_deg[0])
        angle_neg = math.radians(profile.flank_angle_deg[1])
    else:
        half_angle = math.radians(profile.included_angle_deg / 2.0)
        angle_pos = half_angle
        angle_neg = half_angle
    slope_pos = math.tan(angle_pos)
    slope_neg = math.tan(angle_neg)
    if slope_pos <= 0 or slope_neg <= 0:
        raise ValueError("Thread flank angles must be between 0 and 90 degrees.")
    full_height = pitch / (slope_pos + slope_neg)
    crest_trunc = profile.crest_truncation
    root_trunc = profile.root_truncation
    crest_radius = profile.crest_radius
    root_radius = profile.root_radius
    symmetric = abs(slope_pos - slope_neg) <= 1e-9
    half_angle = angle_pos if symmetric else None
    if _is_iso_metric_form(profile.form):
        if not symmetric:
            raise ValueError("ISO metric threads require symmetric flank angles.")
        if abs(profile.included_angle_deg - 60.0) > 1e-3:
            raise ValueError("ISO metric threads require a 60 degree included angle.")
        if profile.crest_shape != "sharp" and crest_trunc is None and crest_radius is None:
            crest_trunc = full_height / 8.0
        if profile.root_shape != "sharp" and root_trunc is None and root_radius is None:
            root_trunc = full_height / 4.0
    crest_t, crest_delta, crest_radius = _resolve_end_geometry(
        shape=profile.crest_shape,
        truncation=crest_trunc,
        radius=crest_radius,
        half_angle=half_angle,
        label="Crest",
    )
    root_t, root_delta, root_radius = _resolve_end_geometry(
        shape=profile.root_shape,
        truncation=root_trunc,
        radius=root_radius,
        half_angle=half_angle,
        label="Root",
    )
    if crest_t + root_t >= full_height:
        raise ValueError("Thread truncations remove entire thread height.")
    height = full_height - crest_delta - root_delta
    if height <= 0:
        raise ValueError("Thread truncations remove entire thread height.")
    crest_x = full_height / 2.0 - crest_delta
    root_x = -full_height / 2.0 + root_delta
    pitch_pos = full_height * slope_pos
    pitch_neg = full_height * slope_neg
    return _ThreadProfileGeometry(
        pitch=pitch,
        full_height=full_height,
        height=height,
        crest_x=crest_x,
        root_x=root_x,
        crest_t=crest_t,
        root_t=root_t,
        crest_radius=crest_radius if crest_radius and crest_radius > 0 else None,
        root_radius=root_radius if root_radius and root_radius > 0 else None,
        crest_delta=crest_delta,
        root_delta=root_delta,
        angle_pos=angle_pos,
        angle_neg=angle_neg,
        slope_pos=slope_pos,
        slope_neg=slope_neg,
        pitch_pos=pitch_pos,
        pitch_neg=pitch_neg,
    )


def _resolve_diameter(min_val: float | None, max_val: float | None) -> float | None:
    if min_val is not None and max_val is not None:
        return 0.5 * (min_val + max_val)
    return max_val if max_val is not None else min_val


def _resolve_thread_diameters(
    spec: ThreadSpec, geom: _ThreadProfileGeometry
) -> tuple[float, float, float]:
    height = geom.height
    crest_x = geom.crest_x
    root_x = geom.root_x
    major = None
    minor = None
    pitch_diameter = None
    if spec.diameters is not None:
        major = _resolve_diameter(spec.diameters.major_min, spec.diameters.major_max)
        minor = _resolve_diameter(spec.diameters.minor_min, spec.diameters.minor_max)
        pitch_diameter = _resolve_diameter(spec.diameters.pitch_min, spec.diameters.pitch_max)
    if major is None:
        major = spec.nominal_diameter
    if major is None and minor is None:
        raise ValueError("Thread needs nominal diameter or explicit major/minor diameters.")
    if minor is None and major is not None:
        minor = major - 2.0 * height
    if major is None and minor is not None:
        major = minor + 2.0 * height
    if major is None or minor is None:
        raise ValueError("Thread diameters could not be resolved.")
    if major <= minor:
        raise ValueError("Thread major diameter must exceed minor diameter.")
    if minor <= 0:
        raise ValueError("Thread minor diameter must be positive.")
    actual_height = (major - minor) / 2.0
    tol = 1e-3 * max(1.0, height)
    if abs(actual_height - height) > tol:
        raise ValueError("Thread diameters do not match pitch/profile height.")
    if pitch_diameter is None:
        pitch_diameter = major - 2.0 * crest_x
    else:
        expected_major = pitch_diameter + 2.0 * crest_x
        expected_minor = pitch_diameter + 2.0 * root_x
        tol_d = 1e-3 * max(1.0, major, minor)
        if abs(expected_major - major) > tol_d or abs(expected_minor - minor) > tol_d:
            raise ValueError("Thread pitch diameter does not match major/minor geometry.")
    if pitch_diameter <= 0:
        raise ValueError("Thread pitch diameter must be positive.")
    return major, minor, pitch_diameter


def _thread_profile(geom: _ThreadProfileGeometry, *, pitch_radius: float) -> cq.Workplane:
    crest_x = geom.crest_x
    root_x = geom.root_x
    crest_t_x = geom.full_height / 2.0 - geom.crest_t
    root_t_x = -geom.full_height / 2.0 + geom.root_t
    crest_z_pos = geom.crest_t * geom.slope_pos
    crest_z_neg = geom.crest_t * geom.slope_neg
    root_z_pos = geom.pitch_pos - geom.root_t * geom.slope_pos
    root_z_neg = geom.pitch_neg - geom.root_t * geom.slope_neg
    if root_z_pos < 0 or root_z_neg < 0:
        raise ValueError("Thread root truncation is too large for given pitch.")

    wp = cq.Workplane("XZ").center(pitch_radius, 0.0)
    wp = wp.moveTo(crest_t_x, crest_z_pos)
    if (crest_t_x, crest_z_pos) != (root_t_x, root_z_pos):
        wp = wp.lineTo(root_t_x, root_z_pos)
    if root_z_pos > 1e-9 or root_z_neg > 1e-9:
        if geom.root_radius is not None:
            wp = wp.threePointArc((root_x, 0.0), (root_t_x, -root_z_neg))
        else:
            wp = wp.lineTo(root_t_x, -root_z_neg)
    if (root_t_x, -root_z_neg) != (crest_t_x, -crest_z_neg):
        wp = wp.lineTo(crest_t_x, -crest_z_neg)
    if crest_z_pos > 1e-9 or crest_z_neg > 1e-9:
        if geom.crest_radius is not None:
            wp = wp.threePointArc((crest_x, 0.0), (crest_t_x, crest_z_pos))
        else:
            wp = wp.lineTo(crest_t_x, crest_z_pos)
    return wp.close()


def _sweep_thread_ridge(
    spec: ThreadSpec,
    *,
    length: float,
    pitch_radius: float,
    geom: _ThreadProfileGeometry,
    taper: ThreadTaper | None,
    centered: bool,
) -> cq.Workplane:
    lead = resolve_lead(spec)
    helix_dir = (0, 0, 1)
    helix_angle = 360.0
    z_offset = -length / 2.0 if centered else 0.0
    if taper is not None:
        taper_angle = _taper_half_angle(taper)
        helix_angle = math.degrees(taper_angle)
        if taper.direction == "-Z":
            helix_dir = (0, 0, -1)
            z_offset = length / 2.0 if centered else 0.0
    wire = cq.Wire.makeHelix(
        pitch=lead,
        height=length,
        radius=pitch_radius,
        dir=cq.Vector(*helix_dir),
        angle=helix_angle,
        lefthand=spec.hand == "LH",
    )
    helix = cq.Workplane(obj=wire)
    profile = _thread_profile(geom, pitch_radius=pitch_radius)
    ridge = profile.sweep(helix, isFrenet=True)
    if z_offset != 0.0:
        ridge = ridge.translate((0, 0, z_offset))
    return ridge


def build_thread_solid(
    spec: ThreadSpec,
    *,
    length: float | None = None,
    centered: bool = True,
) -> cq.Workplane:
    """
    Build a helical thread solid. For internal threads, use the returned solid as a cutter.
    """
    _validate_thread(spec)
    pitch = resolve_pitch(spec)
    length_value = _resolve_thread_length(spec, length)
    geom = _profile_geometry(spec.profile, pitch)
    major, minor, pitch_diameter = _resolve_thread_diameters(spec, geom)
    taper = spec.taper
    if taper is not None:
        if taper.reference_diameter == "major":
            pitch_radius = major / 2.0 - geom.crest_x
        elif taper.reference_diameter == "minor":
            pitch_radius = minor / 2.0 - geom.root_x
        else:
            pitch_radius = pitch_diameter / 2.0
    else:
        pitch_radius = pitch_diameter / 2.0
    if pitch_radius <= 0:
        raise ValueError("Thread pitch radius must be positive.")
    taper_radii = None
    if taper is not None:
        taper_radii = _taper_radii(
            taper, pitch_radius=pitch_radius, length=length_value
        )
    helix_radius = pitch_radius
    if taper_radii is not None:
        helix_radius = taper_radii[0]
    ridge = _sweep_thread_ridge(
        spec,
        length=length_value,
        pitch_radius=helix_radius,
        geom=geom,
        taper=taper,
        centered=centered,
    )
    ridges = [ridge]
    if spec.starts > 1:
        step = 360.0 / spec.starts
        for idx in range(1, spec.starts):
            ridges.append(ridge.rotate((0, 0, 0), (0, 0, 1), step * idx))
    ridge_union = union_solids(ridges)
    if ridge_union is None:
        raise ValueError("Thread sweep failed to produce geometry.")
    if taper_radii is None:
        core = (
            cq.Workplane("XY")
            .circle(minor / 2.0)
            .extrude(length_value, both=centered)
        )
        envelope = (
            cq.Workplane("XY")
            .circle(major / 2.0)
            .extrude(length_value, both=centered)
        )
    else:
        r_start, r_end = taper_radii
        major_start = r_start + geom.crest_x
        major_end = r_end + geom.crest_x
        minor_start = r_start + geom.root_x
        minor_end = r_end + geom.root_x
        if minor_start <= 0 or minor_end <= 0:
            raise ValueError("Thread taper results in non-positive minor diameter.")
        core = _cone_between_radii(
            minor_start,
            minor_end,
            length_value,
            centered=centered,
            direction=taper.direction,
        )
        envelope = _cone_between_radii(
            major_start,
            major_end,
            length_value,
            centered=centered,
            direction=taper.direction,
        )
    thread = core.union(ridge_union)
    return thread.intersect(envelope)


def build_thread_cutter(
    spec: ThreadSpec,
    *,
    length: float | None = None,
    centered: bool = True,
) -> cq.Workplane:
    """
    Build a cutter solid for subtractive internal threads.
    """
    return build_thread_solid(spec, length=length, centered=centered)
