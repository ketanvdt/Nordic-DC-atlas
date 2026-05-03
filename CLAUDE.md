# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Nordic Data Center Site Atlas (v1) — local-first internal GIS overlay tool for EcoDataCenter site selection across SE/NO/FI. Streamlit UI on top of PostGIS, with an H3-indexed cell model and weighted-overlay scoring exposed as SQL functions.

## Commands

All commands assume Docker is running. The `Makefile` is the source of truth (`PYTHON ?= python`):

- `make up` / `make down` / `make logs` — control the `postgis/postgis:16-3.4` container (`nordic_atlas_db`).
- `make install` — `pip install -r requirements.txt` (the actual deps live in `pyproject.toml`; `requirements.txt` is a one-line `-e .`).
- `make migrate` — runs every file in `sql/migrations/*.sql` in lexical order via `scripts/run_migrations.py`. Idempotent (uses `IF NOT EXISTS` / `ON CONFLICT`).
- `make seed-grid` — populates `grid_cells` with H3 res-8 cells covering coarse SE/NO/FI bbox polygons (`src/characterize/seed_h3_grid.py`).
- `make characterize` — runs `scripts/run_characterization.py`: bidding zones + zone profiles → DH tiers → placeholder soft features → exclusion layers from `data/processed/*.gpkg`.
- `make refresh-norm` — `REFRESH MATERIALIZED VIEW grid_cells_normalized;` (must be re-run after any column update for scoring to see new values).
- `make app` — `streamlit run src/app/Home.py`.
- `make test` / `make lint` — `pytest -q` and `python -m compileall src` (lint is compile-only; no ruff/mypy).
- `python -m src.characterize.exclusion_qa` — asserts total exclusion ratio falls within 0.30–0.50 (run after characterize).

Optional real-data ingestion (not wired into `make characterize`):
- `python scripts/fetch_osm_layers.py` — pulls Natura 2000, protected areas, airports, substations, transmission lines via Overpass into `data/processed/*.gpkg`.
- `python -m src.characterize.real_ingest` — replaces placeholder distances/exclusions for those layers using the fetched GPKGs.

Single-test invocation: `pytest tests/test_weight_normalization.py::test_weights_sum_to_one -q`.

## Architecture

**The data flow has one direction**: ingest → transform → seed grid → characterize (write columns into `grid_cells`) → refresh `grid_cells_normalized` → score via SQL function → Streamlit UI. The materialized view is the choke point — column updates without `make refresh-norm` will not appear in the UI.

**Scoring lives in SQL, not Python.** `sql/migrations/002_normalized_and_scoring.sql` defines:
- `grid_cells_normalized` — materialized view that min-max normalizes every soft feature into 0–1 with the correct sign (lower distance to substation = higher score, etc.). The `norm_surface_water` column has hand-coded piecewise logic (penalty < 500 m, sweet spot ~2.75 km, decay beyond) — do not replace with linear normalization without preserving the curve.
- `score_cells(weights JSONB, exclusions JSONB, bbox..., limit_n)` — applies grouped weights, returns NULL for any cell where an active exclusion flag is true.
- `top_candidate_cells(weights, exclusions, top_n)` — wraps `score_cells` with a 2M cap; UI uses this for the ranked list.

**Five weight buckets** (`src/score/service.py::DEFAULT_WEIGHTS` and the SQL must stay in sync): `power`, `heat_offtake`, `climate`, `connectivity`, `commercial`. The Python service normalizes negatives to 0 and rescales to sum 1 before passing JSONB to Postgres.

**Exclusions are 12 boolean columns** on `grid_cells` (`excl_natura2000`, `excl_protected`, ... `excl_sami_reindeer`). The UI exposes 11 toggles (`airport` covers both `excl_airport` and `excl_airport_ols`). Adding a new exclusion requires changes in **all** of: `001_core_schema.sql` (column), `002_normalized_and_scoring.sql` (view + `score_cells` CASE), `src/score/service.py::DEFAULT_EXCLUSIONS`, `src/characterize/exclusion_qa.py`, and the matching characterizer.

**Two parallel exclusion characterizers exist**:
- `src/characterize/exclusions.py` — config-driven from `config/layers.yaml`, loads `data/processed/{key}.gpkg`, uses `unary_union` + WKT (small layers only). Wired into `make characterize`.
- `src/characterize/real_ingest.py` — staging-table approach with server-side `ST_MakeValid` and GIST indexes. Used for large OSM layers (40k+ polygons) where `unary_union` blows memory. Adds `intersects` strategy (boolean overlap, fastest). Standalone — not in the make target.

When a layer outgrows `exclusions.py` move it to `real_ingest.py`'s `EXCLUSIONS` tuple rather than trying to scale the union approach.

**CRS conventions**: storage and indexing in EPSG:4326 (`grid_cells.geom_4326` with GIST index); area math and buffering in EPSG:3035 (Lambert Azimuthal Equal-Area, Europe); display in 4326 via PyDeck. The `assert_geometry_srid()` SQL function enforces this. `EPSG:3035` reprojection on a join side has no usable index — only do it for small source layers.

**OSM voltage parsing** (`real_ingest._parse_voltage_kv`): tags are free-text like `"132000"`, `"132 kV"`, `"400000;220000"`. Always parse client-side, not in SQL regex. Substations are split into 400 kV (300–10000 kV band) and 130 kV (100–299 kV band) via the voltage filter.

**Placeholder soft features** (`src/characterize/soft_features.py`): columns without a real source get `random()`-based values, but every assignment is wrapped in `COALESCE(col, expr)` so real values from `real_ingest`/`power_layers`/`dh_tiers` are preserved. When you wire up a new real source, **remove the column from `_PLACEHOLDER_COLUMN_EXPRS`** so future re-runs don't overwrite it after a non-COALESCE path is added later.

**Layer source registry** (`config/layers/*.yaml`, 27 files): authoritative metadata for each geospatial input. The researcher workflow is documented in `config/layers/README.md` — `_template.yaml` is the schema, `_index.yaml` drives priority order. CRS must be `EPSG:xxxx` (never `WGS84`); license must be a recognized ID or URL (never "open"). This registry is *currently aspirational* — most YAMLs are `pending_verification` and not yet consumed by ingest code.

**Manual-digitization layers** land in `data/manual/<layer_id>.geojson` with provenance in `data/manual/source_notes.md`. The list is maintained in `config/layers/README.md` (grid capacity heatmap, airport OLS, military zones, announced DC projects, DH tier table, municipal receptivity, subsea cable landings).

**The H3 extension is optional** in v1. Migration `001_core_schema.sql` tries `CREATE EXTENSION h3` and falls back silently to TEXT-encoded `h3_index` if not available — all Python uses the `h3` Python package (>=4.x: `h3.cell_to_latlng`, `h3.cell_to_boundary`, `h3.geo_to_cells`).

## Known gaps to preserve in UI

These warnings are tested (`tests/test_known_gap_copy.py`) and must remain visible: directional grid-capacity layer, manual coding for DH/municipal receptivity, incomplete fiber backbone, final shortlist requires DSO-queue + permit checks. Don't remove the "Known gaps" section from `src/app/Home.py` without updating the test.

## Performance notes (from `docs/runbook.md`)

- Keep `score_cells` viewport-bounded with bbox arguments in UI queries.
- Do not refresh `grid_cells_normalized` on slider movement — only after characterize.
- Use `top_candidate_cells` for ranking to avoid full-result scans.
- Keep GIST on `geom_4326` and unique index on `grid_cells_normalized.h3_index`.
