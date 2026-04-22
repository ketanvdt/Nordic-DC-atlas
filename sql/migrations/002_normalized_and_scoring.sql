DROP MATERIALIZED VIEW IF EXISTS grid_cells_normalized;

CREATE MATERIALIZED VIEW grid_cells_normalized AS
WITH bounds AS (
  SELECT
    MIN(dist_substation_400kv_m) AS min_sub400, MAX(dist_substation_400kv_m) AS max_sub400,
    MIN(dist_substation_130kv_m) AS min_sub130, MAX(dist_substation_130kv_m) AS max_sub130,
    MIN(dist_transmission_line_m) AS min_tx, MAX(dist_transmission_line_m) AS max_tx,
    MIN(bidding_zone_price_3y) AS min_price, MAX(bidding_zone_price_3y) AS max_price,
    MIN(grid_capacity_heatmap) AS min_capacity, MAX(grid_capacity_heatmap) AS max_capacity,
    MIN(annual_mean_temp_c) AS min_temp, MAX(annual_mean_temp_c) AS max_temp,
    MIN(dist_fiber_m) AS min_fiber, MAX(dist_fiber_m) AS max_fiber,
    MIN(dist_surface_water_m) AS min_water, MAX(dist_surface_water_m) AS max_water,
    MIN(land_cost_proxy_eur_m2) AS min_land, MAX(land_cost_proxy_eur_m2) AS max_land,
    MIN(skilled_workforce_density) AS min_workforce, MAX(skilled_workforce_density) AS max_workforce
  FROM grid_cells
)
SELECT
  c.h3_index,
  c.country,
  c.bidding_zone,
  c.geom_4326,
  COALESCE(1 - ((c.dist_substation_400kv_m - b.min_sub400) / NULLIF(b.max_sub400 - b.min_sub400, 0)), 0) AS norm_substation_400kv,
  COALESCE(1 - ((c.dist_substation_130kv_m - b.min_sub130) / NULLIF(b.max_sub130 - b.min_sub130, 0)), 0) AS norm_substation_130kv,
  COALESCE(1 - ((c.dist_transmission_line_m - b.min_tx) / NULLIF(b.max_tx - b.min_tx, 0)), 0) AS norm_transmission_line,
  COALESCE(1 - ((c.bidding_zone_price_3y - b.min_price) / NULLIF(b.max_price - b.min_price, 0)), 0) AS norm_bidding_zone,
  COALESCE((c.grid_capacity_heatmap - b.min_capacity) / NULLIF(b.max_capacity - b.min_capacity, 0), 0) AS norm_grid_capacity,
  COALESCE((c.dh_readiness_tier + 1)::DOUBLE PRECISION / 3.0, 0) AS norm_dh_proximity,
  COALESCE(1 - ((c.annual_mean_temp_c - b.min_temp) / NULLIF(b.max_temp - b.min_temp, 0)), 0) AS norm_temperature,
  COALESCE(1 - ((c.dist_fiber_m - b.min_fiber) / NULLIF(b.max_fiber - b.min_fiber, 0)), 0) AS norm_fiber,
  CASE
    WHEN c.dist_surface_water_m < 500 THEN 0
    WHEN c.dist_surface_water_m <= 5000 THEN 1 - ABS(c.dist_surface_water_m - 2750) / 2250
    ELSE COALESCE(1 - ((c.dist_surface_water_m - b.min_water) / NULLIF(b.max_water - b.min_water, 0)), 0) * 0.3
  END AS norm_surface_water,
  COALESCE(1 - ((c.land_cost_proxy_eur_m2 - b.min_land) / NULLIF(b.max_land - b.min_land, 0)), 0) AS norm_land_cost,
  COALESCE((c.skilled_workforce_density - b.min_workforce) / NULLIF(b.max_workforce - b.min_workforce, 0), 0) AS norm_workforce,
  COALESCE((c.municipal_receptivity + 1)::DOUBLE PRECISION / 2.0, 0) AS norm_receptivity,
  c.excl_natura2000, c.excl_protected, c.excl_floodplain, c.excl_heritage,
  c.excl_airport, c.excl_airport_ols, c.excl_military, c.excl_steep_slope, c.excl_seveso,
  c.excl_water_protected, c.excl_urban_industrial, c.excl_sami_reindeer
FROM grid_cells c
CROSS JOIN bounds b;

CREATE UNIQUE INDEX IF NOT EXISTS idx_grid_cells_normalized_h3
ON grid_cells_normalized (h3_index);

CREATE INDEX IF NOT EXISTS idx_grid_cells_normalized_geom
ON grid_cells_normalized USING GIST (geom_4326);

CREATE OR REPLACE FUNCTION score_cells(
  weights JSONB,
  exclusions JSONB,
  bbox_west DOUBLE PRECISION DEFAULT NULL,
  bbox_south DOUBLE PRECISION DEFAULT NULL,
  bbox_east DOUBLE PRECISION DEFAULT NULL,
  bbox_north DOUBLE PRECISION DEFAULT NULL,
  limit_n INTEGER DEFAULT 50000
)
RETURNS TABLE (h3_index TEXT, score DOUBLE PRECISION) AS $$
  SELECT
    n.h3_index,
    CASE
      WHEN COALESCE((exclusions->>'natura2000')::BOOLEAN, FALSE)      AND n.excl_natura2000      THEN NULL
      WHEN COALESCE((exclusions->>'protected')::BOOLEAN, FALSE)       AND n.excl_protected       THEN NULL
      WHEN COALESCE((exclusions->>'floodplain')::BOOLEAN, FALSE)      AND n.excl_floodplain      THEN NULL
      WHEN COALESCE((exclusions->>'heritage')::BOOLEAN, FALSE)        AND n.excl_heritage        THEN NULL
      WHEN COALESCE((exclusions->>'airport')::BOOLEAN, FALSE)         AND (n.excl_airport OR n.excl_airport_ols) THEN NULL
      WHEN COALESCE((exclusions->>'military')::BOOLEAN, FALSE)        AND n.excl_military        THEN NULL
      WHEN COALESCE((exclusions->>'steep_slope')::BOOLEAN, FALSE)     AND n.excl_steep_slope     THEN NULL
      WHEN COALESCE((exclusions->>'seveso')::BOOLEAN, FALSE)          AND n.excl_seveso          THEN NULL
      WHEN COALESCE((exclusions->>'water_protected')::BOOLEAN, FALSE) AND n.excl_water_protected THEN NULL
      WHEN COALESCE((exclusions->>'urban_industrial')::BOOLEAN, FALSE) AND n.excl_urban_industrial THEN NULL
      WHEN COALESCE((exclusions->>'sami_reindeer')::BOOLEAN, FALSE)   AND n.excl_sami_reindeer   THEN NULL
      ELSE
        COALESCE((weights->>'power')::DOUBLE PRECISION * (n.norm_substation_400kv + n.norm_substation_130kv + n.norm_transmission_line + n.norm_bidding_zone + n.norm_grid_capacity) / 5.0, 0)
      + COALESCE((weights->>'heat_offtake')::DOUBLE PRECISION * n.norm_dh_proximity, 0)
      + COALESCE((weights->>'climate')::DOUBLE PRECISION * (n.norm_temperature + n.norm_surface_water) / 2.0, 0)
      + COALESCE((weights->>'connectivity')::DOUBLE PRECISION * n.norm_fiber, 0)
      + COALESCE((weights->>'commercial')::DOUBLE PRECISION * (n.norm_land_cost + n.norm_workforce + n.norm_receptivity) / 3.0, 0)
    END AS score
  FROM grid_cells_normalized n
  WHERE (
    bbox_west IS NULL OR
    ST_Intersects(n.geom_4326, ST_MakeEnvelope(bbox_west, bbox_south, bbox_east, bbox_north, 4326))
  )
  LIMIT limit_n;
$$ LANGUAGE SQL STABLE;

CREATE OR REPLACE FUNCTION top_candidate_cells(
  weights JSONB,
  exclusions JSONB,
  top_n INTEGER DEFAULT 50
)
RETURNS TABLE (h3_index TEXT, score DOUBLE PRECISION) AS $$
  SELECT s.h3_index, s.score
  FROM score_cells(weights, exclusions, NULL, NULL, NULL, NULL, 2000000) s
  WHERE s.score IS NOT NULL
  ORDER BY s.score DESC
  LIMIT top_n;
$$ LANGUAGE SQL STABLE;
