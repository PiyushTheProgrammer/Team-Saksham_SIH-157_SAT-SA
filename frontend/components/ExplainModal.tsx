"use client";

import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Props {
  anomalyType: string;
  rowData: Record<string, any>;
  onClose: () => void;
}

interface RecommendedReference {
  match_found: boolean;
  similarity_score: number;
  similarity_ratio: number;
  matched_ticket_id: string;
  matched_entity_id: string;
  matched_asset_name: string;
  matched_category: string;
  matched_severity: string;
  historical_notes: string;
  historical_capa: string;
  closure_reason: string;
  closed_by: string;
  notification_message: string;
  is_cross_cse: boolean;
}

interface ExplainResponse {
  explanation: string;
  source: "ollama" | "rule_engine";
  model: string | null;
  recommended_reference?: RecommendedReference | null;
}

function Spinner() {
  return (
    <div
      style={{
        width: 20,
        height: 20,
        border: "2px solid #000000",
        borderTopColor: "#0B2A4A",
        borderRadius: "50%",
      }}
      className="animate-spin"
    />
  );
}

function typeLabel(type: string): string {
  return (
    {
      speed_anomaly:    "Execution Gap — Speed Anomaly",
      repetitive_notes: "Process Violation — Repetitive Notes",
      blind_spot:       "Telemetry Failure — Blind Spot",
    }[type] ?? type
  );
}

function typeColor(type: string): string {
  return (
    {
      speed_anomaly:    "#DC2626",
      repetitive_notes: "#000000",
      blind_spot:       "#0B2A4A",
    }[type] ?? "#0B2A4A"
  );
}

function buildPayload(anomalyType: string, rowData: Record<string, any>) {
  // Map row data to the API's expected payload shape
  if (anomalyType === "speed_anomaly") {
    return {
      anomaly_type:    "speed_anomaly",
      ticket_id:       rowData.ticket_id,
      severity:        rowData.severity,
      time_to_close:   rowData.time_to_close,
      analyst:         rowData.analyst,
      alert_type:      rowData.alert_type,
      escalated:       rowData.escalated,
      explanation:     rowData.explanation,
    };
  }
  if (anomalyType === "repetitive_notes") {
    return {
      anomaly_type:    "repetitive_notes",
      analyst:         rowData.analyst,
      alert_type:      (rowData.distinct_alert_types ?? []).join(", "),
      explanation:     rowData.explanation,
    };
  }
  // blind_spot
  return {
    anomaly_type:    "blind_spot",
    asset_id:        rowData.asset_id,
    actual_alerts:   rowData.actual_alerts,
    expected_mean:   rowData.expected_mean,
    explanation:     rowData.explanation,
  };
}

export default function ExplainModal({ anomalyType, rowData, onClose }: Props) {
  const [status, setStatus] = useState<"loading" | "done" | "error">("loading");
  const [response, setResponse] = useState<ExplainResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string>("");
  const [showCapaDetails, setShowCapaDetails] = useState<boolean>(true);
  const [copiedCapa, setCopiedCapa] = useState<boolean>(false);

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  // Fetch explanation
  const fetchExplanation = useCallback(async () => {
    setStatus("loading");
    setResponse(null);
    setErrorMsg("");
    try {
      const payload = buildPayload(anomalyType, rowData);
      const res = await axios.post<ExplainResponse>(
        `${API_BASE}/api/explain-anomaly`,
        payload,
        { timeout: 120_000 }  // Ollama can be slow — give it 2 minutes
      );
      setResponse(res.data);
      setStatus("done");
    } catch (err: any) {
      setErrorMsg(err?.message ?? "Unknown error");
      setStatus("error");
    }
  }, [anomalyType, rowData]);

  useEffect(() => {
    fetchExplanation();
  }, [fetchExplanation]);

  const color = typeColor(anomalyType);

  return (
    <div
      className="modal-overlay"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div className="modal-box">
        {/* ── Header ── */}
        <div className="modal-header">
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {/* Type indicator */}
            <div
              style={{
                width: 4,
                height: 28,
                background: color,
                borderRadius: 2,
                boxShadow: `0 0 8px ${color}`,
              }}
            />
            <div>
              <div
                id="modal-title"
                style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)", marginBottom: 2 }}
              >
                {typeLabel(anomalyType)}
              </div>
              <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
                {rowData.ticket_id && `Ticket: ${rowData.ticket_id}`}
                {rowData.analyst && !rowData.ticket_id && `Analyst: ${rowData.analyst}`}
                {rowData.asset_id && !rowData.ticket_id && !rowData.analyst && `Asset: ${rowData.asset_id}`}
              </div>
            </div>
          </div>

          {/* Close button */}
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "var(--text-muted)",
              padding: 6,
              borderRadius: 6,
              display: "flex",
              alignItems: "center",
            }}
            id="modal-close"
            aria-label="Close"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>

        {/* ── Body ── */}
        <div className="modal-body">
          {/* Anomaly metadata strip */}
          <div
            style={{
              background: "var(--bg-elevated)",
              border: "1px solid var(--border)",
              borderRadius: 8,
              padding: "12px 16px",
              marginBottom: 20,
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(130px, 1fr))",
              gap: "8px 16px",
            }}
          >
            {Object.entries(rowData)
              .filter(([k]) => !["explanation", "ticket_ids", "distinct_alert_types"].includes(k))
              .slice(0, 8)
              .map(([k, v]) => (
                <div key={k}>
                  <div style={{ fontSize: 10, color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 2 }}>
                    {k.replace(/_/g, " ")}
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      color: "var(--text-secondary)",
                      fontWeight: 600,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {typeof v === "boolean" ? (v ? "Yes" : "No") : String(v ?? "N/A")}
                  </div>
                </div>
              ))}
          </div>

          {/* AI Explanation section */}
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              textTransform: "uppercase",
              letterSpacing: "0.08em",
              color: "var(--text-muted)",
              marginBottom: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
            }}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#0B2A4A" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 2a2 2 0 0 1 2 2c0 .74-.4 1.39-1 1.73V7h1a7 7 0 0 1 7 7h1a1 1 0 0 1 1 1v3a1 1 0 0 1-1 1h-1v1a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-1H1a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1h1a7 7 0 0 1 7-7h1V5.73c-.6-.34-1-.99-1-1.73a2 2 0 0 1 2-2z"/>
            </svg>
            AI Audit Finding
          </div>

          {/* Loading state */}
          {status === "loading" && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 12,
                padding: "32px 0",
                color: "var(--text-muted)",
                fontSize: 13,
              }}
            >
              <Spinner />
              <span>Querying local Ollama instance&hellip;</span>
              <span style={{ fontSize: 11, opacity: 0.6 }}>
                This may take 10–30 seconds depending on your hardware.
              </span>
            </div>
          )}

          {/* Error state */}
          {status === "error" && (
            <div
              style={{
                background: "var(--danger-dim)",
                border: "1px solid rgba(239,68,68,0.3)",
                borderRadius: 8,
                padding: "16px",
                fontSize: 13,
                color: "var(--danger)",
                marginBottom: 12,
              }}
            >
              <strong>Could not reach backend:</strong> {errorMsg}
              <div style={{ marginTop: 8 }}>
                <button className="btn btn-ghost" onClick={fetchExplanation} style={{ fontSize: 12 }}>
                  Retry
                </button>
              </div>
            </div>
          )}

          {/* Result */}
          {status === "done" && response && (
            <div>
              <div
                style={{
                  background: "var(--bg-elevated)",
                  border: `1px solid ${color}33`,
                  borderLeft: `3px solid ${color}`,
                  borderRadius: 8,
                  padding: "16px 20px",
                  fontSize: 14,
                  color: "var(--text-primary)",
                  lineHeight: 1.7,
                  marginBottom: 12,
                }}
              >
                {response.explanation}
              </div>

              {/* Source badge */}
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    fontSize: 11,
                    fontWeight: 600,
                    padding: "3px 10px",
                    borderRadius: 999,
                    background:
                      response.source === "ollama"
                        ? "rgba(16,185,129,0.12)"
                        : "rgba(100,116,139,0.15)",
                    color:
                      response.source === "ollama"
                        ? "var(--success)"
                        : "var(--text-muted)",
                    border: `1px solid ${
                      response.source === "ollama"
                        ? "rgba(16,185,129,0.25)"
                        : "rgba(100,116,139,0.2)"
                    }`,
                  }}
                >
                  {response.source === "ollama" ? (
                    <>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--success)" }} />
                      AI — {response.model ?? "Ollama"}
                    </>
                  ) : (
                    <>
                      <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--text-muted)" }} />
                      Rule Engine (Ollama unavailable)
                    </>
                  )}
                </span>
                <span style={{ fontSize: 11, color: "var(--text-muted)" }}>
                  All inference runs locally. No data left this machine.
                </span>
              </div>

              {/* ── Cross-CSE Similar Ticket Audit Reference Notification ── */}
              {response.recommended_reference && response.recommended_reference.match_found && (
                <div
                  style={{
                    marginTop: 18,
                    padding: "16px 18px",
                    background: "linear-gradient(135deg, rgba(30, 58, 138, 0.08) 0%, rgba(59, 130, 246, 0.12) 100%)",
                    border: "1px solid rgba(59, 130, 246, 0.35)",
                    borderRadius: 10,
                    boxShadow: "0 2px 10px rgba(59, 130, 246, 0.06)",
                  }}
                >
                  {/* Notification Header */}
                  <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
                    <div
                      style={{
                        width: 32,
                        height: 32,
                        borderRadius: 8,
                        background: "#2563eb",
                        color: "#ffffff",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                        marginTop: 2,
                      }}
                    >
                      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                        <path d="m9 12 2 2 4-4" />
                      </svg>
                    </div>

                    <div style={{ flex: 1 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", marginBottom: 4 }}>
                        <span style={{ fontSize: 13, fontWeight: 700, color: "#1e3a8a" }}>
                          Cross-CSE Audit Reference Available
                        </span>
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 700,
                            padding: "2px 8px",
                            borderRadius: 999,
                            background: "#dcfce7",
                            color: "#15803d",
                            border: "1px solid #bbf7d0",
                          }}
                        >
                          {response.recommended_reference.similarity_score}% NLP Match
                        </span>
                        <span
                          style={{
                            fontSize: 11,
                            fontWeight: 600,
                            padding: "2px 8px",
                            borderRadius: 4,
                            background: "#eff6ff",
                            color: "#1d4ed8",
                            border: "1px solid #dbeafe",
                          }}
                        >
                          {response.recommended_reference.matched_entity_id}
                        </span>
                      </div>

                      {/* Exact prompt requirement */}
                      <p style={{ margin: "4px 0 10px", fontSize: 13, color: "#1e293b", lineHeight: 1.5, fontWeight: 500 }}>
                        You have audited a similar anomaly from another CSE before. Do you want to review that historical Corrective Action (CAPA) as a reference?
                      </p>

                      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="btn btn-primary"
                          onClick={() => setShowCapaDetails(!showCapaDetails)}
                          style={{
                            fontSize: 12,
                            padding: "6px 14px",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 6,
                            background: "#2563eb",
                            color: "#ffffff",
                            borderRadius: 6,
                            fontWeight: 600,
                            border: "none",
                            cursor: "pointer",
                          }}
                        >
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                            <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z" />
                            <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z" />
                          </svg>
                          {showCapaDetails ? "Hide Historical CAPA" : "Review Historical CAPA"}
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Expandable Historical CAPA Reference Card */}
                  {showCapaDetails && (
                    <div
                      style={{
                        marginTop: 14,
                        padding: 14,
                        background: "#ffffff",
                        borderRadius: 8,
                        border: "1px solid #bfdbfe",
                        boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
                      }}
                    >
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 10, marginBottom: 12 }}>
                        <div style={{ fontSize: 11 }}>
                          <span style={{ color: "var(--text-muted)", display: "block" }}>Historical Ticket ID</span>
                          <code style={{ fontSize: 12, fontWeight: 700, color: "#1e40af" }}>
                            {response.recommended_reference.matched_ticket_id}
                          </code>
                        </div>
                        <div style={{ fontSize: 11 }}>
                          <span style={{ color: "var(--text-muted)", display: "block" }}>Source Entity (CSE)</span>
                          <strong style={{ fontSize: 12, color: "#0f172a" }}>
                            {response.recommended_reference.matched_entity_id}
                          </strong>
                        </div>
                        <div style={{ fontSize: 11 }}>
                          <span style={{ color: "var(--text-muted)", display: "block" }}>Category &amp; Severity</span>
                          <strong style={{ fontSize: 12, color: "#0f172a" }}>
                            {response.recommended_reference.matched_category} ({response.recommended_reference.matched_severity})
                          </strong>
                        </div>
                        <div style={{ fontSize: 11 }}>
                          <span style={{ color: "var(--text-muted)", display: "block" }}>Audited By</span>
                          <span style={{ fontSize: 12, color: "#475569" }}>
                            {response.recommended_reference.closed_by}
                          </span>
                        </div>
                      </div>

                      {response.recommended_reference.historical_notes && (
                        <div style={{ marginBottom: 10 }}>
                          <span style={{ fontSize: 11, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                            Historical Resolution Notes
                          </span>
                          <div style={{ fontSize: 12, fontStyle: "italic", color: "#334155", background: "#f8fafc", padding: "6px 10px", borderRadius: 4, marginTop: 3 }}>
                            &ldquo;{response.recommended_reference.historical_notes}&rdquo;
                          </div>
                        </div>
                      )}

                      <div>
                        <span style={{ fontSize: 11, fontWeight: 700, color: "#1e3a8a", textTransform: "uppercase", letterSpacing: "0.05em", display: "flex", alignItems: "center", gap: 4 }}>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2">
                            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                          </svg>
                          Historical Corrective Action (CAPA) Precedent
                        </span>
                        <div
                          style={{
                            marginTop: 4,
                            padding: "10px 14px",
                            background: "#f0fdf4",
                            borderLeft: "3px solid #16a34a",
                            borderRadius: 6,
                            fontSize: 13,
                            color: "#14532d",
                            lineHeight: 1.6,
                            fontWeight: 500,
                          }}
                        >
                          {response.recommended_reference.historical_capa}
                        </div>
                      </div>

                      <div style={{ marginTop: 12, display: "flex", justifyContent: "flex-end", gap: 8 }}>
                        <button
                          type="button"
                          className="btn btn-ghost"
                          onClick={() => {
                            navigator.clipboard?.writeText(response.recommended_reference?.historical_capa || "");
                            setCopiedCapa(true);
                            setTimeout(() => setCopiedCapa(false), 2000);
                          }}
                          style={{ fontSize: 11, padding: "4px 10px" }}
                        >
                          {copiedCapa ? "✓ Copied to Clipboard" : "Copy CAPA Precedent"}
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
