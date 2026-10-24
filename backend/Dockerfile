FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000
# Run DB migrations (best-effort — the app also serves in degraded mode if the
# DB is unreachable), then start the API.
CMD ["sh", "-c", "alembic upgrade head || echo 'migrations skipped'; exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
