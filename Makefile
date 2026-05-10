PYTHON ?= python

.PHONY: install up down logs migrate ingest fetch-osm transform characterize refresh-norm seed-grid seed-municipalities country-outlines app test lint

install:
	$(PYTHON) -m pip install -r requirements.txt

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f db

migrate:
	$(PYTHON) scripts/run_migrations.py

ingest:
	$(PYTHON) -m src.ingest.pipeline

# Fetch OSM-backed layers (natura2000, protected, airport, substations,
# transmission_lines) via Overpass. Separate target from `ingest`
# because Overpass needs network access to overpass-api.de (and mirrors)
# that aren't always reachable in sandboxed environments. Outputs land
# in data/processed/*.gpkg, which `make characterize` then picks up.
fetch-osm:
	$(PYTHON) scripts/fetch_osm_layers.py

# Re-vendor the Nordic country outlines from the Natural Earth GitHub
# mirror. Run-once; output is committed at
# data/manual/country_outlines.geojson.
country-outlines:
	$(PYTHON) scripts/build_country_outlines.py

transform:
	$(PYTHON) -m src.transform.pipeline

seed-grid:
	$(PYTHON) -m src.characterize.seed_h3_grid

seed-municipalities:
	$(PYTHON) scripts/seed_municipality_lookup.py

characterize:
	$(PYTHON) scripts/run_characterization.py

refresh-norm:
	$(PYTHON) scripts/refresh_materialized_views.py

app:
	streamlit run src/app/Home.py

test:
	pytest -q

lint:
	$(PYTHON) -m compileall src
