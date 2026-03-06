FROM python:3.11-slim

# Install system dependencies for psycopg (libpq)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY src/ src/

# Install dependencies (mcp, qdrant-client, psycopg)
RUN pip install --no-cache-dir .

EXPOSE 8081

CMD ["python", "-m", "memory_steward_mcp.server"]
