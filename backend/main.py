"""
SAT-SA — Phase 3: FastAPI Application (The Bridge)
====================================================
Serves the analytics engine output via a REST API and provides a local-LLM
explainability endpoint powered by LangChain + Ollama.

Endpoints:
  POST /api/upload                — Upload CSV, trigger analytics engine
  GET  /api/dashboard/summary     — Full anomaly report (cached in memory)
  POST /api/explain-anomaly       — LLM-generated explanation via Ollama
  GET  /api/health                — System + Ollama status

Air-gap constraints:
  - CORS locked to localhost origins only
  - All AI inference runs through a local Ollama instance (no cloud calls)
  - All data stored in local CSV / PostgreSQL — no external DB

Usage:
  cd backend/
  uvicorn main:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import io
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import aiofiles
import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

# ── Local modules ──────────────────────────────
from analytics_engine import AnalyticsOrchestrator, AnomalyReport
from supervisory_assessment import build_assessment
from priority_engine import generate_priority_queue
from report_generator import build_report, render_report

# ── Database (PostgreSQL via SQLAlchemy — air-gap safe) ──────────────────────
from database import get_db, init_db, engine
from models import (
    AssetInventory, SocAlerts, SOCAlert, SocAlertRecord,
    CaseManagement, InvestigationWorkflows, EscalationRecords, AlertClosures
)
from recommendation_engine import recommendation_engine
from sqlalchemy import select, text
from sqlalchemy.orm import Session

# ── LangChain (local only — no cloud imports) ──
try:
    from langchain_ollama import ChatOllama
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    LANGCHAIN_AVAILABLE = True
except ImportError:
    LANGCHAIN_AVAILABLE = False
    logging.warning(
        "langchain-ollama not installed. AI explanations will fall back to "
        "rule-engine text. Run: pip install langchain-ollama langchain-core"
    )

# ══════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════

DATA_DIR   = Path(__file__).parent / "data"
ALERTS_CSV = DATA_DIR / "soc_alerts.csv"
INV_CSV    = DATA_DIR / "asset_inventory.csv"

# Local Ollama settings — all inference stays on this machine
OLLAMA_BASE_URL = "http://localhost:11434"   # default Ollama port
OLLAMA_MODEL    = "llama3"                   # change to "phi3" if preferred

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("sat-sa")

# ══════════════════════════════════════════════════
# IN-MEMORY REPORT CACHE
# ══════════════════════════════════════════════════
# The report is computed on startup and on each /upload call.
# Stored as a plain dict so it serialises cleanly to JSON.

_report_cache: dict[str, Any] = {}
_assessment_cache: dict[str, Any] = {}
_priority_cache: list[dict[str, Any]] = []
_priority_status: dict[str, str] = {}
_alerts_cache: pd.DataFrame | None = None
_inventory_cache: pd.DataFrame | None = None
_cache_lock = asyncio.Lock()


def _empty_summary() -> dict[str, Any]:
    return {
        "total_alerts": 0,
        "total_flagged_anomalies": 0,
        "speed_anomalies_count": 0,
        "repetitive_notes_clusters": 0,
        "repetitive_notes_tickets": 0,
        "blind_spots_count": 0,
        "overall_risk_score": 0.0,
        "entity_risk": [],
        "trend": [],
        "ml_capabilities": {
            "speed_anomaly_detection": False,
            "repetitive_notes_detection": False,
            "blind_spot_detection": False,
        },
        "disabled_flags": [],
    }


def _wipe_all_caches() -> None:
    """
    Completely wipe all in-memory caches, global Pandas DataFrames,
    and priority status mappings holding previous ML anomalies.
    """
    global _report_cache, _assessment_cache, _priority_cache, _alerts_cache, _inventory_cache, _priority_status
    _report_cache = AnomalyReport(summary=_empty_summary()).to_dict()
    _assessment_cache = {
        "overall_score": 100.0,
        "dimensions": [],
        "findings": [],
        "evidence": [],
        "assets": [],
        "lifecycle": {
            "stages": ["Alert", "Case", "Investigation", "Escalation", "Response", "Recovery", "Closure"],
            "records_assessed": 0,
            "finding": "No records assessed.",
        },
        "basis": "Missing evidence is an assessment signal, not proof that an action did not happen.",
        "analytics_signal_count": 0,
    }
    _priority_cache = []
    _alerts_cache = None
    _inventory_cache = None
    _priority_status.clear()


# Initialize caches cleanly
_wipe_all_caches()


def _run_engine(alerts_path: Path, inv_path: Path) -> dict[str, Any]:
    """Run the analytics orchestrator synchronously and return a dict."""
    try:
        orchestrator = AnalyticsOrchestrator(
            alerts_path=alerts_path,
            inventory_path=inv_path,
        )
        report: AnomalyReport = orchestrator.run()
        return report.to_dict()
    except Exception as e:
        logger.error("ML Engine Error: %s", str(e), exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"ML Engine Error: {str(e)}",
        ) from e


async def _refresh_cache() -> None:
    """Run the analytics, assessment and priority engines pulling strictly from PostgreSQL using .outerjoin()."""
    global _report_cache, _assessment_cache, _priority_cache, _alerts_cache, _inventory_cache
    try:
        from database import engine
        import pandas as pd
        
        # Read strictly from the PostgreSQL database using .outerjoin() to prevent data loss
        with engine.connect() as conn:
            stmt = (
                select(
                    SocAlerts.id,
                    SocAlerts.timestamp,
                    SocAlerts.alert_id,
                    SocAlerts.entity_id,
                    SocAlerts.asset_name,
                    SocAlerts.alert_category,
                    SocAlerts.alert_severity,
                    SocAlerts.time_to_close_seconds,
                    SocAlerts.escalated,
                    SocAlerts.resolution_notes,
                    SocAlerts.is_speed_anomaly,
                    SocAlerts.is_repetitive_anomaly,
                    SocAlerts.is_negative_space,
                    SocAlerts.is_anomaly,
                    AssetInventory.asset_type,
                    AssetInventory.department,
                    AssetInventory.asset_criticality,
                    CaseManagement.case_id,
                    CaseManagement.sensor_id,
                    CaseManagement.mitre_tactic,
                    CaseManagement.source_ip,
                    CaseManagement.destination_ip,
                    InvestigationWorkflows.action_taken,
                    InvestigationWorkflows.action_timestamp.label("investigation_started"),
                    InvestigationWorkflows.result.label("investigation_conclusion"),
                    InvestigationWorkflows.time_spent_minutes,
                    InvestigationWorkflows.investigator,
                    EscalationRecords.escalated_from_tier,
                    EscalationRecords.escalated_to_tier,
                    EscalationRecords.escalation_reason,
                    EscalationRecords.escalation_timestamp,
                    AlertClosures.closure_id,
                    AlertClosures.closed_by,
                    AlertClosures.closure_reason,
                    AlertClosures.closure_timestamp,
                    AlertClosures.capa_action,
                )
                .select_from(SocAlerts)
                .outerjoin(AssetInventory, SocAlerts.asset_name == AssetInventory.asset_name)
                .outerjoin(CaseManagement, SocAlerts.alert_id == CaseManagement.alert_id)
                .outerjoin(InvestigationWorkflows, SocAlerts.alert_id == InvestigationWorkflows.alert_id)
                .outerjoin(EscalationRecords, SocAlerts.alert_id == EscalationRecords.alert_id)
                .outerjoin(AlertClosures, SocAlerts.alert_id == AlertClosures.alert_id)
            )
            try:
                alerts_df = pd.read_sql(stmt, conn)
            except Exception as read_exc:
                logger.warning("Outerjoin SQL read failed: %s; falling back to direct table read", read_exc)
                alerts_df = pd.read_sql("SELECT * FROM soc_alerts", conn)

            try:
                db_inventory_df = pd.read_sql(select(AssetInventory), conn)
            except Exception:
                try:
                    db_inventory_df = pd.read_sql("SELECT * FROM asset_inventory", conn)
                except Exception:
                    db_inventory_df = pd.DataFrame()

        # Build inventory_df
        if not db_inventory_df.empty:
            inventory_df = db_inventory_df.copy()
            if "asset_name" not in inventory_df.columns and "asset_id" in inventory_df.columns:
                inventory_df["asset_name"] = inventory_df["asset_id"]
        elif not alerts_df.empty and "asset_name" in alerts_df.columns:
            # Fallback baseline from alerts if no dedicated asset_inventory table data
            inventory_df = pd.DataFrame({"asset_name": alerts_df["asset_name"].dropna().unique()})
            inventory_df["asset_id"] = inventory_df["asset_name"]
            inventory_df["asset_type"] = "Server"
            inventory_df["asset_criticality"] = "HIGH"
            inventory_df["criticality"] = "HIGH"
            inventory_df["department"] = "IT Infrastructure"
        else:
            inventory_df = pd.DataFrame(columns=["asset_id", "asset_name", "asset_type", "asset_criticality", "department"])

        # Compatibility column mappings for analytics & supervisory assessment
        if not alerts_df.empty:
            if "ticket_id" not in alerts_df.columns and "alert_id" in alerts_df.columns:
                alerts_df["ticket_id"] = alerts_df["alert_id"]
            if "dest_asset" not in alerts_df.columns and "asset_name" in alerts_df.columns:
                alerts_df["dest_asset"] = alerts_df["asset_name"]
            if "alert_type" not in alerts_df.columns and "alert_category" in alerts_df.columns:
                alerts_df["alert_type"] = alerts_df["alert_category"]
            if "time_to_close" not in alerts_df.columns and "time_to_close_seconds" in alerts_df.columns:
                alerts_df["time_to_close"] = alerts_df["time_to_close_seconds"]

            # Explicit dependency validation: check whether time_to_close and resolution_notes were provided
            has_ttc = (
                ("time_to_close_seconds" in alerts_df.columns and alerts_df["time_to_close_seconds"].notna().any() and (alerts_df["time_to_close_seconds"] >= 0).any())
                or ("time_to_close" in alerts_df.columns and alerts_df["time_to_close"].notna().any() and (alerts_df["time_to_close"] >= 0).any())
            )
            alerts_df["_has_time_to_close"] = bool(has_ttc)
            alerts_df.attrs["has_time_to_close"] = bool(has_ttc)

            has_notes = (
                "resolution_notes" in alerts_df.columns
                and alerts_df["resolution_notes"].notna().any()
                and alerts_df["resolution_notes"].astype(str).str.strip().ne("").any()
            )
            alerts_df["_has_resolution_notes"] = bool(has_notes)
            alerts_df.attrs["has_resolution_notes"] = bool(has_notes)

        if alerts_df.empty and db_inventory_df.empty:
            alerts_df = pd.DataFrame(columns=[
                "alert_id", "entity_id", "asset_name", "alert_category",
                "alert_severity", "time_to_close_seconds", "escalated", "resolution_notes"
            ])
            result = AnomalyReport(summary=_empty_summary()).to_dict()
            assessment = {
                "overall_score": 100.0,
                "dimensions": [],
                "findings": [],
                "evidence": [],
                "assets": [],
                "lifecycle": {
                    "stages": ["Alert", "Case", "Investigation", "Escalation", "Response", "Recovery", "Closure"],
                    "records_assessed": 0,
                    "finding": "No records assessed.",
                },
                "basis": "Missing evidence is an assessment signal, not proof that an action did not happen.",
                "analytics_signal_count": 0,
            }
            priorities = []
        else:
            if alerts_df.empty:
                alerts_df = pd.DataFrame(columns=[
                    "alert_id", "entity_id", "asset_name", "alert_category",
                    "alert_severity", "time_to_close_seconds", "escalated", "resolution_notes"
                ])
                result = AnomalyReport(summary=_empty_summary()).to_dict()
            else:
                loop = asyncio.get_event_loop()
                def _run():
                    orchestrator = AnalyticsOrchestrator(alerts_df=alerts_df, inventory_df=inventory_df)
                    return orchestrator.run().to_dict()
                result = await loop.run_in_executor(None, _run)

            loop = asyncio.get_event_loop()
            assessment = await loop.run_in_executor(
                None,
                lambda: build_assessment(alerts_df, inventory_df, result),
            )
            priorities = await loop.run_in_executor(
                None,
                lambda: generate_priority_queue(alerts_df, inventory_df, assessment, result),
            )
            for item in priorities:
                item["status"] = _priority_status.get(item["ticket_id"], item.get("status", "NEW"))

        # Synchronize newly detected ML anomaly flags into the PostgreSQL database
        if not alerts_df.empty:
            try:
                from database import SessionLocal
                with SessionLocal() as sync_db:
                    sync_db.query(SocAlerts).update({
                        SocAlerts.is_speed_anomaly: False,
                        SocAlerts.is_repetitive_anomaly: False,
                        SocAlerts.is_negative_space: False,
                        SocAlerts.is_anomaly: False,
                    }, synchronize_session=False)

                    speed_ids = [a["ticket_id"] for a in result.get("speed_anomalies", [])]
                    if speed_ids:
                        sync_db.query(SocAlerts).filter(SocAlerts.alert_id.in_(speed_ids)).update({
                            SocAlerts.is_speed_anomaly: True,
                            SocAlerts.is_anomaly: True,
                        }, synchronize_session=False)

                    rep_ids = [t for c in result.get("repetitive_notes", []) for t in c.get("ticket_ids", [])]
                    if rep_ids:
                        sync_db.query(SocAlerts).filter(SocAlerts.alert_id.in_(rep_ids)).update({
                            SocAlerts.is_repetitive_anomaly: True,
                            SocAlerts.is_anomaly: True,
                        }, synchronize_session=False)
                    sync_db.commit()
            except Exception as sync_exc:
                logger.debug("Database ML anomaly flags sync notice: %s", sync_exc)

        async with _cache_lock:
            _report_cache = result
            _assessment_cache = assessment
            _priority_cache = priorities
            _alerts_cache = alerts_df
            _inventory_cache = inventory_df

        if not alerts_df.empty or not db_inventory_df.empty:
            logger.info("Report cache refreshed — %d alerts, %d assets, %d speed anomalies, %d blind spots",
                        len(alerts_df),
                        len(inventory_df),
                        result.get("summary", {}).get("speed_anomalies_count", 0),
                        result.get("summary", {}).get("blind_spots_count", 0))
        else:
            logger.info("Report cache refreshed — Database is empty. Displaying 0 records.")
            
    except Exception as exc:
        logger.error("Failed to refresh analytics cache: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"ML Engine Error: {str(exc)}",
        ) from exc


# ══════════════════════════════════════════════════
# LIFESPAN — run engine once on startup
# ══════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-compute the anomaly report if CSV data already exists."""
    # ── Initialise PostgreSQL schema (idempotent — CREATE TABLE IF NOT EXISTS) ──
    logger.info("Startup: initialising PostgreSQL database schema ...")
    init_db()
    logger.info("Startup: PostgreSQL schema ready (sat_sa_db.soc_alert_records)")

    logger.info("Startup: pre-computing anomaly report from DB ...")
    await _refresh_cache()
    yield
    logger.info("SAT-SA API shutting down.")


# ══════════════════════════════════════════════════
# FASTAPI APP
# ══════════════════════════════════════════════════

app = FastAPI(
    title="SAT-SA — Supervisory Analytics Tool for SOC Assessment",
    description="Local prototype API for supervisory SOC assessment using synthetic operational evidence.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — localhost only (air-gap enforcement)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ══════════════════════════════════════════════════
# PYDANTIC MODELS
# ══════════════════════════════════════════════════

class AnomalyExplainRequest(BaseModel):
    """Payload for the /api/explain-anomaly endpoint."""
    anomaly_type: str                     # "speed_anomaly" | "repetitive_notes" | "blind_spot"
    ticket_id: Optional[str] = None
    severity: Optional[str] = None
    time_to_close: Optional[int] = None
    analyst: Optional[str] = None
    alert_type: Optional[str] = None
    alert_category: Optional[str] = None
    escalated: Optional[bool] = None
    asset_id: Optional[str] = None
    actual_alerts: Optional[int] = None
    expected_mean: Optional[float] = None
    explanation: str                      # rule-engine explanation (fallback)
    resolution_notes: Optional[str] = None
    entity_id: Optional[str] = None


class AnomalyExplainResponse(BaseModel):
    """Response from the /api/explain-anomaly endpoint."""
    explanation: str
    source: str                           # "ollama" | "rule_engine"
    model: Optional[str] = None
    recommended_reference: Optional[dict[str, Any]] = None


class AuditRecommendRequest(BaseModel):
    """Payload for the /api/audit/recommend-reference endpoint."""
    ticket_id: Optional[str] = None
    entity_id: Optional[str] = None
    asset_name: Optional[str] = None
    alert_category: Optional[str] = None
    alert_severity: Optional[str] = None
    resolution_notes: Optional[str] = None


class PriorityStatusUpdate(BaseModel):
    status: str


class ReportExportRequest(BaseModel):
    scope: str = "assessment"
    format: str = "json"
    filters: dict[str, Any] = {}
    ticket_id: Optional[str] = None


# ══════════════════════════════════════════════════
# LANGCHAIN PROMPT TEMPLATE
# ══════════════════════════════════════════════════

_EXPLAIN_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        (
            "You are a senior SOC assessment analyst supporting an internal supervisory review. "
            "Your tone is authoritative, concise, and professional. "
            "You write exactly 2 sentences — no more, no less. "
            "The first sentence states what the anomaly is and why it is operationally impossible or suspicious. "
            "The second sentence states what specific evidence a supervisor should request during an audit."
        ),
    ),
    (
        "human",
        (
            "Anomaly Type: {anomaly_type}\n"
            "Ticket ID: {ticket_id}\n"
            "Severity: {severity}\n"
            "Time to Close: {time_to_close} seconds\n"
            "Analyst: {analyst}\n"
            "Alert Type: {alert_type}\n"
            "Escalated: {escalated}\n"
            "Asset ID: {asset_id}\n"
            "Actual Alerts: {actual_alerts}\n"
            "Expected Mean Alerts: {expected_mean}\n"
            "Rule-Engine Finding: {explanation}\n\n"
            "Write your 2-sentence audit finding:"
        ),
    ),
])


def _build_llm_chain(timeout: float = 5.0):
    """Build the LangChain chain. Returns None if Ollama is unavailable."""
    if not LANGCHAIN_AVAILABLE:
        return None
    try:
        llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.3,         # low temp for consistent, professional output
            num_predict=200,         # cap output length — 2 sentences is enough
        )
        chain = _EXPLAIN_PROMPT | llm | StrOutputParser()
        return chain
    except Exception as exc:
        logger.warning("Could not build LangChain chain: %s", exc)
        return None


async def generate_llm_rationale(
    payload: dict[str, Any],
    fallback_text: Optional[str] = None,
    timeout: float = 5.0,
) -> tuple[str, str]:
    """
    Execute generation request against local Ollama API with strict timeout
    and graceful offline/error fallback.

    Returns:
        tuple[str, str]: (rationale_text, source)
    """
    default_fallback = (
        fallback_text
        if fallback_text and fallback_text.strip()
        else "AI rationale generation bypassed: Local LLM engine is currently unreachable. Anomaly flagged by statistical engine."
    )

    try:
        chain = _build_llm_chain(timeout=timeout)
        if chain is None:
            logger.warning("Local LLM engine unavailable. Bypassing AI rationale generation.")
            return (
                default_fallback,
                "rule_engine" if fallback_text else "fallback",
            )

        # Ensure all template variables have safe defaults
        full_payload = {
            "anomaly_type": str(payload.get("anomaly_type") or "anomaly"),
            "ticket_id": str(payload.get("ticket_id") or "N/A"),
            "severity": str(payload.get("severity") or "N/A"),
            "time_to_close": str(payload.get("time_to_close") or "N/A"),
            "analyst": str(payload.get("analyst") or "N/A"),
            "alert_type": str(payload.get("alert_type") or "N/A"),
            "escalated": str(payload.get("escalated") if payload.get("escalated") is not None else "N/A"),
            "asset_id": str(payload.get("asset_id") or "N/A"),
            "actual_alerts": str(payload.get("actual_alerts") if payload.get("actual_alerts") is not None else "N/A"),
            "expected_mean": str(payload.get("expected_mean") if payload.get("expected_mean") is not None else "N/A"),
            "explanation": str(payload.get("explanation") or "Statistical anomaly flagged."),
        }

        # Enforce strict 5.0 second timeout to avoid pipeline blocking or 500 timeouts
        result: str = await asyncio.wait_for(chain.ainvoke(full_payload), timeout=timeout)
        cleaned = result.strip() if result else default_fallback
        return (cleaned, "ollama")

    except asyncio.TimeoutError as te:
        logger.warning(
            "Local LLM rationale generation timed out after %.1fs (%s). Returning fallback rationale.",
            timeout,
            te,
        )
        return (
            "AI rationale generation bypassed: Local LLM engine is currently unreachable. Anomaly flagged by statistical engine.",
            "fallback",
        )
    except Exception as exc:
        logger.warning(
            "Local LLM API error during rationale generation (%s). Returning fallback rationale.",
            exc,
        )
        return (
            "AI rationale generation bypassed: Local LLM engine is currently unreachable. Anomaly flagged by statistical engine.",
            "fallback",
        )


# ══════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════

@app.get("/api/health", summary="System and Ollama health check")
async def health_check():
    """Returns system status and whether the local Ollama service is reachable."""
    ollama_ok = False
    ollama_error = None

    if LANGCHAIN_AVAILABLE:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=3.0) as client:
                r = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                ollama_ok = r.status_code == 200
        except Exception as exc:
            ollama_error = str(exc)
    else:
        ollama_error = "langchain-ollama package not installed"

    return {
        "status": "ok",
        "data_loaded": bool(_report_cache),
        "ollama_available": ollama_ok,
        "ollama_model": OLLAMA_MODEL,
        "ollama_url": OLLAMA_BASE_URL,
        "ollama_error": ollama_error,
        "langchain_installed": LANGCHAIN_AVAILABLE,
    }


import zipfile

# ── Hierarchical Ingestion Helpers ──────────────────────────────────────────
HIERARCHY_LEVELS = {
    "asset_inventory": 1,
    "soc_alerts": 2,
    "case_management": 3,
    "investigation_workflows": 4,
    "escalation_records": 5,
    "alert_closures": 6,
}


def _clean_str(val: Any) -> Optional[str]:
    if pd.isna(val) or val is None:
        return None
    val_str = str(val).strip()
    return val_str if val_str else None


def _clean_int(val: Any) -> Optional[int]:
    if pd.isna(val) or val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _clean_bool(val: Any, default: bool = False) -> bool:
    if pd.isna(val) or val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return bool(val)
    if isinstance(val, str):
        return val.strip().lower() in {"true", "1", "yes", "t"}
    return default


def _detect_dataset_type(df: pd.DataFrame, filename: str = "") -> str:
    cols = {str(c).strip().lower().replace(" ", "_") for c in df.columns}
    fname = filename.lower()

    if "inventory" in fname or (
        ("asset_type" in cols or "department" in cols or "asset_criticality" in cols)
        and not ("alert_id" in cols or "ticket_id" in cols)
    ):
        return "asset_inventory"

    if "escalation" in fname or ("escalation_id" in cols or "escalated_from_tier" in cols or "escalation_reason" in cols):
        return "escalation_records"

    if "workflow" in fname or "investigation" in fname or ("workflow_id" in cols or "action_taken" in cols or "time_spent_minutes" in cols):
        return "investigation_workflows"

    if "closure" in fname or ("closure_id" in cols or "capa_action" in cols or "closure_reason" in cols or "closed_by" in cols):
        return "alert_closures"

    if "case" in fname or (
        ("sensor_id" in cols or "mitre_tactic" in cols or "source_ip" in cols or "destination_ip" in cols)
        and not ("time_to_close_seconds" in cols or "time_to_close" in cols)
    ):
        return "case_management"

    if "alert_id" in cols or "ticket_id" in cols or "time_to_close_seconds" in cols or "alert_category" in cols:
        return "soc_alerts"

    if "asset_name" in cols or "asset_id" in cols:
        return "asset_inventory"

    return "soc_alerts"


def _ingest_hierarchical_datasets(
    datasets: list[tuple[str, str, pd.DataFrame]],
    db: Session,
) -> dict[str, Any]:
    """
    Ingests parsed datasets strictly in parent-first hierarchical order:
      1. asset_inventory
      2. soc_alerts
      3. case_management
      4. investigation_workflows
      5. escalation_records
      6. alert_closures
    Guarantees zero Foreign Key violations by ensuring parent records exist before inserting child rows.
    """
    # Sort strictly by defined hierarchy order
    sorted_datasets = sorted(datasets, key=lambda item: HIERARCHY_LEVELS.get(item[0], 99))
    results_summary: dict[str, int] = {}

    for dtype, fname, df in sorted_datasets:
        # Standardize column headers
        df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]

        if dtype == "asset_inventory":
            # ── 1. ASSET INVENTORY (Root Parent) ──────────────────────────
            records = []
            seen = set()
            for _, row in df.iterrows():
                asset_name = _clean_str(row.get("asset_name") or row.get("asset_id") or row.get("asset"))
                if not asset_name or asset_name in seen:
                    continue
                seen.add(asset_name)
                records.append({
                    "asset_name": asset_name,
                    "asset_type": _clean_str(row.get("asset_type") or row.get("type")) or "Server",
                    "department": _clean_str(row.get("department") or row.get("dept")) or "IT",
                    "asset_criticality": (_clean_str(row.get("asset_criticality") or row.get("criticality")) or "MEDIUM").upper(),
                })
            if records:
                for rec in records:
                    db.merge(AssetInventory(**rec))
                db.commit()
                results_summary["asset_inventory"] = len(records)
                logger.info("Hierarchical Ingestion: Upserted %d records into asset_inventory.", len(records))

        elif dtype == "soc_alerts":
            # ── 2. SOC ALERTS (Child of asset_inventory, Parent of Evidence) ──
            # Step A: Enforce FK integrity on asset_name by pre-seeding missing assets
            all_assets = {
                _clean_str(row.get("asset_name") or row.get("dest_asset") or row.get("asset"))
                for _, row in df.iterrows()
            } - {None}

            if all_assets:
                existing_assets = {
                    a[0] for a in db.query(AssetInventory.asset_name).filter(AssetInventory.asset_name.in_(all_assets)).all()
                }
                missing_assets = all_assets - existing_assets
                if missing_assets:
                    for m in missing_assets:
                        db.add(AssetInventory(
                            asset_name=m,
                            asset_type="Server",
                            department="IT Infrastructure",
                            asset_criticality="HIGH",
                        ))
                    db.commit()
                    logger.info("Hierarchical Ingestion: Pre-seeded %d missing parent assets into asset_inventory.", len(missing_assets))

            # Step B: Insert SOC alerts
            alert_records = []
            seen_alerts = set()
            for _, row in df.iterrows():
                raw_alert_id = _clean_str(row.get("alert_id") or row.get("ticket_id"))
                if not raw_alert_id or raw_alert_id in seen_alerts:
                    continue
                seen_alerts.add(raw_alert_id)

                raw_timestamp = (
                    row.get("timestamp")
                    if "timestamp" in row and pd.notna(row["timestamp"])
                    else (row.get("date") or row.get("time") or row.get("created_at"))
                )
                raw_entity_id = row.get("entity_id") if "entity_id" in row else row.get("entity")
                raw_asset_name = row.get("asset_name") if "asset_name" in row else (row.get("dest_asset") or row.get("asset"))
                raw_category = row.get("alert_category") if "alert_category" in row else (row.get("alert_type") or row.get("category"))
                raw_severity = row.get("alert_severity") if "alert_severity" in row else row.get("severity")
                raw_ttc = row.get("time_to_close_seconds") if "time_to_close_seconds" in row else row.get("time_to_close")
                raw_notes = row.get("resolution_notes") if "resolution_notes" in row else row.get("notes")

                alert_records.append({
                    "timestamp": _clean_str(raw_timestamp),
                    "alert_id": raw_alert_id,
                    "entity_id": _clean_str(raw_entity_id),
                    "asset_name": _clean_str(raw_asset_name),
                    "alert_category": _clean_str(raw_category),
                    "alert_severity": _clean_str(raw_severity),
                    "time_to_close_seconds": _clean_int(raw_ttc),
                    "escalated": _clean_bool(row.get("escalated")),
                    "resolution_notes": _clean_str(raw_notes),
                    "is_speed_anomaly": _clean_bool(row.get("is_speed_anomaly"), False),
                    "is_repetitive_anomaly": _clean_bool(row.get("is_repetitive_anomaly"), False),
                    "is_negative_space": _clean_bool(row.get("is_negative_space"), False),
                    "is_anomaly": _clean_bool(row.get("is_anomaly"), False),
                })

            if alert_records:
                for rec in alert_records:
                    existing = db.query(SocAlerts).filter(SocAlerts.alert_id == rec["alert_id"]).first()
                    if existing:
                        for k, v in rec.items():
                            setattr(existing, k, v)
                    else:
                        db.add(SocAlerts(**rec))
                db.commit()
                results_summary["soc_alerts"] = len(alert_records)
                logger.info("Hierarchical Ingestion: Ingested %d records into soc_alerts.", len(alert_records))

        elif dtype == "case_management":
            # ── 3. CASE MANAGEMENT (Child of soc_alerts) ───────────────────
            case_records = []
            for _, row in df.iterrows():
                alert_id = _clean_str(row.get("alert_id") or row.get("ticket_id"))
                if not alert_id:
                    continue
                # Ensure parent alert exists
                parent = db.query(SocAlerts).filter(SocAlerts.alert_id == alert_id).first()
                if not parent:
                    parent = SocAlerts(
                        alert_id=alert_id,
                        timestamp=_clean_str(row.get("timestamp")),
                        alert_category=_clean_str(row.get("alert_name") or row.get("category")),
                        alert_severity=_clean_str(row.get("severity") or "Medium"),
                    )
                    db.add(parent)
                    db.flush()

                case_records.append({
                    "case_id": _clean_str(row.get("case_id")),
                    "alert_id": alert_id,
                    "timestamp": _clean_str(row.get("timestamp")),
                    "sensor_id": _clean_str(row.get("sensor_id")),
                    "alert_name": _clean_str(row.get("alert_name")),
                    "severity": _clean_str(row.get("severity")),
                    "mitre_tactic": _clean_str(row.get("mitre_tactic")),
                    "source_ip": _clean_str(row.get("source_ip")),
                    "destination_ip": _clean_str(row.get("destination_ip")),
                    "asset_id": _clean_str(row.get("asset_id")),
                })

            if case_records:
                db.bulk_insert_mappings(CaseManagement, case_records)
                db.commit()
                results_summary["case_management"] = len(case_records)
                logger.info("Hierarchical Ingestion: Inserted %d records into case_management.", len(case_records))

        elif dtype == "investigation_workflows":
            # ── 4. INVESTIGATION WORKFLOWS (Child of soc_alerts) ───────────
            wf_records = []
            for _, row in df.iterrows():
                alert_id = _clean_str(row.get("alert_id"))
                case_id = _clean_str(row.get("case_id"))
                if not alert_id and case_id:
                    # Resolve alert_id from CaseManagement if available
                    linked = db.query(CaseManagement).filter(CaseManagement.case_id == case_id).first()
                    if linked:
                        alert_id = linked.alert_id
                    else:
                        alert_id = case_id  # fallback to case_id as alert_id stub

                if not alert_id:
                    continue

                parent = db.query(SocAlerts).filter(SocAlerts.alert_id == alert_id).first()
                if not parent:
                    parent = SocAlerts(alert_id=alert_id, alert_category="Investigated Case", alert_severity="Medium")
                    db.add(parent)
                    db.flush()

                wf_records.append({
                    "workflow_id": _clean_str(row.get("workflow_id")),
                    "alert_id": alert_id,
                    "case_id": case_id,
                    "action_taken": _clean_str(row.get("action_taken")),
                    "action_timestamp": _clean_str(row.get("action_timestamp")),
                    "result": _clean_str(row.get("result")),
                    "time_spent_minutes": _clean_int(row.get("time_spent_minutes")),
                    "investigator": _clean_str(row.get("investigator") or row.get("analyst")),
                })

            if wf_records:
                db.bulk_insert_mappings(InvestigationWorkflows, wf_records)
                db.commit()
                results_summary["investigation_workflows"] = len(wf_records)
                logger.info("Hierarchical Ingestion: Inserted %d records into investigation_workflows.", len(wf_records))

        elif dtype == "escalation_records":
            # ── 5. ESCALATION RECORDS (Child of soc_alerts) ────────────────
            esc_records = []
            for _, row in df.iterrows():
                alert_id = _clean_str(row.get("alert_id"))
                case_id = _clean_str(row.get("case_id"))
                if not alert_id and case_id:
                    linked = db.query(CaseManagement).filter(CaseManagement.case_id == case_id).first()
                    if linked:
                        alert_id = linked.alert_id
                    else:
                        alert_id = case_id

                if not alert_id:
                    continue

                parent = db.query(SocAlerts).filter(SocAlerts.alert_id == alert_id).first()
                if not parent:
                    parent = SocAlerts(alert_id=alert_id, alert_category="Escalated Case", alert_severity="High", escalated=True)
                    db.add(parent)
                    db.flush()

                esc_records.append({
                    "escalation_id": _clean_str(row.get("escalation_id")),
                    "alert_id": alert_id,
                    "case_id": case_id,
                    "escalated_from_tier": _clean_str(row.get("escalated_from_tier")),
                    "escalated_to_tier": _clean_str(row.get("escalated_to_tier")),
                    "escalation_reason": _clean_str(row.get("escalation_reason")),
                    "escalation_timestamp": _clean_str(row.get("escalation_timestamp")),
                })

            if esc_records:
                db.bulk_insert_mappings(EscalationRecords, esc_records)
                db.commit()
                results_summary["escalation_records"] = len(esc_records)
                logger.info("Hierarchical Ingestion: Inserted %d records into escalation_records.", len(esc_records))

        elif dtype == "alert_closures":
            # ── 6. ALERT CLOSURES (Child of soc_alerts) ────────────────────
            closure_records = []
            for _, row in df.iterrows():
                alert_id = _clean_str(row.get("alert_id"))
                if not alert_id:
                    continue

                parent = db.query(SocAlerts).filter(SocAlerts.alert_id == alert_id).first()
                if not parent:
                    parent = SocAlerts(alert_id=alert_id, alert_category="Closed Incident", alert_severity="Low")
                    db.add(parent)
                    db.flush()

                closure_records.append({
                    "closure_id": _clean_str(row.get("closure_id")),
                    "alert_id": alert_id,
                    "closed_by": _clean_str(row.get("closed_by") or row.get("analyst")),
                    "closure_reason": _clean_str(row.get("closure_reason")),
                    "resolution_notes": _clean_str(row.get("resolution_notes")),
                    "closure_timestamp": _clean_str(row.get("closure_timestamp")),
                    "capa_action": _clean_str(row.get("capa_action")),
                    "is_verified": _clean_bool(row.get("is_verified"), False),
                })

            if closure_records:
                db.bulk_insert_mappings(AlertClosures, closure_records)
                db.commit()
                results_summary["alert_closures"] = len(closure_records)
                logger.info("Hierarchical Ingestion: Inserted %d records into alert_closures.", len(closure_records))

    return results_summary


@app.post("/upload", summary="Upload and ingest SOC evidence datasets (.csv, .json, or .zip)")
@app.post("/api/upload", summary="Upload and ingest SOC evidence datasets (.csv, .json, or .zip)")
async def upload_file(
    request: Request,
    file: Optional[UploadFile] = File(None),
    files: Optional[list[UploadFile]] = File(None),
    strict_schema: bool = Query(False, description="Throw 422 if required ML columns (time_to_close_seconds, resolution_notes) are missing"),
    db: Session = Depends(get_db),
):
    """
    Ingest one or multiple SOC evidence datasets in CSV, JSON, or ZIP format strictly in hierarchical order:
      Parent Tables First:  1. AssetInventory -> 2. SocAlerts
      Child Tables Last:    3. CaseManagement -> 4. InvestigationWorkflows -> 5. EscalationRecords -> 6. AlertClosures
    Prevents Foreign Key violation errors, completely clears previous caches and anomalies,
    and refreshes analytics using .outerjoin(). Supports single or multiple file uploads simultaneously.
    """
    # ── State Invalidation 1: Wipe all in-memory caches immediately upon upload request ──
    async with _cache_lock:
        _wipe_all_caches()

    # Collect all uploaded files from form, files list, and single file argument
    uploaded_files: list[UploadFile] = []
    seen_ids = set()

    try:
        form = await request.form()
        for key in ("files", "file"):
            for item in form.getlist(key):
                if hasattr(item, "filename") and id(item) not in seen_ids:
                    seen_ids.add(id(item))
                    uploaded_files.append(item)
        for _, item in form.multi_items():
            if hasattr(item, "filename") and id(item) not in seen_ids:
                seen_ids.add(id(item))
                uploaded_files.append(item)
    except Exception:
        pass

    if not uploaded_files:
        if files:
            for f in files:
                if id(f) not in seen_ids:
                    seen_ids.add(id(f))
                    uploaded_files.append(f)
        if file and id(file) not in seen_ids:
            seen_ids.add(id(file))
            uploaded_files.append(file)

    if not uploaded_files:
        raise HTTPException(
            status_code=400,
            detail="No files uploaded. Please attach at least one .csv, .json, or .zip file.",
        )

    extracted_tables: list[tuple[str, str, pd.DataFrame]] = []
    processed_filenames: list[str] = []
    case_saved_files: list[str] = []

    for up_file in uploaded_files:
        filename = up_file.filename or "uploaded_dataset"
        extension = Path(filename).suffix.lower()

        if extension not in {".csv", ".json", ".zip", ".pdf", ".docx"}:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format '{extension}' for file '{filename}'. Please upload a .csv, .json, or .zip file.",
            )

        # Handle document uploads (PDF/DOCX) for case reviews
        if extension in {".pdf", ".docx"}:
            case_dir = DATA_DIR / "case_uploads"
            case_dir.mkdir(parents=True, exist_ok=True)
            destination = case_dir / filename
            async with aiofiles.open(destination, "wb") as out:
                while chunk := await up_file.read(1024 * 64):
                    await out.write(chunk)
            case_saved_files.append(filename)
            processed_filenames.append(filename)
            continue

        contents = await up_file.read()
        if not contents:
            continue

        processed_filenames.append(filename)

        try:
            if extension == ".zip":
                # Extract multiple datasets from zip archive
                with zipfile.ZipFile(io.BytesIO(contents)) as z:
                    for z_name in z.namelist():
                        z_ext = Path(z_name).suffix.lower()
                        if z_ext in {".csv", ".json"} and not z_name.startswith("__MACOSX"):
                            raw_data = z.read(z_name)
                            if z_ext == ".csv":
                                df = pd.read_csv(io.BytesIO(raw_data))
                            else:
                                df = pd.read_json(io.BytesIO(raw_data))
                            if not df.empty:
                                dtype = _detect_dataset_type(df, z_name)
                                extracted_tables.append((dtype, z_name, df))
            elif extension == ".csv":
                df = pd.read_csv(io.BytesIO(contents))
                if not df.empty:
                    dtype = _detect_dataset_type(df, filename)
                    extracted_tables.append((dtype, filename, df))
            elif extension == ".json":
                df = pd.read_json(io.BytesIO(contents))
                if not df.empty:
                    dtype = _detect_dataset_type(df, filename)
                    extracted_tables.append((dtype, filename, df))
        except Exception as parse_exc:
            logger.error("Failed to parse uploaded %s file '%s': %s", extension, filename, parse_exc)
            raise HTTPException(
                status_code=400,
                detail=f"Failed to parse {extension.upper()} file '{filename}': {str(parse_exc)}",
            )

    if not extracted_tables and case_saved_files:
        return {
            "status": "success",
            "message": f"{len(case_saved_files)} case document(s) uploaded for local review: {', '.join(case_saved_files)}.",
            "filename": ", ".join(case_saved_files),
            "files_processed": case_saved_files,
            "records_ingested": 0,
            "total_records": 0,
        }

    if not extracted_tables:
        raise HTTPException(status_code=400, detail="The uploaded file(s) contain no data rows or recognizable tables.")

    # ── Dependency Check & Schema Validation ──
    for dtype, tbl_name, tdf in extracted_tables:
        tcols = {str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in tdf.columns}
        if dtype == "soc_alerts":
            # Ensure primary key exists
            if not ({"alert_id", "ticket_id", "id"} & tcols):
                raise HTTPException(
                    status_code=422,
                    detail=f"Unprocessable Entity: Schema in '{tbl_name}' is missing primary identifier 'alert_id' or 'ticket_id'.",
                )
            
            has_ttc = bool({"time_to_close_seconds", "time_to_close", "close_time", "ttc"} & tcols)
            has_notes = bool({"resolution_notes", "notes", "resolution"} & tcols)

            if strict_schema and (not has_ttc or not has_notes):
                missing_cols = []
                if not has_ttc:
                    missing_cols.append("time_to_close_seconds")
                if not has_notes:
                    missing_cols.append("resolution_notes")
                raise HTTPException(
                    status_code=422,
                    detail=f"Unprocessable Entity: Schema in '{tbl_name}' lacks required columns for ML analytics: {', '.join(missing_cols)}. Upload with these columns or run with graceful ML degradation.",
                )

    # ── State Invalidation 2: Targeted table wiping based on uploaded datasets ──
    try:
        uploaded_types = {dt for dt, _, _ in extracted_tables}
        # If uploading new alerts (soc_alerts) or any multi-table bundle/zip, wipe previous alerts & child tables
        if "soc_alerts" in uploaded_types or any(Path(f).suffix.lower() == ".zip" for f in processed_filenames):
            db.query(AlertClosures).delete()
            db.query(EscalationRecords).delete()
            db.query(InvestigationWorkflows).delete()
            db.query(CaseManagement).delete()
            db.query(SocAlerts).delete()
            if "asset_inventory" in uploaded_types:
                db.query(AssetInventory).delete()
        else:
            # If uploading a specific child evidence table, only wipe that specific table
            if "alert_closures" in uploaded_types:
                db.query(AlertClosures).delete()
            if "escalation_records" in uploaded_types:
                db.query(EscalationRecords).delete()
            if "investigation_workflows" in uploaded_types:
                db.query(InvestigationWorkflows).delete()
            if "case_management" in uploaded_types:
                db.query(CaseManagement).delete()
            if "asset_inventory" in uploaded_types:
                db.query(AssetInventory).delete()
        db.commit()
    except Exception as wipe_err:
        db.rollback()
        logger.warning("Database pre-upload table wipe notice: %s", wipe_err)

    try:
        summary_results = _ingest_hierarchical_datasets(extracted_tables, db)
    except Exception as db_exc:
        db.rollback()
        logger.error("Hierarchical ingestion error: %s", db_exc, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Database hierarchical ingestion error: {str(db_exc)}",
        )

    # Refresh analytics caches using .outerjoin() query
    try:
        await _refresh_cache()
    except HTTPException:
        raise
    except Exception as engine_err:
        logger.error("ML Engine failed on uploaded file: %s", engine_err, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"ML Engine Error: {str(engine_err)}",
        )

    total_records = sum(summary_results.values())
    primary_dataset = extracted_tables[0][0] if len(extracted_tables) == 1 else "relational_evidence_bundle"
    ml_caps = _report_cache.get("summary", {}).get("ml_capabilities", {})
    disabled_flags = _report_cache.get("summary", {}).get("disabled_flags", [])
    display_filename = ", ".join(processed_filenames) if len(processed_filenames) > 1 else (processed_filenames[0] if processed_filenames else "uploaded_datasets")

    return {
        "status": "success",
        "dataset_type": primary_dataset,
        "message": f"Hierarchical ingestion complete: {total_records} records ingested across {len(extracted_tables)} dataset table(s) from {len(processed_filenames)} file(s).",
        "filename": display_filename,
        "files_processed": processed_filenames,
        "summary": summary_results,
        "records_ingested": total_records,
        "total_records": total_records,
        "ml_capabilities": ml_caps,
        "ml_flags_disabled": disabled_flags,
    }


@app.delete("/api/data/clear", summary="Clear all SOC and Asset records from database")
@app.delete("/data/clear", summary="Clear all SOC and Asset records from database")
async def clear_database(db: Session = Depends(get_db)):
    """
    Wipe all existing records from the PostgreSQL database in strict reverse hierarchical order
    (Child tables first, then Parent tables) and completely reset all in-memory analytics caches.
    """
    # ── State Invalidation: Wipe all in-memory caches immediately ──
    async with _cache_lock:
        _wipe_all_caches()

    try:
        # Reverse hierarchical deletion to prevent Foreign Key reference errors
        db.query(AlertClosures).delete()
        db.query(EscalationRecords).delete()
        db.query(InvestigationWorkflows).delete()
        db.query(CaseManagement).delete()
        db.query(SocAlerts).delete()
        db.query(AssetInventory).delete()
        db.commit()
        logger.info("PostgreSQL: All records deleted in reverse hierarchical order from all 6 tables.")

        # Synchronously refresh in-memory analytics caches from the now-empty database
        await _refresh_cache()

        return {
            "status": "success",
            "message": "Database and all in-memory analytics caches completely cleared across all normalized relational tables.",
        }
    except Exception as e:
        db.rollback()
        logger.error("Failed to clear database: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear database: {str(e)}",
        )


@app.get("/api/dashboard/summary", summary="Full anomaly report")
async def dashboard_summary():
    """
    Returns the cached anomaly report including:
    - summary metrics and entity risk scores
    - speed_anomalies list
    - repetitive_notes list
    - blind_spots list
    """
    if not _report_cache:
        raise HTTPException(
            status_code=503,
            detail=(
                "No data loaded yet. Either upload a CSV via POST /api/upload "
                "or ensure soc_alerts.csv exists in the data/ directory "
                "and restart the server."
            ),
        )
    return _report_cache


def _require_assessment() -> dict[str, Any]:
    if not _assessment_cache:
        raise HTTPException(
            status_code=503,
            detail="No assessment data loaded. Upload a CSV or restart with local data.",
        )
    return _assessment_cache


@app.get("/api/assessment", summary="Supervisory assessment dimensions and lifecycle")
async def assessment_summary():
    return _require_assessment()


@app.get("/api/findings", summary="Supervisory findings work queue")
async def assessment_findings():
    return {"findings": _require_assessment()["findings"]}


@app.get("/api/evidence", summary="Ticket evidence review records")
async def evidence_records():
    return {"evidence": _require_assessment()["evidence"]}


@app.get("/api/evidence/{ticket_id}", summary="Evidence detail for one ticket")
async def evidence_detail(ticket_id: str, db: Session = Depends(get_db)):
    for record in _require_assessment()["evidence"]:
        if record["ticket_id"] == ticket_id:
            rec = recommendation_engine.find_recommendation(record, db=db)
            return {**record, "recommended_reference": rec}
    raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} was not found.")


@app.get("/api/assets", summary="Asset monitoring assessment")
async def asset_monitoring():
    return {"assets": _require_assessment()["assets"]}


@app.get("/api/data-quality", summary="Dataset quality and processing metadata")
async def data_quality():
    assessment = _require_assessment()
    alerts = _alerts_cache
    if alerts is None:
        raise HTTPException(status_code=503, detail="Dataset cache is not ready.")
    timestamps = pd.to_datetime(alerts.get("timestamp"), errors="coerce")
    return {
        "dataset": {
            "file_name": ALERTS_CSV.name,
            "records": len(alerts),
            "date_range": {"start": timestamps.min().isoformat() if not timestamps.isna().all() else None, "end": timestamps.max().isoformat() if not timestamps.isna().all() else None},
            "assets": len(assessment["assets"]),
            "analysts": int(alerts["assigned_analyst"].nunique()) if "assigned_analyst" in alerts else 0,
            "last_processed": timestamps.max().isoformat() if not timestamps.isna().all() else None,
        },
        "data_quality": {
            "missing_values": int(alerts.isna().sum().sum()),
            "duplicate_ids": int(alerts["ticket_id"].duplicated().sum()) if "ticket_id" in alerts else 0,
            "invalid_timestamps": int(timestamps.isna().sum()),
            "missing_severity": int(alerts["alert_severity"].isna().sum()) if "alert_severity" in alerts else len(alerts),
            "missing_escalation_field": int(alerts["escalated"].isna().sum()) if "escalated" in alerts else len(alerts),
        },
        "processing": {"local_processing": "Operational", "analytics_engine": "Operational", "last_analysis": timestamps.max().isoformat() if not timestamps.isna().all() else None},
    }


def _require_priorities() -> list[dict[str, Any]]:
    if not _priority_cache:
        raise HTTPException(status_code=503, detail="No priority data loaded. Upload a CSV or restart with local data.")
    return _priority_cache


@app.get("/api/priorities", summary="AI-assisted case review priority queue")
async def priorities(severity: Optional[str] = None, status: Optional[str] = None, analyst: Optional[str] = None, asset: Optional[str] = None):
    queue = _require_priorities()
    return {"recommendation_only": True, "decision_authority": "analyst", "priorities": [item for item in queue if (not severity or item["severity"] == severity.upper()) and (not status or item["status"] == status.upper()) and (not analyst or item["analyst"] == analyst) and (not asset or item["asset"] == asset)]}


@app.get("/api/priorities/{ticket_id}", summary="Priority detail for one ticket")
async def priority_detail(ticket_id: str, db: Session = Depends(get_db)):
    for item in _require_priorities():
        if item["ticket_id"] == ticket_id:
            rec = recommendation_engine.find_recommendation(item, db=db)
            return {"recommendation_only": True, **item, "recommended_reference": rec}
    raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} was not found.")


@app.patch("/api/priorities/{ticket_id}/status", summary="Update analyst review status")
async def update_priority_status(ticket_id: str, update: PriorityStatusUpdate):
    allowed = {"NEW", "UNDER_REVIEW", "ASSIGNED", "INVESTIGATING", "ESCALATED", "RESOLVED", "CLOSED"}
    status = update.status.upper()
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(sorted(allowed))}")
    for item in _require_priorities():
        if item["ticket_id"] == ticket_id:
            _priority_status[ticket_id] = status
            item["status"] = status
            return item
    raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} was not found.")


@app.post("/api/reports/export", summary="Generate a local SAT-SA report")
async def export_report(request: ReportExportRequest):
    assessment = _require_assessment()
    if not _report_cache:
        raise HTTPException(status_code=503, detail="No analytics data loaded.")
    quality = await data_quality()
    ticket = None
    if request.ticket_id:
        ticket = next((item for item in assessment["evidence"] if item["ticket_id"] == request.ticket_id), None)
        if ticket:
            ticket["priority"] = next((item for item in _priority_cache if item["ticket_id"] == request.ticket_id), None)
            ticket["findings"] = [finding for finding in assessment["findings"] if finding.get("entity") == request.ticket_id]
    filters = request.filters or {}
    filtered_priorities = [item for item in _priority_cache if all(not filters.get(key) or str(item.get(key, "")).upper() == str(value).upper() for key, value in filters.items() if key in {"severity", "status", "analyst", "asset"})]
    filtered_assessment = dict(assessment)
    if filters.get("status"):
        filtered_assessment["findings"] = [finding for finding in assessment["findings"] if str(finding.get("status", "")).upper() == str(filters["status"]).upper()]
    try:
        report = build_report(request.scope, filtered_assessment, _report_cache, filtered_priorities, quality, ticket)
        content, media_type = render_report(report, request.format)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filename = f"sat-sa-{request.scope}.{request.format}"
    return Response(content=content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


# ══════════════════════════════════════════════════════════════════════════════
# CROSS-CSE AUDIT RECOMMENDATION ENGINE ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/api/audit/recommend-reference", summary="Cross-CSE Audit Recommendation via Local TF-IDF NLP Similarity")
async def recommend_reference(request: AuditRecommendRequest, db: Session = Depends(get_db)):
    """
    Given a ticket/anomaly being audited on the supervisor dashboard, runs an offline
    TF-IDF cosine similarity text-matching engine against historically audited tickets.
    Returns recommended_reference if match > 85%.
    """
    target = request.model_dump()
    # If ticket_id provided, look up full context if resolution_notes missing
    if target.get("ticket_id") and not target.get("resolution_notes"):
        t_id = target["ticket_id"]
        db_alert = db.query(SocAlerts).filter(SocAlerts.alert_id == t_id).first()
        if db_alert:
            target["resolution_notes"] = db_alert.resolution_notes
            target["alert_category"] = target.get("alert_category") or db_alert.alert_category
            target["alert_severity"] = target.get("alert_severity") or db_alert.alert_severity
            target["entity_id"] = target.get("entity_id") or db_alert.entity_id

    rec = recommendation_engine.find_recommendation(target, db=db)
    return {
        "status": "success",
        "threshold": recommendation_engine.threshold,
        "has_recommendation": rec is not None,
        "recommended_reference": rec,
    }


@app.get("/api/audit/recommend-reference/{ticket_id}", summary="Get Cross-CSE Recommendation for specific ticket")
async def recommend_reference_by_ticket(ticket_id: str, db: Session = Depends(get_db)):
    """
    Fetches ticket details for ticket_id and runs offline similarity matching against historically audited tickets.
    """
    target = None
    try:
        db_alert = db.query(SocAlerts).filter(SocAlerts.alert_id == ticket_id).first()
        if db_alert:
            target = db_alert.to_dict()
    except Exception:
        pass

    if not target and _alerts_cache is not None and not _alerts_cache.empty:
        id_col = "alert_id" if "alert_id" in _alerts_cache.columns else ("ticket_id" if "ticket_id" in _alerts_cache.columns else None)
        if id_col:
            match = _alerts_cache[_alerts_cache[id_col] == ticket_id]
            if not match.empty:
                target = match.iloc[0].to_dict()

    if not target and _assessment_cache and "evidence" in _assessment_cache:
        for rec in _assessment_cache["evidence"]:
            if rec.get("ticket_id") == ticket_id:
                target = rec
                break

    if not target:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} was not found.")

    rec = recommendation_engine.find_recommendation(target, db=db)
    return {
        "ticket_id": ticket_id,
        "has_recommendation": rec is not None,
        "recommended_reference": rec,
    }


@app.post(
    "/api/explain-anomaly",
    response_model=AnomalyExplainResponse,
    summary="Generate a 2-sentence AI explanation for a flagged anomaly and check Cross-CSE recommendation",
)
async def explain_anomaly(request: AnomalyExplainRequest, db: Session = Depends(get_db)):
    """
    Uses LangChain + local Ollama to generate a professional audit explanation.
    Simultaneously runs local Cross-CSE TF-IDF NLP similarity against historically solved tickets.
    If match > 85%, appends recommended_reference to the response.
    All inference is 100% local — zero external API calls.
    """
    payload = {
        "anomaly_type":     request.anomaly_type,
        "ticket_id":        request.ticket_id        or "N/A",
        "severity":         request.severity          or "N/A",
        "time_to_close":    request.time_to_close     or "N/A",
        "analyst":          request.analyst           or "N/A",
        "alert_type":       request.alert_type        or "N/A",
        "alert_category":   request.alert_category    or request.alert_type or "N/A",
        "escalated":        request.escalated         if request.escalated is not None else "N/A",
        "asset_id":         request.asset_id          or "N/A",
        "actual_alerts":    request.actual_alerts     if request.actual_alerts is not None else "N/A",
        "expected_mean":    request.expected_mean     if request.expected_mean is not None else "N/A",
        "explanation":      request.explanation,
        "resolution_notes": request.resolution_notes  or request.explanation,
        "entity_id":        request.entity_id         or "N/A",
    }

    # If ticket_id is available and resolution notes missing, fetch from database
    if request.ticket_id and (not request.resolution_notes or request.resolution_notes == request.explanation):
        try:
            db_alert = db.query(SocAlerts).filter(SocAlerts.alert_id == request.ticket_id).first()
            if db_alert:
                payload["resolution_notes"] = db_alert.resolution_notes or payload["resolution_notes"]
                payload["alert_category"] = db_alert.alert_category or payload["alert_category"]
                payload["severity"] = db_alert.alert_severity or payload["severity"]
                payload["entity_id"] = db_alert.entity_id or payload["entity_id"]
        except Exception:
            pass

    # 1. Generate supervisory explanation via Ollama / fallback
    explanation, source = await generate_llm_rationale(
        payload=payload,
        fallback_text=request.explanation,
        timeout=5.0,
    )

    # 2. Run instant offline Cross-CSE similarity matching
    recommendation = recommendation_engine.find_recommendation(payload, db=db)

    return AnomalyExplainResponse(
        explanation=explanation,
        source=source,
        model=OLLAMA_MODEL if source == "ollama" else None,
        recommended_reference=recommendation,
    )
