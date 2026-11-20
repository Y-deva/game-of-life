"""Built-in pattern library (RLE encoded)."""

from __future__ import annotations

from .model import Pattern

PATTERNS: tuple[Pattern, ...] = (
    Pattern(
        "Glider",
        "x = 3, y = 3, rule = B3/S23\nbob$2bo$3o!",
        "The classic spaceship: it travels one cell diagonally every four generations.",
    ),
    Pattern(
        "Blinker",
        "x = 3, y = 3, rule = B3/S23\n3o!",
        "The simplest oscillator, with a period of two.",
    ),
    Pattern(
        "Toad",
        "x = 4, y = 2, rule = B3/S23\nb3o$3o!",
        "A period-two oscillator made of two rows of three cells.",
    ),
    Pattern(
        "Block",
        "x = 2, y = 2, rule = B3/S23\n2o$2o!",
        "A still life: four cells that never change.",
    ),
    Pattern(
        "Tub",
        "x = 3, y = 3, rule = B3/S23\nbo$obo$bo!",
        "A small still life with a hollow centre.",
    ),
    Pattern(
        "Beacon",
        "x = 4, y = 4, rule = B3/S23\n2o2b$2o2b$2b2o$2b2o!",
        "A period-two oscillator built from two blocks.",
    ),
    Pattern(
        "Pulsar",
        "x = 13, y = 13, rule = B3/S23\n"
        "2b3o3b3o2b$13b$o4bobo4bo$o4bobo4bo$o4bobo4bo$"
        "2b3o3b3o2b$13b$2b3o3b3o2b$o4bobo4bo$o4bobo4bo$"
        "o4bobo4bo$13b$2b3o3b3o2b!",
        "A large, symmetric period-three oscillator.",
    ),
    Pattern(
        "Pentadecathlon",
        "x = 10, y = 3, rule = B3/S23\n2bo4bo2b$2ob4ob2o$2bo4bo2b!",
        "An oscillator with a period of fifteen.",
    ),
    Pattern(
        "Lightweight spaceship",
        "x = 5, y = 4, rule = B3/S23\nbo2bo$o4b$o3bo$4o!",
        "A small spaceship that travels horizontally at c/2.",
    ),
    Pattern(
        "Acorn",
        "x = 7, y = 3, rule = B3/S23\nbo5b$3bo3b$2o2b3o!",
        "A small seed that keeps evolving for thousands of generations.",
    ),
    Pattern(
        "R-pentomino",
        "x = 3, y = 3, rule = B3/S23\nb2o$2o$bo!",
        "A famous five-cell seed with a long, chaotic history.",
    ),
    Pattern(
        "Gosper glider gun",
        "x = 36, y = 9, rule = B3/S23\n"
        "24bo11b$22bobo11b$12b2o6b2o12b2o$11bo3bo4b2o12b2o$"
        "2o8bo5bo3b2o14b$2o8bo3bob2o4bobo11b$10bo5bo7bo11b$"
        "11bo3bo20b$12b2o!",
        "The first known gun: it fires a glider every thirty generations.",
    ),
    Pattern(
        "Diehard",
        "x = 8, y = 3, rule = B3/S23\n6bo$2o$bo3b3o!",
        "A seven-cell pattern that disappears after 130 generations.",
    ),
)


PATTERNS_BY_NAME: dict[str, Pattern] = {pattern.name: pattern for pattern in PATTERNS}


def get_pattern(name: str) -> Pattern:
    """Return a library pattern by name, raising ``KeyError`` when unknown."""
    return PATTERNS_BY_NAME[name]
