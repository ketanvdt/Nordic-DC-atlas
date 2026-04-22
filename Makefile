PYTHON ?= python

.PHONY: install up down logs migrate characterize refresh-norm seed-grid app test lint

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

characterize:
	$(PYTHON) scripts/run_characterization.py

refresh-norm:
	$(PYTHON) scripts/refresh_materialized_views.py

seed-grid:
	$(PYTHON) -m src.characterize.seed_h3_grid

app:
	streamlit run src/app/Home.py

test:
	pytest -q

lint:
	$(PYTHON) -m compileall src
