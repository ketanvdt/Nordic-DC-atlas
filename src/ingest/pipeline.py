from __future__ import annotations

from pathlib import Path

import yaml

from src.common.settings import settings
from src.ingest.base import download_if_changed, record_source


def run_ingest(config_path: str = "config/layers.yaml") -> None:
    cfg = yaml.safe_load(Path(config_path).read_text(encoding="utf-8"))
    exclusions = cfg.get("exclusions", [])
    for layer in exclusions:
        key = layer["key"]
        url = layer.get("source_url")
        if not url or url in {"country_specific", "overpass", "sametinget_nve_paliskuntain", "copernicus_clc_osm", "copernicus_eu_dem"}:
            continue
        filename = f"{key}.bin"
        artifact = download_if_changed(key, url, filename)
        changed = record_source(artifact, metadata={"layer_type": "exclusion"})
        state = "updated" if changed else "unchanged"
        print(f"[{state}] {key} -> {artifact.local_path}")


if __name__ == "__main__":
    Path(settings.raw_dir).mkdir(parents=True, exist_ok=True)
    run_ingest()
