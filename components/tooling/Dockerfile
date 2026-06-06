# components/tooling/Dockerfile
# Build context is the REPO ROOT (so we can copy scripts/ and sql/migrations/).
# Published by CI as ghcr.io/<owner>/<repo>/tooling. One image for every
# operational job: migrate / backup / restore / export / qdrant-init.
FROM python:3.12-slim

# psql/pg_dump/pg_restore + curl + bash; thin.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
         postgresql-client curl bash ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir "psycopg[binary]==3.*" "requests>=2.31,<3"

WORKDIR /opt/tooling

# Operational scripts.
COPY scripts/migrate.sh scripts/backup.sh scripts/restore.sh \
     scripts/init_qdrant.sh scripts/memory_export.py /opt/tooling/
# Migrations are BAKED IN: the image digest pins exactly which migrations exist.
COPY sql/migrations/ /opt/tooling/migrations/

RUN chmod +x /opt/tooling/*.sh

ENV MIGRATIONS_DIR=/opt/tooling/migrations \
    PYTHONUNBUFFERED=1

# No default CMD: each Job/CronJob specifies its own command.
