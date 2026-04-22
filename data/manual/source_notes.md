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

(no entries yet)
