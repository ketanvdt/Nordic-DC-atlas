# Manual Data Provenance Notes

Every manually-digitized / manually-curated artifact in this directory must have an entry here documenting:
- What was produced
- When (date)
- Who (researcher)
- Source URL(s) used
- Digitization method / decisions
- Known approximations or confidence level

## Layers that land here (from config/layers/ manual-flagged YAMLs)

| file | layer_id | format |
|---|---|---|
| `grid_capacity_heatmap.geojson` | `grid_capacity_heatmap` | GeoJSON, polygons with `capacity_tier` 0–3 |
| `airport_ols.geojson` | `airport_ols` | GeoJSON, buffered airport polygons (v1 pragmatic) |
| `military_zones.geojson` | `military_zones` | GeoJSON — only if public data found |
| `announced_dc_projects.geojson` | `announced_dc_projects` | GeoJSON points |
| `subsea_cable_landings.geojson` | `subsea_cable_landings` | GeoJSON points |
| `dh_offtake_tier.csv` | `dh_offtake_tier` | CSV keyed by municipality code |
| `municipal_receptivity.csv` | `municipal_receptivity` | CSV keyed by municipality code |

## Provenance entries

(Researchers append an entry below per artifact produced. Template:)

```
### <filename> — <YYYY-MM-DD> — <researcher name>

Source(s):
- <URL or citation>

Method:
- <brief description of how the data was produced>

Confidence:
- high | medium | low

Known caveats:
- <any approximations, limitations>

Next refresh:
- <YYYY-MM-DD or "on publication of newer source">
```

---

### grid_capacity_heatmap.geojson — 2026-05-09 — claude-on-branch (v0 starter)

Source(s):
- `data/raw/svk_natutveckling_nup_2026-2035.pdf` (Svenska kraftnät, NUP 2026–2035 — executive summary on regional capacity deficits, north-south corridor)
- `data/raw/svenska-kraftnats-investeringspaket-nordsyd.pdf` (Svk north-south investment package — confirms SE3/SE4 deficit framing)
- `data/raw/ellevios-natutvecklingsplan-2025-2034.pdf` (Ellevio DSO plan — Mälardalen reinforcement priorities)
- `data/raw/vattenfall-eldistributions-natutvecklingsplan-2025-2034.pdf` (Vattenfall DSO plan — Stockholm region capacity overview)
- Live capacity portal cross-reference: <https://www.svk.se/utveckling-av-kraftsystemet/nats-och-systemutveckling/kapacitetsbrister/>

Method:
- Sweden-only v0 digitization at the bidding-zone level, with one finer
  Stockholm/Mälardalen sub-polygon to encode the well-known SE3 hotspot.
  Each polygon is a hand-drawn lat/lon rectangle (NOT a traced TSO outline)
  reflecting the SE bidding-zone latitudes used in `power_layers.py`.
- Capacity tiers (0–3) follow the YAML scale in
  `config/layers/grid_capacity_heatmap.yaml`:
  3 = green/ample, 2 = yellow/limited, 1 = orange/constrained, 0 = red/very-constrained.
- The overlay logic (`apply_overlay_tier` in `src/characterize/real_ingest.py`)
  uses `MIN(capacity_tier)` per cell, so the SE3-Stockholm tier-0 polygon
  correctly overrides the surrounding SE3 tier-1 polygon for cells inside
  Mälardalen.

Tiers chosen:
- SE1 → tier 3 (Norrbotten net-export)
- SE2 → tier 3 (Västerbotten/Jämtland net-export)
- SE3 (general) → tier 1 (net-import; deficit zone driving Svk investment)
- SE3 Stockholm/Mälardalen → tier 0 (long-acknowledged hotspot)
- SE4 → tier 0 (largest SE net-import deficit)

Confidence:
- low (v0). Polygons are rectangles, not traced TSO outlines. Sufficient
  to exercise the wiring end-to-end and produce realistic cell-level
  rankings; not adequate for site-level decisions.

Known caveats:
- NO and FI are not yet covered. Cells in NO/FI fall back to the
  bidding-zone baseline from `power_zone_profiles` — see
  `src/characterize/power_layers.py:apply_zone_profiles`.
- Localized constraints (e.g. Sundsvall/Östersund corridor inside SE2,
  individual SE3 substations) are not yet encoded.
- Tier 2 (yellow/limited) is not used in v0 — researchers will subdivide
  the SE3 surround as more granular Svk publications are traced.
- "valid_from" is set to 2026-01-01 (start of the NUP plan window); the
  source PDFs are dated 2025–2026.

Next refresh:
- Land NO and FI as separate features in the same GeoJSON (target sprint).
- Replace SE rectangles with traced sub-region polygons from
  <https://www.svk.se/.../kapacitetsbrister/> when the next Svk
  capacity-map publication lands.
