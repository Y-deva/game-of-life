"""Allow ``python -m game_of_life`` to launch the application."""

from .window import run


def main() -> int:
    """Entry point for the ``game-of-life`` console script."""
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
