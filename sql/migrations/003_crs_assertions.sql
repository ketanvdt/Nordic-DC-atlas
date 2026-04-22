CREATE OR REPLACE FUNCTION assert_geometry_srid()
RETURNS TABLE(check_name TEXT, ok BOOLEAN, details TEXT) AS $$
  SELECT
    'grid_cells_geom_4326'::TEXT,
    COALESCE(bool_and(ST_SRID(geom_4326) = 4326), TRUE),
    'All non-null grid_cells.geom_4326 rows must be SRID 4326'
  FROM grid_cells;
$$ LANGUAGE SQL STABLE;
