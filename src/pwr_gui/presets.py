"""Persistent, local-only selection presets."""

from __future__ import annotations

import json
import os
from pathlib import Path


def default_preset_path() -> Path:
    base = Path(os.environ.get("APPDATA") or (Path.home() / ".config"))
    return base / "PDF Watermark Remover" / "presets.json"


class PresetStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_preset_path()

    def _read(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def names(self) -> list[str]:
        return sorted(self._read(), key=str.casefold)

    def load(self, name: str) -> dict | None:
        value = self._read().get(name)
        return value if isinstance(value, dict) else None

    def save(self, name: str, payload: dict) -> None:
        clean_name = " ".join(name.split()).strip()
        if not clean_name:
            raise ValueError("Tên preset không được để trống.")
        presets = self._read()
        presets[clean_name] = payload
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(presets, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temp, self.path)
