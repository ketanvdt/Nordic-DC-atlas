PYTHON ?= python

.PHONY: install up down logs migrate ingest transform characterize refresh-norm seed-grid seed-municipalities app test lint

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
