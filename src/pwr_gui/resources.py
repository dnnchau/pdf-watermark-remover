"""Paths to bundled GUI resources in source and PyInstaller builds."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """Resolve an asset from the repository or PyInstaller extraction folder."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    root = Path(frozen_root) if frozen_root else Path(__file__).resolve().parents[2]
    return root.joinpath(*parts)


def app_icon_path() -> Path:
    return resource_path("assets", "app-icon.png")

