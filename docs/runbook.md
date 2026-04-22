# Runbook: Nordic Atlas v1

## Refresh cycle

1. `make up`
2. `make migrate`
3. `python -m src.ingest.pipeline`
4. `python -m src.transform.pipeline`
5. `make seed-grid`
6. `make characterize`
7. `make refresh-norm`
8. `make app`

## Performance notes

- Keep `score_cells` viewport-bounded using bbox arguments in UI queries.
- Do not refresh `grid_cells_normalized` on slider movement.
- Use `top_candidate_cells` for ranking to avoid full result scans in UI.
- Keep GIST index on `geom_4326` and unique index on normalized `h3_index`.

## Data quality checks

- Run `python -m src.characterize.exclusion_qa` to enforce exclusion coverage band.
- Run CRS assertions: `SELECT * FROM assert_geometry_srid();`
- Ensure source freshness metadata in `data_sources` updates for changed checksums.

## Known-gap communication

- Keep directional-grid-capacity warning visible in UI.
- Keep DH/fiber/manual-input quality warnings visible in UI.
- Keep final disclaimer: shortlist needs DSO queue and permitting checks.
