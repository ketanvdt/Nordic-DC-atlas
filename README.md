# Nordic Data Center Site Atlas (v1)

Local-first internal GIS overlay tool for EcoDataCenter site selection across Sweden, Norway, and Finland.

## Quick start

1. Copy `.env.example` to `.env`.
2. Start database: `make up`
3. Install Python deps: `make install`
4. Apply schema: `make migrate`
5. (Optional) Fetch and stage open layers: `make ingest && make transform`
6. Seed initial H3 grid: `make seed-grid`
7. Seed municipality names: `make seed-municipalities`
8. Run characterization: `make characterize`
9. Refresh normalized view: `make refresh-norm`
10. Run app: `make app`

## Stack

- Python 3.11+
- Streamlit UI
- PostgreSQL/PostGIS (Docker Compose)
- H3-indexed cell model with weighted overlay scoring

## QA

- Unit tests: `make test`
- Compile/lint sanity: `make lint`
- Exclusion band check: `python -m src.characterize.exclusion_qa`

## Data sources

Per-layer source registry at `config/layers/*.yaml` (27 layers across W1–W4). Start at `config/layers/README.md` for the researcher verification workflow. Manual-digitization artifacts land in `data/manual/` with provenance in `data/manual/source_notes.md`.
