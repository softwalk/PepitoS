FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# Migra y arranca. El seed es opcional: SEED=true python -m app.seed
CMD ["sh", "-c", "alembic upgrade head && ( [ \"$SEED\" = \"true\" ] && python -m app.seed || true ) && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
