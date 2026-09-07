#!/bin/sh
# Respaldo y restauración de PostgreSQL de PEPITO OS.
#   backup.sh once                 → un pg_dump comprimido en /backups/pepito-YYYYmmdd-HHMM.sql.gz
#   backup.sh loop                 → un respaldo diario a BACKUP_HOUR_UTC y purga > BACKUP_KEEP_DAYS (servicio `backup`)
#   backup.sh restore ARCHIVO.sql.gz → restaura en una base limpia (¡destruye la actual!). Ver docs/OPERACION.md.
#   backup.sh verify ARCHIVO.sql.gz  → restaura en pepito_verify y cuenta tablas (prueba de restore sin tocar producción)
set -eu
HOST=${PGHOST:-db}; USER=${PGUSER:-pepito}; DB=${PGDATABASE:-pepito}; DIR=${BACKUP_DIR:-/backups}
KEEP=${BACKUP_KEEP_DAYS:-14}; HOUR=${BACKUP_HOUR_UTC:-8}
mkdir -p "$DIR"

do_backup() {
  f="$DIR/pepito-$(date -u +%Y%m%d-%H%M).sql.gz"
  pg_dump -h "$HOST" -U "$USER" -d "$DB" --no-owner --no-privileges | gzip -9 > "$f.tmp" && mv "$f.tmp" "$f"
  echo "backup ok: $f ($(du -h "$f" | cut -f1))"
  find "$DIR" -name 'pepito-*.sql.gz' -mtime +"$KEEP" -delete
}

case "${1:-once}" in
  once) do_backup ;;
  loop)
    echo "servicio de respaldo: diario a las ${HOUR}:05 UTC, conserva ${KEEP} días"
    while true; do
      if [ "$(date -u +%H)" = "$(printf '%02d' "$HOUR")" ] && [ "$(date -u +%M)" -lt 10 ]; then do_backup; sleep 700; fi
      sleep 300
    done ;;
  restore)
    [ -n "${2:-}" ] || { echo "uso: backup.sh restore ARCHIVO.sql.gz"; exit 1; }
    echo "Restaurando $2 en $DB (se destruye la base actual) en 5 s…"; sleep 5
    psql -h "$HOST" -U "$USER" -d postgres -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE)" -c "CREATE DATABASE ${DB}"
    gunzip -c "$2" | psql -h "$HOST" -U "$USER" -d "$DB" -q
    echo "restore ok" ;;
  verify)
    [ -n "${2:-}" ] || { echo "uso: backup.sh verify ARCHIVO.sql.gz"; exit 1; }
    psql -h "$HOST" -U "$USER" -d postgres -c "DROP DATABASE IF EXISTS pepito_verify WITH (FORCE)" -c "CREATE DATABASE pepito_verify" -q
    gunzip -c "$2" | psql -h "$HOST" -U "$USER" -d pepito_verify -q
    psql -h "$HOST" -U "$USER" -d pepito_verify -Atc "select 'tablas: '||count(*) from information_schema.tables where table_schema='public'; select 'ventas: '||count(*) from sales; select 'turnos: '||count(*) from shifts;"
    psql -h "$HOST" -U "$USER" -d postgres -c "DROP DATABASE pepito_verify" -q
    echo "verify ok" ;;
  *) echo "uso: backup.sh once|loop|restore ARCHIVO|verify ARCHIVO"; exit 1 ;;
esac
