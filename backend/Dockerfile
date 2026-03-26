FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install -e ".[dev]"

COPY . .

EXPOSE 8000

# Run DB migrations then start the server.
# Railway injects $PORT; fall back to 8000 for local Docker Compose.
CMD alembic upgrade head && \
    uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
