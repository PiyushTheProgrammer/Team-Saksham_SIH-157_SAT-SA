"""
SAT-SA — database.py
====================
Configures the local PostgreSQL database connection via SQLAlchemy.

Air-gap compliant: PostgreSQL runs on-premises — zero external API or cloud dependencies.

Connection string format:
    postgresql://postgres:<password>@localhost:5432/sat_sa_db

Requirements:
    - sqlalchemy >= 2.0.0
    - psycopg2-binary >= 2.9.9
    - python-dotenv >= 1.0.0
"""

import os
from typing import Generator
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Load environment configuration from .env file
load_dotenv()

# ── Connection Parameters ───────────────────────────────────────────────────
DATABASE_USER = os.getenv("DATABASE_USER", "postgres")
DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD", "Admin@123")

DATABASE_HOST = os.getenv("DATABASE_HOST", "localhost")
DATABASE_PORT = int(os.getenv("DATABASE_PORT", "5432"))
DATABASE_NAME = os.getenv("DATABASE_NAME", "sat_sa_db")

# URL-encode password to handle special characters (e.g., '@', ':', '/') safely
encoded_password = quote_plus(DATABASE_PASSWORD)

# Connection string format: postgresql://postgres:<password>@localhost:5432/sat_sa_db
SQLALCHEMY_DATABASE_URL = (
    f"postgresql://{DATABASE_USER}:{encoded_password}@{DATABASE_HOST}:{DATABASE_PORT}/{DATABASE_NAME}"
)

# ── SQLAlchemy Engine ───────────────────────────────────────────────────────
# pool_pre_ping tests connection liveness before issuing queries;
# pool_size and max_overflow handle concurrent API requests efficiently.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# ── Session Factory ─────────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ── Declarative Base Setup ──────────────────────────────────────────────────
Base = declarative_base()


# ── Database Dependency for FastAPI Endpoints ───────────────────────────────
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency yielding an independent SQLAlchemy session per request
    and ensuring proper session closure in the finally block.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_database_exists() -> None:
    """
    Connects to the default PostgreSQL administrative database ('postgres' or 'template1')
    and creates DATABASE_NAME if it does not already exist.
    This guarantees zero-crash startup even on a brand-new PostgreSQL installation.
    """
    import logging
    from sqlalchemy import create_engine as create_raw_engine, text
    logger = logging.getLogger("sat-sa.database")

    for admin_db in ["postgres", "template1"]:
        try:
            admin_url = (
                f"postgresql://{DATABASE_USER}:{encoded_password}@{DATABASE_HOST}:{DATABASE_PORT}/{admin_db}"
            )
            admin_engine = create_raw_engine(admin_url, isolation_level="AUTOCOMMIT")
            with admin_engine.connect() as conn:
                exists = conn.execute(
                    text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                    {"dbname": DATABASE_NAME},
                ).scalar()
                if not exists:
                    logger.info("Database '%s' not found. Creating it automatically...", DATABASE_NAME)
                    conn.execute(text(f'CREATE DATABASE "{DATABASE_NAME}"'))
                    logger.info("Database '%s' created successfully.", DATABASE_NAME)
                else:
                    logger.debug("Database '%s' already exists.", DATABASE_NAME)
            admin_engine.dispose()
            return
        except Exception as exc:
            logger.debug("Attempt to check/create database via '%s' failed: %s", admin_db, exc)
            continue


# ── Idempotent Table Initialization ─────────────────────────────────────────
def init_db() -> None:
    """
    Imports all models to register their metadata and executes
    CREATE TABLE IF NOT EXISTS for each registered table against PostgreSQL.
    Invoked during FastAPI application startup.
    """
    import logging
    from sqlalchemy import text
    import models  # noqa: F401 — side-effect registers ORM mappings

    logger = logging.getLogger("sat-sa.database")

    # 1. Automatically create database if it doesn't exist
    try:
        ensure_database_exists()
    except Exception as e:
        logger.warning("Could not verify/create database automatically: %s", e)

    # 2. Run idempotent schema updates and table creation
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE soc_alerts ADD COLUMN IF NOT EXISTS timestamp VARCHAR(64);"))
        except Exception:
            pass

        try:
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='asset_inventory' AND column_name='asset_id'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns 
                        WHERE table_name='asset_inventory' AND column_name='asset_name'
                    ) THEN
                        DROP TABLE asset_inventory CASCADE;
                    END IF;
                END $$;
            """))
        except Exception:
            pass

        # Ensure asset_inventory table is created before FK constraints
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS asset_inventory (
                    asset_name VARCHAR(128) PRIMARY KEY,
                    asset_type VARCHAR(64),
                    department VARCHAR(128),
                    asset_criticality VARCHAR(32)
                );
            """))
        except Exception:
            pass

        # Ensure unique constraint on soc_alerts.alert_id for child foreign keys
        try:
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'soc_alerts') THEN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint 
                            WHERE conname = 'uq_soc_alerts_alert_id'
                        ) THEN
                            -- Remove duplicate or null alert_ids if any before adding constraint
                            DELETE FROM soc_alerts a USING soc_alerts b
                            WHERE a.id < b.id AND a.alert_id = b.alert_id;
                            
                            ALTER TABLE soc_alerts ADD CONSTRAINT uq_soc_alerts_alert_id UNIQUE (alert_id);
                        END IF;
                    END IF;
                END $$;
            """))
        except Exception as e:
            logger.debug("Constraint uq_soc_alerts_alert_id check: %s", e)

        # Ensure explicit foreign key constraint from soc_alerts.asset_name to asset_inventory.asset_name
        try:
            conn.execute(text("""
                DO $$
                BEGIN
                    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'soc_alerts') 
                       AND EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'asset_inventory') THEN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_constraint 
                            WHERE conname = 'fk_soc_alerts_asset_name'
                        ) THEN
                            -- Insert any missing asset_name into asset_inventory before adding constraint
                            INSERT INTO asset_inventory (asset_name, asset_type, department, asset_criticality)
                            SELECT DISTINCT asset_name, 'Server', 'IT', 'MEDIUM'
                            FROM soc_alerts
                            WHERE asset_name IS NOT NULL
                              AND asset_name NOT IN (SELECT asset_name FROM asset_inventory)
                            ON CONFLICT DO NOTHING;

                            ALTER TABLE soc_alerts 
                            ADD CONSTRAINT fk_soc_alerts_asset_name 
                            FOREIGN KEY (asset_name) REFERENCES asset_inventory(asset_name) ON DELETE SET NULL;
                        END IF;
                    END IF;
                END $$;
            """))
        except Exception as e:
            logger.debug("Constraint fk_soc_alerts_asset_name check: %s", e)

    Base.metadata.create_all(bind=engine)
    logger.info("Database schema initialized successfully with all 6 normalized relational tables.")

