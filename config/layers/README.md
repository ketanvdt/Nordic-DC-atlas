# Nordic Atlas v1 — Layer Source Registry

Machine-readable registry of every geospatial layer the atlas ingests. One YAML per layer, consumed by `src/ingest/` loaders. Built from the research plan at `C:\Users\ketan\.claude\plans\what-all-data-sources-noble-nova.md`.

## Workflow for researchers

1. Pick the next `status: pending_verification` layer from `_index.yaml`.
2. Open its `<layer_id>.yaml`. Every file is pre-populated with a best-known starting-point — your job is to verify, not rediscover.
3. Open the `authority.url` and `dataset.landing_url`. Confirm the dataset still exists and the download link resolves.
4. Download a small sample (first feature or bbox-clipped to Stockholm for test). Inspect in QGIS.
5. Fill every `unknown` field. Any field that stays `unknown` needs an explicit reason in `quality.known_caveats`.
6. Load the sample into the dev Postgres via a throwaway ingest. Confirm the pipeline parses the format and CRS.
7. Set `quality.last_verified` to today and `quality.verified_by` to your name.
8. Set `status: verified`.
9. Open a PR. A second researcher reviews CRS and license fields specifically before merge.

## Status values

- `pending_verification` — starter data is in the file; nothing has been downloaded yet.
- `verified` — someone downloaded, inspected, and confirmed all fields; second reviewer approved.
- `blocked` — cannot be sourced via free/open channels. Include reason in `known_caveats`.
- `deferred` — intentionally skipped for v1 (e.g., `land_cost`). Include reason.

## Field rules

- `native_crs` must be an explicit `EPSG:xxxx` code. Never `WGS84` or `RD New` by name — EPSG only.
- `license` must be either a recognized license ID (`CC BY 4.0`, `CC0`, `ODbL`) or a direct URL to the license text. Never just "open" or "free".
- `update_cadence` is one of: `continuous`, `monthly`, `quarterly`, `annual`, `biennial`, `ad_hoc`, `frozen`.
- `exclusion_semantics` is the rule applied to turn this layer into an H3 cell mask: `centroid` (cell is excluded if its centroid is inside any source polygon), `overlap_gte_Npct` (cell is excluded if ≥N% of its area is inside), or `buffer(N)` (apply N-meter buffer to source features first). Null for feature layers.
- `score_sign` is `+1` if higher values improve the score, `-1` if worse, `piecewise` if the relationship is non-monotonic (document the curve in `known_caveats`).

## Paired review checklist

Reviewer of any YAML before `verified` must confirm:

- [ ] Download URL resolves and returns a file (not a 403/login redirect).
- [ ] `native_crs` matches what the file actually declares (open in QGIS → Layer Properties).
- [ ] License is either CC-family, ODbL, or a named national open-data license — not "contact us".
- [ ] Attribution string (if `attribution_required: true`) is added to `src/app/about.py` UI string bundle.
- [ ] The Nordic atlas plan's W-tier for this layer still matches the `priority` field.

## Manual-digitization layers

A subset of layers must be manually traced from PDFs or interactive viewers:

- `grid_capacity_heatmap` (Svk / Statnett / Fingrid regional capacity maps)
- `airport_ols` (AIP obstacle data, fallback: 15 km buffer around commercial airports)
- `military_zones` (public restriction zones only)
- `announced_dc_projects` (news-sourced list)
- `dh_offtake_tier` (per-municipality tier table)
- `municipal_receptivity` (per-municipality 3-tier tag)
- `subsea_cable_landings` (geocode landing station points)

Outputs land in `data/manual/<layer_id>.geojson` (or `.csv`). Provenance lives in `data/manual/source_notes.md`.

## Related files

- `_template.yaml` — copy-paste template for new layers.
- `_index.yaml` — priority-ordered list driving ingest order.
- `../../data/manual/` — manually digitized GeoJSONs and their provenance notes.
