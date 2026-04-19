"""Rect primitives for occupancy-based region packing.

Used by `RegionBasedPacker` to record the bounding boxes of pieces already
placed in a region (`occupied`) and to track the remaining guillotine-valid
empty spaces (`free_rects`). Phase B (trim placement backtracking) consumes
these to avoid overwriting already-occupied cells — which the previous
row-based abstraction failed to prevent for stacked groups.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def x2(self) -> int:
        return self.x + self.w

    @property
    def y2(self) -> int:
        return self.y + self.h

    @property
    def area(self) -> int:
        return self.w * self.h


def intersects(a: Rect, b: Rect) -> bool:
    """True iff the two rectangles overlap with positive area."""
    return a.x < b.x2 and b.x < a.x2 and a.y < b.y2 and b.y < a.y2


def contains(outer: Rect, inner: Rect) -> bool:
    """True iff `inner` is fully inside `outer` (boundaries may touch)."""
    return (
        outer.x <= inner.x
        and outer.y <= inner.y
        and inner.x2 <= outer.x2
        and inner.y2 <= outer.y2
    )


def split_guillotine(free: Rect, used: Rect) -> list[Rect]:
    """Cut `used` out of `free` with a single guillotine split, return the leftovers.

    `used` must be corner-aligned to `free` (top-left origin) — callers that
    place a piece at the top-left of a free rect satisfy this.

    The split axis is chosen by the SHORTER_AXIS rule: cut along the shorter
    remaining dimension first so the larger surviving piece stays intact,
    which typically yields better packing downstream.

    Returns 0, 1, or 2 rectangles.
    """
    if not contains(free, used):
        raise ValueError(f"used {used} not contained in free {free}")

    right_w = free.w - used.w
    below_h = free.h - used.h

    if right_w == 0 and below_h == 0:
        return []
    if right_w == 0:
        return [Rect(free.x, used.y2, free.w, below_h)]
    if below_h == 0:
        return [Rect(used.x2, free.y, right_w, free.h)]

    # SHORTER_AXIS: pick the cut direction that keeps the larger piece whole.
    if right_w <= below_h:
        # Vertical cut at used.x2: right strip full-height, below strip used-width
        return [
            Rect(used.x2, free.y, right_w, free.h),
            Rect(free.x, used.y2, used.w, below_h),
        ]
    # Horizontal cut at used.y2: below strip full-width, right strip used-height
    return [
        Rect(free.x, used.y2, free.w, below_h),
        Rect(used.x2, free.y, right_w, used.h),
    ]
