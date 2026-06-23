from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lab_radar.simple_yaml import load_yaml


@dataclass(frozen=True)
class LabRadarConfig:
    raw: dict[str, Any]
    path: Path

    @property
    def core_keywords(self) -> list[str]:
        return list(self.raw.get("interests", {}).get("core_keywords", []))

    @property
    def adjacent_keywords(self) -> list[str]:
        return list(self.raw.get("interests", {}).get("adjacent_keywords", []))

    @property
    def watched_authors(self) -> list[str]:
        return list(self.raw.get("interests", {}).get("watched_authors", []))

    def source(self, name: str) -> dict[str, Any]:
        return dict(self.raw.get("sources", {}).get(name, {}))

    def report_value(self, name: str, default: Any) -> Any:
        return self.raw.get("report", {}).get(name, default)


def load_config(path: str | Path = "config.yaml") -> LabRadarConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return LabRadarConfig(raw=load_yaml(config_path), path=config_path)
