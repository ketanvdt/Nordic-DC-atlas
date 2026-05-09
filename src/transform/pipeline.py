"""Stage downloaded raw inputs into `data/processed/` for each layer with a
runtime block that points at a `data/processed/*.gpkg` source.

v1 transform is a copy from data/raw/<layer_id>.gpkg to the runtime path —
adequate when the source is already 4326 GPKG. For sources that need
reprojection or clipping, use `src.transform.geometry.reproject_and_clip`
explicitly per layer (a follow-up will register that step in the registry
itself).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from src.common.layer_registry import load_layers
from src.common.settings import settings


def run_transform() -> None:
    raw_dir = Path(settings.raw_dir)
    for spec in load_layers().values():
        # Each runtime kind exposes a `source` path; collect it uniformly.
        source = (
            (spec.exclusion_runtime and spec.exclusion_runtime.source)
            or (spec.distance_runtime and spec.distance_runtime.source)
            or (spec.overlay_tier_runtime and spec.overlay_tier_runtime.source)
        )
        if not source:
            continue
        out_path = Path(source)
        if not out_path.parts or out_path.parts[0] != "data" or out_path.parts[1] != "processed":
            # overlay_tier sources live under data/manual/; researchers manage them directly.
            continue
        raw_path = raw_dir / out_path.name
        if not raw_path.exists():
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw_path, out_path)
        print(f"[processed] {spec.layer_id} -> {out_path}")


if __name__ == "__main__":
    run_transform()
