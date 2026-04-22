CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- Optional: h3 extension availability depends on installation.
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS h3;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'h3 extension not available; using TEXT h3 indexes in v1 local mode.';
END$$;

CREATE TABLE IF NOT EXISTS data_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_key TEXT UNIQUE NOT NULL,
  source_url TEXT,
  license TEXT,
  checksum TEXT NOT NULL,
  fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS grid_cells (
  h3_index TEXT PRIMARY KEY,
  country CHAR(2) NOT NULL,
  municipality_code TEXT,
  bidding_zone TEXT,
  geom_4326 geometry(Polygon, 4326),

  dist_substation_400kv_m DOUBLE PRECISION,
  dist_substation_130kv_m DOUBLE PRECISION,
  dist_transmission_line_m DOUBLE PRECISION,
  bidding_zone_price_3y DOUBLE PRECISION,
  grid_capacity_indicator SMALLINT,
  grid_capacity_heatmap DOUBLE PRECISION,
  dist_dh_network_m DOUBLE PRECISION,
  dh_readiness_tier SMALLINT,
  annual_mean_temp_c DOUBLE PRECISION,
  dist_fiber_m DOUBLE PRECISION,
  dist_surface_water_m DOUBLE PRECISION,
  land_cost_proxy_eur_m2 DOUBLE PRECISION,
  skilled_workforce_density DOUBLE PRECISION,
  municipal_receptivity SMALLINT,

  excl_natura2000 BOOLEAN DEFAULT FALSE,
  excl_protected BOOLEAN DEFAULT FALSE,
  excl_floodplain BOOLEAN DEFAULT FALSE,
  excl_heritage BOOLEAN DEFAULT FALSE,
  excl_airport BOOLEAN DEFAULT FALSE,
  excl_airport_ols BOOLEAN DEFAULT FALSE,
  excl_military BOOLEAN DEFAULT FALSE,
  excl_steep_slope BOOLEAN DEFAULT FALSE,
  excl_seveso BOOLEAN DEFAULT FALSE,
  excl_water_protected BOOLEAN DEFAULT FALSE,
  excl_urban_industrial BOOLEAN DEFAULT FALSE,
  excl_sami_reindeer BOOLEAN DEFAULT FALSE,

  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_grid_cells_country ON grid_cells (country);
CREATE INDEX IF NOT EXISTS idx_grid_cells_bidding_zone ON grid_cells (bidding_zone);
CREATE INDEX IF NOT EXISTS idx_grid_cells_geom ON grid_cells USING GIST (geom_4326);

CREATE TABLE IF NOT EXISTS scenarios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  description TEXT,
  owner_user_id TEXT NOT NULL DEFAULT 'local-user',
  weights JSONB NOT NULL,
  exclusions_active JSONB NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE OR REPLACE FUNCTION touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_grid_cells_touch ON grid_cells;
CREATE TRIGGER trg_grid_cells_touch
BEFORE UPDATE ON grid_cells
FOR EACH ROW
EXECUTE FUNCTION touch_updated_at();

DROP TRIGGER IF EXISTS trg_scenarios_touch ON scenarios;
CREATE TRIGGER trg_scenarios_touch
BEFORE UPDATE ON scenarios
FOR EACH ROW
EXECUTE FUNCTION touch_updated_at();
