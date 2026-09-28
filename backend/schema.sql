-- ==============================================================================
-- SAT-SA (Supervisory Analytics Tool for SOC Assessment) - Database Schema
-- Database: sat_sa_db
-- Target: PostgreSQL 14+ (Local Air-Gapped)
-- Normalized Relational Schema for Evidence Ingestion & Verification
-- ==============================================================================

-- 1. Create 'asset_inventory' Table (Root Parent Table)
CREATE TABLE IF NOT EXISTS asset_inventory (
    asset_name VARCHAR(128) PRIMARY KEY,
    asset_type VARCHAR(64),
    department VARCHAR(128),
    asset_criticality VARCHAR(32)
);

CREATE INDEX IF NOT EXISTS ix_asset_inventory_asset_name ON asset_inventory (asset_name);

-- 2. Create 'soc_alerts' Table (Child of asset_inventory, Parent of Evidence tables)
CREATE TABLE IF NOT EXISTS soc_alerts (
    id SERIAL PRIMARY KEY,
    timestamp VARCHAR(64),
    alert_id VARCHAR(64) UNIQUE NOT NULL,
    entity_id VARCHAR(64),
    asset_name VARCHAR(128) REFERENCES asset_inventory(asset_name) ON DELETE SET NULL,
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

CREATE INDEX IF NOT EXISTS ix_soc_alerts_id ON soc_alerts (id);
CREATE INDEX IF NOT EXISTS ix_soc_alerts_alert_id ON soc_alerts (alert_id);
CREATE INDEX IF NOT EXISTS ix_soc_alerts_timestamp ON soc_alerts (timestamp);
CREATE INDEX IF NOT EXISTS ix_soc_alerts_entity_id ON soc_alerts (entity_id);
CREATE INDEX IF NOT EXISTS ix_soc_alerts_asset_name ON soc_alerts (asset_name);

-- 3. Create 'case_management' Table (Child of soc_alerts)
CREATE TABLE IF NOT EXISTS case_management (
    id SERIAL PRIMARY KEY,
    case_id VARCHAR(64),
    alert_id VARCHAR(64) NOT NULL REFERENCES soc_alerts(alert_id) ON DELETE CASCADE,
    timestamp VARCHAR(64),
    sensor_id VARCHAR(64),
    alert_name VARCHAR(128),
    severity VARCHAR(32),
    mitre_tactic VARCHAR(64),
    source_ip VARCHAR(64),
    destination_ip VARCHAR(64),
    asset_id VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS ix_case_management_case_id ON case_management (case_id);
CREATE INDEX IF NOT EXISTS ix_case_management_alert_id ON case_management (alert_id);

-- 4. Create 'investigation_workflows' Table (Child of soc_alerts)
CREATE TABLE IF NOT EXISTS investigation_workflows (
    id SERIAL PRIMARY KEY,
    workflow_id VARCHAR(64),
    alert_id VARCHAR(64) NOT NULL REFERENCES soc_alerts(alert_id) ON DELETE CASCADE,
    case_id VARCHAR(64),
    action_taken TEXT,
    action_timestamp VARCHAR(64),
    result TEXT,
    time_spent_minutes INTEGER,
    investigator VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS ix_investigation_workflows_workflow_id ON investigation_workflows (workflow_id);
CREATE INDEX IF NOT EXISTS ix_investigation_workflows_alert_id ON investigation_workflows (alert_id);

-- 5. Create 'escalation_records' Table (Child of soc_alerts)
CREATE TABLE IF NOT EXISTS escalation_records (
    id SERIAL PRIMARY KEY,
    escalation_id VARCHAR(64),
    alert_id VARCHAR(64) NOT NULL REFERENCES soc_alerts(alert_id) ON DELETE CASCADE,
    case_id VARCHAR(64),
    escalated_from_tier VARCHAR(32),
    escalated_to_tier VARCHAR(32),
    escalation_reason TEXT,
    escalation_timestamp VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS ix_escalation_records_escalation_id ON escalation_records (escalation_id);
CREATE INDEX IF NOT EXISTS ix_escalation_records_alert_id ON escalation_records (alert_id);

-- 6. Create 'alert_closures' Table (Child of soc_alerts)
CREATE TABLE IF NOT EXISTS alert_closures (
    id SERIAL PRIMARY KEY,
    closure_id VARCHAR(64),
    alert_id VARCHAR(64) NOT NULL REFERENCES soc_alerts(alert_id) ON DELETE CASCADE,
    closed_by VARCHAR(64),
    closure_reason VARCHAR(128),
    resolution_notes TEXT,
    closure_timestamp VARCHAR(64),
    capa_action TEXT,
    is_verified BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS ix_alert_closures_closure_id ON alert_closures (closure_id);
CREATE INDEX IF NOT EXISTS ix_alert_closures_alert_id ON alert_closures (alert_id);
