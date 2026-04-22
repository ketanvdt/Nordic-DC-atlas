from __future__ import annotations

from pathlib import Path
import shutil

import yaml

from src.common.settings import settings


def run_transform(config_path: str = "config/layers.yaml") -> None:
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    for layer in cfg.get("exclusions", []):
        key = layer["key"]
        raw_path = Path(settings.raw_dir) / f"{key}.gpkg"
        if not raw_path.exists():
            continue
        out_path = Path(settings.processed_dir) / f"{key}.gpkg"
        # Placeholder for full reprojection+clip transformations.
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw_path, out_path)
        print(f"[processed] {key} -> {out_path}")


if __name__ == "__main__":
    run_transform()
