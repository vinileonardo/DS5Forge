"""PyInstaller entry point for the headless DS5Forge core sidecar."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from dualsense_companion.app import main


def sidecar_argv(argv: Sequence[str]) -> list[str]:
    """Force headless mode while preserving shell-supplied bind arguments."""

    return ["--headless", *(arg for arg in argv if arg != "--headless")]


if __name__ == "__main__":
    main(sidecar_argv(sys.argv[1:]))
