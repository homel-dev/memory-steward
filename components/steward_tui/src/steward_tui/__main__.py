# components/steward_tui/src/steward_tui/__main__.py
"""Entrypoint: `python -m steward_tui` or the `steward-tui` console script."""
from steward_tui.app import StewardTUI


def main() -> None:
    StewardTUI().run()


if __name__ == "__main__":
    main()
