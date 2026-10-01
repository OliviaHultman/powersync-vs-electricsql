#!/bin/bash
set -e

# Creates the PowerSync replication role/publication (source DB) and the bucket
# storage database/user, using passwords supplied via container env vars.

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE powersync_storage;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE ROLE powersync_role WITH REPLICATION BYPASSRLS LOGIN PASSWORD '${POWERSYNC_PG_PASSWORD}';
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO powersync_role;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO powersync_role;
    CREATE PUBLICATION powersync FOR ALL TABLES;
EOSQL

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "powersync_storage" <<-EOSQL
    CREATE USER powersync_storage_user WITH PASSWORD '${POWERSYNC_STORAGE_PASSWORD}';
    GRANT CREATE ON DATABASE powersync_storage TO powersync_storage_user;
EOSQL
