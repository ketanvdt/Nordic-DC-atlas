-- Phase 2.3: provenance for grid_capacity_heatmap.
--
-- Each cell's value comes from one of two paths:
--   - "bidding_zone": the lat/lon-rule baseline applied by power_layers.py,
--                     pulled from power_zone_profiles.capacity_score.
--   - "manual_digitization": overridden by a polygon in
--                     data/manual/grid_capacity_heatmap.geojson via the
--                     overlay_tier runtime path.
--
-- The freshness panel and cell inspector read this column so the UI can
-- show where the value actually came from.

ALTER TABLE grid_cells
  ADD COLUMN IF NOT EXISTS grid_capacity_source TEXT;

-- The bidding-zone baseline always runs before the manual overlay (see
-- scripts/run_characterization.py order). Default any not-yet-set rows
-- to "bidding_zone" so cells outside the manual polygons report the
-- baseline source rather than NULL.
UPDATE grid_cells
SET grid_capacity_source = 'bidding_zone'
WHERE grid_capacity_heatmap IS NOT NULL
  AND grid_capacity_source IS NULL;
