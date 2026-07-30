"""Slice a panel that is too wide to read comfortably on a small screen into
vertical strips. Seams dodge the speech balloons and characters Magi found, so
a cut never lands in the middle of a face or a line of dialogue."""
from __future__ import annotations

from math import ceil

from manga_panels.detect import Box


def _crossings(seam: int, obstacles) -> int:
    """How many obstacle boxes a vertical cut at `seam` would slice through."""
    return sum(1 for o in obstacles if o[0] < seam < o[2])


def split_wide(box: Box, obstacles, *, max_ratio: float,
               window: float = 0.15) -> list[Box]:
    """Cut `box` into vertical slices when it is wider than max_ratio:1.

    `obstacles` are Magi's text/character boxes as [x1, y1, x2, y2] in page
    pixels. Each seam starts at the even split point and slides within
    +/-`window` of a slice width to the position that cuts through the fewest
    obstacles, preferring the one closest to even. Returns the slices right to
    left (manga reading order), or [box] untouched when it already fits."""
    if max_ratio <= 0:
        raise ValueError(f"max_ratio must be > 0, got {max_ratio!r}")
    x, y, w, h = box
    if h <= 0 or w / h <= max_ratio:
        return [box]
    n = min(ceil((w / h) / max_ratio), w)      # >=1px per slice, so seams stay ordered
    if n < 2:
        return [box]
    slice_w = w / n
    # only obstacles that actually overlap the panel can be cut by its seams
    hits = [o for o in obstacles
            if o[0] < x + w and o[2] > x and o[1] < y + h and o[3] > y]

    edges, prev = [x], x
    for k in range(1, n):
        ideal = x + slice_w * k
        # lo/hi keep seams strictly increasing and leave 1px for every slice
        # still to come; slice_w >= 1 guarantees lo <= hi.
        lo = max(prev + 1, round(ideal - window * slice_w))
        hi = min(x + w - (n - k), round(ideal + window * slice_w))
        prev = min(range(lo, hi + 1),
                   key=lambda s: (_crossings(s, hits), abs(s - ideal)))
        edges.append(prev)
    edges.append(x + w)

    slices = [(edges[i], y, edges[i + 1] - edges[i], h) for i in range(n)]
    return slices[::-1]                        # rightmost slice is read first
