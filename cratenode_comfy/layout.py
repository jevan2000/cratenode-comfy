"""Layout without pixel arithmetic: stack, place and grid scene parts in a box.

A *part* is any scene; its content is measured by its bounds (text by its line
boxes), so a title that wraps pushes everything after it down. Each part
becomes one GroupItem, moved into position.
"""

from __future__ import annotations

from .fonts import FontRegistry, registry
from .scene import GroupItem, LayoutItem, Scene, content_bounds

AREAS = ["safe area", "canvas", "custom"]
H_POS = ["left", "center", "right"]
V_POS = ["top", "middle", "bottom"]
DIRECTIONS = ["vertical", "horizontal"]


def _offset(pos: str, space: float, size: float) -> float:
    if pos in ("center", "middle"):
        return (space - size) / 2
    if pos in ("right", "bottom"):
        return space - size
    return 0.0


# Grid placement: inside the cell at align/valign, or centred on the cell's line that
# align/valign names (left/top = its first line, right/bottom = its second, center/middle
# = its centre line), so parts straddle the grid lines and their crossings.
PLACEMENTS = ["within cell", "on grid line"]


def _line_offset(pos: str, space: float, size: float) -> float:
    if pos in ("center", "middle"):
        return (space - size) / 2
    if pos in ("right", "bottom"):
        return space - size / 2
    return -size / 2


def area_box(scene: Scene, area: str, x: float, y: float, w: float, h: float):
    """(x, y, w, h) for an area choice; custom sizes of 0 run to the canvas edge."""
    if area == "canvas":
        return (0.0, 0.0, float(scene.width), float(scene.height))
    if area == "safe area":
        return scene.safe_box()
    return (x, y, w if w > 0 else scene.width - x, h if h > 0 else scene.height - y)


def _parts(parts: list[Scene], reg: FontRegistry):
    out = []
    for p in parts:
        b = content_bounds(p.items, reg)
        if b is not None:
            out.append((p.items, b))
    return out


def stack(parts: list[Scene], box, direction="vertical", gap=24.0, align="center", valign="top",
          reg: FontRegistry | None = None) -> list[GroupItem]:
    """Parts in a column (or row) with ``gap``; the group sits in ``box`` at align/valign,
    and parts line up across the stack by align (vertical) or valign (horizontal)."""
    reg = reg or registry()
    groups = _parts(parts, reg)
    if not groups:
        return []
    vertical = direction != "horizontal"
    n = len(groups)
    ws = [b[2] - b[0] for _, b in groups]
    hs = [b[3] - b[1] for _, b in groups]
    main = (sum(hs) if vertical else sum(ws)) + gap * (n - 1)
    cross = max(ws) if vertical else max(hs)
    gw, gh = (cross, main) if vertical else (main, cross)
    bx, by, bw, bh = box
    gx, gy = bx + _offset(align, bw, gw), by + _offset(valign, bh, gh)
    out, cursor = [], 0.0
    for (items, b), w, h in zip(groups, ws, hs):
        if vertical:
            tx, ty = gx + _offset(align, cross, w), gy + cursor
            cursor += h + gap
        else:
            tx, ty = gx + cursor, gy + _offset(valign, cross, h)
            cursor += w + gap
        out.append(GroupItem(items=items, dx=tx - b[0], dy=ty - b[1]))
    return out


def stack_item(parts: list[Scene], box, direction="vertical", gap=24.0, align="center", valign="top") -> LayoutItem:
    """A stack that is arranged at draw time (reflows when a part's text changes)."""
    return LayoutItem("stack", tuple(p.items for p in parts if p.items), tuple(box), direction, gap,
                      align=align, valign=valign)


def grid_item(parts: list[Scene], box, columns=3, gap_x=24.0, gap_y=24.0, align="center",
              valign="middle", direction="vertical", placement="within cell") -> LayoutItem:
    return LayoutItem("grid", tuple(p.items for p in parts if p.items), tuple(box), direction, gap=gap_x,
                      gap_y=gap_y, columns=columns, align=align, valign=valign,
                      placement="" if placement == "within cell" else placement)


def arrange(it: LayoutItem, reg: FontRegistry | None = None) -> tuple:
    """The GroupItems a LayoutItem resolves to right now."""
    parts = [Scene(1, 1, items=p) for p in it.parts]
    if it.kind == "grid":
        return tuple(grid(parts, it.box, it.columns, it.gap, it.gap_y, it.align, it.valign, reg, it.direction,
                          it.placement or "within cell"))
    return tuple(stack(parts, it.box, it.direction, it.gap, it.align, it.valign, reg))


def place(part: Scene, box, align="center", valign="middle", reg: FontRegistry | None = None) -> list[GroupItem]:
    return stack([part], box, "vertical", 0.0, align, valign, reg)


def grid_cells(n: int, box, count=3, gap_x=24.0, gap_y=24.0, direction="vertical"):
    """(cells, columns, rows) for ``n`` parts. Each cell is (x, y, w, h), in fill order.

    vertical: ``count`` columns; parts fill a row left to right, then the next row
    down (the grid grows downwards). horizontal: ``count`` rows; parts fill a column
    top to bottom, then the next column to the right (the grid grows sideways).
    Cells divide the box; the list covers every cell, including empty ones at the end."""
    k = max(1, int(count))
    lines = max(1, (n + k - 1) // k)
    cols, rows = (lines, k) if direction == "horizontal" else (k, lines)
    bx, by, bw, bh = box
    cw = (bw - gap_x * (cols - 1)) / cols
    ch = (bh - gap_y * (rows - 1)) / rows
    cells = []
    for i in range(cols * rows):
        c, r = divmod(i, rows) if direction == "horizontal" else divmod(i, cols)[::-1]
        cells.append((bx + c * (cw + gap_x), by + r * (ch + gap_y), cw, ch))
    return cells, cols, rows


def grid(parts: list[Scene], box, columns=3, gap_x=24.0, gap_y=24.0, align="center", valign="middle",
         reg: FontRegistry | None = None, direction="vertical", placement="within cell") -> list[GroupItem]:
    """Parts in equal cells (see ``grid_cells`` for the fill order); each part sits in
    its cell at align/valign, or centred on that cell line ("on grid line"). Cells
    divide the box."""
    reg = reg or registry()
    groups = _parts(parts, reg)
    if not groups:
        return []
    cells, _, _ = grid_cells(len(groups), box, columns, gap_x, gap_y, direction)
    off = _line_offset if placement == "on grid line" else _offset
    out = []
    for (items, b), (cx, cy, cw, ch) in zip(groups, cells):
        w, h = b[2] - b[0], b[3] - b[1]
        tx, ty = cx + off(align, cw, w), cy + off(valign, ch, h)
        out.append(GroupItem(items=items, dx=tx - b[0], dy=ty - b[1]))
    return out
