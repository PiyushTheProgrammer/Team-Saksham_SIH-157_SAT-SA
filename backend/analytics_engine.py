"""
SAT-SA — Phase 2: Analytics Engine (The Brain)
================================================
Processes SOC alert CSVs to detect three classes of operational anomalies:

  1. SpeedAnomalyDetector   — Improbably fast ticket closures using
                               Isolation Forest + rule-based thresholds.
  2. RepetitiveNotesDetector — Analysts pasting identical resolution text
                               across different alert types (TF-IDF + cosine).
  3. BlindSpotDetector       — Critical assets with statistically improbable
                               zero (or near-zero) alert volumes.

Orchestrator: AnalyticsOrchestrator runs all detectors and produces a
              unified AnomalyReport serialisable to JSON.

All processing is 100 % offline — no network calls.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


# ════════════════════════════════════════════════
# DATA CLASSES
# ════════════════════════════════════════════════


@dataclass
class SpeedAnomaly:
    """A single ticket flagged for improbably fast closure."""
    ticket_id: str
    severity: str
    time_to_close: int
    time_to_acknowledge: int
    escalated: bool
    analyst: str
    alert_type: str
    dest_asset: str
    timestamp: str
    explanation: str


@dataclass
class RepetitiveNoteCluster:
    """A group of tickets sharing near-identical resolution notes."""
    analyst: str
    repeated_note_snippet: str
    ticket_ids: list[str]
    distinct_alert_types: list[str]
    ticket_count: int
    explanation: str


@dataclass
class BlindSpot:
    """An asset flagged for statistically improbable alert silence."""
    asset_id: str
    criticality: str
    asset_type: str
    actual_alerts: int
    expected_mean: float
    expected_std: float
    explanation: str


@dataclass
class AnomalyReport:
    """Unified output from the analytics engine."""
    summary: dict[str, Any] = field(default_factory=dict)
    speed_anomalies: list[SpeedAnomaly] = field(default_factory=list)
    repetitive_notes: list[RepetitiveNoteCluster] = field(default_factory=list)
    blind_spots: list[BlindSpot] = field(default_factory=list)
    trend: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "trend": self.trend or self.summary.get("trend", []),
            "speed_anomalies": [asdict(a) for a in self.speed_anomalies],
            "repetitive_notes": [asdict(c) for c in self.repetitive_notes],
            "blind_spots": [asdict(b) for b in self.blind_spots],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


# ════════════════════════════════════════════════
# PREPROCESSING & NORMALIZATION UTILITIES
# ════════════════════════════════════════════════

# Hard thresholds (seconds) — tickets below these are suspicious
SEVERITY_SPEED_THRESHOLDS = {
    "CRITICAL": 120,   # < 2 minutes
    "HIGH": 60,        # < 1 minute
    "MEDIUM": 30,
    "LOW": 15,
}

SEVERITY_ENCODING = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "4": 4,
    "3": 3,
    "2": 2,
    "1": 1,
    "0": 1,
}


def _prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Bullet-proof data preprocessing and normalization.
    Ensures that ML models (Isolation Forest, TF-IDF, etc.) receive clean,
    well-typed, and schema-compliant DataFrames regardless of CSV variations.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()

    # 1. Normalize column names: strip, lowercase, replace spaces/dashes with underscores
    df.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]

    # 2. Rename Columns: time_to_close_seconds -> time_to_close
    has_ttc_col = False
    for col in ["time_to_close_seconds", "time_to_close", "close_time", "ttc"]:
        if col in df.columns:
            has_ttc_col = True
            if col != "time_to_close":
                df["time_to_close"] = df[col]
            break

    if has_ttc_col:
        numeric_ttc = pd.to_numeric(df["time_to_close"], errors="coerce")
        has_valid_ttc = bool(numeric_ttc.notna().any())
        df["time_to_close"] = numeric_ttc.fillna(-1).astype(int)
        df["_has_time_to_close"] = has_valid_ttc
        df.attrs["has_time_to_close"] = has_valid_ttc
    else:
        df["time_to_close"] = -1
        df["_has_time_to_close"] = False
        df.attrs["has_time_to_close"] = False

    # 3. Missing Columns: time_to_acknowledge fallback (fill with 0)
    if "time_to_acknowledge" not in df.columns:
        if "time_to_acknowledge_seconds" in df.columns:
            df["time_to_acknowledge"] = df["time_to_acknowledge_seconds"]
        elif "ack_time" in df.columns:
            df["time_to_acknowledge"] = df["ack_time"]
        elif "tta" in df.columns:
            df["time_to_acknowledge"] = df["tta"]
        else:
            df["time_to_acknowledge"] = 0
    df["time_to_acknowledge"] = pd.to_numeric(df["time_to_acknowledge"], errors="coerce").fillna(0).astype(int)

    # 4. Standardize ticket_id / alert_id / id
    if "ticket_id" not in df.columns:
        if "alert_id" in df.columns:
            df["ticket_id"] = df["alert_id"].astype(str)
        elif "id" in df.columns:
            df["ticket_id"] = df["id"].astype(str)
        else:
            df["ticket_id"] = [f"TICK-{i:05d}" for i in range(len(df))]
    else:
        df["ticket_id"] = df["ticket_id"].astype(str)

    # 5. Standardize alert_type / alert_category / category
    if "alert_type" not in df.columns:
        if "alert_category" in df.columns:
            df["alert_type"] = df["alert_category"].fillna("General").astype(str)
        elif "category" in df.columns:
            df["alert_type"] = df["category"].fillna("General").astype(str)
        else:
            df["alert_type"] = "General"
    else:
        df["alert_type"] = df["alert_type"].fillna("General").astype(str)

    # 6. Standardize assigned_analyst / entity_id / entity / analyst
    if "assigned_analyst" not in df.columns:
        if "entity_id" in df.columns:
            df["assigned_analyst"] = df["entity_id"].fillna("Analyst_1").astype(str)
        elif "entity" in df.columns:
            df["assigned_analyst"] = df["entity"].fillna("Analyst_1").astype(str)
        elif "analyst" in df.columns:
            df["assigned_analyst"] = df["analyst"].fillna("Analyst_1").astype(str)
        else:
            df["assigned_analyst"] = "Analyst_1"
    else:
        df["assigned_analyst"] = df["assigned_analyst"].fillna("Analyst_1").astype(str)

    # 7. Standardize dest_asset / asset_name / asset / asset_id
    if "dest_asset" not in df.columns:
        if "asset_name" in df.columns:
            df["dest_asset"] = df["asset_name"].fillna("Unknown Asset").astype(str)
        elif "asset" in df.columns:
            df["dest_asset"] = df["asset"].fillna("Unknown Asset").astype(str)
        elif "asset_id" in df.columns:
            df["dest_asset"] = df["asset_id"].fillna("Unknown Asset").astype(str)
        else:
            df["dest_asset"] = "Unknown Asset"
    else:
        df["dest_asset"] = df["dest_asset"].fillna("Unknown Asset").astype(str)

    # 8. Standardize resolution_notes / notes / resolution
    has_notes_col = False
    for col in ["resolution_notes", "notes", "resolution"]:
        if col in df.columns:
            has_notes_col = True
            if col != "resolution_notes":
                df["resolution_notes"] = df[col]
            break

    if has_notes_col:
        df["resolution_notes"] = df["resolution_notes"].fillna("").astype(str)
        has_valid_notes = bool(df["resolution_notes"].str.strip().ne("").any())
        df["_has_resolution_notes"] = has_valid_notes
        df.attrs["has_resolution_notes"] = has_valid_notes
    else:
        df["resolution_notes"] = ""
        df["_has_resolution_notes"] = False
        df.attrs["has_resolution_notes"] = False

    # 9. Standardize timestamp / time / date
    if "timestamp" not in df.columns:
        if "time" in df.columns:
            df["timestamp"] = df["time"].fillna("").astype(str)
        elif "date" in df.columns:
            df["timestamp"] = df["date"].fillna("").astype(str)
        else:
            df["timestamp"] = ""
    else:
        df["timestamp"] = df["timestamp"].fillna("").astype(str)

    # 10. Severity Mapping: 'Critical' -> 4, 'High' -> 3, 'Medium' -> 2, 'Low' -> 1
    if "alert_severity" not in df.columns:
        if "severity" in df.columns:
            df["alert_severity"] = df["severity"]
        else:
            df["alert_severity"] = "LOW"
    df["alert_severity"] = df["alert_severity"].fillna("LOW").astype(str).str.strip().str.upper()
    df["severity_num"] = df["alert_severity"].map(SEVERITY_ENCODING).fillna(1).astype(int)

    # 11. Escalation Mapping: boolean or string 'True'/'False' -> escalated (bool) & escalated_num (int 1/0)
    if "escalated" not in df.columns:
        df["escalated"] = False
        df["escalated_num"] = 0
    else:
        def _parse_bool(val: Any) -> bool:
            if pd.isna(val) or val is None:
                return False
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return bool(val)
            s = str(val).strip().lower()
            return s in {"true", "1", "yes", "t", "y"}

        df["escalated"] = df["escalated"].apply(_parse_bool)
        df["escalated_num"] = df["escalated"].astype(int)

    return df


# Alias for backward compatibility
_preprocess_alerts_df = _prepare_dataframe


def _preprocess_inventory_df(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize inventory DataFrame column names and types."""
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.copy()
    df.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]

    if "asset_id" not in df.columns:
        if "asset_name" in df.columns:
            df["asset_id"] = df["asset_name"].astype(str)
        elif "asset" in df.columns:
            df["asset_id"] = df["asset"].astype(str)
        elif "id" in df.columns:
            df["asset_id"] = df["id"].astype(str)
        else:
            df["asset_id"] = [f"ASSET-{i:03d}" for i in range(len(df))]
    else:
        df["asset_id"] = df["asset_id"].astype(str)

    if "asset_criticality" not in df.columns:
        if "criticality" in df.columns:
            df["asset_criticality"] = df["criticality"]
        elif "severity" in df.columns:
            df["asset_criticality"] = df["severity"]
        else:
            df["asset_criticality"] = "MEDIUM"
    df["asset_criticality"] = df["asset_criticality"].fillna("MEDIUM").astype(str).str.strip().str.upper()

    if "asset_type" not in df.columns:
        if "type" in df.columns:
            df["asset_type"] = df["type"]
        else:
            df["asset_type"] = "Server"
    df["asset_type"] = df["asset_type"].fillna("Server").astype(str)

    if "department" not in df.columns:
        if "dept" in df.columns:
            df["department"] = df["dept"].astype(str)
        else:
            df["department"] = "IT Infrastructure"
    df["department"] = df["department"].fillna("IT Infrastructure").astype(str)

    return df


# ════════════════════════════════════════════════
# DETECTOR 1: Speed Anomaly Detector
# ════════════════════════════════════════════════


class SpeedAnomalyDetector:
    """
    Detect tickets closed improbably fast relative to their severity.

    Hybrid approach:
      1. Rule-based filter: Flag CRITICAL/HIGH tickets below time thresholds.
      2. Isolation Forest scoring: Fit an unsupervised model on ticket features
         and compute anomaly scores. Tickets that pass the rule-based filter
         AND score highly anomalous are ranked first.

    This ensures we never miss obvious speed anomalies (the rule catches them)
    while the ML model provides a confidence/ranking signal.
    """

    def __init__(self, contamination: float = 0.05, random_state: int = 42):
        self.model = IsolationForest(
            contamination=contamination,
            random_state=random_state,
            n_estimators=200,
            n_jobs=-1,
        )

    def detect(self, df: pd.DataFrame) -> list[SpeedAnomaly]:
        """Run detection on the alerts DataFrame. Returns flagged tickets."""
        if df is None or df.empty:
            return []

        # Robust feature extraction and column normalization
        df = _preprocess_alerts_df(df)

        has_ttc = getattr(df, "attrs", {}).get("has_time_to_close", None)
        if has_ttc is None:
            has_ttc = bool(df["_has_time_to_close"].any()) if "_has_time_to_close" in df.columns else False
        if not has_ttc:
            # Gracefully disable detector when required time_to_close column is missing
            return []

        features = df[["severity_num", "time_to_close", "time_to_acknowledge", "escalated_num"]].values

        if len(features) == 0:
            return []

        # Fit the model and get anomaly scores (lower = more anomalous)
        try:
            self.model.fit(features)
            df["anomaly_score"] = self.model.decision_function(features)
        except Exception:
            # Fallback if IsolationForest fails (e.g. edge cases)
            df["anomaly_score"] = 0.0

        # Primary detection: rule-based severity threshold filter
        # Secondary signal: Isolation Forest anomaly score for ranking
        flagged: list[SpeedAnomaly] = []
        for _, row in df.iterrows():
            sev = str(row["alert_severity"]).upper()
            ttc = int(row["time_to_close"])
            if ttc < 0:
                continue
            threshold = SEVERITY_SPEED_THRESHOLDS.get(sev, 15)

            # Rule-based gate: must be CRITICAL/HIGH AND below time threshold
            if ttc < threshold and sev in ("CRITICAL", "HIGH"):
                score = float(row.get("anomaly_score", 0.0))
                escalated = bool(row["escalated"])
                esc_note = " without escalation" if not escalated else " (was escalated)"
                explanation = (
                    f"{sev} alert closed in {ttc}s (threshold: {threshold}s)"
                    f"{esc_note}. "
                    f"Anomaly score: {score:.4f}. "
                    f"Analyst: {row['assigned_analyst']}. "
                    f"Alert type: {row['alert_type']}."
                )
                flagged.append(
                    SpeedAnomaly(
                        ticket_id=str(row["ticket_id"]),
                        severity=sev,
                        time_to_close=ttc,
                        time_to_acknowledge=int(row["time_to_acknowledge"]),
                        escalated=escalated,
                        analyst=str(row["assigned_analyst"]),
                        alert_type=str(row["alert_type"]),
                        dest_asset=str(row["dest_asset"]),
                        timestamp=str(row["timestamp"]),
                        explanation=explanation,
                    )
                )

        # Sort by anomaly score (most anomalous first — lowest time to close)
        flagged.sort(key=lambda a: a.time_to_close)
        return flagged


# ════════════════════════════════════════════════
# DETECTOR 2: Repetitive Notes Detector
# ════════════════════════════════════════════════


class RepetitiveNotesDetector:
    """
    Detect analysts who paste near-identical resolution notes across
    multiple, disparate alert types.

    Approach:
      1. Group tickets by analyst.
      2. For each analyst, TF-IDF-vectorise their resolution notes.
      3. Compute pairwise cosine similarity.
      4. Cluster notes with similarity ≥ 0.95.
      5. Flag clusters of ≥ 10 tickets spanning ≥ 3 different alert types.
    """

    def __init__(self, similarity_threshold: float = 0.95, min_cluster_size: int = 10, min_alert_types: int = 3):
        self.sim_threshold = similarity_threshold
        self.min_cluster = min_cluster_size
        self.min_types = min_alert_types

    def detect(self, df: pd.DataFrame) -> list[RepetitiveNoteCluster]:
        """Run detection. Returns flagged clusters."""
        if df is None or df.empty:
            return []

        df = _preprocess_alerts_df(df)
        has_notes = getattr(df, "attrs", {}).get("has_resolution_notes", None)
        if has_notes is None:
            has_notes = bool(df["_has_resolution_notes"].any()) if "_has_resolution_notes" in df.columns else False
        if not has_notes or df["resolution_notes"].str.strip().eq("").all():
            # Gracefully disable detector when required resolution_notes column is missing
            return []

        flagged: list[RepetitiveNoteCluster] = []

        for analyst, group in df.groupby("assigned_analyst"):
            if len(group) < self.min_cluster:
                continue

            clusters = self._find_clusters(group)
            for cluster_indices in clusters:
                cluster_df = group.iloc[cluster_indices]
                unique_types = cluster_df["alert_type"].unique().tolist()

                if len(cluster_indices) >= self.min_cluster and len(unique_types) >= self.min_types:
                    raw_snippet = cluster_df["resolution_notes"].iloc[0] if not cluster_df["resolution_notes"].empty else ""
                    note_snippet = str(raw_snippet)[:120]
                    explanation = (
                        f"Analyst {analyst} used near-identical resolution notes across "
                        f"{len(cluster_indices)} tickets spanning {len(unique_types)} "
                        f"different alert types ({', '.join(unique_types[:5])}). "
                        f"Note snippet: \"{note_snippet}…\""
                    )
                    flagged.append(
                        RepetitiveNoteCluster(
                            analyst=str(analyst),
                            repeated_note_snippet=note_snippet,
                            ticket_ids=[str(t) for t in cluster_df["ticket_id"].tolist()],
                            distinct_alert_types=unique_types,
                            ticket_count=len(cluster_indices),
                            explanation=explanation,
                        )
                    )

        return flagged

    def _find_clusters(self, group: pd.DataFrame) -> list[list[int]]:
        """
        Use TF-IDF + cosine similarity to find clusters of near-identical notes.
        Returns a list of index-lists (each list is one cluster).
        """
        notes = group["resolution_notes"].fillna("").tolist()

        # Fast path: hash-based grouping for exact duplicates first
        hash_groups: dict[str, list[int]] = {}
        for i, note in enumerate(notes):
            h = hashlib.md5(note.strip().lower().encode()).hexdigest()
            hash_groups.setdefault(h, []).append(i)

        clusters: list[list[int]] = []
        seen: set[int] = set()

        # Exact-match clusters
        for indices in hash_groups.values():
            if len(indices) >= self.min_cluster:
                clusters.append(indices)
                seen.update(indices)

        # For remaining notes, use TF-IDF for near-duplicate detection
        remaining_indices = [i for i in range(len(notes)) if i not in seen]
        if len(remaining_indices) < self.min_cluster:
            return clusters

        remaining_notes = [notes[i] for i in remaining_indices]

        try:
            vectorizer = TfidfVectorizer(
                max_features=5000,
                stop_words="english",
                ngram_range=(1, 2),
            )
            tfidf_matrix = vectorizer.fit_transform(remaining_notes)
            sim_matrix = cosine_similarity(tfidf_matrix)
        except ValueError:
            # Edge case: all notes are empty or too short for TF-IDF
            return clusters

        # Greedy clustering on the similarity matrix
        used = set()
        for i in range(len(remaining_indices)):
            if i in used:
                continue
            cluster = [remaining_indices[i]]
            for j in range(i + 1, len(remaining_indices)):
                if j in used:
                    continue
                if sim_matrix[i, j] >= self.sim_threshold:
                    cluster.append(remaining_indices[j])
                    used.add(j)
            if len(cluster) >= self.min_cluster:
                clusters.append(cluster)
                used.add(i)

        return clusters


# ════════════════════════════════════════════════
# DETECTOR 3: Blind Spot Detector
# ════════════════════════════════════════════════


class BlindSpotDetector:
    """
    Detect critical assets with statistically improbable zero (or near-zero)
    alert volumes compared to peers of the same criticality level.

    Approach:
      1. Count alerts per asset from the ticket data.
      2. Compute mean and std alert volume per criticality group.
      3. Flag assets with 0 alerts (and criticality ≥ HIGH).
      4. Also flag assets below 2 standard deviations from their group mean.
    """

    def __init__(self, z_threshold: float = 2.0):
        self.z_threshold = z_threshold

    def detect(
        self,
        alerts_df: pd.DataFrame,
        inventory_df: pd.DataFrame | None = None,
    ) -> list[BlindSpot]:
        """Run detection. Returns flagged assets."""
        if inventory_df is None or (isinstance(inventory_df, pd.DataFrame) and inventory_df.empty):
            try:
                from database import engine
                with engine.connect() as conn:
                    db_inv = pd.read_sql("SELECT * FROM asset_inventory", conn)
                if not db_inv.empty:
                    inventory_df = db_inv
            except Exception:
                pass

        if alerts_df is None or inventory_df is None or inventory_df.empty:
            return []

        alerts = _preprocess_alerts_df(alerts_df)
        inv = _preprocess_inventory_df(inventory_df)

        # Count alerts per asset
        alert_counts = alerts["dest_asset"].value_counts().to_dict()

        # Merge counts into inventory
        inv["actual_alerts"] = inv["asset_id"].map(alert_counts).fillna(0).astype(int)

        # Compute group statistics
        group_stats = inv.groupby("asset_criticality")["actual_alerts"].agg(["mean", "std"]).to_dict("index")

        flagged: list[BlindSpot] = []
        for _, row in inv.iterrows():
            crit = str(row["asset_criticality"]).upper()
            actual = int(row["actual_alerts"])
            stats = group_stats.get(crit, {"mean": 0, "std": 0})
            mean_val = float(stats.get("mean", 0) if pd.notna(stats.get("mean")) else 0)
            std_val = float(stats.get("std", 0) if pd.notna(stats.get("std")) else 0)

            # Only flag HIGH and CRITICAL assets
            if crit not in ("CRITICAL", "HIGH"):
                continue

            # Flag zero-alert assets
            if actual == 0 and mean_val > 0:
                explanation = (
                    f"CRITICAL asset '{row['asset_id']}' ({row['asset_type']}) "
                    f"generated 0 alerts over 30 days. "
                    f"Expected ~{mean_val:.1f} (σ={std_val:.1f}) based on "
                    f"{crit}-class peers. "
                    f"Possible telemetry failure or monitoring gap."
                )
                flagged.append(
                    BlindSpot(
                        asset_id=str(row["asset_id"]),
                        criticality=crit,
                        asset_type=str(row["asset_type"]),
                        actual_alerts=actual,
                        expected_mean=round(mean_val, 2),
                        expected_std=round(std_val, 2),
                        explanation=explanation,
                    )
                )
            # Flag statistically low assets (> 0 but below 2σ)
            elif std_val > 0 and actual < (mean_val - self.z_threshold * std_val) and actual > 0:
                explanation = (
                    f"Asset '{row['asset_id']}' ({crit}) has {actual} alerts, "
                    f"significantly below the {crit}-class mean of "
                    f"{mean_val:.1f} (σ={std_val:.1f}). "
                    f"Z-score: {(actual - mean_val) / std_val:.2f}. "
                    f"Investigate potential monitoring gap."
                )
                flagged.append(
                    BlindSpot(
                        asset_id=str(row["asset_id"]),
                        criticality=crit,
                        asset_type=str(row["asset_type"]),
                        actual_alerts=actual,
                        expected_mean=round(mean_val, 2),
                        expected_std=round(std_val, 2),
                        explanation=explanation,
                    )
                )

        return flagged


# ════════════════════════════════════════════════
# ORCHESTRATOR
# ════════════════════════════════════════════════


def _compute_risk_score(report: AnomalyReport, total_tickets: int) -> float:
    """
    Compute an overall risk score (0–100) based on anomaly density.

    Weighting:
      - Speed anomalies:   high weight (direct compliance risk)
      - Repetitive notes:  medium weight (process risk)
      - Blind spots:       high weight (visibility risk)
    """
    if total_tickets == 0:
        return 0.0

    speed_ratio = len(report.speed_anomalies) / total_tickets
    rep_ticket_count = sum(c.ticket_count for c in report.repetitive_notes)
    rep_ratio = rep_ticket_count / total_tickets
    blind_count = len(report.blind_spots)

    # Weighted score components (each normalised to ~0-1 then scaled)
    speed_score = min(speed_ratio * 500, 40)       # max 40 pts
    rep_score = min(rep_ratio * 300, 30)            # max 30 pts
    blind_score = min(blind_count * 6, 30)          # max 30 pts (5 assets = 30)

    return round(min(speed_score + rep_score + blind_score, 100), 1)


class AnalyticsOrchestrator:
    """
    Central coordinator that loads data, runs all detectors, and produces
    a unified AnomalyReport.
    """

    def __init__(
        self,
        alerts_df: pd.DataFrame | None = None,
        inventory_df: pd.DataFrame | None = None,
    ):
        self._alerts_df = alerts_df
        self._inventory_df = inventory_df

        # If inventory_df is not provided or empty, dynamically query PostgreSQL AssetInventory
        if self._inventory_df is None or (isinstance(self._inventory_df, pd.DataFrame) and self._inventory_df.empty):
            try:
                from database import engine
                with engine.connect() as conn:
                    db_inv = pd.read_sql("SELECT * FROM asset_inventory", conn)
                if not db_inv.empty:
                    self._inventory_df = db_inv
            except Exception:
                pass

    @property
    def alerts_df(self) -> pd.DataFrame:
        if self._alerts_df is None:
            raise RuntimeError("Data not loaded.")
        return self._alerts_df

    @property
    def inventory_df(self) -> pd.DataFrame:
        if self._inventory_df is None:
            raise RuntimeError("Data not loaded.")
        return self._inventory_df

    def run(self) -> AnomalyReport:
        """Execute all detectors and build the unified report."""
        report = AnomalyReport()

        # ── Detector 1: Speed anomalies ──
        print("\n[Engine] Running Speed Anomaly Detector ...")
        speed_det = SpeedAnomalyDetector()
        report.speed_anomalies = speed_det.detect(self.alerts_df)
        print(f"         -> {len(report.speed_anomalies)} tickets flagged.")

        # ── Detector 2: Repetitive notes ──
        print("[Engine] Running Repetitive Notes Detector ...")
        notes_det = RepetitiveNotesDetector()
        report.repetitive_notes = notes_det.detect(self.alerts_df)
        total_rep = sum(c.ticket_count for c in report.repetitive_notes)
        print(f"         -> {len(report.repetitive_notes)} clusters ({total_rep} tickets) flagged.")

        # ── Detector 3: Blind spots ──
        print("[Engine] Running Blind Spot Detector ...")
        blind_det = BlindSpotDetector()
        report.blind_spots = blind_det.detect(self.alerts_df, self.inventory_df)
        print(f"         -> {len(report.blind_spots)} assets flagged.")

        # ── Build summary ──
        total = len(self.alerts_df)
        total_flagged = (
            len(report.speed_anomalies) + total_rep + len(report.blind_spots)
        )
        risk_score = _compute_risk_score(report, total)

        # Per-analyst risk breakdown
        analyst_speed = {}
        for a in report.speed_anomalies:
            analyst_speed[a.analyst] = analyst_speed.get(a.analyst, 0) + 1
        analyst_rep = {}
        for c in report.repetitive_notes:
            analyst_rep[c.analyst] = analyst_rep.get(c.analyst, 0) + c.ticket_count

        # Merge into per-entity risk
        all_entities = set(analyst_speed.keys()) | set(analyst_rep.keys())
        entity_risk: list[dict[str, Any]] = []
        for entity in sorted(all_entities):
            speed_n = analyst_speed.get(entity, 0)
            rep_n = analyst_rep.get(entity, 0)
            entity_score = min(
                (speed_n * 3) + (rep_n * 1.5), 100
            )
            entity_risk.append(
                {
                    "entity": entity,
                    "speed_anomalies": speed_n,
                    "repetitive_notes": rep_n,
                    "risk_score": round(entity_score, 1),
                }
            )

        # Add blind-spot assets as entities
        for b in report.blind_spots:
            entity_risk.append(
                {
                    "entity": b.asset_id,
                    "blind_spot": True,
                    "actual_alerts": b.actual_alerts,
                    "expected_mean": b.expected_mean,
                    "risk_score": 90.0,  # silent critical assets get a high score
                }
            )

        # Temporal analysis: Group alerts / findings by timestamp date
        trend_map: dict[str, int] = {}
        if "timestamp" in self.alerts_df.columns:
            for ts in self.alerts_df["timestamp"].dropna():
                ts_str = str(ts).strip()
                if len(ts_str) >= 10:
                    date_str = ts_str[:10]
                    trend_map[date_str] = trend_map.get(date_str, 0) + 1

        trend_data = [
            {"date": d, "shortDate": d[5:] if len(d) >= 10 else d, "findings": c}
            for d, c in sorted(trend_map.items())
        ]
        report.trend = trend_data

        has_ttc = getattr(self.alerts_df, "attrs", {}).get("has_time_to_close", None)
        if has_ttc is None:
            has_ttc = bool(self.alerts_df["_has_time_to_close"].any()) if "_has_time_to_close" in self.alerts_df.columns else False

        has_notes = getattr(self.alerts_df, "attrs", {}).get("has_resolution_notes", None)
        if has_notes is None:
            has_notes = bool(self.alerts_df["_has_resolution_notes"].any()) if "_has_resolution_notes" in self.alerts_df.columns else False

        disabled_flags: list[str] = []
        if not has_ttc:
            disabled_flags.append("speed_anomalies: missing required column 'time_to_close_seconds'")
        if not has_notes:
            disabled_flags.append("repetitive_notes: missing required column 'resolution_notes'")

        report.summary = {
            "total_alerts": total,
            "total_flagged_anomalies": total_flagged,
            "speed_anomalies_count": len(report.speed_anomalies),
            "repetitive_notes_clusters": len(report.repetitive_notes),
            "repetitive_notes_tickets": total_rep,
            "blind_spots_count": len(report.blind_spots),
            "overall_risk_score": risk_score,
            "entity_risk": entity_risk,
            "trend": trend_data,
            "ml_capabilities": {
                "speed_anomaly_detection": bool(has_ttc),
                "repetitive_notes_detection": bool(has_notes),
                "blind_spot_detection": not self.inventory_df.empty,
            },
            "disabled_flags": disabled_flags,
        }

        print(f"\n[Engine] [OK] Analysis complete. Risk score: {risk_score}/100")
        print(f"         Total flagged: {total_flagged} items")
        return report


# ════════════════════════════════════════════════
# STANDALONE EXECUTION
# ════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SAT-SA Analytics Engine (Phase 2)")
    parser.add_argument(
        "--data-dir",
        type=str,
        default=str(Path(__file__).parent / "data"),
        help="Directory containing soc_alerts.csv and asset_inventory.csv",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Path to write JSON report (default: print to stdout)",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    orchestrator = AnalyticsOrchestrator(
        alerts_path=data_dir / "soc_alerts.csv",
        inventory_path=data_dir / "asset_inventory.csv",
    )

    report = orchestrator.run()

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(report.to_json(), encoding="utf-8")
        print(f"\n[Engine] Report written to {out_path}")
    else:
        print("\n" + "═" * 60)
        print("ANOMALY REPORT (JSON)")
        print("═" * 60)
        print(report.to_json())
