from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable, Literal, Mapping

import cadquery as cq

from simparts.machining.gcode import ToolPath
from simparts.machining.operations import MachiningPlan, MaterialAction, OperationKind, OperationRecord
from simparts.machining.primitives import Axis, VectorLike, box, cylinder, extruded_profile, sphere, torus, tube
from simparts.machining.tools import Tool


FinishSelector = str
MaterialMode = Literal["cut", "add"]


def _operation(
    *,
    name: str,
    kind: OperationKind,
    action: MaterialAction,
    tool: Tool | None,
    strategy: str,
    parameters: Mapping[str, Any] | None,
    toolpath: ToolPath | None,
    spindle_rpm: float | None,
    feed: float | None,
    coolant: bool,
) -> OperationRecord:
    return OperationRecord(
        name=name,
        kind=kind,
        action=action,
        tool=tool,
        strategy=strategy,
        parameters=dict(parameters or {}),
        toolpath=toolpath,
        spindle_rpm=spindle_rpm,
        feed=feed,
        coolant=coolant,
    )


@dataclass(frozen=True)
class Workpiece:
    """A CadQuery solid plus the virtual CNC operations used to make it."""

    solid: cq.Workplane
    name: str = "workpiece"
    plan: MachiningPlan = MachiningPlan()

    @classmethod
    def from_solid(
        cls,
        solid: cq.Workplane,
        *,
        name: str = "workpiece",
        stock_name: str = "load stock",
        stock_parameters: Mapping[str, Any] | None = None,
    ) -> Workpiece:
        operation = OperationRecord(
            name=stock_name,
            kind="setup",
            action="replace",
            strategy="load or fixture pre-existing stock",
            parameters=dict(stock_parameters or {}),
        )
        return cls(solid=solid, name=name, plan=MachiningPlan((operation,)))

    @classmethod
    def box_stock(
        cls,
        x: float,
        y: float,
        z: float,
        *,
        name: str = "box_stock",
        center: VectorLike = (0.0, 0.0, 0.0),
        centered: tuple[bool, bool, bool] = (True, True, True),
    ) -> Workpiece:
        return cls.from_solid(
            box(x, y, z, center=center, centered=centered),
            name=name,
            stock_name="load box stock",
            stock_parameters={"x": x, "y": y, "z": z, "center": center},
        )

    @classmethod
    def cylinder_stock(
        cls,
        diameter: float,
        length: float,
        *,
        name: str = "cylindrical_stock",
        axis: Axis = "Z",
        center: VectorLike = (0.0, 0.0, 0.0),
        centered: bool = True,
    ) -> Workpiece:
        return cls.from_solid(
            cylinder(diameter, length, axis=axis, center=center, centered=centered),
            name=name,
            stock_name="load cylindrical stock",
            stock_parameters={"diameter": diameter, "length": length, "axis": axis, "center": center},
        )

    @classmethod
    def tube_stock(
        cls,
        outer_diameter: float,
        inner_diameter: float,
        length: float,
        *,
        name: str = "tube_stock",
        axis: Axis = "Z",
        center: VectorLike = (0.0, 0.0, 0.0),
        centered: bool = True,
    ) -> Workpiece:
        return cls.from_solid(
            tube(
                outer_diameter,
                inner_diameter,
                length,
                axis=axis,
                center=center,
                centered=centered,
            ),
            name=name,
            stock_name="load tube stock",
            stock_parameters={
                "outer_diameter": outer_diameter,
                "inner_diameter": inner_diameter,
                "length": length,
                "axis": axis,
                "center": center,
            },
        )

    @classmethod
    def profile_stock(
        cls,
        profile: cq.Workplane,
        distance: float,
        *,
        name: str = "profile_stock",
        centered: bool = True,
        twist_angle_deg: float = 0.0,
    ) -> Workpiece:
        return cls.from_solid(
            extruded_profile(profile, distance, centered=centered, twist_angle_deg=twist_angle_deg),
            name=name,
            stock_name="load profiled stock",
            stock_parameters={"distance": distance, "centered": centered, "twist_angle_deg": twist_angle_deg},
        )

    @classmethod
    def ball_stock(
        cls,
        diameter: float,
        *,
        name: str = "ball_stock",
        center: VectorLike = (0.0, 0.0, 0.0),
    ) -> Workpiece:
        return cls.from_solid(
            sphere(diameter, center=center),
            name=name,
            stock_name="load spherical stock",
            stock_parameters={"diameter": diameter, "center": center},
        )

    def _with_operation(self, solid: cq.Workplane, operation: OperationRecord) -> Workpiece:
        return replace(self, solid=solid, plan=self.plan.append(operation))

    def as_workplane(self) -> cq.Workplane:
        return self.solid

    def to_gcode(self, *, program_name: str | None = None) -> str:
        return self.plan.to_gcode(program_name=program_name or self.name.upper())

    def apply(
        self,
        transform: Callable[[cq.Workplane], cq.Workplane],
        *,
        name: str = "custom operation",
        kind: OperationKind = "custom",
        action: MaterialAction = "replace",
        tool: Tool | None = None,
        strategy: str = "custom CadQuery-backed operation",
        parameters: Mapping[str, Any] | None = None,
        toolpath: ToolPath | None = None,
        spindle_rpm: float | None = None,
        feed: float | None = None,
        coolant: bool = False,
    ) -> Workpiece:
        operation = _operation(
            name=name,
            kind=kind,
            action=action,
            tool=tool,
            strategy=strategy,
            parameters=parameters,
            toolpath=toolpath,
            spindle_rpm=spindle_rpm,
            feed=feed,
            coolant=coolant,
        )
        return self._with_operation(transform(self.solid), operation)

    def cut(
        self,
        cutter: cq.Workplane,
        *,
        tool: Tool | None = None,
        name: str = "cut",
        kind: OperationKind = "custom",
        strategy: str = "subtract explicit CadQuery cutter volume",
        parameters: Mapping[str, Any] | None = None,
        toolpath: ToolPath | None = None,
        spindle_rpm: float | None = None,
        feed: float | None = None,
        coolant: bool = False,
    ) -> Workpiece:
        operation = _operation(
            name=name,
            kind=kind,
            action="cut",
            tool=tool,
            strategy=strategy,
            parameters=parameters,
            toolpath=toolpath,
            spindle_rpm=spindle_rpm,
            feed=feed,
            coolant=coolant,
        )
        return self._with_operation(self.solid.cut(cutter), operation)

    def add(
        self,
        solid: cq.Workplane,
        *,
        tool: Tool | None = None,
        name: str = "add material",
        kind: OperationKind = "insert",
        strategy: str = "join or insert prepared stock",
        parameters: Mapping[str, Any] | None = None,
        toolpath: ToolPath | None = None,
    ) -> Workpiece:
        operation = _operation(
            name=name,
            kind=kind,
            action="add",
            tool=tool,
            strategy=strategy,
            parameters=parameters,
            toolpath=toolpath,
            spindle_rpm=None,
            feed=None,
            coolant=False,
        )
        return self._with_operation(self.solid.union(solid), operation)

    def insert(
        self,
        solid: cq.Workplane,
        *,
        name: str = "insert prepared component",
        parameters: Mapping[str, Any] | None = None,
    ) -> Workpiece:
        return self.add(
            solid,
            name=name,
            kind="insert",
            strategy="place and join prepared component stock",
            parameters=parameters,
        )

    def cut_many(
        self,
        cutters: Iterable[tuple[str, cq.Workplane] | cq.Workplane],
        *,
        tool: Tool | None = None,
        name: str = "pattern cut",
        kind: OperationKind = "custom",
        strategy: str = "subtract repeated cutter volumes",
        parameters: Mapping[str, Any] | None = None,
        toolpath: ToolPath | None = None,
        spindle_rpm: float | None = None,
        feed: float | None = None,
        coolant: bool = False,
    ) -> Workpiece:
        result = self.solid
        count = 0
        for item in cutters:
            cutter = item[1] if isinstance(item, tuple) else item
            result = result.cut(cutter)
            count += 1
        merged_parameters = dict(parameters or {})
        merged_parameters.setdefault("count", count)
        operation = _operation(
            name=name,
            kind=kind,
            action="cut",
            tool=tool,
            strategy=strategy,
            parameters=merged_parameters,
            toolpath=toolpath,
            spindle_rpm=spindle_rpm,
            feed=feed,
            coolant=coolant,
        )
        return self._with_operation(result, operation)

    def add_many(
        self,
        solids: Iterable[tuple[str, cq.Workplane] | cq.Workplane],
        *,
        tool: Tool | None = None,
        name: str = "pattern add",
        kind: OperationKind = "insert",
        strategy: str = "join repeated prepared solids",
        parameters: Mapping[str, Any] | None = None,
        toolpath: ToolPath | None = None,
    ) -> Workpiece:
        result = self.solid
        count = 0
        for item in solids:
            solid = item[1] if isinstance(item, tuple) else item
            result = result.union(solid)
            count += 1
        merged_parameters = dict(parameters or {})
        merged_parameters.setdefault("count", count)
        operation = _operation(
            name=name,
            kind=kind,
            action="add",
            tool=tool,
            strategy=strategy,
            parameters=merged_parameters,
            toolpath=toolpath,
            spindle_rpm=None,
            feed=None,
            coolant=False,
        )
        return self._with_operation(result, operation)

    def drill(
        self,
        diameter: float,
        depth: float,
        *,
        center: VectorLike = (0.0, 0.0, 0.0),
        axis: Axis = "Z",
        tool: Tool | None = None,
        name: str = "drill",
        toolpath: ToolPath | None = None,
        peck_depth: float | None = None,
        spindle_rpm: float | None = None,
        feed: float | None = None,
        coolant: bool = False,
    ) -> Workpiece:
        cutter = cylinder(diameter, depth, axis=axis, center=center, centered=True)
        parameters: dict[str, Any] = {"diameter": diameter, "depth": depth, "center": center, "axis": axis}
        if peck_depth is not None:
            parameters["peck_depth"] = peck_depth
        return self.cut(
            cutter,
            tool=tool,
            name=name,
            kind="drill",
            strategy="axial drill cycle",
            parameters=parameters,
            toolpath=toolpath,
            spindle_rpm=spindle_rpm,
            feed=feed,
            coolant=coolant,
        )

    def bore(
        self,
        diameter: float,
        depth: float,
        *,
        center: VectorLike = (0.0, 0.0, 0.0),
        axis: Axis = "Z",
        tool: Tool | None = None,
        name: str = "bore",
        toolpath: ToolPath | None = None,
        spindle_rpm: float | None = None,
        feed: float | None = None,
        coolant: bool = False,
    ) -> Workpiece:
        cutter = cylinder(diameter, depth, axis=axis, center=center, centered=True)
        return self.cut(
            cutter,
            tool=tool,
            name=name,
            kind="bore",
            strategy="interpolated bore or boring cycle",
            parameters={"diameter": diameter, "depth": depth, "center": center, "axis": axis},
            toolpath=toolpath,
            spindle_rpm=spindle_rpm,
            feed=feed,
            coolant=coolant,
        )

    def profile_cut(
        self,
        profile: cq.Workplane,
        depth: float,
        *,
        tool: Tool | None = None,
        name: str = "profile cut",
        kind: OperationKind = "profile_mill",
        centered: bool = True,
        twist_angle_deg: float = 0.0,
        toolpath: ToolPath | None = None,
        spindle_rpm: float | None = None,
        feed: float | None = None,
        coolant: bool = False,
    ) -> Workpiece:
        cutter = extruded_profile(profile, depth, centered=centered, twist_angle_deg=twist_angle_deg)
        strategy = "2.5D profile mill"
        if abs(twist_angle_deg) > 1e-9:
            strategy = "synchronized helical profile mill"
        return self.cut(
            cutter,
            tool=tool,
            name=name,
            kind=kind,
            strategy=strategy,
            parameters={"depth": depth, "centered": centered, "twist_angle_deg": twist_angle_deg},
            toolpath=toolpath,
            spindle_rpm=spindle_rpm,
            feed=feed,
            coolant=coolant,
        )

    def pocket_cut(
        self,
        profile: cq.Workplane,
        depth: float,
        *,
        tool: Tool | None = None,
        name: str = "pocket",
        centered: bool = True,
        toolpath: ToolPath | None = None,
        spindle_rpm: float | None = None,
        feed: float | None = None,
        coolant: bool = False,
    ) -> Workpiece:
        return self.profile_cut(
            profile,
            depth,
            tool=tool,
            name=name,
            kind="pocket_mill",
            centered=centered,
            toolpath=toolpath,
            spindle_rpm=spindle_rpm,
            feed=feed,
            coolant=coolant,
        )

    def form_torus_cut(
        self,
        major_radius: float,
        minor_radius: float,
        *,
        axis: Axis = "Z",
        center: VectorLike = (0.0, 0.0, 0.0),
        tool: Tool | None = None,
        name: str = "form torus cut",
        spindle_rpm: float | None = None,
        feed: float | None = None,
        coolant: bool = False,
    ) -> Workpiece:
        cutter = torus(major_radius, minor_radius, axis=axis, center=center)
        return self.cut(
            cutter,
            tool=tool,
            name=name,
            kind="form_cut",
            strategy="form tool or ball-end contour following toroidal groove",
            parameters={
                "major_radius": major_radius,
                "minor_radius": minor_radius,
                "axis": axis,
                "center": center,
            },
            spindle_rpm=spindle_rpm,
            feed=feed,
            coolant=coolant,
        )

    def turn_cut(
        self,
        cutter: cq.Workplane,
        *,
        tool: Tool | None = None,
        name: str = "turn cut",
        strategy: str = "lathe turning cutter envelope",
        parameters: Mapping[str, Any] | None = None,
        toolpath: ToolPath | None = None,
    ) -> Workpiece:
        return self.cut(
            cutter,
            tool=tool,
            name=name,
            kind="turn",
            strategy=strategy,
            parameters=parameters,
            toolpath=toolpath,
        )

    def thread_cut(
        self,
        cutter: cq.Workplane,
        *,
        tool: Tool | None = None,
        name: str = "thread cut",
        strategy: str = "thread mill or single-point thread cutter envelope",
        parameters: Mapping[str, Any] | None = None,
        toolpath: ToolPath | None = None,
    ) -> Workpiece:
        return self.cut(
            cutter,
            tool=tool,
            name=name,
            kind="thread",
            strategy=strategy,
            parameters=parameters,
            toolpath=toolpath,
        )

    def sweep_cut(
        self,
        cutter: cq.Workplane,
        *,
        tool: Tool | None = None,
        name: str = "sweep cut",
        strategy: str = "5-axis swept cutter envelope",
        parameters: Mapping[str, Any] | None = None,
        toolpath: ToolPath | None = None,
        spindle_rpm: float | None = None,
        feed: float | None = None,
        coolant: bool = False,
    ) -> Workpiece:
        return self.cut(
            cutter,
            tool=tool,
            name=name,
            kind="sweep_cut",
            strategy=strategy,
            parameters=parameters,
            toolpath=toolpath,
            spindle_rpm=spindle_rpm,
            feed=feed,
            coolant=coolant,
        )

    def wire_form(
        self,
        formed_solid: cq.Workplane,
        *,
        tool: Tool | None = None,
        name: str = "wire form",
        strategy: str = "bend wire along swept centerline",
        parameters: Mapping[str, Any] | None = None,
    ) -> Workpiece:
        return self.add(
            formed_solid,
            tool=tool,
            name=name,
            kind="wire_form",
            strategy=strategy,
            parameters=parameters,
        )

    def finish_chamfer(
        self,
        selector: FinishSelector,
        distance: float,
        distance2: float | None = None,
        *,
        tool: Tool | None = None,
        name: str = "chamfer",
    ) -> Workpiece:
        if distance2 is None:
            result = self.solid.edges(selector).chamfer(distance)
            params = {"selector": selector, "distance": distance}
        else:
            result = self.solid.edges(selector).chamfer(distance, distance2)
            params = {"selector": selector, "distance": distance, "distance2": distance2}
        operation = _operation(
            name=name,
            kind="finish",
            action="finish",
            tool=tool,
            strategy="edge chamfer finishing pass",
            parameters=params,
            toolpath=None,
            spindle_rpm=None,
            feed=None,
            coolant=False,
        )
        return self._with_operation(result, operation)

    def finish_fillet(
        self,
        selector: FinishSelector,
        radius: float,
        *,
        tool: Tool | None = None,
        name: str = "fillet",
    ) -> Workpiece:
        result = self.solid.edges(selector).fillet(radius)
        operation = _operation(
            name=name,
            kind="finish",
            action="finish",
            tool=tool,
            strategy="edge radius finishing pass",
            parameters={"selector": selector, "radius": radius},
            toolpath=None,
            spindle_rpm=None,
            feed=None,
            coolant=False,
        )
        return self._with_operation(result, operation)
