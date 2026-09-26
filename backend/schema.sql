-- ==============================================================================
-- SAT-SA (Supervisory Analytics Tool for SOC Assessment) - Database Schema
-- Database: sat_sa_db
-- Target: PostgreSQL 14+ (Local Air-Gapped)
-- ==============================================================================

-- 1. Create Database (Run as 'postgres' superuser if not already created)
-- CREATE DATABASE "sat_sa_db";
-- \c "sat_sa_db";

-- 2. Create 'soc_alerts' Table
CREATE TABLE IF NOT EXISTS soc_alerts (
    id SERIAL PRIMARY KEY,
    timestamp VARCHAR(64),
    alert_id VARCHAR(64),
    entity_id VARCHAR(64),
    asset_name VARCHAR(128),
    alert_category VARCHAR(64),
    alert_severity VARCHAR(32),
    time_to_close_seconds INTEGER,
    escalated BOOLEAN,
    resolution_notes TEXT,
    is_speed_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
    is_repetitive_anomaly BOOLEAN NOT NULL DEFAULT FALSE,
    is_negative_space BOOLEAN NOT NULL DEFAULT FALSE,
    is_anomaly BOOLEAN NOT NULL DEFAULT FALSE
);

-- Indexes for high-performance supervisory queries and filtering
CREATE INDEX IF NOT EXISTS ix_soc_alerts_id ON soc_alerts (id);
CREATE INDEX IF NOT EXISTS ix_soc_alerts_timestamp ON soc_alerts (timestamp);
CREATE INDEX IF NOT EXISTS ix_soc_alerts_alert_id ON soc_alerts (alert_id);
CREATE INDEX IF NOT EXISTS ix_soc_alerts_entity_id ON soc_alerts (entity_id);
CREATE INDEX IF NOT EXISTS ix_soc_alerts_asset_name ON soc_alerts (asset_name);

-- 3. Create 'asset_inventory' Table
CREATE TABLE IF NOT EXISTS asset_inventory (
    asset_name VARCHAR(128) PRIMARY KEY,
    asset_type VARCHAR(64),
    department VARCHAR(128),
    asset_criticality VARCHAR(32)
);

CREATE INDEX IF NOT EXISTS ix_asset_inventory_asset_name ON asset_inventory (asset_name);
