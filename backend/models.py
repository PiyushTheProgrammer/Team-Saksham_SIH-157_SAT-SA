"""
SAT-SA — models.py
==================
SQLAlchemy ORM models representing the normalized relational schema for SOC Assessment evidence:
  1. AssetInventory         (Parent Table)
  2. SocAlerts              (Child of AssetInventory, Parent of evidence tables)
  3. CaseManagement         (Child of SocAlerts, references alert_id)
  4. InvestigationWorkflows (Child of SocAlerts, references alert_id)
  5. EscalationRecords      (Child of SocAlerts, references alert_id)
  6. AlertClosures          (Child of SocAlerts, references alert_id)

Strictly air-gap compliant: PostgreSQL runs on-premises — zero external calls.
Enforces explicit Foreign Key constraints for relational data integrity.
"""

from typing import Any, Optional
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from database import Base


# ══════════════════════════════════════════════════════════════════════════════
# 1. ASSET INVENTORY (Parent Table)
# ══════════════════════════════════════════════════════════════════════════════

class AssetInventory(Base):
    """
    SQLAlchemy ORM model representing an asset in the organization inventory.
    Serves as the root parent entity for all SOC alert correlations.

    Columns:
      - asset_name: Host / asset name (Primary Key)
      - asset_type: Category/type of asset (e.g. Server, Workstation, Firewall)
      - department: Owning department (e.g. IT, Finance, Engineering)
      - asset_criticality: Criticality rating (CRITICAL, HIGH, MEDIUM, LOW)
    """

    __tablename__ = "asset_inventory"

    asset_name = Column(String(128), primary_key=True, index=True, comment="Unique asset name (Primary Key)")
    asset_type = Column(String(64), nullable=True, comment="Asset category/type, e.g. Server, Workstation")
    department = Column(String(128), nullable=True, comment="Owner department, e.g. Engineering, Finance")
    asset_criticality = Column(String(32), nullable=True, comment="Criticality level: CRITICAL, HIGH, MEDIUM, LOW")

    # Relationship to child SocAlerts
    alerts = relationship("SocAlerts", back_populates="asset_rel", cascade="all, delete-orphan", passive_deletes=True)

    @property
    def asset_id(self) -> str:
        return self.asset_name

    def to_dict(self) -> dict[str, Any]:
        """Convert ORM model instance into a dictionary."""
        return {
            "asset_name": self.asset_name,
            "asset_id": self.asset_name,
            "asset_type": self.asset_type,
            "department": self.department,
            "asset_criticality": self.asset_criticality,
        }

    def __repr__(self) -> str:
        return (
            f"<AssetInventory asset_name={self.asset_name!r} type={self.asset_type!r} "
            f"criticality={self.asset_criticality!r}>"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2. SOC ALERTS (Child of AssetInventory, Parent of Child Evidence Tables)
# ══════════════════════════════════════════════════════════════════════════════

class SocAlerts(Base):
    """
    SQLAlchemy ORM model representing a single SOC alert record matching
    the NCIIPC operational dataset structure.

    Foreign Keys:
      - asset_name -> asset_inventory.asset_name (Parent constraint)

    Columns:
      - id: Primary Key (auto-incrementing integer)
      - timestamp: Alert timestamp or creation time
      - alert_id: Unique alert identifier (e.g., AL-1001) - referenced by child tables
      - entity_id: Critical sector / entity identifier (e.g., ENT-A)
      - asset_name: Host / asset name referencing AssetInventory
      - alert_category: Threat category (e.g., Malware, DDoS, Unauthorized Access)
      - alert_severity: Severity level (Critical, High, Medium, Low)
      - time_to_close_seconds: Resolution time in seconds
      - escalated: Boolean flag indicating if the alert was escalated
      - resolution_notes: Text notes entered by the analyst upon closure

    Analytics Engine Anomaly Flags:
      - is_speed_anomaly: Flagged if time_to_close is suspiciously rapid
      - is_repetitive_anomaly: Flagged if closure notes match copy-paste patterns
      - is_negative_space: Flagged if asset exhibits silent/dormant periods
      - is_anomaly: Aggregate anomaly indicator for backwards compatibility
    """

    __tablename__ = "soc_alerts"

    # ── Primary Key ───────────────────────────────────────────────────────────
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # ── NCIIPC Synthetic Dataset Core Columns ─────────────────────────────────
    timestamp = Column(String(64), index=True, nullable=True, comment="Alert timestamp or creation time")
    alert_id = Column(String(64), unique=True, index=True, nullable=False, comment="Unique alert identifier, e.g. AL-1001")
    entity_id = Column(String(64), index=True, nullable=True, comment="Entity identifier, e.g. ENT-A")

    # Explicit Foreign Key to AssetInventory parent
    asset_name = Column(
        String(128),
        ForeignKey("asset_inventory.asset_name", ondelete="SET NULL"),
        index=True,
        nullable=True,
        comment="Foreign Key referencing asset_inventory.asset_name"
    )

    alert_category = Column(String(64), nullable=True, comment="Category: Malware, DDoS, etc.")
    alert_severity = Column(String(32), nullable=True, comment="Severity: Critical, High, Medium, Low")
    time_to_close_seconds = Column(Integer, nullable=True, comment="Resolution time in seconds")
    escalated = Column(Boolean, nullable=True, comment="True if alert was escalated")
    resolution_notes = Column(Text, nullable=True, comment="Analyst resolution commentary")

    # ── Analytics Engine Flags ────────────────────────────────────────────────
    is_speed_anomaly = Column(Boolean, nullable=False, default=False, comment="Suspiciously fast closure")
    is_repetitive_anomaly = Column(Boolean, nullable=False, default=False, comment="Repetitive copy-paste resolution")
    is_negative_space = Column(Boolean, nullable=False, default=False, comment="Negative space / blind spot anomaly")
    is_anomaly = Column(Boolean, nullable=False, default=False, comment="General anomaly flag")

    # ── Relationships ─────────────────────────────────────────────────────────
    asset_rel = relationship("AssetInventory", back_populates="alerts")
    cases = relationship("CaseManagement", back_populates="alert_rel", cascade="all, delete-orphan", passive_deletes=True)
    investigations = relationship("InvestigationWorkflows", back_populates="alert_rel", cascade="all, delete-orphan", passive_deletes=True)
    escalations = relationship("EscalationRecords", back_populates="alert_rel", cascade="all, delete-orphan", passive_deletes=True)
    closures = relationship("AlertClosures", back_populates="alert_rel", cascade="all, delete-orphan", passive_deletes=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert ORM model instance into a dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "alert_id": self.alert_id,
            "entity_id": self.entity_id,
            "asset_name": self.asset_name,
            "alert_category": self.alert_category,
            "alert_severity": self.alert_severity,
            "time_to_close_seconds": self.time_to_close_seconds,
            "escalated": self.escalated,
            "resolution_notes": self.resolution_notes,
            "is_speed_anomaly": self.is_speed_anomaly,
            "is_repetitive_anomaly": self.is_repetitive_anomaly,
            "is_negative_space": self.is_negative_space,
            "is_anomaly": self.is_anomaly,
        }

    def __repr__(self) -> str:
        return (
            f"<SocAlerts id={self.id} alert_id={self.alert_id!r} "
            f"entity_id={self.entity_id!r} severity={self.alert_severity!r}>"
        )


# Backward compatibility aliases
SOCAlert = SocAlerts
SocAlertRecord = SocAlerts


# ══════════════════════════════════════════════════════════════════════════════
# 3. CASE MANAGEMENT (Child Table referencing soc_alerts.alert_id)
# ══════════════════════════════════════════════════════════════════════════════

class CaseManagement(Base):
    """
    SQLAlchemy ORM model representing incident case management records.
    Foreign Keys:
      - alert_id -> soc_alerts.alert_id
    """

    __tablename__ = "case_management"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    case_id = Column(String(64), index=True, nullable=True, comment="Case identifier, e.g. CAS-901")
    alert_id = Column(
        String(64),
        ForeignKey("soc_alerts.alert_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="Foreign Key referencing soc_alerts.alert_id"
    )
    timestamp = Column(String(64), index=True, nullable=True, comment="Case creation timestamp")
    sensor_id = Column(String(64), nullable=True, comment="Sensor identifier, e.g. SENS-FW-01")
    alert_name = Column(String(128), nullable=True, comment="Alert descriptive name")
    severity = Column(String(32), nullable=True, comment="Severity: Critical, High, Medium, Low")
    mitre_tactic = Column(String(64), nullable=True, comment="MITRE ATT&CK tactic")
    source_ip = Column(String(64), nullable=True, comment="Source IP address")
    destination_ip = Column(String(64), nullable=True, comment="Destination IP address")
    asset_id = Column(String(64), nullable=True, comment="Asset identifier")

    alert_rel = relationship("SocAlerts", back_populates="cases")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "case_id": self.case_id,
            "alert_id": self.alert_id,
            "timestamp": self.timestamp,
            "sensor_id": self.sensor_id,
            "alert_name": self.alert_name,
            "severity": self.severity,
            "mitre_tactic": self.mitre_tactic,
            "source_ip": self.source_ip,
            "destination_ip": self.destination_ip,
            "asset_id": self.asset_id,
        }

    def __repr__(self) -> str:
        return f"<CaseManagement id={self.id} case_id={self.case_id!r} alert_id={self.alert_id!r}>"


# ══════════════════════════════════════════════════════════════════════════════
# 4. INVESTIGATION WORKFLOWS (Child Table referencing soc_alerts.alert_id)
# ══════════════════════════════════════════════════════════════════════════════

class InvestigationWorkflows(Base):
    """
    SQLAlchemy ORM model representing analyst investigation workflows and action trails.
    Foreign Keys:
      - alert_id -> soc_alerts.alert_id
    """

    __tablename__ = "investigation_workflows"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    workflow_id = Column(String(64), index=True, nullable=True, comment="Workflow identifier, e.g. WF-001")
    alert_id = Column(
        String(64),
        ForeignKey("soc_alerts.alert_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="Foreign Key referencing soc_alerts.alert_id"
    )
    case_id = Column(String(64), index=True, nullable=True, comment="Associated case identifier")
    action_taken = Column(Text, nullable=True, comment="Action taken during investigation")
    action_timestamp = Column(String(64), nullable=True, comment="Timestamp of action execution")
    result = Column(Text, nullable=True, comment="Outcome / result of action")
    time_spent_minutes = Column(Integer, nullable=True, comment="Time spent in minutes")
    investigator = Column(String(64), nullable=True, comment="Analyst executing the investigation")

    alert_rel = relationship("SocAlerts", back_populates="investigations")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "alert_id": self.alert_id,
            "case_id": self.case_id,
            "action_taken": self.action_taken,
            "action_timestamp": self.action_timestamp,
            "result": self.result,
            "time_spent_minutes": self.time_spent_minutes,
            "investigator": self.investigator,
        }

    def __repr__(self) -> str:
        return f"<InvestigationWorkflows id={self.id} workflow_id={self.workflow_id!r} alert_id={self.alert_id!r}>"


# ══════════════════════════════════════════════════════════════════════════════
# 5. ESCALATION RECORDS (Child Table referencing soc_alerts.alert_id)
# ══════════════════════════════════════════════════════════════════════════════

class EscalationRecords(Base):
    """
    SQLAlchemy ORM model representing tier escalations and justification records.
    Foreign Keys:
      - alert_id -> soc_alerts.alert_id
    """

    __tablename__ = "escalation_records"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    escalation_id = Column(String(64), index=True, nullable=True, comment="Escalation identifier, e.g. ESC-01")
    alert_id = Column(
        String(64),
        ForeignKey("soc_alerts.alert_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="Foreign Key referencing soc_alerts.alert_id"
    )
    case_id = Column(String(64), index=True, nullable=True, comment="Associated case identifier")
    escalated_from_tier = Column(String(32), nullable=True, comment="Source tier (e.g. Tier-1)")
    escalated_to_tier = Column(String(32), nullable=True, comment="Target tier (e.g. Tier-3)")
    escalation_reason = Column(Text, nullable=True, comment="Detailed escalation justification")
    escalation_timestamp = Column(String(64), nullable=True, comment="Timestamp when escalation occurred")

    alert_rel = relationship("SocAlerts", back_populates="escalations")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "escalation_id": self.escalation_id,
            "alert_id": self.alert_id,
            "case_id": self.case_id,
            "escalated_from_tier": self.escalated_from_tier,
            "escalated_to_tier": self.escalated_to_tier,
            "escalation_reason": self.escalation_reason,
            "escalation_timestamp": self.escalation_timestamp,
        }

    def __repr__(self) -> str:
        return f"<EscalationRecords id={self.id} escalation_id={self.escalation_id!r} alert_id={self.alert_id!r}>"


# ══════════════════════════════════════════════════════════════════════════════
# 6. ALERT CLOSURES (Child Table referencing soc_alerts.alert_id)
# ══════════════════════════════════════════════════════════════════════════════

class AlertClosures(Base):
    """
    SQLAlchemy ORM model representing alert closure records and Corrective Action (CAPA).
    Foreign Keys:
      - alert_id -> soc_alerts.alert_id
    """

    __tablename__ = "alert_closures"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    closure_id = Column(String(64), index=True, nullable=True, comment="Closure identifier, e.g. CLS-001")
    alert_id = Column(
        String(64),
        ForeignKey("soc_alerts.alert_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
        comment="Foreign Key referencing soc_alerts.alert_id"
    )
    closed_by = Column(String(64), nullable=True, comment="Analyst who authorized closure")
    closure_reason = Column(String(128), nullable=True, comment="Reason for closure, e.g. Remediation Applied")
    resolution_notes = Column(Text, nullable=True, comment="Detailed closure and containment notes")
    closure_timestamp = Column(String(64), nullable=True, comment="Timestamp of alert closure")
    capa_action = Column(Text, nullable=True, comment="Corrective and Preventive Action (CAPA) details")
    is_verified = Column(Boolean, nullable=False, default=False, comment="Supervisory verification sign-off")

    alert_rel = relationship("SocAlerts", back_populates="closures")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "closure_id": self.closure_id,
            "alert_id": self.alert_id,
            "closed_by": self.closed_by,
            "closure_reason": self.closure_reason,
            "resolution_notes": self.resolution_notes,
            "closure_timestamp": self.closure_timestamp,
            "capa_action": self.capa_action,
            "is_verified": self.is_verified,
        }

    def __repr__(self) -> str:
        return f"<AlertClosures id={self.id} closure_id={self.closure_id!r} alert_id={self.alert_id!r}>"
