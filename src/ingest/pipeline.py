"""Download raw inputs for layers whose `dataset.download_url` is a single
resolvable HTTP URL.

OSM-based layers (Overpass) and per-country sources that aren't a single URL
are skipped here; the layer's YAML caveats document the manual download path
and the file lands under data/raw/ via the researcher workflow.
"""
from __future__ import annotations

from pathlib import Path

from src.common.layer_registry import load_layers
from src.common.settings import settings
from src.ingest.base import download_if_changed, record_source


_SKIP_VALUES = {"unknown", None, "", "country_specific"}


def run_ingest() -> None:
    Path(settings.raw_dir).mkdir(parents=True, exist_ok=True)
    for spec in load_layers().values():
        dataset = spec.raw.get("dataset", {}) or {}
        url = dataset.get("download_url")
        if url in _SKIP_VALUES or not isinstance(url, str) or not url.startswith(("http://", "https://")):
            continue
        # Multi-URL blocks (per-country) come through as multi-line strings; skip too.
        if "\n" in url:
            continue
        suffix = (dataset.get("format") or "bin").lower()
        out_name = f"{spec.layer_id}.{suffix}"
        artifact = download_if_changed(spec.layer_id, url, out_name)
        changed = record_source(
            artifact,
            license_name=str(dataset.get("license", "unknown")),
            metadata={"layer_kind": spec.category, "priority": spec.priority},
        )
        state = "updated" if changed else "unchanged"
        print(f"[{state}] {spec.layer_id} -> {artifact.local_path}")


if __name__ == "__main__":
    run_ingest()
