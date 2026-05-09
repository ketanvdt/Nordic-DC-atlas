-- Phase 1.2: rewrite score_cells to skip NULL inputs per bucket and return
-- a per-cell coverage fraction = (count of non-NULL norm_* used) / (total
-- non-NULL norm_* the active weights would have wanted).
--
-- Per-bucket averaging changes shape: a bucket with only 1 of 3 inputs
-- present averages over 1 (not 3). A bucket whose weight is 0 contributes
-- nothing to the score AND nothing to coverage. A bucket whose weight is
-- non-zero but whose every input is NULL contributes 0 to score and 0/N
-- to coverage so the user sees the gap.

CREATE OR REPLACE FUNCTION score_cells(
  weights JSONB,
  exclusions JSONB,
  bbox_west DOUBLE PRECISION DEFAULT NULL,
  bbox_south DOUBLE PRECISION DEFAULT NULL,
  bbox_east DOUBLE PRECISION DEFAULT NULL,
  bbox_north DOUBLE PRECISION DEFAULT NULL,
  limit_n INTEGER DEFAULT 50000
)
RETURNS TABLE (h3_index TEXT, score DOUBLE PRECISION, coverage DOUBLE PRECISION) AS $$
WITH
  weighted AS (
    SELECT
      n.h3_index,
      n.geom_4326,
      -- Active flags: a bucket is active if its weight > 0 AND it has at
      -- least one non-NULL input present in the row.
      (COALESCE((weights->>'power')::DOUBLE PRECISION, 0) > 0)
        AS w_power_active,
      (COALESCE((weights->>'heat_offtake')::DOUBLE PRECISION, 0) > 0)
        AS w_heat_active,
      (COALESCE((weights->>'climate')::DOUBLE PRECISION, 0) > 0)
        AS w_climate_active,
      (COALESCE((weights->>'connectivity')::DOUBLE PRECISION, 0) > 0)
        AS w_conn_active,
      (COALESCE((weights->>'commercial')::DOUBLE PRECISION, 0) > 0)
        AS w_comm_active,

      -- Hard exclusion: any active exclusion flag => score NULL.
      (
           (COALESCE((exclusions->>'natura2000')::BOOLEAN, FALSE)      AND n.excl_natura2000)
        OR (COALESCE((exclusions->>'protected')::BOOLEAN, FALSE)       AND n.excl_protected)
        OR (COALESCE((exclusions->>'floodplain')::BOOLEAN, FALSE)      AND n.excl_floodplain)
        OR (COALESCE((exclusions->>'heritage')::BOOLEAN, FALSE)        AND n.excl_heritage)
        OR (COALESCE((exclusions->>'airport')::BOOLEAN, FALSE)         AND (n.excl_airport OR n.excl_airport_ols))
        OR (COALESCE((exclusions->>'military')::BOOLEAN, FALSE)        AND n.excl_military)
        OR (COALESCE((exclusions->>'steep_slope')::BOOLEAN, FALSE)     AND n.excl_steep_slope)
        OR (COALESCE((exclusions->>'seveso')::BOOLEAN, FALSE)          AND n.excl_seveso)
        OR (COALESCE((exclusions->>'water_protected')::BOOLEAN, FALSE) AND n.excl_water_protected)
        OR (COALESCE((exclusions->>'urban_industrial')::BOOLEAN, FALSE) AND n.excl_urban_industrial)
        OR (COALESCE((exclusions->>'sami_reindeer')::BOOLEAN, FALSE)   AND n.excl_sami_reindeer)
      ) AS hard_excluded,

      -- Power bucket: 5 inputs, average over the non-NULL ones.
      (
        SELECT AVG(v) FROM (VALUES
          (n.norm_substation_400kv),
          (n.norm_substation_130kv),
          (n.norm_transmission_line),
          (n.norm_bidding_zone),
          (n.norm_grid_capacity)
        ) AS t(v) WHERE v IS NOT NULL
      ) AS power_avg,
      -- Inputs present count per bucket, used for coverage.
      ((n.norm_substation_400kv IS NOT NULL)::INT
       + (n.norm_substation_130kv IS NOT NULL)::INT
       + (n.norm_transmission_line IS NOT NULL)::INT
       + (n.norm_bidding_zone IS NOT NULL)::INT
       + (n.norm_grid_capacity IS NOT NULL)::INT) AS power_n,
      5 AS power_total,

      n.norm_dh_proximity AS heat_avg,
      (n.norm_dh_proximity IS NOT NULL)::INT AS heat_n,
      1 AS heat_total,

      (
        SELECT AVG(v) FROM (VALUES
          (n.norm_temperature),
          (n.norm_surface_water)
        ) AS t(v) WHERE v IS NOT NULL
      ) AS climate_avg,
      ((n.norm_temperature IS NOT NULL)::INT
       + (n.norm_surface_water IS NOT NULL)::INT) AS climate_n,
      2 AS climate_total,

      n.norm_fiber AS conn_avg,
      (n.norm_fiber IS NOT NULL)::INT AS conn_n,
      1 AS conn_total,

      (
        SELECT AVG(v) FROM (VALUES
          (n.norm_land_cost),
          (n.norm_workforce),
          (n.norm_receptivity)
        ) AS t(v) WHERE v IS NOT NULL
      ) AS comm_avg,
      ((n.norm_land_cost IS NOT NULL)::INT
       + (n.norm_workforce IS NOT NULL)::INT
       + (n.norm_receptivity IS NOT NULL)::INT) AS comm_n,
      3 AS comm_total
    FROM grid_cells_normalized n
    WHERE (
      bbox_west IS NULL OR
      ST_Intersects(n.geom_4326, ST_MakeEnvelope(bbox_west, bbox_south, bbox_east, bbox_north, 4326))
    )
  )
SELECT
  w.h3_index,
  CASE WHEN w.hard_excluded THEN NULL
       ELSE
           COALESCE((weights->>'power')::DOUBLE PRECISION        * w.power_avg,   0)
         + COALESCE((weights->>'heat_offtake')::DOUBLE PRECISION * w.heat_avg,    0)
         + COALESCE((weights->>'climate')::DOUBLE PRECISION      * w.climate_avg, 0)
         + COALESCE((weights->>'connectivity')::DOUBLE PRECISION * w.conn_avg,    0)
         + COALESCE((weights->>'commercial')::DOUBLE PRECISION   * w.comm_avg,    0)
  END AS score,
  CASE
    WHEN w.hard_excluded THEN NULL
    WHEN (
      (CASE WHEN w.w_power_active   THEN w.power_total   ELSE 0 END)
    + (CASE WHEN w.w_heat_active    THEN w.heat_total    ELSE 0 END)
    + (CASE WHEN w.w_climate_active THEN w.climate_total ELSE 0 END)
    + (CASE WHEN w.w_conn_active    THEN w.conn_total    ELSE 0 END)
    + (CASE WHEN w.w_comm_active    THEN w.comm_total    ELSE 0 END)
    ) = 0 THEN NULL
    ELSE
      ((CASE WHEN w.w_power_active   THEN w.power_n   ELSE 0 END)
     + (CASE WHEN w.w_heat_active    THEN w.heat_n    ELSE 0 END)
     + (CASE WHEN w.w_climate_active THEN w.climate_n ELSE 0 END)
     + (CASE WHEN w.w_conn_active    THEN w.conn_n    ELSE 0 END)
     + (CASE WHEN w.w_comm_active    THEN w.comm_n    ELSE 0 END))::DOUBLE PRECISION
      /
      NULLIF((CASE WHEN w.w_power_active   THEN w.power_total   ELSE 0 END)
           + (CASE WHEN w.w_heat_active    THEN w.heat_total    ELSE 0 END)
           + (CASE WHEN w.w_climate_active THEN w.climate_total ELSE 0 END)
           + (CASE WHEN w.w_conn_active    THEN w.conn_total    ELSE 0 END)
           + (CASE WHEN w.w_comm_active    THEN w.comm_total    ELSE 0 END), 0)
  END AS coverage
FROM weighted w
LIMIT limit_n;
$$ LANGUAGE SQL STABLE;

CREATE OR REPLACE FUNCTION top_candidate_cells(
  weights JSONB,
  exclusions JSONB,
  top_n INTEGER DEFAULT 50
)
RETURNS TABLE (h3_index TEXT, score DOUBLE PRECISION, coverage DOUBLE PRECISION) AS $$
  SELECT s.h3_index, s.score, s.coverage
  FROM score_cells(weights, exclusions, NULL, NULL, NULL, NULL, 2000000) s
  WHERE s.score IS NOT NULL
  ORDER BY s.score DESC
  LIMIT top_n;
$$ LANGUAGE SQL STABLE;
