"""
SAT-SA AI-Assisted Case Priority Engine

Ranks SOC cases for analyst review using transparent,
evidence-based signals.

This is decision support, NOT autonomous incident classification.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _safe_number(value: Any, default: float = 0.0) -> float:
    """Safely convert a value to a number."""
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _is_true(value: Any) -> bool:
    """Handle common boolean representations."""
    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in {
        "true",
        "yes",
        "y",
        "1",
    }


def calculate_priority(row: pd.Series, criticality: str = "", signals: set[str] | None = None) -> dict[str, Any]:
    """
    Calculate a transparent 0-100 review-priority score.

    Higher score = should be reviewed earlier.

    The score combines:
    - alert severity
    - asset criticality
    - existing analytics anomalies
    - escalation/evidence gaps
    - closure speed
    """

    score = 0.0
    reasons: list[str] = []

    # ---------------------------------------------------------
    # 1. ALERT SEVERITY
    # ---------------------------------------------------------

    severity = str(row.get("alert_severity", "")).upper()

    severity_points = {
        "CRITICAL": 35,
        "HIGH": 25,
        "MEDIUM": 15,
        "LOW": 5,
    }

    severity_score = severity_points.get(severity, 0)
    score += severity_score

    if severity == "CRITICAL":
        reasons.append("Critical severity")
    elif severity == "HIGH":
        reasons.append("High severity")

    # ---------------------------------------------------------
    # 2. ASSET CRITICALITY
    # ---------------------------------------------------------

    asset_criticality = str(row.get("asset_criticality", row.get("criticality", criticality))).upper()

    asset_points = {
        "CRITICAL": 25,
        "HIGH": 18,
        "MEDIUM": 10,
        "LOW": 3,
    }

    asset_score = asset_points.get(asset_criticality, 0)
    score += asset_score

    if asset_criticality == "CRITICAL":
        reasons.append("Critical asset")
    elif asset_criticality == "HIGH":
        reasons.append("High-criticality asset")

    # ---------------------------------------------------------
    # 3. ESCALATION / EVIDENCE GAP
    # ---------------------------------------------------------

    escalated = row.get("escalated")

    if severity in {"CRITICAL", "HIGH"} and not _is_true(escalated):
        score += 15
        reasons.append("Escalation evidence missing")

    # ---------------------------------------------------------
    # 4. SPEED ANOMALY
    # ---------------------------------------------------------

    time_to_close = _safe_number(row.get("time_to_close"))

    # These thresholds intentionally remain conservative.
    if severity == "CRITICAL" and 0 < time_to_close < 120:
        score += 10
        reasons.append("Unusually fast closure")

    elif severity == "HIGH" and 0 < time_to_close < 60:
        score += 7
        reasons.append("Unusually fast closure")

    # ---------------------------------------------------------
    # 5. REPETITIVE RESOLUTION NOTE
    # ---------------------------------------------------------

    repetitive = row.get("repetitive_note", False) or "repetitive" in (signals or set())

    if _is_true(repetitive):
        score += 8
        reasons.append("Repetitive resolution pattern")

    # ---------------------------------------------------------
    # 6. EVIDENCE COMPLETENESS
    # ---------------------------------------------------------

    evidence_complete = row.get("evidence_complete", row.get("evidence_attached"))

    if evidence_complete is not None and not _is_true(evidence_complete):
        score += 7
        reasons.append("Evidence incomplete")

    if "missing_escalation" in (signals or set()) and "Escalation evidence missing" not in reasons:
        score += 15
        reasons.append("Escalation evidence missing")

    if "evidence_gap" in (signals or set()) and "Evidence incomplete" not in reasons:
        score += 7
        reasons.append("Evidence incomplete")

    # ---------------------------------------------------------
    # FINAL SCORE
    # ---------------------------------------------------------

    score = min(round(score), 100)

    if score >= 80:
        priority = "URGENT"
    elif score >= 65:
        priority = "HIGH"
    elif score >= 45:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    return {
        "ticket_id": str(row.get("ticket_id", "")),
        "priority_score": score,
        "priority": priority,
        "priority_classification": priority,
        "severity": severity,
        "asset": str(
            row.get("dest_asset")
            if str(row.get("dest_asset", "")).strip().lower() not in {"unknown asset", "unknown", "nan", "none", ""}
            else (
                row.get("asset_name")
                if str(row.get("asset_name", "")).strip().lower() not in {"", "nan", "none"}
                else row.get("asset_id", "Unknown")
            )
        ),
        "alert_type": str(row.get("alert_type", "Unknown")),
        "analyst": str(
            row.get("assigned_analyst", "Unassigned")
        ),
        "timestamp": str(row.get("timestamp", "")),
        "status": str(row.get("status", "NEW")),
        "reasons": reasons,
    }


def generate_priority_queue(
    df: pd.DataFrame,
    inventory_df: pd.DataFrame | None = None,
    assessment: dict[str, Any] | None = None,
    report: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Generate a ranked priority queue from the SOC dataset.
    """

    if df is None or df.empty:
        return []

    from analytics_engine import _prepare_dataframe, _preprocess_inventory_df
    df = _prepare_dataframe(df)
    if inventory_df is not None:
        inventory_df = _preprocess_inventory_df(inventory_df)

    asset_criticality = {}
    if inventory_df is not None and {"asset_id", "asset_criticality"}.issubset(inventory_df.columns):
        asset_criticality = inventory_df.set_index("asset_id")["asset_criticality"].to_dict()
    signal_map: dict[str, set[str]] = {}
    for anomaly in (report or {}).get("speed_anomalies", []):
        signal_map.setdefault(str(anomaly.get("ticket_id")), set()).add("speed")
    repetitive_ids = {ticket_id for cluster in (report or {}).get("repetitive_notes", []) for ticket_id in cluster.get("ticket_ids", [])}
    for ticket_id in repetitive_ids:
        signal_map.setdefault(str(ticket_id), set()).add("repetitive")
    for finding in (assessment or {}).get("findings", []):
        ticket_id = str(finding.get("entity", ""))
        if ticket_id:
            signal_map.setdefault(ticket_id, set()).add("missing_escalation" if finding.get("dimension") == "Escalation" else "evidence_gap")

    results = []

    for _, row in df.iterrows():
        ticket_id = str(row.get("ticket_id", ""))
        results.append(calculate_priority(row, str(asset_criticality.get(row.get("dest_asset"), "")), signal_map.get(ticket_id)))

    # Highest priority first.
    results.sort(
        key=lambda item: (
            item["priority_score"],
            item["severity"],
        ),
        reverse=True,
    )

    # Add rank after sorting.
    for rank, item in enumerate(results, start=1):
        item["rank"] = rank

    return results


def get_top_priorities(
    df: pd.DataFrame,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Return the highest-priority cases.
    """

    queue = generate_priority_queue(df)

    return queue[:limit]