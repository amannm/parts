from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MoveKind = Literal["rapid", "linear", "arc_cw", "arc_ccw", "dwell", "comment"]


def _fmt_axis(letter: str, value: float | None) -> str | None:
    if value is None:
        return None
    return f"{letter}{value:.6g}"


def _comment(text: str) -> str:
    return f"({text.replace(')', ']')})"


@dataclass(frozen=True)
class Move:
    kind: MoveKind
    x: float | None = None
    y: float | None = None
    z: float | None = None
    i: float | None = None
    j: float | None = None
    k: float | None = None
    r: float | None = None
    feed: float | None = None
    dwell_seconds: float | None = None
    text: str | None = None

    @classmethod
    def rapid(cls, x: float | None = None, y: float | None = None, z: float | None = None) -> Move:
        return cls("rapid", x=x, y=y, z=z)

    @classmethod
    def line(
        cls,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        *,
        feed: float | None = None,
    ) -> Move:
        return cls("linear", x=x, y=y, z=z, feed=feed)

    @classmethod
    def arc_cw(
        cls,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        *,
        i: float | None = None,
        j: float | None = None,
        k: float | None = None,
        r: float | None = None,
        feed: float | None = None,
    ) -> Move:
        return cls("arc_cw", x=x, y=y, z=z, i=i, j=j, k=k, r=r, feed=feed)

    @classmethod
    def arc_ccw(
        cls,
        x: float | None = None,
        y: float | None = None,
        z: float | None = None,
        *,
        i: float | None = None,
        j: float | None = None,
        k: float | None = None,
        r: float | None = None,
        feed: float | None = None,
    ) -> Move:
        return cls("arc_ccw", x=x, y=y, z=z, i=i, j=j, k=k, r=r, feed=feed)

    @classmethod
    def dwell(cls, seconds: float) -> Move:
        return cls("dwell", dwell_seconds=seconds)

    @classmethod
    def comment(cls, text: str) -> Move:
        return cls("comment", text=text)

    def to_gcode(self) -> str:
        if self.kind == "comment":
            return _comment(self.text or "")
        if self.kind == "dwell":
            seconds = self.dwell_seconds if self.dwell_seconds is not None else 0.0
            return f"G4 P{seconds:.6g}"

        command = {
            "rapid": "G0",
            "linear": "G1",
            "arc_cw": "G2",
            "arc_ccw": "G3",
        }[self.kind]
        fields = [
            command,
            _fmt_axis("X", self.x),
            _fmt_axis("Y", self.y),
            _fmt_axis("Z", self.z),
            _fmt_axis("I", self.i),
            _fmt_axis("J", self.j),
            _fmt_axis("K", self.k),
            _fmt_axis("R", self.r),
            _fmt_axis("F", self.feed),
        ]
        return " ".join(field for field in fields if field is not None)


@dataclass(frozen=True)
class ToolPath:
    """Optional low-level motion trace for an operation.

    A ToolPath is intentionally simple. Most framework operations only know the
    CadQuery cutter volume and emit operation-level comments, while operations
    that do know coordinates can attach actual G0/G1/G2/G3 moves.
    """

    moves: tuple[Move, ...] = ()

    @classmethod
    def of(cls, *moves: Move) -> ToolPath:
        return cls(tuple(moves))

    def to_gcode(self) -> list[str]:
        return [move.to_gcode() for move in self.moves]
