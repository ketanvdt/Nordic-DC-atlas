"""Fetch real geospatial layers via OSM Overpass and write them as GPKGs.

Feeds `data/processed/` so that `src/characterize/exclusions.py` and the
real-feature characterization see actual polygons and points — not the
placeholder random values shipped in `src/characterize/soft_features.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

# When run as `python scripts/fetch_osm_layers.py` the package root isn't on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.ingest.overpass import build_queries, fetch_and_save


def main() -> None:
    out_dir = Path("data/processed")
    for spec in build_queries():
        try:
            fetch_and_save(spec, out_dir)
        except Exception as exc:
            print(f"[error] {spec.key}: {exc!r}")


if __name__ == "__main__":
    main()
