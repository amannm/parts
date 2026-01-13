from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import cadquery as cq

from features.package import union_solids


ThreadHand = Literal["RH", "LH"]
ThreadSide = Literal["internal", "external"]
ThreadUnits = Literal["mm", "inch"]
ThreadReferenceDiameter = Literal["major", "pitch", "minor"]


@dataclass(frozen=True)
class ThreadProfile:
    form: str
    included_angle_deg: float
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


def _format_value(value: float) -> str:
    return f"{value:g}"


def _validate_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive.")


def _validate_non_negative(name: str, value: float) -> None:
    if value < 0:
        raise ValueError(f"{name} must be non-negative.")


def _validate_profile(profile: ThreadProfile) -> None:
    if not profile.form:
        raise ValueError("Thread profile form must be provided.")
    _validate_positive("Thread profile included_angle_deg", profile.included_angle_deg)
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
            _validate_non_negative(name, value)
    if profile.crest_shape not in ("flat", "sharp"):
        raise NotImplementedError("Only flat or sharp crest shapes are supported.")
    if profile.root_shape not in ("flat", "sharp"):
        raise NotImplementedError("Only flat or sharp root shapes are supported.")


def _validate_engagement(engagement: ThreadEngagement) -> None:
    if engagement.length is not None:
        _validate_positive("Thread length", engagement.length)
    if engagement.depth is not None:
        _validate_positive("Thread depth", engagement.depth)
    if engagement.min_engagement is not None:
        _validate_positive("Thread min engagement", engagement.min_engagement)
    if engagement.runout is not None:
        _validate_non_negative("Thread runout", engagement.runout)
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
            _validate_positive(name, value)
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
        _validate_positive("Thread taper_per_length", taper.taper_per_length)
    if taper.taper_angle_deg is not None:
        _validate_positive("Thread taper_angle_deg", taper.taper_angle_deg)
    if taper.gage_plane is not None:
        _validate_non_negative("Thread gage_plane", taper.gage_plane)


def _validate_finish(finish: ThreadFinish) -> None:
    if finish.surface_finish_ra is not None:
        _validate_non_negative("Thread surface_finish_ra", finish.surface_finish_ra)


def _resolve_pitch_from_tpi(tpi: float, units: ThreadUnits) -> float:
    pitch_inch = 1.0 / tpi
    if units == "mm":
        return pitch_inch * 25.4
    return pitch_inch


def resolve_pitch(spec: ThreadSpec) -> float:
    if spec.pitch is not None and spec.tpi is not None:
        raise ValueError("Thread spec cannot define both pitch and tpi.")
    if spec.pitch is not None:
        _validate_positive("Thread pitch", spec.pitch)
        return spec.pitch
    if spec.tpi is not None:
        _validate_positive("Thread tpi", spec.tpi)
        return _resolve_pitch_from_tpi(spec.tpi, spec.units)
    raise ValueError("Thread spec must define pitch or tpi.")


def resolve_tpi(spec: ThreadSpec) -> float | None:
    if spec.tpi is not None:
        _validate_positive("Thread tpi", spec.tpi)
        return spec.tpi
    if spec.pitch is None:
        return None
    _validate_positive("Thread pitch", spec.pitch)
    if spec.units == "mm":
        return 25.4 / spec.pitch
    return 1.0 / spec.pitch


def resolve_lead(spec: ThreadSpec) -> float:
    pitch = resolve_pitch(spec)
    expected = pitch * spec.starts
    if spec.lead is None:
        return expected
    _validate_positive("Thread lead", spec.lead)
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
        _validate_positive("Thread nominal_diameter", spec.nominal_diameter)
    if spec.pitch is not None and spec.tpi is not None:
        raise ValueError("Thread spec cannot define both pitch and tpi.")
    if spec.pitch is not None:
        _validate_positive("Thread pitch", spec.pitch)
    if spec.tpi is not None:
        _validate_positive("Thread tpi", spec.tpi)
    if spec.starts <= 0:
        raise ValueError("Thread starts must be positive.")
    if spec.lead is not None:
        _validate_positive("Thread lead", spec.lead)
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
        _validate_positive("Thread length", length)
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


def _resolve_truncations(profile: ThreadProfile) -> tuple[float, float]:
    crest_trunc = profile.crest_truncation or 0.0
    root_trunc = profile.root_truncation or 0.0
    if profile.crest_shape == "sharp":
        crest_trunc = 0.0
    if profile.root_shape == "sharp":
        root_trunc = 0.0
    return crest_trunc, root_trunc


def _thread_height_from_pitch(profile: ThreadProfile, pitch: float) -> tuple[float, float, float]:
    half_angle = math.radians(profile.included_angle_deg / 2.0)
    if abs(math.tan(half_angle)) < 1e-9:
        raise ValueError("Thread included angle results in invalid flank slope.")
    full_height = pitch / (2.0 * math.tan(half_angle))
    crest_trunc, root_trunc = _resolve_truncations(profile)
    height = full_height - crest_trunc - root_trunc
    if height <= 0:
        raise ValueError("Thread truncations remove entire thread height.")
    return height, crest_trunc, root_trunc


def _resolve_diameter(min_val: float | None, max_val: float | None) -> float | None:
    if min_val is not None and max_val is not None:
        return 0.5 * (min_val + max_val)
    return max_val if max_val is not None else min_val


def _resolve_thread_diameters(
    spec: ThreadSpec, pitch: float
) -> tuple[float, float, float, float, float]:
    height, crest_trunc, root_trunc = _thread_height_from_pitch(spec.profile, pitch)
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
        pitch_diameter = 0.5 * (major + minor)
    if pitch_diameter <= 0:
        raise ValueError("Thread pitch diameter must be positive.")
    return major, minor, pitch_diameter, crest_trunc, root_trunc


def _thread_profile(
    pitch: float,
    height: float,
    included_angle_deg: float,
    crest_trunc: float,
    root_trunc: float,
    pitch_radius: float,
) -> cq.Workplane:
    half_angle = math.radians(included_angle_deg / 2.0)
    flank_slope = math.tan(half_angle)
    if flank_slope <= 0:
        raise ValueError("Thread flank slope must be positive.")
    top_width = 2.0 * crest_trunc * flank_slope
    bottom_width = pitch - 2.0 * root_trunc * flank_slope
    if bottom_width <= 0:
        raise ValueError("Thread root truncation too large for given pitch.")
    if top_width < 0:
        raise ValueError("Thread crest truncation too large for given pitch.")
    crest_x = height / 2.0
    root_x = -height / 2.0
    wp = cq.Workplane("XZ").center(pitch_radius, 0.0)
    if top_width <= 1e-8:
        half_bottom = bottom_width / 2.0
        return wp.polyline(
            [
                (crest_x, 0.0),
                (root_x, half_bottom),
                (root_x, -half_bottom),
            ]
        ).close()
    half_top = top_width / 2.0
    half_bottom = bottom_width / 2.0
    return wp.polyline(
        [
            (crest_x, -half_top),
            (crest_x, half_top),
            (root_x, half_bottom),
            (root_x, -half_bottom),
        ]
    ).close()


def _sweep_thread_ridge(
    spec: ThreadSpec,
    *,
    length: float,
    pitch: float,
    height: float,
    pitch_radius: float,
    crest_trunc: float,
    root_trunc: float,
    centered: bool,
) -> cq.Workplane:
    lead = resolve_lead(spec)
    wire = cq.Wire.makeHelix(
        pitch=lead,
        height=length,
        radius=pitch_radius,
        lefthand=spec.hand == "LH",
    )
    helix = cq.Workplane(obj=wire)
    profile = _thread_profile(
        pitch=pitch,
        height=height,
        included_angle_deg=spec.profile.included_angle_deg,
        crest_trunc=crest_trunc,
        root_trunc=root_trunc,
        pitch_radius=pitch_radius,
    )
    ridge = profile.sweep(helix, isFrenet=True)
    if centered:
        ridge = ridge.translate((0, 0, -length / 2.0))
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
    major, minor, pitch_diameter, crest_trunc, root_trunc = _resolve_thread_diameters(
        spec, pitch
    )
    height = (major - minor) / 2.0
    pitch_radius = pitch_diameter / 2.0
    ridge = _sweep_thread_ridge(
        spec,
        length=length_value,
        pitch=pitch,
        height=height,
        pitch_radius=pitch_radius,
        crest_trunc=crest_trunc,
        root_trunc=root_trunc,
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
