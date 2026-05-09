"""Idempotent ensure-columns step for grid_cells.

Earlier versions of this module filled six columns with `random()` so the
score path produced visible output before real ingest existed. That noise
masked the actual coverage problem and is removed: missing values stay
NULL, the materialized view skips them, and the scoring function reports
a per-cell coverage fraction so the UI can show how grounded each ranking is.

This module is now a no-op safety net — the columns it would create are
already declared in migration 001. It exists so `make characterize` can
keep its pre-real-ingest call site without changing shape.
"""
from __future__ import annotations


def populate_placeholder_soft_features() -> None:
    """No-op kept for call-site stability.

    All grid_cells columns are created in migration 001. There is no longer
    any random() fallback — see freshness_panel for missing-data semantics.
    """
    print("soft_features: no random fill (Phase 1.2). Columns stay NULL until real ingest.")


if __name__ == "__main__":
    populate_placeholder_soft_features()
