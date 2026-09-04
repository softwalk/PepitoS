#!/usr/bin/env bash
set -e

HOST="${1:-127.0.0.1}"
API_URL="http://${HOST}:8000"
OPERATOR_URL="http://${HOST}:8081"
BACKOFFICE_URL="http://${HOST}:8082"

echo "=========================================================="
echo "           PEPITO OS — SCRIPT DE LEVANTAMIENTO            "
echo "=========================================================="
echo "Host objetivo: $HOST"
echo "Fecha y hora: $(date)"
echo ""

echo "--- [1/5] Levantando servicios con Docker Compose ---"
docker compose up --build -d
echo ""

echo "--- [2/5] Esperando a que la API esté lista ---"
for i in {1..30}; do
  if curl -fsS "${API_URL}/v1/health" >/dev/null 2>&1; then
    echo "API saludable en ${API_URL}/v1/health"
    break
  fi
  sleep 2
done

echo ""
echo "--- [3/5] Comprobación de Salud y Endpoints HTTP ---"
HEALTH=$(curl -fsS "${API_URL}/v1/health")
echo "Healthcheck API: $HEALTH"
echo "Operador PWA (${OPERATOR_URL}): HTTP $(curl -s -o /dev/null -w "%{http_code}" "${OPERATOR_URL}")"
echo "Backoffice   (${BACKOFFICE_URL}): HTTP $(curl -s -o /dev/null -w "%{http_code}" "${BACKOFFICE_URL}")"
echo ""

echo "--- [4/5] Prueba de Autenticación (Login Demo) ---"
echo "1. Login Operador (op1):"
OP_TOKEN=$(curl -fsS -X POST "${API_URL}/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"op1","password":"op123","device_id":"dev-levantar-1"}' | jq -r .access_token)
echo "   Token JWT emitido exitosamente (longitud: ${#OP_TOKEN})"

echo "2. Asignación del operador op1:"
ASSIGNMENT=$(curl -fsS "${API_URL}/v1/me/assignment" -H "Authorization: Bearer ${OP_TOKEN}")
POINT_NAME=$(echo "$ASSIGNMENT" | jq -r .assignment.point.name)
CART_CODE=$(echo "$ASSIGNMENT" | jq -r .assignment.cart.code)
echo "   Punto asignado: $POINT_NAME | Carrito: $CART_CODE"

echo "3. Login Admin (admin):"
ADMIN_TOKEN=$(curl -fsS -X POST "${API_URL}/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123","device_id":"dev-levantar-admin"}' | jq -r .access_token)
echo "   Token Admin emitido exitosamente (longitud: ${#ADMIN_TOKEN})"
echo ""

echo "--- [5/5] Ejecución de Pruebas Automatizadas (65 Tests Pytest) ---"
docker exec \
  -e DATABASE_URL=postgresql+psycopg://pepito:pepito@db:5432/pepito_test \
  -e TEST_DATABASE_URL=postgresql+psycopg://pepito:pepito@db:5432/pepito_test \
  -e RUN_SCHEDULER=false \
  pepito-os-api-1 python -m pytest -q

echo ""
echo "=========================================================="
echo "          TODO EL SISTEMA ESTÁ OPERATIVO Y AL 100%        "
echo "=========================================================="
echo "Accesos HTTP directos:"
echo "  • Operador PWA : ${OPERATOR_URL}"
echo "  • Backoffice   : ${BACKOFFICE_URL}"
echo "  • API Backend  : ${API_URL}/v1/health"
echo ""
echo "Accesos HTTPS (Caddy - Móviles / PWA con Offline + GPS):"
echo "  • Operador PWA : https://${HOST}:8443"
echo "  • Backoffice   : https://${HOST}:8444"
echo "  • API Backend  : https://${HOST}:8445/v1/health"
echo "  • Certificado CA: http://${HOST}:8446/ca.crt"
echo "=========================================================="
