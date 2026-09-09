-- CodeAtlas AI — PostgreSQL initialisation script
-- Runs once when the postgres container is first created.

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "btree_gin";

-- Ensure the application role exists (idempotent)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'codeatlas') THEN
        CREATE ROLE codeatlas LOGIN PASSWORD 'password';
    END IF;
END
$$;

-- Grant privileges (idempotent — safe to re-run)
GRANT ALL PRIVILEGES ON DATABASE codeatlas TO codeatlas;
ALTER DATABASE codeatlas SET timezone TO 'UTC';

-- Full-text search configuration
ALTER DATABASE codeatlas SET default_text_search_config TO 'pg_catalog.english';
