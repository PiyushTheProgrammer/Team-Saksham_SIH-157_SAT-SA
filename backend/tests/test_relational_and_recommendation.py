"""
Unit & Integration Tests for Normalized Relational Schema & Cross-CSE Recommendation Engine
=============================================================================================
Tests:
  1. Relational schema models and Foreign Key enforcement
  2. Hierarchical ingestion (Parent tables first, Child tables second)
  3. Outerjoin analytics fetching preventing data loss
  4. Cross-CSE TF-IDF cosine similarity recommendation engine (>85% trigger)
"""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import engine, get_db, init_db
from main import app
from models import (
    AlertClosures,
    AssetInventory,
    CaseManagement,
    EscalationRecords,
    InvestigationWorkflows,
    SocAlerts,
)
from recommendation_engine import recommendation_engine


@pytest.fixture(scope="module")
def client():
    init_db()
    with TestClient(app) as c:
        yield c


def test_normalized_tables_exist():
    """Verify all 6 relational models exist in PostgreSQL schema."""
    insp = inspect(engine)
    tables = insp.get_table_names()
    expected = [
        "asset_inventory",
        "soc_alerts",
        "case_management",
        "investigation_workflows",
        "escalation_records",
        "alert_closures",
    ]
    for table in expected:
        assert table in tables, f"Expected table '{table}' in database, found: {tables}"


def test_foreign_key_constraints():
    """Verify explicit Foreign Key constraints are properly configured."""
    insp = inspect(engine)

    # 1. soc_alerts -> asset_inventory
    soc_fks = insp.get_foreign_keys("soc_alerts")
    assert any(
        fk.get("referred_table") == "asset_inventory" and "asset_name" in fk.get("constrained_columns", [])
        for fk in soc_fks
    ), f"Missing Foreign Key from soc_alerts.asset_name to asset_inventory: {soc_fks}"

    # 2. Evidence tables -> soc_alerts.alert_id
    for child_table in ["case_management", "investigation_workflows", "escalation_records", "alert_closures"]:
        child_fks = insp.get_foreign_keys(child_table)
        assert any(
            fk.get("referred_table") == "soc_alerts" and "alert_id" in fk.get("constrained_columns", [])
            for fk in child_fks
        ), f"Missing Foreign Key from {child_table}.alert_id to soc_alerts.alert_id: {child_fks}"


def test_hierarchical_upload_and_outerjoin(client):
    """Verify hierarchical upload and outerjoin fetching without data loss."""
    # Step 1: Clear database
    clear_res = client.delete("/api/data/clear")
    assert clear_res.status_code == 200

    # Step 2: Ingest AssetInventory (Parent)
    inv_csv = (
        "asset_name,asset_type,department,asset_criticality\n"
        "web-server-01,Server,IT,HIGH\n"
        "db-prod-01,Database,Engineering,CRITICAL\n"
    )
    res_inv = client.post(
        "/api/upload",
        files={"file": ("asset_inventory.csv", inv_csv.encode("utf-8"), "text/csv")},
    )
    assert res_inv.status_code == 200
    assert res_inv.json()["dataset_type"] == "asset_inventory"

    # Step 3: Ingest SocAlerts (Child of AssetInventory)
    alerts_csv = (
        "timestamp,alert_id,entity_id,asset_name,alert_category,alert_severity,time_to_close_seconds,escalated,resolution_notes\n"
        "2026-09-15T10:00:00Z,TEST-AL-01,CSE-Alpha,web-server-01,Malware,Critical,30,False,Quarantined file.\n"
        "2026-09-15T11:00:00Z,TEST-AL-02,CSE-Beta,db-prod-01,Unauthorized Access,High,45,True,Checked logs. All good.\n"
    )
    res_alerts = client.post(
        "/api/upload",
        files={"file": ("soc_alerts.csv", alerts_csv.encode("utf-8"), "text/csv")},
    )
    assert res_alerts.status_code == 200
    assert res_alerts.json()["dataset_type"] == "soc_alerts"

    # Step 4: Ingest CaseManagement (Child of SocAlerts)
    case_csv = (
        "case_id,alert_id,timestamp,sensor_id,alert_name,severity,mitre_tactic,source_ip,destination_ip,asset_id\n"
        "CAS-101,TEST-AL-01,2026-09-15T10:00:00Z,SENS-01,Malware Infection,Critical,Execution,10.0.0.1,10.0.0.2,AST-01\n"
    )
    res_case = client.post(
        "/api/upload",
        files={"file": ("case_management.csv", case_csv.encode("utf-8"), "text/csv")},
    )
    assert res_case.status_code == 200

    # Step 5: Verify outerjoin query returns both alerts with joined case details
    dash_res = client.get("/api/dashboard/summary")
    assert dash_res.status_code == 200
    summary = dash_res.json().get("summary", {})
    assert summary.get("total_alerts", 0) >= 2


def test_cross_cse_recommendation_trigger(client):
    """Verify recommendation engine triggers when candidate match > 85%."""
    # Test identical category, severity, and resolution notes from a different entity
    query_payload = {
        "ticket_id": "TEST-AUDIT-99",
        "entity_id": "CSE-Alpha",
        "asset_name": "db-prod-01",
        "alert_category": "Unauthorized Access",
        "alert_severity": "Critical",
        "resolution_notes": "Checked logs. All good.",
    }

    res = client.post("/api/audit/recommend-reference", json=query_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["has_recommendation"] is True
    ref = data["recommended_reference"]
    assert ref["match_found"] is True
    assert ref["similarity_score"] >= 85.0
    assert "historical_capa" in ref
    assert ref["notification_message"] == (
        "You have audited a similar anomaly from another CSE before. "
        "Do you want to review that historical Corrective Action (CAPA) as a reference?"
    )


def test_explain_anomaly_includes_recommendation(client):
    """Verify /api/explain-anomaly endpoint appends recommended_reference object."""
    explain_payload = {
        "anomaly_type": "speed_anomaly",
        "ticket_id": "TEST-AL-02",
        "severity": "Critical",
        "time_to_close": 4,
        "analyst": "Analyst-1",
        "alert_type": "Unauthorized Access",
        "alert_category": "Unauthorized Access",
        "escalated": False,
        "explanation": "Critical alert closed in 4s without escalation.",
        "resolution_notes": "Checked logs. All good.",
        "entity_id": "CSE-New",
    }

    res = client.post("/api/explain-anomaly", json=explain_payload)
    assert res.status_code == 200
    data = res.json()
    assert "explanation" in data
    assert "recommended_reference" in data
    ref = data["recommended_reference"]
    assert ref is not None
    assert ref["match_found"] is True
    assert ref["similarity_score"] >= 85.0
