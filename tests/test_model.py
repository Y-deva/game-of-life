"""Unit tests for the model, rules, RLE handling and the pattern library."""

from __future__ import annotations

import random
import unittest

from game_of_life.model import (
    PRESETS,
    LifeGrid,
    RLEError,
    Rule,
    RuleError,
    dump_rle,
    parse_rle,
)
from game_of_life.patterns import PATTERNS, get_pattern


def make(width: int = 20, height: int = 20, cells=()) -> LifeGrid:
    grid = LifeGrid(width, height, torus=True)
    grid.set_cells(cells, clear=True)
    return grid


def snapshot(grid: LifeGrid) -> frozenset[tuple[int, int]]:
    return frozenset(grid.live)


class RuleTests(unittest.TestCase):
    def test_parse_and_render(self) -> None:
        rule = Rule.parse("b36/s23")
        self.assertEqual(rule.birth, frozenset({3, 6}))
        self.assertEqual(rule.survive, frozenset({2, 3}))
        self.assertEqual(str(rule), "B36/S23")

    def test_presets(self) -> None:
        self.assertEqual(Rule(), PRESETS["Conway's Life (B3/S23)"])
        self.assertEqual(Rule.parse("B3/S23").name, "Conway's Life (B3/S23)")
        self.assertEqual(Rule.parse("B36/S23").name, "HighLife (B36/S23)")
        self.assertEqual(Rule.parse("B1/S1").name, "Custom rule")

    def test_rejects_malformed_text(self) -> None:
        for text in ("", "S23", "B9/S23", "B3-S23", "life"):
            with self.subTest(text=text):
                with self.assertRaises(RuleError):
                    Rule.parse(text)

    def test_custom_rule_drives_the_step(self) -> None:
        grid = make(5, 5)
        grid.set_rule(Rule.parse("B8/S8"))
        for y in range(1, 4):
            for x in range(1, 4):
                grid.set_cell(x, y)
        grid.step()
        self.assertEqual(grid.live, {(2, 2)})
        grid.step()
        self.assertEqual(grid.live, set())


class StepTests(unittest.TestCase):
    def test_blinker_period_two(self) -> None:
        grid = make(10, 10, ((4, 5), (5, 5), (6, 5)))
        start = snapshot(grid)
        grid.step()
        self.assertEqual(snapshot(grid), frozenset({(5, 4), (5, 5), (5, 6)}))
        grid.step()
        self.assertEqual(snapshot(grid), start)

    def test_block_is_stable(self) -> None:
        grid = make(10, 10, ((4, 4), (5, 4), (4, 5), (5, 5)))
        start = snapshot(grid)
        for _ in range(5):
            grid.step()
        self.assertEqual(snapshot(grid), start)

    def test_tub_is_stable(self) -> None:
        grid = make(10, 10, ((4, 5), (5, 4), (6, 5), (5, 6)))
        start = snapshot(grid)
        for _ in range(4):
            grid.step()
        self.assertEqual(snapshot(grid), start)

    def test_glider_moves_one_cell_diagonally_in_four_steps(self) -> None:
        glider = ((1, 0), (2, 1), (0, 2), (1, 2), (2, 2))
        grid = make(20, 20, glider)
        start = snapshot(grid)
        for _ in range(4):
            grid.step()
        self.assertEqual(snapshot(grid), {(x + 1, y + 1) for x, y in start})

    def test_torus_wraps_around_the_edges(self) -> None:
        grid = make(10, 10, ((0, 5), (1, 5), (2, 5)))
        grid.step()
        self.assertEqual(snapshot(grid), frozenset({(1, 4), (1, 5), (1, 6)}))

    def test_non_torus_clips_cells_at_the_border(self) -> None:
        grid = make(10, 10, ((9, 0), (9, 1), (9, 2)))
        grid.torus = False
        grid.step()
        self.assertNotIn((10, 1), grid.live)

    def test_population_and_generation_counters(self) -> None:
        grid = make(10, 10, ((4, 5), (5, 5), (6, 5)))
        self.assertEqual(len(grid.live), 3)
        self.assertEqual(grid.step(), 3)
        self.assertEqual(grid.generation, 1)
        self.assertEqual(grid.step(), 3)
        self.assertEqual(grid.generation, 2)

    def test_pulsar_has_period_three(self) -> None:
        grid = make(40, 40)
        grid.place_centered(get_pattern("Pulsar").parse().cells)
        start = snapshot(grid)
        for _ in range(3):
            grid.step()
        self.assertEqual(snapshot(grid), start)

    def test_pentadecathlon_has_period_fifteen(self) -> None:
        grid = make(40, 40)
        grid.place_centered(get_pattern("Pentadecathlon").parse().cells)
        start = snapshot(grid)
        for _ in range(15):
            grid.step()
        self.assertEqual(snapshot(grid), start)

    def test_gosper_gun_grows(self) -> None:
        grid = make(60, 60)
        grid.place_centered(get_pattern("Gosper glider gun").parse().cells)
        start = len(grid.live)
        for _ in range(60):
            grid.step()
        self.assertGreater(len(grid.live), start)


class EditingTests(unittest.TestCase):
    def test_toggle_and_set_cell(self) -> None:
        grid = make()
        self.assertTrue(grid.set_cell(1, 1))
        self.assertIn((1, 1), grid.live)
        self.assertTrue(grid.set_cell(1, 1, alive=False))
        self.assertNotIn((1, 1), grid.live)
        grid.toggle_cell(2, 2)
        self.assertIn((2, 2), grid.live)
        grid.toggle_cell(2, 2)
        self.assertNotIn((2, 2), grid.live)

    def test_resize_keeps_and_recentres_cells(self) -> None:
        grid = make(20, 20, ((9, 9),))
        grid.resize(10, 10, keep=True)
        self.assertEqual(grid.live, {(4, 4)})
        grid.resize(10, 10, keep=False)
        self.assertEqual(grid.live, set())

    def test_normalized_cells_are_translated(self) -> None:
        grid = make(20, 20, ((5, 7), (6, 7)))
        self.assertEqual(grid.bounding_box(), (5, 7, 6, 7))
        self.assertEqual(sorted(grid.normalized_cells()), [(0, 0), (1, 0)])

    def test_randomize_is_reproducible_with_seed(self) -> None:
        a = make(30, 30)
        b = make(30, 30)
        a.randomize(0.3, random.Random(42))
        b.randomize(0.3, random.Random(42))
        self.assertEqual(a.live, b.live)
        self.assertTrue(0 < len(a.live) < 900)


class RLETests(unittest.TestCase):
    def test_parse_glider(self) -> None:
        pattern = parse_rle("x = 3, y = 3, rule = B3/S23\nbob$2bo$3o!")
        self.assertEqual(len(pattern.cells), 5)
        self.assertEqual(pattern.width, 3)
        self.assertEqual(pattern.height, 3)
        self.assertEqual(pattern.rule, "B3/S23")
        self.assertEqual(pattern.population, 5)

    def test_dump_roundtrip(self) -> None:
        cells = {(x, y) for x in range(7) for y in range(5) if (x * 3 + y * 5) % 4 == 0}
        text = dump_rle(cells, name="test")
        parsed = parse_rle(text)
        min_x = min(x for x, _ in cells)
        min_y = min(y for _, y in cells)
        normalized = {(x - min_x, y - min_y) for x, y in cells}
        self.assertEqual(set(parsed.cells), normalized)

    def test_dump_long_line_wraps_at_sixty_characters(self) -> None:
        cells = {(x, 0) for x in range(200)}
        text = dump_rle(cells)
        body = [line for line in text.splitlines() if not line.startswith("#")]
        self.assertTrue(all(len(line) <= 60 for line in body))
        self.assertEqual(set(parse_rle(text).cells), cells)

    def test_parse_rejects_garbage(self) -> None:
        with self.assertRaises(RLEError):
            parse_rle("x = 3, y = 3\nb?o!")
        with self.assertRaises(RLEError):
            parse_rle("not a header")

    def test_all_library_patterns_parse(self) -> None:
        self.assertGreaterEqual(len(PATTERNS), 10)
        for pattern in PATTERNS:
            with self.subTest(pattern=pattern.name):
                parsed = pattern.parse()
                self.assertTrue(parsed.cells)
                self.assertGreater(parsed.population, 0)


if __name__ == "__main__":
    unittest.main()
