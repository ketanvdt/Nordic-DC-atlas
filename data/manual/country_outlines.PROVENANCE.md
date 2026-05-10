# country_outlines.geojson — provenance

**Purpose**: real country outlines for `src/characterize/seed_h3_grid.py`.
Replaces the bbox-rectangle fallback that produced H3 cells over the
Norwegian Sea, the Bothnian Bay, and parts of foreign countries.

**Source**: Natural Earth 1:50m Cultural Vectors, "Admin 0 - Countries"
(public domain). Mirrored on GitHub by
[`nvkelso/natural-earth-vector`](https://github.com/nvkelso/natural-earth-vector).

**License**: public domain (Natural Earth is explicit on this).

**Build**: `python scripts/build_country_outlines.py`. The script:

1. Pulls `geojson/ne_50m_admin_0_countries.geojson` from the GitHub raw
   mirror (the upstream `naciscdn.org` host is firewalled in some
   sandbox environments; the GitHub mirror is the de-facto canonical
   copy).
2. Filters to SE / NO / FI by `ADM0_A3`. We do **not** filter by
   `ISO_A2` because Natural Earth's `ISO_A2` for Norway is `-99` (the
   dispute-resolution sentinel for territories with contested codes).
   `ADM0_A3` is the only stable identifier across all three.
3. Clips each MultiPolygon to a Nordic study bbox of 4-32 °E,
   55-72 °N. This drops Svalbard / Jan Mayen / Bouvet Island from
   Norway (out of scope for v1 siting; would otherwise produce H3
   cells in the Arctic and the South Atlantic). It is a no-op on
   Sweden and Finland.
4. Simplifies to ~0.01 degree tolerance (~1 km), which is well below
   H3 res-8 cell size (~0.74 km²) and shrinks the vendored file
   from ~3 MB to ~170 KB.

**When to refresh**: only if Natural Earth releases a corrected outline
or you change the study bbox. Re-running `build_country_outlines.py`
overwrites the file in place; commit the diff.

**Schema**:

```
FeatureCollection
  features[]
    type: "Feature"
    properties:
      ISO_A2: "SE" | "NO" | "FI"   # used as grid_cells.country
      name:   "Sweden" | "Norway" | "Finland"
    geometry: Polygon | MultiPolygon (EPSG:4326)
```
