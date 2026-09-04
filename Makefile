.PHONY: up down logs api-test operator-test backoffice-test test build
up:            ## Levanta todo con Docker (db + api + operador :8081 + backoffice :8082)
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f api
api-test:
	cd apps/api && python -m pytest -q
operator-test:
	cd apps/operator && npm test -- --run
backoffice-test:
	cd apps/backoffice && npm test -- --run
test: api-test operator-test backoffice-test
build:
	cd apps/operator && npm run build && cd ../backoffice && npm run build
