"""Conway's Game of Life — a PyQt6 playground.

Run the application with ``python -m game_of_life``.
"""

from .model import (
    LIFE,
    PRESETS,
    LifeGrid,
    Pattern,
    RLEError,
    RLEPattern,
    Rule,
    RuleError,
    dump_rle,
    parse_rle,
)
from .patterns import PATTERNS, PATTERNS_BY_NAME, get_pattern

__version__ = "2.0.0"
__all__ = [
    "LIFE",
    "PRESETS",
    "LifeGrid",
    "Pattern",
    "RLEError",
    "RLEPattern",
    "Rule",
    "RuleError",
    "dump_rle",
    "parse_rle",
    "PATTERNS",
    "PATTERNS_BY_NAME",
    "get_pattern",
]
