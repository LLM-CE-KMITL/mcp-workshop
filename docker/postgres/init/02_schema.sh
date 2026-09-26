#!/bin/bash
# Renders 02_schema.sql.template with EMBEDDING_DIM (from .env, passed
# through to this container's environment in docker-compose.yml) and
# applies it. A plain .sql file cannot read environment variables, so the
# substitution has to happen here before psql ever sees the schema.
set -e

DIM="${EMBEDDING_DIM:-1024}"

sed "s/__EMBEDDING_DIM__/${DIM}/g" \
    /docker-entrypoint-initdb.d/02_schema.sql.template \
  | psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB"
