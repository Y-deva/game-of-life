"""Game of Life domain model: grid, life-like rules and RLE serialisation.

The model is deliberately independent of Qt so it can be tested and reused on
its own. Live cells are stored in a ``set`` of ``(x, y)`` tuples; each cell
also carries an age counter that the view uses for colouring.
"""

from __future__ import annotations

import random
import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

Cell = tuple[int, int]

MAX_DIMENSION = 10_000

_NEIGHBOURS: tuple[Cell, ...] = tuple(
    (dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy
)

_HEADER_RE = re.compile(r"x\s*=\s*(\d+)\s*,\s*y\s*=\s*(\d+)", re.IGNORECASE)
_RULE_RE = re.compile(r"rule\s*=\s*B([0-8]*)\s*/\s*S([0-8]*)", re.IGNORECASE)
_RULE_TEXT_RE = re.compile(r"B([0-8]*)\s*/\s*S([0-8]*)", re.IGNORECASE)


class RLEError(ValueError):
    """Raised when an RLE document cannot be parsed."""


class RuleError(ValueError):
    """Raised when a rule string cannot be parsed."""


@dataclass(frozen=True, slots=True)
class Rule:
    """A life-like birth/survival rule such as ``B3/S23``."""

    birth: frozenset[int] = frozenset({3})
    survive: frozenset[int] = frozenset({2, 3})

    def __post_init__(self) -> None:
        for group in (self.birth, self.survive):
            for count in group:
                if not 0 <= count <= 8:
                    raise RuleError("neighbour counts must be between 0 and 8")

    @classmethod
    def parse(cls, text: str) -> "Rule":
        """Parse ``B3/S23`` (whitespace and lower case are accepted)."""
        match = _RULE_TEXT_RE.fullmatch(text.strip())
        if match is None:
            raise RuleError(f"invalid rule {text!r}; expected a value like B3/S23")
        return cls(
            birth=frozenset(int(digit) for digit in match.group(1)),
            survive=frozenset(int(digit) for digit in match.group(2)),
        )

    def __str__(self) -> str:
        birth = "".join(str(n) for n in sorted(self.birth))
        survive = "".join(str(n) for n in sorted(self.survive))
        return f"B{birth}/S{survive}"

    @property
    def name(self) -> str:
        """Human readable preset name, or ``Custom rule``."""
        return PRESETS_BY_TEXT.get(str(self), "Custom rule")


LIFE = Rule()
HIGHLIFE = Rule.parse("B36/S23")
SEEDS = Rule.parse("B2/S")
DAY_AND_NIGHT = Rule.parse("B3678/S34678")
DIAMOEBA = Rule.parse("B35678/S5678")

PRESETS: dict[str, Rule] = {
    "Conway's Life (B3/S23)": LIFE,
    "HighLife (B36/S23)": HIGHLIFE,
    "Seeds (B2/S)": SEEDS,
    "Day & Night (B3678/S34678)": DAY_AND_NIGHT,
    "Diamoeba (B35678/S5678)": DIAMOEBA,
}

PRESETS_BY_TEXT: dict[str, str] = {str(rule): name for name, rule in PRESETS.items()}


@dataclass(frozen=True, slots=True)
class RLEPattern:
    """A parsed RLE pattern."""

    cells: tuple[Cell, ...]
    width: int
    height: int
    rule: str = "B3/S23"
    comments: tuple[str, ...] = ()

    @property
    def population(self) -> int:
        return len(self.cells)


@dataclass(frozen=True, slots=True)
class Pattern:
    """An entry in the built-in pattern library."""

    name: str
    rle: str
    description: str = ""

    def parse(self) -> RLEPattern:
        return parse_rle(self.rle)


class LifeGrid:
    """A finite (or toroidal) Game of Life universe."""

    __slots__ = ("width", "height", "torus", "live", "age", "generation", "rule")

    def __init__(
        self,
        width: int = 160,
        height: int = 100,
        torus: bool = True,
        rule: Rule = LIFE,
    ) -> None:
        if width < 1 or height < 1:
            raise ValueError("grid dimensions must be positive")
        self.width = int(width)
        self.height = int(height)
        self.torus = bool(torus)
        self.rule = rule
        self.live: set[Cell] = set()
        self.age: dict[Cell, int] = {}
        self.generation = 0

    def __len__(self) -> int:
        return len(self.live)

    def __contains__(self, cell: Cell) -> bool:
        return cell in self.live

    def clear(self) -> None:
        """Empty the universe and reset the generation counter."""
        self.live.clear()
        self.age.clear()
        self.generation = 0

    def copy(self) -> "LifeGrid":
        clone = LifeGrid(self.width, self.height, self.torus, self.rule)
        clone.live = set(self.live)
        clone.age = dict(self.age)
        clone.generation = self.generation
        return clone

    def set_rule(self, rule: Rule) -> None:
        self.rule = rule

    # -- editing ---------------------------------------------------------

    def randomize(self, density: float = 0.25, rng: random.Random | None = None) -> None:
        """Fill the grid with random live cells (density in ``[0, 1]``)."""
        if not 0.0 <= density <= 1.0:
            raise ValueError("density must be within [0, 1]")
        chooser = rng or random.Random()
        self.live = {
            (x, y)
            for y in range(self.height)
            for x in range(self.width)
            if chooser.random() < density
        }
        self.age = {cell: 0 for cell in self.live}
        self.generation = 0

    def set_cell(self, x: int, y: int, alive: bool = True) -> bool:
        """Set one cell; returns ``True`` when the state changed."""
        if not (0 <= x < self.width and 0 <= y < self.height):
            return False
        cell = (x, y)
        if alive:
            if cell in self.live:
                return False
            self.live.add(cell)
            self.age[cell] = 0
            return True
        if cell not in self.live:
            return False
        self.live.discard(cell)
        self.age.pop(cell, None)
        return True

    def toggle_cell(self, x: int, y: int) -> bool:
        return self.set_cell(x, y, (x, y) not in self.live)

    def set_cells(self, cells: Iterable[Cell], clear: bool = True) -> int:
        """Copy ``cells`` into the grid, clipping anything outside the bounds."""
        if clear:
            self.live.clear()
            self.age.clear()
        added = 0
        for x, y in cells:
            if 0 <= x < self.width and 0 <= y < self.height:
                if (x, y) not in self.live:
                    added += 1
                self.live.add((x, y))
                self.age[(x, y)] = 0
        return added

    def place(self, cells: Iterable[Cell], x0: int, y0: int) -> int:
        """Place a pattern so its top-left corner lands on ``(x0, y0)``."""
        return self.set_cells(((x0 + x, y0 + y) for x, y in cells), clear=False)

    def place_centered(self, cells: Iterable[Cell]) -> None:
        cells = list(cells)
        if not cells:
            return
        min_x = min(x for x, _ in cells)
        max_x = max(x for x, _ in cells)
        min_y = min(y for _, y in cells)
        max_y = max(y for _, y in cells)
        width = max_x - min_x + 1
        height = max_y - min_y + 1
        self.place(
            ((x - min_x, y - min_y) for x, y in cells),
            (self.width - width) // 2,
            (self.height - height) // 2,
        )

    def resize(self, width: int, height: int, keep: bool = True) -> None:
        """Change the universe size, optionally keeping and re-centring cells."""
        width, height = max(1, int(width)), max(1, int(height))
        if width == self.width and height == self.height:
            if not keep:
                self.clear()
            return
        if keep:
            dx = (width - self.width) // 2
            dy = (height - self.height) // 2
            moved = {(x + dx, y + dy): age for (x, y), age in self.age.items()}
            self.live = {(x, y) for (x, y) in moved if 0 <= x < width and 0 <= y < height}
            self.age = {cell: age for cell, age in moved.items() if cell in self.live}
        else:
            self.clear()
        self.width, self.height = width, height

    # -- evolution -------------------------------------------------------

    def step(self) -> int:
        """Advance one generation; returns the number of live cells."""
        width, height, torus = self.width, self.height, self.torus
        birth, survive = self.rule.birth, self.rule.survive
        counts: dict[Cell, int] = defaultdict(int)
        for x, y in self.live:
            for dx, dy in _NEIGHBOURS:
                nx, ny = x + dx, y + dy
                if torus:
                    nx %= width
                    ny %= height
                elif not (0 <= nx < width and 0 <= ny < height):
                    continue
                counts[(nx, ny)] += 1

        live = self.live
        new_live: set[Cell] = set()
        new_age: dict[Cell, int] = {}
        for cell, neighbours in counts.items():
            alive = cell in live
            if (neighbours in survive) if alive else (neighbours in birth):
                new_live.add(cell)
                new_age[cell] = self.age.get(cell, 0) + 1 if alive else 0

        self.live = new_live
        self.age = new_age
        self.generation += 1
        return len(new_live)

    # -- helpers ---------------------------------------------------------

    def bounding_box(self) -> tuple[int, int, int, int] | None:
        """Return ``(min_x, min_y, max_x, max_y)`` of the live cells."""
        if not self.live:
            return None
        xs = [x for x, _ in self.live]
        ys = [y for _, y in self.live]
        return min(xs), min(ys), max(xs), max(ys)

    def normalized_cells(self) -> list[Cell]:
        """Live cells translated so the bounding box starts at ``(0, 0)``."""
        box = self.bounding_box()
        if box is None:
            return []
        min_x, min_y, _, _ = box
        return sorted((x - min_x, y - min_y) for x, y in self.live)


def parse_rle(text: str) -> RLEPattern:
    """Parse a Run Length Encoded pattern (comments, header and body)."""
    comments: list[str] = []
    header_width = header_height = 0
    rule_text = "B3/S23"
    body_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            comments.append(line.lstrip("# ").strip())
            continue
        if not body_lines and _HEADER_RE.search(line):
            match = _HEADER_RE.search(line)
            header_width, header_height = int(match.group(1)), int(match.group(2))
            rule_match = _RULE_RE.search(line)
            if rule_match:
                rule_text = f"B{rule_match.group(1)}/S{rule_match.group(2)}"
            continue
        body_lines.append(line)

    body = "".join(body_lines)
    if "!" not in body:
        raise RLEError("RLE body is missing the terminating '!'")

    cells: list[Cell] = []
    x = y = 0
    count_digits = ""
    index = 0
    while index < len(body):
        char = body[index]
        index += 1
        if char.isdigit():
            count_digits += char
            continue
        if char.isspace():
            continue
        if char not in "bo$!":
            raise RLEError(f"unexpected character {char!r} in RLE body")
        count = int(count_digits) if count_digits else 1
        count_digits = ""
        if count <= 0:
            raise RLEError("RLE run length must be positive")
        if char == "b":
            x += count
        elif char == "o":
            for _ in range(count):
                cells.append((x, y))
                x += 1
        elif char == "$":
            y += count
            x = 0
        else:  # "!"
            break
        if x > MAX_DIMENSION or y > MAX_DIMENSION:
            raise RLEError("pattern is unreasonably large")

    if not cells:
        raise RLEError("RLE pattern contains no live cells")

    width = header_width or max(cx for cx, _ in cells) + 1
    height = header_height or max(cy for _, cy in cells) + 1
    return RLEPattern(tuple(cells), width, height, rule_text, tuple(comments))


def dump_rle(cells: Iterable[Cell], rule: str = "B3/S23", name: str | None = None) -> str:
    """Serialise cells to an RLE document (bounding box normalised)."""
    cells = sorted(set(cells))
    if not cells:
        raise RLEError("cannot encode an empty pattern")
    min_x = min(x for x, _ in cells)
    min_y = min(y for _, y in cells)
    max_x = max(x for x, _ in cells)
    max_y = max(y for _, y in cells)
    width, height = max_x - min_x + 1, max_y - min_y + 1
    alive = {(x - min_x, y - min_y) for x, y in cells}

    lines: list[str] = []
    if name:
        lines.append(f"#N {name}")
    lines.append(f"x = {width}, y = {height}, rule = {rule}")

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current_len
        if not current:
            return
        chunks.append("".join(current))
        current.clear()
        current_len = 0

    def emit(count: int, symbol: str) -> None:
        nonlocal current_len
        part = f"{count}{symbol}" if count > 1 else symbol
        if current and current_len + len(part) > 60:
            flush()
        current.append(part)
        current_len += len(part)

    for row in range(height):
        run_cell: int | None = None
        run = 0

        def flush_run() -> None:
            nonlocal run_cell, run
            if run_cell is not None and run:
                emit(run, "o" if run_cell else "b")
            run = 0

        for column in range(width):
            state = 1 if (column, row) in alive else 0
            if run_cell is None:
                run_cell = state
                run = 1
            elif state == run_cell:
                run += 1
            else:
                flush_run()
                run_cell = state
                run = 1
        flush_run()
        if row != height - 1:
            emit(1, "$")
    flush()
    lines.append("".join(chunks) + "!")
    return "\n".join(lines) + "\n"
