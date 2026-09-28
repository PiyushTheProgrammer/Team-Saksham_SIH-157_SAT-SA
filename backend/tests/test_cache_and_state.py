"""
Test Suite: Cache Invalidation, State Management, and Dependency Checking
========================================================================
Validates that:
1. All in-memory caches and DB ML anomalies are completely wiped on /api/upload and /api/data/clear.
2. An uploaded dataset lacking `time_to_close_seconds` and `resolution_notes` (e.g. alert_metadata.csv):
   - Gracefully disables speed anomalies and repetitive notes detectors instead of fabricating fake anomalies.
   - Throws 422 Unprocessable Entity when strict_schema=true.
3. State does not blend between consecutive uploads of different datasets.
"""

import io
import sys
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app, _report_cache, _assessment_cache, _alerts_cache


@pytest.fixture
def client():
    return TestClient(app)


def test_clear_database_wipes_all_caches(client: TestClient):
    """Ensure /api/data/clear wipes in-memory cache and returns clean zero-state."""
    res = client.delete("/api/data/clear")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"

    # Verify summary endpoint returns zero state
    summary_res = client.get("/api/dashboard/summary")
    assert summary_res.status_code == 200
    summary = summary_res.json()["summary"]
    assert summary["total_alerts"] == 0
    assert summary["speed_anomalies_count"] == 0
    assert summary["repetitive_notes_clusters"] == 0

    # Verify assessment returns 0 records assessed
    assess_res = client.get("/api/assessment")
    assert assess_res.status_code == 200
    assess = assess_res.json()
    assert assess["lifecycle"]["records_assessed"] == 0
    assert len(assess["findings"]) == 0


def test_missing_dependency_graceful_ml_degradation(client: TestClient):
    """
    When alert_metadata.csv lacks time_to_close_seconds and resolution_notes:
    - Speed anomalies must NOT be flagged (count == 0).
    - Repetitive notes must NOT be flagged (count == 0).
    - Summary reports ml_capabilities and disabled_flags.
    """
    # Create mock alert_metadata.csv with 4 records (2 Critical/High) lacking TTC and resolution notes
    csv_content = """alert_id,entity_id,asset_name,alert_category,alert_severity
ALT-001,ENT-1,srv-web-01,Brute Force,CRITICAL
ALT-002,ENT-1,srv-db-01,Privilege Escalation,HIGH
ALT-003,ENT-2,srv-app-02,Port Scan,MEDIUM
ALT-004,ENT-2,srv-app-03,Anomalous Login,LOW
"""
    files = {"file": ("alert_metadata.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/api/upload", files=files)
    assert res.status_code == 200
    resp_data = res.json()
    assert resp_data["records_ingested"] == 4
    assert resp_data["ml_capabilities"]["speed_anomaly_detection"] is False
    assert resp_data["ml_capabilities"]["repetitive_notes_detection"] is False
    assert any("time_to_close_seconds" in f for f in resp_data["ml_flags_disabled"])

    # Check /api/dashboard/summary: speed_anomalies MUST be 0
    summary_res = client.get("/api/dashboard/summary")
    assert summary_res.status_code == 200
    sum_data = summary_res.json()
    assert sum_data["summary"]["total_alerts"] == 4
    assert sum_data["summary"]["speed_anomalies_count"] == 0
    assert len(sum_data["speed_anomalies"]) == 0

    # Check /api/assessment: records_assessed must be 4
    assess_res = client.get("/api/assessment")
    assert assess_res.status_code == 200
    assess = assess_res.json()
    assert assess["lifecycle"]["records_assessed"] == 4


def test_missing_dependency_strict_validation_throws_422(client: TestClient):
    """
    When strict_schema=true and required ML columns are missing,
    the API must throw 422 Unprocessable Entity.
    """
    csv_content = """alert_id,entity_id,asset_name,alert_category,alert_severity
ALT-101,ENT-1,srv-web-01,Brute Force,CRITICAL
"""
    files = {"file": ("alert_metadata.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    res = client.post("/api/upload?strict_schema=true", files=files)
    assert res.status_code == 422
    assert "Unprocessable Entity" in res.json()["detail"]
    assert "time_to_close_seconds" in res.json()["detail"]


def test_upload_wipes_previous_state_no_blending(client: TestClient):
    """
    Uploading a new dataset must completely wipe the previous dataset's records
    and anomaly cache from both in-memory and database.
    """
    # Upload first dataset with 3 alerts
    csv_1 = """alert_id,entity_id,asset_name,alert_category,alert_severity,time_to_close_seconds,resolution_notes
TICK-A1,ENT-A,srv-1,Malware,CRITICAL,12,Resolved per SOP.
TICK-A2,ENT-A,srv-2,Phishing,HIGH,15,Resolved per SOP.
TICK-A3,ENT-A,srv-3,DDoS,LOW,500,Normal closure.
"""
    files1 = {"file": ("dataset_1.csv", io.BytesIO(csv_1.encode("utf-8")), "text/csv")}
    res1 = client.post("/api/upload", files=files1)
    assert res1.status_code == 200
    assert res1.json()["records_ingested"] == 3

    # Upload second dataset with completely different 2 alerts (lacking TTC)
    csv_2 = """alert_id,entity_id,asset_name,alert_category,alert_severity
TICK-B1,ENT-B,srv-x,Ransomware,CRITICAL
TICK-B2,ENT-B,srv-y,Exfiltration,HIGH
"""
    files2 = {"file": ("dataset_2.csv", io.BytesIO(csv_2.encode("utf-8")), "text/csv")}
    res2 = client.post("/api/upload", files=files2)
    assert res2.status_code == 200
    assert res2.json()["records_ingested"] == 2

    # Verify that dataset_1 records are completely gone
    summary_res = client.get("/api/dashboard/summary")
    sum_data = summary_res.json()["summary"]
    # Total alerts MUST be 2 (from dataset_2 only), NOT 5!
    assert sum_data["total_alerts"] == 2
    # Speed anomalies MUST be 0 (dataset_2 has no TTC), NOT carrying over TICK-A1/TICK-A2!
    assert sum_data["speed_anomalies_count"] == 0

    assess_res = client.get("/api/assessment")
    assess = assess_res.json()
    assert assess["lifecycle"]["records_assessed"] == 2
