#!/usr/bin/env bash
# Levanta un PostgreSQL 16 local de desarrollo en el puerto 5433.
# - initdb en $PGDATA (default: <repo>/.pgdata) si no existe
# - pg_ctl start con socket en /tmp
# - crea usuario pepito/pepito y base pepito
# Si se ejecuta como root, corre postgres como usuario `pg` (lo crea si falta).
set -euo pipefail

PGBIN="${PGBIN:-/usr/lib/postgresql/16/bin}"
REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
PGDATA="${PGDATA:-$REPO_ROOT/.pgdata}"
PGPORT="${PGPORT:-5433}"
PGLOG="${PGLOG:-$PGDATA/postgres.log}"
DB_NAME="${DB_NAME:-pepito}"
DB_USER="${DB_USER:-pepito}"
DB_PASS="${DB_PASS:-pepito}"
ACTION="${1:-start}"

run_as_pg() {
  if [ "$(id -u)" = "0" ]; then
    if ! id pg >/dev/null 2>&1; then
      useradd -m -s /bin/bash pg
    fi
    runuser -u pg -- "$@"
  else
    "$@"
  fi
}

case "$ACTION" in
  start)
    if [ ! -d "$PGDATA" ]; then
      mkdir -p "$PGDATA"
      if [ "$(id -u)" = "0" ]; then
        id pg >/dev/null 2>&1 || useradd -m -s /bin/bash pg
        chown pg:pg "$PGDATA"
        chmod 700 "$PGDATA"
      fi
      run_as_pg "$PGBIN/initdb" -D "$PGDATA" -U postgres --auth=trust --encoding=UTF8 --locale=C.UTF-8 >/dev/null
      echo "initdb listo en $PGDATA"
    fi
    if run_as_pg "$PGBIN/pg_ctl" -D "$PGDATA" status >/dev/null 2>&1; then
      echo "postgres ya está corriendo (puerto $PGPORT)"
    else
      run_as_pg "$PGBIN/pg_ctl" -D "$PGDATA" -l "$PGLOG" -o "-p $PGPORT -k /tmp" -w start >/dev/null
      echo "postgres iniciado en puerto $PGPORT (log: $PGLOG)"
    fi
    PSQL="$PGBIN/psql -h /tmp -p $PGPORT -U postgres -v ON_ERROR_STOP=1 -tAq"
    if [ -z "$($PSQL -c "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'")" ]; then
      $PSQL -c "CREATE ROLE $DB_USER LOGIN PASSWORD '$DB_PASS' SUPERUSER;"
      echo "usuario $DB_USER creado"
    fi
    if [ -z "$($PSQL -c "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'")" ]; then
      $PSQL -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
      echo "base $DB_NAME creada"
    fi
    echo "DATABASE_URL=postgresql+psycopg://$DB_USER:$DB_PASS@localhost:$PGPORT/$DB_NAME"
    ;;
  stop)
    run_as_pg "$PGBIN/pg_ctl" -D "$PGDATA" -m fast stop
    ;;
  status)
    run_as_pg "$PGBIN/pg_ctl" -D "$PGDATA" status
    ;;
  *)
    echo "uso: $0 [start|stop|status]" >&2
    exit 1
    ;;
esac
