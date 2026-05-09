-- Phase 1.2: rewrite the normalized view so cells with NULL inputs stay NULL
-- (rather than collapsing to 0 via COALESCE). The score function in 008
-- consumes these NULLs and skips them per bucket; coverage is reported back.

DROP MATERIALIZED VIEW IF EXISTS grid_cells_normalized;

CREATE MATERIALIZED VIEW grid_cells_normalized AS
WITH bounds AS (
  SELECT
    MIN(dist_substation_400kv_m) FILTER (WHERE dist_substation_400kv_m IS NOT NULL) AS min_sub400,
    MAX(dist_substation_400kv_m) FILTER (WHERE dist_substation_400kv_m IS NOT NULL) AS max_sub400,
    MIN(dist_substation_130kv_m) FILTER (WHERE dist_substation_130kv_m IS NOT NULL) AS min_sub130,
    MAX(dist_substation_130kv_m) FILTER (WHERE dist_substation_130kv_m IS NOT NULL) AS max_sub130,
    MIN(dist_transmission_line_m) FILTER (WHERE dist_transmission_line_m IS NOT NULL) AS min_tx,
    MAX(dist_transmission_line_m) FILTER (WHERE dist_transmission_line_m IS NOT NULL) AS max_tx,
    MIN(bidding_zone_price_3y) FILTER (WHERE bidding_zone_price_3y IS NOT NULL) AS min_price,
    MAX(bidding_zone_price_3y) FILTER (WHERE bidding_zone_price_3y IS NOT NULL) AS max_price,
    MIN(grid_capacity_heatmap) FILTER (WHERE grid_capacity_heatmap IS NOT NULL) AS min_capacity,
    MAX(grid_capacity_heatmap) FILTER (WHERE grid_capacity_heatmap IS NOT NULL) AS max_capacity,
    MIN(annual_mean_temp_c) FILTER (WHERE annual_mean_temp_c IS NOT NULL) AS min_temp,
    MAX(annual_mean_temp_c) FILTER (WHERE annual_mean_temp_c IS NOT NULL) AS max_temp,
    MIN(dist_fiber_m) FILTER (WHERE dist_fiber_m IS NOT NULL) AS min_fiber,
    MAX(dist_fiber_m) FILTER (WHERE dist_fiber_m IS NOT NULL) AS max_fiber,
    MIN(dist_surface_water_m) FILTER (WHERE dist_surface_water_m IS NOT NULL) AS min_water,
    MAX(dist_surface_water_m) FILTER (WHERE dist_surface_water_m IS NOT NULL) AS max_water,
    MIN(land_cost_proxy_eur_m2) FILTER (WHERE land_cost_proxy_eur_m2 IS NOT NULL) AS min_land,
    MAX(land_cost_proxy_eur_m2) FILTER (WHERE land_cost_proxy_eur_m2 IS NOT NULL) AS max_land,
    MIN(skilled_workforce_density) FILTER (WHERE skilled_workforce_density IS NOT NULL) AS min_workforce,
    MAX(skilled_workforce_density) FILTER (WHERE skilled_workforce_density IS NOT NULL) AS max_workforce
  FROM grid_cells
)
SELECT
  c.h3_index,
  c.country,
  c.bidding_zone,
  c.geom_4326,
  CASE WHEN c.dist_substation_400kv_m IS NULL THEN NULL
       ELSE 1 - (c.dist_substation_400kv_m - b.min_sub400) / NULLIF(b.max_sub400 - b.min_sub400, 0) END AS norm_substation_400kv,
  CASE WHEN c.dist_substation_130kv_m IS NULL THEN NULL
       ELSE 1 - (c.dist_substation_130kv_m - b.min_sub130) / NULLIF(b.max_sub130 - b.min_sub130, 0) END AS norm_substation_130kv,
  CASE WHEN c.dist_transmission_line_m IS NULL THEN NULL
       ELSE 1 - (c.dist_transmission_line_m - b.min_tx) / NULLIF(b.max_tx - b.min_tx, 0) END AS norm_transmission_line,
  CASE WHEN c.bidding_zone_price_3y IS NULL THEN NULL
       ELSE 1 - (c.bidding_zone_price_3y - b.min_price) / NULLIF(b.max_price - b.min_price, 0) END AS norm_bidding_zone,
  CASE WHEN c.grid_capacity_heatmap IS NULL THEN NULL
       ELSE (c.grid_capacity_heatmap - b.min_capacity) / NULLIF(b.max_capacity - b.min_capacity, 0) END AS norm_grid_capacity,
  CASE WHEN c.dh_readiness_tier IS NULL THEN NULL
       ELSE (c.dh_readiness_tier + 1)::DOUBLE PRECISION / 3.0 END AS norm_dh_proximity,
  CASE WHEN c.annual_mean_temp_c IS NULL THEN NULL
       ELSE 1 - (c.annual_mean_temp_c - b.min_temp) / NULLIF(b.max_temp - b.min_temp, 0) END AS norm_temperature,
  CASE WHEN c.dist_fiber_m IS NULL THEN NULL
       ELSE 1 - (c.dist_fiber_m - b.min_fiber) / NULLIF(b.max_fiber - b.min_fiber, 0) END AS norm_fiber,
  CASE
    WHEN c.dist_surface_water_m IS NULL THEN NULL
    WHEN c.dist_surface_water_m < 500 THEN 0
    WHEN c.dist_surface_water_m <= 5000 THEN 1 - ABS(c.dist_surface_water_m - 2750) / 2250
    ELSE COALESCE(1 - ((c.dist_surface_water_m - b.min_water) / NULLIF(b.max_water - b.min_water, 0)), 0) * 0.3
  END AS norm_surface_water,
  CASE WHEN c.land_cost_proxy_eur_m2 IS NULL THEN NULL
       ELSE 1 - (c.land_cost_proxy_eur_m2 - b.min_land) / NULLIF(b.max_land - b.min_land, 0) END AS norm_land_cost,
  CASE WHEN c.skilled_workforce_density IS NULL THEN NULL
       ELSE (c.skilled_workforce_density - b.min_workforce) / NULLIF(b.max_workforce - b.min_workforce, 0) END AS norm_workforce,
  CASE WHEN c.municipal_receptivity IS NULL THEN NULL
       ELSE (c.municipal_receptivity + 1)::DOUBLE PRECISION / 2.0 END AS norm_receptivity,
  c.excl_natura2000, c.excl_protected, c.excl_floodplain, c.excl_heritage,
  c.excl_airport, c.excl_airport_ols, c.excl_military, c.excl_steep_slope, c.excl_seveso,
  c.excl_water_protected, c.excl_urban_industrial, c.excl_sami_reindeer
FROM grid_cells c
CROSS JOIN bounds b;

CREATE UNIQUE INDEX IF NOT EXISTS idx_grid_cells_normalized_h3
ON grid_cells_normalized (h3_index);

CREATE INDEX IF NOT EXISTS idx_grid_cells_normalized_geom
ON grid_cells_normalized USING GIST (geom_4326);
