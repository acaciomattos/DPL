from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path
    runtime_root: Path
    studies_root: Path


def get_settings() -> Settings:
    project_root = Path(__file__).resolve().parents[1]
    runtime_root = project_root / "runtime"
    studies_root = runtime_root / "studies"
    return Settings(
        project_root=project_root,
        runtime_root=runtime_root,
        studies_root=studies_root,
    )

