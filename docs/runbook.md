# Runbook: Nordic Atlas v1

## Refresh cycle

1. `make up`
2. `make migrate`
3. `make ingest`              # download layers whose YAML has a single HTTP download_url
4. `make transform`           # stage data/raw/<layer>.gpkg into data/processed/
5. `make seed-grid`
6. `make seed-municipalities` # one-shot Nordic ADM2 seed (skip if already seeded)
7. `make characterize`        # power_layers, dh_tiers, soft_features (no-op), real_ingest (registry-driven)
8. `make refresh-norm`
9. `make app`

## Performance notes

- Keep `score_cells` viewport-bounded using bbox arguments in UI queries.
- Do not refresh `grid_cells_normalized` on slider movement.
- Use `top_candidate_cells` for ranking to avoid full result scans in UI.
- Keep GIST index on `geom_4326` and unique index on normalized `h3_index`.

## Data quality checks

- Run `python -m src.characterize.exclusion_qa` to enforce exclusion coverage band.
- Run CRS assertions: `SELECT * FROM assert_geometry_srid();`
- Ensure source freshness metadata in `data_sources` updates for changed checksums.

## Layer registry

All layer metadata lives in `config/layers/*.yaml`. The optional `runtime`
block on each YAML is read by `src.common.layer_registry.load_layers()` and
drives ingest / characterization. Adding a new layer means adding a YAML and
(if it has a code path) a `runtime` block — no Python changes required.

## Known-gap communication

- Score uses NULL (not random) for missing inputs; the per-cell coverage
  fraction is exposed in the UI top-50 table and cell inspector.
- Keep DH/fiber/manual-input quality warnings visible in UI.
- Keep final disclaimer: shortlist needs DSO queue and permitting checks.
