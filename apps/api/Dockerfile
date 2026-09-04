FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# Migra y arranca. Seed según SEED_MODE (demo | prod | none). Compatibilidad: SEED=true equivale a SEED_MODE=demo.
# Sin SEED_MODE ni SEED=true no se siembra nada.
CMD ["sh", "-c", "alembic upgrade head && MODE=\"${SEED_MODE:-$([ \"$SEED\" = \"true\" ] && echo demo || echo none)}\" && SEED_MODE=\"$MODE\" python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
