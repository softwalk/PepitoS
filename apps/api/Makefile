.PHONY: db db-stop db-status install migrate seed run test docker-build

PY ?= python

db:            ## Levanta PostgreSQL 16 local (puerto 5433) y crea usuario/base
	./scripts/dev_db.sh start

db-stop:
	./scripts/dev_db.sh stop

db-status:
	./scripts/dev_db.sh status

install:       ## Instala dependencias
	pip install --break-system-packages -r requirements.txt

migrate:       ## Aplica migraciones Alembic
	alembic upgrade head

seed:          ## Carga datos demo (idempotente)
	$(PY) -m app.seed

run:           ## Arranca la API con recarga
	uvicorn app.main:app --reload --port 8000

test:          ## Corre pytest (usa TEST_DATABASE_URL, recrea pepito_test)
	$(PY) -m pytest -q

docker-build:
	docker build -t pepito-os-api .

up: db migrate seed run  ## Todo en uno
