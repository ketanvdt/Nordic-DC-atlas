-- Knowledge-base layer for forward-looking grid data.
--
-- Holds:
--   source_documents     — every PDF / register / open-data feed that contributes attributes
--   grid_projects        — canonical project rows (Pillar 2: transmission development over time)
--   project_aliases      — publisher-specific IDs that resolve to the same canonical project
--
-- Geometry resolution and grid_cell linkage are intentionally NOT in this migration.
-- They land in 008 (Phase C) and 009 (Phase D) respectively.

CREATE TABLE IF NOT EXISTS source_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_key TEXT UNIQUE NOT NULL,
  publisher TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  title TEXT,
  publication_date DATE,
  horizon_start_year INT,
  horizon_end_year INT,
  language CHAR(2) DEFAULT 'sv',
  confidentiality TEXT,
  source_url TEXT,
  local_path TEXT,
  sha256 TEXT,
  page_count INT,
  added_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_source_documents_publisher ON source_documents (publisher);
CREATE INDEX IF NOT EXISTS idx_source_documents_doc_type ON source_documents (doc_type);

CREATE TABLE IF NOT EXISTS grid_projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_key TEXT UNIQUE NOT NULL,

  project_type TEXT NOT NULL CHECK (project_type IN (
    'station_new', 'station_renewal', 'line_new', 'line_upgrade',
    'line_renewal', 'reinforcement', 'compensation', 'other'
  )),
  name TEXT NOT NULL,
  motivation TEXT CHECK (motivation IN (
    'connection', 'system_reinforcement', 'reinvestment', 'market_integration', 'unknown'
  )),

  voltage_from_kv INT,
  voltage_to_kv INT,

  planned_commission_year INT,
  lifecycle_phase TEXT NOT NULL CHECK (lifecycle_phase IN (
    'conceptual', 'permit_pending', 'permitted', 'construction', 'in_service'
  )),
  raw_status TEXT,

  geom_4326 geometry(Geometry, 4326),
  region_hint TEXT,

  operator TEXT,

  source_doc_id UUID NOT NULL REFERENCES source_documents(id),
  source_page INT,
  extraction_method TEXT NOT NULL CHECK (extraction_method IN (
    'open_data', 'llm_extracted', 'manual_digitization'
  )),
  extraction_run_id TEXT,
  extraction_prompt_version TEXT,
  confidence_tier TEXT NOT NULL CHECK (confidence_tier IN (
    'observed', 'derived', 'estimated', 'narrative'
  )),

  added_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_grid_projects_geom ON grid_projects USING GIST (geom_4326);
CREATE INDEX IF NOT EXISTS idx_grid_projects_phase ON grid_projects (lifecycle_phase);
CREATE INDEX IF NOT EXISTS idx_grid_projects_year ON grid_projects (planned_commission_year);
CREATE INDEX IF NOT EXISTS idx_grid_projects_operator ON grid_projects (operator);

CREATE TABLE IF NOT EXISTS project_aliases (
  project_id UUID NOT NULL REFERENCES grid_projects(id) ON DELETE CASCADE,
  alias TEXT NOT NULL,
  alias_source TEXT NOT NULL,
  match_confidence TEXT CHECK (match_confidence IN ('exact', 'high', 'medium', 'low')) DEFAULT 'exact',
  PRIMARY KEY (project_id, alias)
);

CREATE INDEX IF NOT EXISTS idx_project_aliases_alias ON project_aliases (alias);

DROP TRIGGER IF EXISTS trg_grid_projects_touch ON grid_projects;
CREATE TRIGGER trg_grid_projects_touch
BEFORE UPDATE ON grid_projects
FOR EACH ROW
EXECUTE FUNCTION touch_updated_at();
