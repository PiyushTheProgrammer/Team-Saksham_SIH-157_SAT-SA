"use client";

export const dynamic = 'force-dynamic';

import { useEffect, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Database, Menu, ShieldCheck } from "lucide-react";
import { Sidebar } from "../components/Sidebar";
import { FindingsTrend } from "../components/FindingsTrend";

const API = "http://127.0.0.1:8000";
type RecordValue = Record<string, any>;
let overviewAnalyticsData: { dashboard: RecordValue; assessment: RecordValue } | null = null;

async function request(path: string, options?: RequestInit) {
  const response = await fetch(`${API}${path}`, { cache: "no-store", ...options });
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail ?? `Request failed (${response.status})`); }
  return response;
}
async function json(path: string) { return (await request(path)).json(); }

function Shell({ children, path, setPath }: { children: React.ReactNode; path: string; setPath: (p: string) => void }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div className="shell">
      <Sidebar
        path={path}
        setPath={setPath}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
      />
      <section className="main">
        <header className="topbar sticky top-0 z-30 bg-white">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setIsOpen(true)}
              className="p-1.5 -ml-1 rounded-lg text-slate-600 hover:text-slate-900 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 cursor-pointer"
              aria-label="Open sidebar menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="flex items-center gap-2.5">
              <Image
                src="/SAT-SA.png"
                alt="SAT-SA Logo"
                width={36}
                height={36}
                className="w-9 h-9 object-contain"
                priority
              />
              <span className="text-xl font-extrabold tracking-tight text-slate-800 leading-none">
                SAT-SA
              </span>
              <span className="text-slate-300 font-light text-base leading-none select-none">|</span>
              <span className="font-semibold text-slate-600 text-sm hidden sm:inline leading-tight">
                Supervisory Analytics Tool for SOC Assessment
              </span>
            </div>
          </div>
        </header>
        <div className="main-scroll">
          {children}
          <footer className="footer">
            <span>SAT-SA Prototype</span>
            <span>Evidence-based supervisory assessment using synthetic local data.</span>
          </footer>
        </div>
      </section>
    </div>
  );
}

function Page({ title, subtitle, children }: { title: string; subtitle: string; children: React.ReactNode }) {
  const statisticalSection = title === "Dashboard Overview" && overviewAnalyticsData
    ? <AnalyticsStatistics dashboard={overviewAnalyticsData.dashboard} assessment={overviewAnalyticsData.assessment} />
    : null;
  return (
    <main className="content">
      <h1 className="page-title">{title}</h1>
      <p className="subtitle">{subtitle}</p>
      {statisticalSection}
      {children}
    </main>
  );
}

function EmptyState({ setPath, title = "No Data Found", message = "Please upload SOC records via the Data Ingestion tab to generate insights." }: { setPath?: (p: string) => void; title?: string; message?: string }) {
  return (
    <div className="panel" style={{ textAlign: "center", padding: "64px 24px", maxWidth: 540, margin: "40px auto" }}>
      <div style={{
        width: 60, height: 60, borderRadius: 16,
        background: "#eff6ff", color: "#2563eb",
        display: "flex", alignItems: "center", justifyContent: "center",
        margin: "0 auto 18px", border: "1px solid #dbeafe"
      }}>
        <Database size={30} strokeWidth={2} />
      </div>
      <h2 style={{ fontSize: "22px", fontWeight: "700", color: "var(--text-primary)", margin: "0 0 8px" }}>
        {title}
      </h2>
      <p style={{ color: "var(--text-secondary)", marginBottom: "28px", fontSize: "14px", lineHeight: "1.6" }}>
        {message}
      </p>
      {setPath && (
        <button
          type="button"
          className="btn-primary"
          style={{ padding: "10px 24px", fontSize: "14px", fontWeight: "600" }}
          onClick={() => setPath("/data-ingestion")}
        >
          Go to Data Ingestion
        </button>
      )}
    </div>
  );
}

function LoadState({ error, setPath }: { error: string | null; setPath?: (p: string) => void }) {
  if (error) {
    return <EmptyState setPath={setPath} />;
  }
  return (
    <div className="panel" style={{ textAlign: "center", padding: "48px 20px", color: "var(--text-secondary)" }}>
      Loading local assessment data...
    </div>
  );
}

function Tag({ value }: { value: string }) {
  const tone = ["Adequate", "Observed", "LOW", "RESOLVED", "CLOSED"].includes(value) ? "green"
    : ["Attention", "Missing", "CRITICAL", "URGENT"].includes(value) ? "red" : "amber";
  return <span className={`tag ${tone}`}>{value}</span>;
}

/* ------------------------------------------------------------------ */
/* Upload Progress Bar Component                                        */
/* ------------------------------------------------------------------ */
const UPLOAD_STAGES = [
  { label: "Uploading Data", from: 0, to: 25 },
  { label: "Running Scikit-Learn Anomaly Detection", from: 25, to: 60 },
  { label: "Generating Local LLM Rationales", from: 60, to: 90 },
  { label: "Finalizing Audit Records", from: 90, to: 100 },
] as const;

function UploadProgressBar({ progress }: { progress: number }) {
  const pct = Math.min(100, Math.max(0, progress));
  const stageIdx = UPLOAD_STAGES.findIndex(s => pct < s.to) === -1
    ? UPLOAD_STAGES.length - 1
    : UPLOAD_STAGES.findIndex(s => pct < s.to);
  const currentLabel = pct >= 100 ? "Complete!" : UPLOAD_STAGES[stageIdx].label;

  return (
    <div className="upload-progress-wrap" aria-live="polite" aria-label={`Upload progress: ${pct}%`}>
      <div className="upload-progress-header">
        <span className="upload-progress-stage">{currentLabel}</span>
        <span className="upload-progress-pct">{pct}%</span>
      </div>
      <div className="upload-progress-track">
        <div className="upload-progress-fill" style={{ width: `${pct}%` }} />
      </div>
      <div className="upload-progress-steps">
        {UPLOAD_STAGES.map((stage, i) => {
          const isDone = pct >= stage.to;
          const isActive = !isDone && pct >= stage.from;
          return (
            <div
              key={stage.label}
              className={`upload-progress-step${isDone ? " done" : isActive ? " active" : ""}`}
              title={stage.label}
            >
              {isDone ? "✓ " : isActive ? "⟳ " : ""}{stage.label}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Data Ingestion – single, centralised upload location                */
/* ------------------------------------------------------------------ */
function DataIngestion({ setPath }: { setPath: (p: string) => void }) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");
  const [uploading, setUploading] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleClearDatabase() {
    const confirmed = window.confirm(
      "Are you sure you want to delete all records from the database? This action cannot be undone."
    );
    if (!confirmed) return;

    setError("");
    setSuccessMsg("");
    setClearing(true);

    try {
      const response = await request("/api/data/clear", { method: "DELETE" });
      const data = await response.json();
      setFile(null);
      setProgress(null);
      setSuccessMsg(data?.message || "Database cleared successfully.");
      router.refresh();
    } catch (err: any) {
      setError(err.message || "Failed to clear database.");
    } finally {
      setClearing(false);
    }
  }

  async function handleUpload(targetFile: File) {
    setFile(targetFile);
    setError("");
    setSuccessMsg("");
    setUploading(true);
    setProgress(0);

    // ── Stage 1: Uploading Data (0 → 25) ─────────────────────────────
    const advanceTo = (target: number, duration: number) =>
      new Promise<void>(resolve => {
        const start = Date.now();
        const startPct = progress ?? 0;
        function tick() {
          const elapsed = Date.now() - start;
          const fraction = Math.min(elapsed / duration, 1);
          const current = Math.round(startPct + (target - startPct) * fraction);
          setProgress(current);
          if (fraction < 1) requestAnimationFrame(tick);
          else resolve();
        }
        tick();
      });

    let currentPct = 0;
    const animate = async (target: number, duration: number) => {
      const start = Date.now();
      const from = currentPct;
      await new Promise<void>(resolve => {
        function tick() {
          const elapsed = Date.now() - start;
          const fraction = Math.min(elapsed / duration, 1);
          currentPct = Math.round(from + (target - from) * fraction);
          setProgress(currentPct);
          if (fraction < 1) requestAnimationFrame(tick);
          else resolve();
        }
        tick();
      });
    };

    try {
      // Fire actual upload while stage 1 animation plays
      const form = new FormData();
      form.append("file", targetFile);

      const uploadPromise = request("/api/upload", { method: "POST", body: form });

      // Stage 1: 0 → 25 (network upload)
      await animate(25, 900);

      // Stage 2: 25 → 60 (wait for backend + animate)
      await animate(60, 1400);

      // Stage 3: 60 → 90 (LLM rationale simulation)
      await animate(90, 1200);

      // Await actual API response before finalizing
      await uploadPromise;

      // Stage 4: 90 → 100 (finalize)
      await animate(100, 600);

      // Brief pause at 100% then navigate
      await new Promise(r => setTimeout(r, 800));
      router.refresh();
      setPath("/");
    } catch (err: any) {
      setProgress(null);
      setError(err.message || "Unable to connect to the local assessment API.");
    } finally {
      setUploading(false);
    }
  }

  function onFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0]; if (f) handleUpload(f);
  }
  function onDrop(e: React.DragEvent) {
    e.preventDefault(); setDragOver(false);
    const f = e.dataTransfer.files?.[0]; if (f) handleUpload(f);
  }

  return (
    <Page title="Data Ingestion" subtitle="Upload SOC alert data for supervisory analysis. Accepted formats: CSV and JSON.">
      <section className="panel" style={{ marginBottom: 20 }}>
        <div className="section-heading" style={{ marginBottom: 24 }}>
          <div>
            <h2>Upload Dataset</h2>
            <p className="chart-note">All processing is local. No data leaves the system.</p>
          </div>
          <span className="tag amber">LOCAL PROCESSING</span>
        </div>

        {/* Drop zone — single unbroken dashed border, fully centred content */}
        <label
          htmlFor="file-upload-input"
          onDragOver={e => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            width: "100%",
            padding: "48px 32px",
            border: `2px dashed ${dragOver ? "var(--accent)" : "#cbd5e1"}`,
            borderRadius: 12,
            background: dragOver ? "var(--accent-dim)" : "#f8fafc",
            cursor: (uploading || clearing) ? "not-allowed" : "pointer",
            transition: "border-color 0.2s, background 0.2s",
            textAlign: "center",
            opacity: (uploading || clearing) ? 0.6 : 1,
            pointerEvents: (uploading || clearing) ? "none" : undefined,
          }}
        >
          <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
            style={{ color: dragOver ? "var(--accent)" : "var(--text-muted)", marginBottom: 14, transition: "color 0.2s" }}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
          </svg>
          <p style={{ margin: "0 0 6px", fontSize: 16, fontWeight: 600, color: "var(--text-primary)" }}>
            Drag &amp; drop your dataset here
          </p>
          <p style={{ margin: 0, fontSize: 14, color: "var(--text-secondary)" }}>
            or click to browse &mdash; accepts <strong>.csv</strong> and <strong>.json</strong>
          </p>
          <input id="file-upload-input" type="file" accept=".csv,.json" onChange={onFileChange} style={{ display: "none" }} />
        </label>

        <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 16, flexWrap: "wrap" }}>
          {file
            ? <span className="file-badge">&#128196; {file.name} <span style={{ color: "var(--text-secondary)" }}>({(file.size / 1024).toFixed(1)} KB)</span></span>
            : <span className="file-badge" style={{ color: "var(--text-muted)" }}>No file selected</span>}
          <button className="btn-primary" onClick={() => file && handleUpload(file)} disabled={!file || uploading || clearing}>
            {uploading ? "Processing…" : "Submit for Analysis"}
          </button>
          <button
            type="button"
            onClick={handleClearDatabase}
            disabled={uploading || clearing}
            style={{
              marginLeft: "auto",
              padding: "9px 18px",
              background: "#dc2626",
              color: "#ffffff",
              border: "1px solid #b91c1c",
              borderRadius: "8px",
              fontWeight: 600,
              fontSize: "14px",
              cursor: (uploading || clearing) ? "not-allowed" : "pointer",
              opacity: (uploading || clearing) ? 0.6 : 1,
              transition: "background 0.2s ease, opacity 0.2s ease",
              display: "inline-flex",
              alignItems: "center",
              gap: "7px",
              boxShadow: "0 1px 2px rgba(220, 38, 38, 0.2)",
            }}
            onMouseOver={e => { if (!uploading && !clearing) e.currentTarget.style.background = "#b91c1c"; }}
            onMouseOut={e => { if (!uploading && !clearing) e.currentTarget.style.background = "#dc2626"; }}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
            </svg>
            {clearing ? "Clearing Database…" : "Clear Database"}
          </button>
        </div>

        {/* Real-time progress bar — shown during upload */}
        {progress !== null && <UploadProgressBar progress={progress} />}

        {successMsg && (
          <div style={{
            marginTop: 16,
            padding: "12px 16px",
            background: "#ecfdf5",
            border: "1px solid #6ee7b7",
            color: "#065f46",
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 500,
            display: "flex",
            alignItems: "center",
            gap: 10
          }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <span>{successMsg}</span>
          </div>
        )}

        {error && <div className="error" style={{ marginTop: 16 }}>{error}</div>}
      </section>

      <section className="panel">
        <div className="section-heading" style={{ marginBottom: 12 }}>
          <div>
            <h2>Relational Evidence Schema &amp; Hierarchical Ingestion</h2>
            <p className="chart-note">Ingestion runs strictly in hierarchical order (Parent tables first, then Child tables) with explicit Foreign Key validation.</p>
          </div>
          <span className="tag blue">POSTGRESQL RELATIONAL</span>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16, marginTop: 12 }}>
          <div style={{ background: "#f8fafc", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#1e3a8a", display: "block", marginBottom: 6 }}>
              Level 1 (Root Parent): AssetInventory
            </span>
            <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 8px" }}>Primary key: <code>asset_name</code></p>
            <div style={{ fontSize: 11, color: "#334155" }}>
              Columns: <code>asset_name, asset_type, department, asset_criticality</code>
            </div>
          </div>
          <div style={{ background: "#f8fafc", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#1e3a8a", display: "block", marginBottom: 6 }}>
              Level 2 (Parent of Evidence): SocAlerts
            </span>
            <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 8px" }}>FK: <code>asset_name &rarr; asset_inventory</code></p>
            <div style={{ fontSize: 11, color: "#334155" }}>
              Columns: <code>alert_id, entity_id, asset_name, alert_category, alert_severity, time_to_close_seconds, escalated, resolution_notes</code>
            </div>
          </div>
          <div style={{ background: "#f8fafc", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#1e3a8a", display: "block", marginBottom: 6 }}>
              Level 3: Case Management
            </span>
            <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 8px" }}>FK: <code>alert_id &rarr; soc_alerts.alert_id</code></p>
            <div style={{ fontSize: 11, color: "#334155" }}>
              Columns: <code>case_id, alert_id, timestamp, sensor_id, alert_name, severity, mitre_tactic, source_ip, destination_ip</code>
            </div>
          </div>
          <div style={{ background: "#f8fafc", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#1e3a8a", display: "block", marginBottom: 6 }}>
              Level 3: Investigation Workflows
            </span>
            <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 8px" }}>FK: <code>alert_id &rarr; soc_alerts.alert_id</code></p>
            <div style={{ fontSize: 11, color: "#334155" }}>
              Columns: <code>workflow_id, alert_id, case_id, action_taken, action_timestamp, result, time_spent_minutes, investigator</code>
            </div>
          </div>
          <div style={{ background: "#f8fafc", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#1e3a8a", display: "block", marginBottom: 6 }}>
              Level 3: Escalation Records
            </span>
            <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 8px" }}>FK: <code>alert_id &rarr; soc_alerts.alert_id</code></p>
            <div style={{ fontSize: 11, color: "#334155" }}>
              Columns: <code>escalation_id, alert_id, case_id, escalated_from_tier, escalated_to_tier, escalation_reason, escalation_timestamp</code>
            </div>
          </div>
          <div style={{ background: "#f8fafc", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#1e3a8a", display: "block", marginBottom: 6 }}>
              Level 3: Alert Closures &amp; CAPA
            </span>
            <p style={{ fontSize: 12, color: "#64748b", margin: "0 0 8px" }}>FK: <code>alert_id &rarr; soc_alerts.alert_id</code></p>
            <div style={{ fontSize: 11, color: "#334155" }}>
              Columns: <code>closure_id, alert_id, closed_by, closure_reason, resolution_notes, closure_timestamp, capa_action, is_verified</code>
            </div>
          </div>
        </div>
      </section>
    </Page>
  );
}

/* ------------------------------------------------------------------ */
/* Execution Gaps                                                       */
/* ------------------------------------------------------------------ */
function ExecutionGaps({ setPath }: { setPath: (p: string) => void }) {
  const [data, setData] = useState<RecordValue | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { json("/api/dashboard/summary").then(setData).catch(e => setError(e.message)); }, []);
  if (!data) return <Page title="Execution Gaps" subtitle="Rapid closures, template-driven notes, lack of escalation."><LoadState error={error} setPath={setPath} /></Page>;

  const speedCount = data.summary?.speed_anomalies_count ?? 0;
  const notesClusters = data.summary?.repetitive_notes_clusters ?? 0;
  const speedAnomalies: RecordValue[] = data.speed_anomalies ?? [];
  const hasData = speedCount > 0 || notesClusters > 0;

  return (
    <Page title="Execution Gaps" subtitle="Supervisory signals indicating shortcuts in alert resolution quality.">
      <div className="grid grid-2" style={{ marginBottom: 16 }}>
        <div className="panel">
          <div className="meta-label">Speed Anomalies</div>
          <div className="meta-value">{speedCount}</div>
          <p className="chart-note" style={{ marginTop: 8 }}>Alerts closed suspiciously fast relative to category norms.</p>
        </div>
        <div className="panel">
          <div className="meta-label">Repetitive Note Clusters</div>
          <div className="meta-value">{notesClusters}</div>
          <p className="chart-note" style={{ marginTop: 8 }}>Template-driven or copy-paste resolution notes detected.</p>
        </div>
      </div>
      <section className="panel">
        <div className="section-heading" style={{ marginBottom: 16 }}>
          <h2>Speed Anomaly Records</h2>
          <span className="muted-note">Alerts flagged for unusually fast closure</span>
        </div>
        {!hasData || speedAnomalies.length === 0 ? (
          <EmptyState
            setPath={setPath}
            title="No Execution Gaps"
            message="No speed anomalies detected in the current dataset."
          />
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr>{["Alert ID", "Entity", "Asset", "Category", "Severity", "Closed (s)", "Escalated", "Notes"].map(h => <th key={h}>{h}</th>)}</tr></thead>
              <tbody>
                {speedAnomalies.slice(0, 50).map((row: RecordValue, i: number) => (
                  <tr key={row.ticket_id || row.alert_id || i}>
                    <td>{row.ticket_id || row.alert_id}</td>
                    <td>{row.entity_id || "–"}</td>
                    <td>{row.dest_asset || row.asset_name || row.asset}</td>
                    <td>{row.alert_type || row.alert_category}</td>
                    <td><Tag value={String(row.severity || row.alert_severity || "").toUpperCase()} /></td>
                    <td><strong style={{ color: "var(--danger)" }}>{row.time_to_close || row.time_to_close_seconds}</strong></td>
                    <td>{row.escalated ? <Tag value="YES" /> : <span style={{ color: "var(--text-muted)" }}>No</span>}</td>
                    <td style={{ maxWidth: 280, whiteSpace: "normal" }}>{row.explanation || row.resolution_notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </Page>
  );
}

/* ------------------------------------------------------------------ */
/* Negative Space                                                       */
/* ------------------------------------------------------------------ */
function NegativeSpace({ setPath }: { setPath: (p: string) => void }) {
  const [data, setData] = useState<RecordValue | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { json("/api/dashboard/summary").then(setData).catch(e => setError(e.message)); }, []);
  if (!data) return <Page title="Negative Space" subtitle="Missing telemetry and monitoring blind spots."><LoadState error={error} setPath={setPath} /></Page>;

  const blindCount = data.summary?.blind_spots_count ?? 0;
  const blindSpots: RecordValue[] = data.blind_spots ?? [];

  return (
    <Page title="Negative Space" subtitle="Assets and time windows with absent telemetry or monitoring coverage.">
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="meta-label">Telemetry Blind Spots Detected</div>
        <div className="meta-value">{blindCount}</div>
      </div>
      <section className="panel">
        <div className="section-heading" style={{ marginBottom: 16 }}>
          <h2>Blind Spot Records</h2>
          <span className="muted-note">Assets or time windows with no monitoring signal</span>
        </div>
        {blindCount === 0 || blindSpots.length === 0 ? (
          <EmptyState
            setPath={setPath}
            title="Insufficient Baseline Data"
            message="Insufficient baseline inventory data to perform Blind Spot analysis. Please ensure asset inventory is provided alongside SOC alerts."
          />
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr>{["Entity", "Asset", "Window / Period", "Signal Type", "Status"].map(h => <th key={h}>{h}</th>)}</tr></thead>
              <tbody>
                {blindSpots.slice(0, 50).map((row: RecordValue, i: number) => (
                  <tr key={i}>
                    <td>{row.entity_id ?? "–"}</td>
                    <td>{row.asset_name ?? row.asset ?? "–"}</td>
                    <td>{row.window ?? row.period ?? "–"}</td>
                    <td>{row.signal_type ?? "Telemetry"}</td>
                    <td><Tag value="Missing" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </Page>
  );
}

/* ------------------------------------------------------------------ */
/* Peer Comparison                                                      */
/* ------------------------------------------------------------------ */
function PeerComparison({ setPath }: { setPath: (p: string) => void }) {
  const [data, setData] = useState<RecordValue | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { json("/api/assets").then(setData).catch(e => setError(e.message)); }, []);
  if (!data) return <Page title="Peer Comparison" subtitle="Entity benchmarking risk indicators."><LoadState error={error} setPath={setPath} /></Page>;
  const assets: RecordValue[] = data.assets ?? [];
  const sorted = [...assets].sort((a, b) => Math.abs(b.deviation ?? 0) - Math.abs(a.deviation ?? 0));
  return (
    <Page title="Peer Comparison" subtitle="Alert volume deviation relative to peer asset group norms.">
      <section className="panel">
        <div className="section-heading" style={{ marginBottom: 16 }}>
          <h2>Asset Risk Benchmarking</h2>
          <span className="muted-note">{assets.length} assets assessed</span>
        </div>
        {assets.length === 0 ? (
          <EmptyState
            setPath={setPath}
            title="Insufficient Baseline Data"
            message="Insufficient baseline inventory data to perform Peer Comparison analysis. Please ensure asset inventory is provided alongside SOC alerts."
          />
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr>{["Asset", "Type", "Dept", "Alert Volume", "Peer Expected", "Deviation", "Status"].map(h => <th key={h}>{h}</th>)}</tr></thead>
              <tbody>
                {sorted.map((asset: RecordValue, i: number) => (
                  <tr key={asset.asset ?? i}>
                    <td><strong>{asset.asset}</strong></td>
                    <td>{asset.type}</td><td>{asset.department}</td>
                    <td>{asset.alert_volume}</td><td>{asset.expected_peer_volume}</td>
                    <td style={{ color: (asset.deviation ?? 0) > 0 ? "var(--danger)" : "var(--success)", fontWeight: 700 }}>
                      {(asset.deviation ?? 0) > 0 ? "+" : ""}{asset.deviation}
                    </td>
                    <td><Tag value={asset.monitoring_status === "Observed" ? "Observed" : "Attention"} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </Page>
  );
}

/* ------------------------------------------------------------------ */
/* Audit Reports                                                        */
/* ------------------------------------------------------------------ */
function AuditReports() {
  const [scope, setScope] = useState("assessment");
  const [format, setFormat] = useState("pdf");
  const [ticket, setTicket] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [download, setDownload] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  async function generate() {
    try {
      setError(null); setDownload(null); setGenerating(true);
      const res = await request("/api/reports/export", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scope, format, ticket_id: scope === "single_case" ? ticket : null }),
      });
      const blob = await res.blob();
      setDownload(URL.createObjectURL(blob));
    } catch (e: any) { setError(e.message); }
    finally { setGenerating(false); }
  }

  return (
    <Page title="Audit Reports" subtitle="Immutable logs of supervisory decisions. Generate and export assessment records.">
      <section className="panel" style={{ marginBottom: 16 }}>
        <h2 style={{ marginBottom: 18 }}>Generate Report</h2>
        <div className="report-builder">
          <label>Scope
            <select value={scope} onChange={e => setScope(e.target.value)}>
              <option value="assessment">Complete Assessment</option>
              <option value="findings">Findings</option>
              <option value="analytics">Analytics Signals</option>
              <option value="assets">Asset Monitoring</option>
              <option value="single_case">Single Case</option>
              <option value="custom">Custom Report</option>
            </select>
          </label>
          {scope === "single_case" && (
            <label>Ticket ID<input value={ticket} onChange={e => setTicket(e.target.value)} placeholder="TKT-000001" /></label>
          )}
          <label>Format
            <select value={format} onChange={e => setFormat(e.target.value)}>
              <option value="pdf">PDF</option><option value="json">JSON</option>
              <option value="csv">CSV</option><option value="txt">TXT</option>
            </select>
          </label>
          <button className="btn-primary" onClick={generate} disabled={generating || (scope === "single_case" && !ticket)}>
            {generating ? "Generating…" : "Generate Report"}
          </button>
          {download && <a className="download" href={download} download={`sat-sa-${scope}.${format}`}>↓ Download report</a>}
        </div>
        {error && <div className="error" style={{ marginTop: 16 }}>{error}</div>}
      </section>
      <div className="notice">
        Reports are generated locally from synthetic demonstration data. No official classification, affiliation, or external integration is implied.
      </div>
    </Page>
  );
}

/* ------------------------------------------------------------------ */
/* Charts                                                               */
/* ------------------------------------------------------------------ */
function SeverityDonut({ counts }: { counts: Record<string, number> }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const total = Object.values(counts).reduce((s, v) => s + v, 0);
  const radius = 42;
  const circ = 2 * Math.PI * radius;
  const colors: Record<string, string> = {
    CRITICAL: "#EF4444",
    HIGH: "#3B82F6",
    MEDIUM: "#F59E0B",
    LOW: "#22C55E",
  };

  // Build arc data first so we can render hovered slice last (on top)
  let off = 0;
  const arcs = ["CRITICAL", "HIGH", "MEDIUM", "LOW"].map(sev => {
    const count = counts[sev] || 0;
    const len = total ? (count / total) * circ : 0;
    const pct = total ? Math.round((count / total) * 100) : 0;
    // Calculate angle for percentage text inside the slice
    const midAngle = total && count > 0 ? -90 + ((off + len / 2) / circ) * 360 : 0;
    const rad = (midAngle * Math.PI) / 180;
    const textX = 56 + radius * Math.cos(rad);
    const textY = 56 + radius * Math.sin(rad);

    const arc = {
      sev,
      count,
      len,
      off,
      pct,
      color: colors[sev],
      textX,
      textY,
    };
    off += len;
    return arc;
  });

  const sorted = [
    ...arcs.filter(a => a.sev !== hovered),
    ...arcs.filter(a => a.sev === hovered),
  ];

  return (
    <div className="donut-wrap">
      <div className="donut-chart">
        <svg
          viewBox="0 0 112 112"
          role="img"
          aria-label={`Findings by severity, ${total} total`}
          style={{ overflow: "visible", width: "100%", height: "100%" }}
        >
          {/* Background track */}
          <circle cx="56" cy="56" r={radius} fill="none" stroke="#dbe7f5" strokeWidth="15" />
          {sorted.map(({ sev, count, len, off: arcOff, color }) => {
            const isHov = hovered === sev;
            return (
              <circle
                key={sev}
                cx="56"
                cy="56"
                r={isHov ? 43 : radius}
                fill="none"
                stroke={color}
                strokeWidth={isHov ? 17 : 15}
                strokeDasharray={`${isHov ? len * (43 / radius) : len} ${circ}`}
                strokeDashoffset={-arcOff}
                transform="rotate(-90 56 56)"
                style={{
                  cursor: "pointer",
                  transition: "r 0.18s, stroke-width 0.18s",
                  filter: isHov ? `drop-shadow(0 0 4px ${color}88)` : "none",
                }}
                onMouseEnter={() => setHovered(sev)}
                onMouseLeave={() => setHovered(null)}
              >
                <title>{sev}: {count.toLocaleString()} ({total ? Math.round((count / total) * 100) : 0}%)</title>
              </circle>
            );
          })}

          {/* Percentages inside donut slices */}
          {arcs.map(({ sev, count, pct, textX, textY }) => {
            if (!count || pct < 6) return null;
            return (
              <text
                key={`pct-${sev}`}
                x={textX}
                y={textY + 2.5}
                textAnchor="middle"
                fill="#ffffff"
                fontSize="6.5"
                fontWeight="800"
                style={{
                  pointerEvents: "none",
                  textShadow: "0 1px 2px rgba(0,0,0,0.45)",
                }}
              >
                {pct}%
              </text>
            );
          })}

          {/* Center text — "TOTAL 8" */}
          <text
            x="56"
            y="50"
            textAnchor="middle"
            fill={hovered ? colors[hovered] : "#475569"}
            fontSize="8"
            fontWeight="700"
            letterSpacing="0.06em"
            style={{ transition: "fill 0.2s" }}
          >
            {hovered || "TOTAL"}
          </text>
          <text
            x="56"
            y="67"
            textAnchor="middle"
            fill="#0f172a"
            fontSize="18"
            fontWeight="800"
          >
            {(hovered ? counts[hovered] : total).toLocaleString()}
          </text>
          {hovered && (
            <text
              x="56"
              y="77"
              textAnchor="middle"
              fill="#64748b"
              fontSize="6.5"
              fontWeight="600"
            >
              {total ? Math.round((counts[hovered] / total) * 100) : 0}% of total
            </text>
          )}
        </svg>
      </div>

      <div className="severity-legend">
        {[
          { key: "CRITICAL", label: "Critical", color: colors.CRITICAL },
          { key: "HIGH", label: "High", color: colors.HIGH },
          { key: "MEDIUM", label: "Medium", color: colors.MEDIUM },
          { key: "LOW", label: "Low", color: colors.LOW },
        ].map(({ key, label, color }) => (
          <div
            key={key}
            onMouseEnter={() => setHovered(key)}
            onMouseLeave={() => setHovered(null)}
            className={`severity-legend-row ${hovered === key ? "active" : ""}`}
            style={{
              cursor: "pointer",
              opacity: hovered && hovered !== key ? 0.45 : 1,
              transition: "opacity 0.15s, background-color 0.15s",
            }}
          >
            <span
              className="legend-bullet"
              style={{ backgroundColor: color }}
            />
            <span className="legend-label">{label}</span>
            <strong className="legend-count">{(counts[key] || 0).toLocaleString()}</strong>
            <small className="legend-pct">
              {total ? `${Math.round(((counts[key] || 0) / total) * 100)}%` : "0%"}
            </small>
          </div>
        ))}
      </div>
    </div>
  );
}



function AnalyticsStatistics({ dashboard, assessment }: { dashboard: RecordValue; assessment: RecordValue }) {
  const counts = ["CRITICAL", "HIGH", "MEDIUM", "LOW"].reduce<Record<string, number>>((r, sev) => {
    r[sev] = assessment.findings.filter((f: RecordValue) => f.severity === sev).length; return r;
  }, {});
  const signals = [
    ["Speed anomalies", dashboard.summary.speed_anomalies_count, "red"],
    ["Repetitive-note clusters", dashboard.summary.repetitive_notes_clusters, "blue"],
    ["Telemetry blind spots", dashboard.summary.blind_spots_count, "black"],
  ];
  const assets = [...assessment.assets].sort((a: RecordValue, b: RecordValue) =>
    Math.abs(b.deviation) - Math.abs(a.deviation)).slice(0, 5);
  return (
    <>
      <section className="panel statistical-summary">
        <div className="section-heading">
          <h2>Statistical Assessment</h2>
          <span className="muted-note">Calculated from supplied operational evidence</span>
        </div>
        <div className="stat-grid">
          {[
            ["Analytics Signals", dashboard.summary.total_flagged_anomalies],
            ["Speed Anomalies", dashboard.summary.speed_anomalies_count],
            ["Repetitive Resolution Patterns", dashboard.summary.repetitive_notes_clusters],
            ["Telemetry Blind Spots", dashboard.summary.blind_spots_count],
            ["Records Assessed", assessment.lifecycle.records_assessed],
            ["Assets Monitored", assessment.assets.length],
          ].map(([label, value]) => (
            <div className="stat-block" key={label}>
              <strong>{Number(value).toLocaleString()}</strong>
              <span>{label}</span>
            </div>
          ))}
        </div>
      </section>
      <div className="analytics-grid">
        <section className="panel panel-findings-severity">
          <h2>Findings by Severity</h2>
          <SeverityDonut counts={counts} />
        </section>
        <section className="panel panel-findings-trend">
          <h2>Findings Trend</h2>
          <p className="chart-note">Closure-speed signals by observed ticket date.</p>
          <FindingsTrend anomalies={dashboard.speed_anomalies} trend={dashboard.trend || dashboard.summary?.trend} />
        </section>
      </div>
      <div className="analytics-grid">
        <section className="panel panel-security-note">
          <div className="section-heading">
            <h2>Security Note</h2>
            <ShieldCheck size={20} style={{ color: "#4f46e5" }} />
          </div>
          <p className="chart-note">Supervisory integrity and evidence provenance.</p>
          <div className="security-note-card">
            <p className="security-note-text">
              All supervisory evaluations, anomaly detection models, and evidence verifications operate in an air-gapped local environment. Operational data is cryptographically tracked and tamper-evident.
            </p>
            <div className="security-signals-list">
              {signals.map(([label, value, tone]) => (
                <div className="security-signal-row" key={label}>
                  <div className="security-signal-info">
                    <span className={`signal-status-dot ${tone}`} />
                    <span className="security-signal-label">{label}</span>
                  </div>
                  <strong>{Number(value).toLocaleString()}</strong>
                </div>
              ))}
            </div>
          </div>
        </section>
        <section className="panel panel-top-assets">
          <h2>Top Assets by Deviation</h2>
          <p className="chart-note">Largest observed departures from peer volume.</p>
          <div className="table-card">
            <table className="mini-table">
              <thead><tr><th>Asset</th><th>Deviation</th><th>Status</th></tr></thead>
              <tbody>
                {assets.map((asset: RecordValue) => (
                  <tr key={asset.asset}>
                    <td>{asset.asset}</td>
                    <td>{asset.deviation > 0 ? "+" : ""}{asset.deviation}</td>
                    <td><Tag value={asset.monitoring_status === "Observed" ? "Observed" : "Attention"} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Dashboard Overview                                                   */
/* ------------------------------------------------------------------ */
function Overview({ setPath }: { setPath: (p: string) => void }) {
  const [data, setData] = useState<RecordValue | null>(null);
  const [loading, setLoading] = useState(true);
  const [empty, setEmpty] = useState(false);

  useEffect(() => {
    let isMounted = true;
    setLoading(true);
    setEmpty(false);

    Promise.all([
      json("/api/assessment").catch(() => null),
      json("/api/dashboard/summary").catch(() => null),
      json("/api/priorities").catch(() => null),
    ])
      .then(([assessment, dashboard, priority]) => {
        if (!isMounted) return;
        if (!assessment || !dashboard || !priority) {
          setEmpty(true);
          setData(null);
          return;
        }

        const totalRecords = assessment.lifecycle?.records_assessed ?? 0;
        const totalFindings = assessment.findings?.length ?? 0;
        const totalSignals = dashboard.summary?.total_flagged_anomalies ?? 0;

        if (totalRecords === 0 && totalFindings === 0 && totalSignals === 0) {
          setEmpty(true);
          setData(null);
        } else {
          setData({ assessment, dashboard, priority });
          setEmpty(false);
        }
      })
      .catch(() => {
        if (!isMounted) return;
        setEmpty(true);
        setData(null);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, []);

  if (loading) {
    return (
      <Page title="Dashboard Overview" subtitle="Operational effectiveness based on available alert, process, and evidence records.">
        <div className="panel" style={{ textAlign: "center", padding: "48px 20px", color: "var(--text-secondary)" }}>
          Loading supervisory assessment data...
        </div>
      </Page>
    );
  }

  if (empty || !data) {
    return (
      <Page title="Dashboard Overview" subtitle="Operational effectiveness based on available alert, process, and evidence records.">
        <EmptyState setPath={setPath} />
      </Page>
    );
  }
  const { assessment, dashboard, priority } = data;
  overviewAnalyticsData = { assessment, dashboard };
  return (
    <Page title="Dashboard Overview" subtitle="High-level risk scores, analytics signals, and assessment dimensions.">
      <div className="grid grid-5">
        {[
          ["Records assessed", assessment.lifecycle.records_assessed.toLocaleString()],
          ["Findings requiring attention", assessment.findings.length],
          ["Analytics signals", dashboard.summary.total_flagged_anomalies],
          ["Assets monitored", assessment.assets.length],
          ["System status", "Operational"],
        ].map(([label, value]) => (
          <div className="panel" key={label}>
            <div className="meta-label">{label}</div>
            <div className="meta-value">{value}</div>
          </div>
        ))}
      </div>
      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <section className="panel">
          <h2>Supervisory Assessment Summary</h2>
          <div style={{ fontSize: 30, margin: "12px 0" }}>
            {assessment.overall_score} <small style={{ color: "var(--text-secondary)", fontSize: 14 }}>/ 100</small>
          </div>
          <div className="bar"><span style={{ width: `${assessment.overall_score}%` }} /></div>
          <p className="subtitle" style={{ margin: "10px 0 0" }}>Weighted result across seven dimensions.</p>
        </section>
        <section className="panel">
          <h2>Findings by Severity</h2>
          <div className="severity-list">
            {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map(sev => (
              <div key={sev}>
                <Tag value={sev} />
                <strong>{assessment.findings.filter((f: RecordValue) => f.severity === sev).length}</strong>
              </div>
            ))}
          </div>
        </section>
      </div>
      <section className="panel" style={{ marginTop: 16 }}>
        <div className="section-heading">
          <h2>AI-Assisted Review Priority</h2>
          <span className="muted-note">Recommendation only. Analyst retains decision authority.</span>
        </div>
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>#</th><th>Case</th><th>Priority</th><th>Severity</th><th>Asset</th><th>Analyst</th><th>Reasons</th></tr></thead>
            <tbody>
              {priority.priorities.slice(0, 8).map((item: RecordValue) => (
                <tr key={item.ticket_id}>
                  <td>{item.rank}</td>
                  <td><a href={`/evidence?ticket=${item.ticket_id}`}>{item.ticket_id}</a></td>
                  <td><strong>{item.priority_score}</strong> <Tag value={item.priority} /></td>
                  <td><Tag value={item.severity} /></td>
                  <td>{item.asset}</td><td>{item.analyst}</td>
                  <td>{item.reasons.join("; ") || "Review recommended from available evidence."}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel" style={{ marginTop: 16 }}>
        <h2>Assessment Dimensions</h2>
        {assessment.dimensions.map((d: RecordValue) => (
          <div className="score-row" key={d.dimension}>
            <strong>{d.dimension}</strong>
            <span className="score-number">{d.score}</span>
            <div className="bar"><span style={{ width: `${d.score}%` }} /></div>
            <Tag value={d.status} />
            <small>{d.finding_count} findings</small>
          </div>
        ))}
      </section>
    </Page>
  );
}

/* ------------------------------------------------------------------ */
/* Legacy pages kept for existing API links                             */
/* ------------------------------------------------------------------ */
function Assessment() {
  const [data, setData] = useState<RecordValue | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { json("/api/assessment").then(setData).catch(e => setError(e.message)); }, []);
  return (
    <Page title="Assessment" subtitle="Transparent dimension scores and assessment logic.">
      {!data ? <LoadState error={error} /> : (
        <div className="grid grid-2">
          {data.dimensions.map((d: RecordValue) => (
            <section className="panel" key={d.dimension}>
              <div className="section-heading"><h2>{d.dimension}</h2><Tag value={d.status} /></div>
              <div style={{ fontSize: 28 }}>{d.score} <small className="muted-note">/ 100 | {d.weight * 100}% weight</small></div>
              <div className="bar" style={{ margin: "10px 0 16px" }}><span style={{ width: `${d.score}%` }} /></div>
              <p className="subtitle">Records assessed: {d.records_assessed} | Missing evidence: {d.records_missing_evidence}</p>
              <p className="logic">{d.assessment_logic}</p>
            </section>
          ))}
        </div>
      )}
    </Page>
  );
}

function Findings() {
  const [data, setData] = useState<RecordValue | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { json("/api/findings").then(setData).catch(e => setError(e.message)); }, []);
  return (
    <Page title="Findings" subtitle="Supervisory work queue. Automated findings are review signals, not final conclusions.">
      {!data ? <LoadState error={error} /> : (
        <section className="panel">
          <div className="filters">
            <select aria-label="Severity"><option>All severities</option></select>
            <select aria-label="Status"><option>All statuses</option><option>Open</option><option>Under Review</option></select>
            <select aria-label="Finding type"><option>All finding types</option></select>
          </div>
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr>{["Priority", "Severity", "Case ID", "Finding", "Asset", "Analyst", "Status"].map(x => <th key={x}>{x}</th>)}</tr></thead>
              <tbody>
                {data.findings.map((f: RecordValue) => (
                  <tr key={f.finding_id}>
                    <td><a href={`/prioritizer?ticket=${f.entity}`}>Review</a></td>
                    <td><Tag value={f.severity} /></td>
                    <td>{f.entity}</td><td>{f.observation}</td><td>{f.asset}</td>
                    <td>{f.analyst || "Not available"}</td>
                    <td><Tag value={f.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </Page>
  );
}

function PriorityWorkspace() {
  // ── All hooks at the top — Rules of Hooks compliance ──
  const [data, setData] = useState<RecordValue | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [severity, setSeverity] = useState("ALL");
  const [classification, setClassification] = useState("ALL");
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [sort, setSort] = useState("score");
  const [selected, setSelected] = useState<RecordValue | null>(null);
  const [recommendedRef, setRecommendedRef] = useState<RecordValue | null>(null);
  const [showCapa, setShowCapa] = useState<boolean>(true);

  useEffect(() => { json("/api/priorities").then(setData).catch(e => setError(e.message)); }, []);

  // Fetch Cross-CSE recommendation whenever the selected ticket changes
  useEffect(() => {
    if (!selected?.ticket_id) { setRecommendedRef(null); return; }
    setRecommendedRef(null);
    json(`/api/audit/recommend-reference/${selected.ticket_id}`)
      .then(res => {
        if (res?.has_recommendation && res?.recommended_reference?.match_found) {
          setRecommendedRef(res.recommended_reference);
        }
      })
      .catch(() => {});
  }, [selected]);

  async function updateStatus(ticketId: string, nextStatus: string) {
    try {
      await request(`/api/priorities/${ticketId}/status`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      setData(cur => cur ? {
        ...cur, priorities: cur.priorities.map((item: RecordValue) =>
          item.ticket_id === ticketId ? { ...item, status: nextStatus } : item)
      } : cur);
      setSelected(cur => cur ? { ...cur, status: nextStatus } : cur);
    } catch (err: any) { setError(err.message); }
  }

  if (!data) return <Page title="AI-Assisted Prioritization" subtitle="Decision-support recommendation. Final review remains with the analyst."><LoadState error={error} /></Page>;
  const visible = [...data.priorities]
    .filter((item: RecordValue) =>
      (severity === "ALL" || item.severity === severity) &&
      (classification === "ALL" || item.priority === classification) &&
      (statusFilter === "ALL" || item.status === statusFilter) &&
      [item.ticket_id, item.asset, item.analyst, item.alert_type].join(" ").toLowerCase().includes(query.toLowerCase()))
    .sort((a: RecordValue, b: RecordValue) =>
      sort === "rank" ? a.rank - b.rank :
        sort === "timestamp" ? String(b.timestamp).localeCompare(String(a.timestamp)) :
          b.priority_score - a.priority_score);

  return (
    <Page title="AI-Assisted Prioritization" subtitle="Recommendation only. Analyst retains decision authority.">
      <div className="filters">
        <input aria-label="Search cases" placeholder="Search case, asset, analyst..." value={query} onChange={e => setQuery(e.target.value)} />
        <select aria-label="Severity filter" value={severity} onChange={e => setSeverity(e.target.value)}>
          <option value="ALL">All severities</option>
          {["CRITICAL", "HIGH", "MEDIUM", "LOW"].map(v => <option key={v}>{v}</option>)}
        </select>
        <select aria-label="Classification filter" value={classification} onChange={e => setClassification(e.target.value)}>
          <option value="ALL">All classifications</option>
          {["URGENT", "HIGH", "MEDIUM", "LOW"].map(v => <option key={v}>{v}</option>)}
        </select>
        <select aria-label="Status filter" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="ALL">All statuses</option>
          {["NEW", "UNDER_REVIEW", "ASSIGNED", "INVESTIGATING", "ESCALATED", "RESOLVED", "CLOSED"].map(v => <option key={v}>{v}</option>)}
        </select>
        <select aria-label="Sort" value={sort} onChange={e => setSort(e.target.value)}>
          <option value="score">Sort by score</option>
          <option value="rank">Sort by rank</option>
          <option value="timestamp">Sort by newest</option>
        </select>
      </div>
      <section className="panel">
        <div className="table-wrap">
          <table className="data-table">
            <thead><tr><th>Rank</th><th>Case</th><th>Score</th><th>Severity</th><th>Asset</th><th>Analyst</th><th>Timestamp</th><th>Status</th><th>Reasons</th></tr></thead>
            <tbody>
              {visible.map((item: RecordValue) => (
                <tr className="link-row" onClick={() => setSelected(item)} key={item.ticket_id}>
                  <td>{item.rank}</td><td>{item.ticket_id}</td>
                  <td><strong>{item.priority_score}</strong> <Tag value={item.priority_classification ?? item.priority} /></td>
                  <td><Tag value={item.severity} /></td>
                  <td>{item.asset}</td><td>{item.analyst}</td>
                  <td>{item.timestamp ? new Date(item.timestamp).toLocaleString() : "Not available"}</td>
                  <td>{item.status}</td>
                  <td>{item.reasons.join("; ") || "Review recommended from available evidence."}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      {selected && (
        <aside className="detail">
          <div className="detail-header">
            <h2>{selected.ticket_id}</h2>
            <button className="close" aria-label="Close" onClick={() => setSelected(null)}>✕</button>
          </div>
          <p className="subtitle">Priority {selected.priority_score} | {selected.severity} | {selected.asset}</p>

          {/* Cross-CSE Similar Ticket Reference Notification Banner */}
          {recommendedRef && (
            <div style={{
              margin: "14px 0",
              padding: "14px",
              background: "#eff6ff",
              border: "1px solid #bfdbfe",
              borderRadius: 8,
              fontSize: 13,
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                <span style={{ fontWeight: 700, color: "#1e40af", fontSize: 12 }}>Cross-CSE Audit Reference Available</span>
                <span style={{ fontSize: 11, fontWeight: 700, padding: "1px 6px", borderRadius: 999, background: "#dcfce7", color: "#15803d" }}>
                  {recommendedRef.similarity_score}% Match
                </span>
                <span style={{ fontSize: 11, fontWeight: 600, padding: "1px 6px", borderRadius: 4, background: "#dbeafe", color: "#1e40af" }}>
                  {recommendedRef.matched_entity_id}
                </span>
              </div>
              <p style={{ margin: "0 0 10px", color: "#1e293b", fontSize: 13, lineHeight: 1.4, fontWeight: 500 }}>
                You have audited a similar anomaly from another CSE before. Do you want to review that historical Corrective Action (CAPA) as a reference?
              </p>
              <button
                type="button"
                className="btn-primary"
                onClick={() => setShowCapa(!showCapa)}
                style={{ fontSize: 12, padding: "5px 12px", background: "#2563eb", color: "#fff", borderRadius: 6, border: "none", cursor: "pointer" }}
              >
                {showCapa ? "Hide Historical CAPA" : "Review Historical CAPA"}
              </button>
              {showCapa && (
                <div style={{ marginTop: 10, padding: 10, background: "#fff", borderRadius: 6, border: "1px solid #cbd5e1" }}>
                  <div style={{ fontSize: 11, color: "#64748b", marginBottom: 4 }}>
                    Historical Precedent: <strong>{recommendedRef.matched_ticket_id}</strong> ({recommendedRef.matched_entity_id}) &mdash; {recommendedRef.matched_category}
                  </div>
                  {recommendedRef.historical_notes && (
                    <div style={{ fontSize: 11, fontStyle: "italic", color: "#475569", marginBottom: 6 }}>
                      &ldquo;{recommendedRef.historical_notes}&rdquo;
                    </div>
                  )}
                  <div style={{ fontSize: 12, color: "#15803d", fontWeight: 600, background: "#f0fdf4", padding: "8px 10px", borderRadius: 4, borderLeft: "3px solid #16a34a" }}>
                    {recommendedRef.historical_capa}
                  </div>
                </div>
              )}
            </div>
          )}

          <label className="detail-status">Review status
            <select aria-label="Update status" value={selected.status} onChange={e => updateStatus(selected.ticket_id, e.target.value)}>
              {["NEW", "UNDER_REVIEW", "ASSIGNED", "INVESTIGATING", "ESCALATED", "RESOLVED", "CLOSED"].map(v => <option key={v}>{v}</option>)}
            </select>
          </label>
          <h3>Review reasons</h3>
          <ul>{selected.reasons.map((r: string) => <li key={r}>{r}</li>)}</ul>
          <p className="logic">Recommendation only. Final review remains with the analyst.</p>
        </aside>
      )}
    </Page>
  );
}

function SimpleDataPage({ endpoint, title, subtitle, columns }: { endpoint: string; title: string; subtitle: string; columns: string[] }) {
  const [data, setData] = useState<RecordValue | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { json(endpoint).then(setData).catch(e => setError(e.message)); }, [endpoint]);
  const rows = data?.evidence ?? data?.assets ?? [];
  return (
    <Page title={title} subtitle={subtitle}>
      {!data ? <LoadState error={error} /> : (
        <section className="panel">
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr>{columns.map(c => <th key={c}>{c.replaceAll("_", " ")}</th>)}</tr></thead>
              <tbody>
                {rows.slice(0, 200).map((row: RecordValue, i: number) => (
                  <tr key={row.ticket_id ?? row.asset ?? i}>
                    {columns.map(col => <td key={col}>{String(row[col] ?? "")}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </Page>
  );
}

function DataSystem() {
  const [data, setData] = useState<RecordValue | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { json("/api/data-quality").then(setData).catch(e => setError(e.message)); }, []);
  return (
    <Page title="Data &amp; System" subtitle="Dataset provenance, quality checks, and local processing status.">
      {!data ? <LoadState error={error} /> : (
        <div className="grid grid-2">
          {["dataset", "data_quality", "processing"].map(section => (
            <section className="panel" key={section}>
              <h2>{section.replaceAll("_", " ")}</h2>
              {Object.entries(data[section]).map(([key, value]) => (
                <div className="score-row" key={key}>
                  <span>{key.replaceAll("_", " ")}</span>
                  <strong>{String(value)}</strong>
                </div>
              ))}
            </section>
          ))}
        </div>
      )}
    </Page>
  );
}

function Evidence() {
  return <SimpleDataPage endpoint="/api/evidence" title="Evidence Review"
    subtitle="Lifecycle evidence review. Missing means not observed in the supplied records."
    columns={["ticket_id", "severity", "alert_type", "analyst", "asset", "assessment"]} />;
}
function Assets() {
  return <SimpleDataPage endpoint="/api/assets" title="Asset Monitoring"
    subtitle="Peer comparison of observed alert volume and telemetry coverage."
    columns={["asset", "criticality", "type", "department", "alert_volume", "expected_peer_volume", "monitoring_status"]} />;
}

/* ------------------------------------------------------------------ */
/* App Router                                                           */
/* ------------------------------------------------------------------ */
export default function App() {
  const [path, setPath] = useState("/");

  const page =
    path === "/data-ingestion" ? <DataIngestion setPath={setPath} /> :
      path === "/execution-gaps" ? <ExecutionGaps setPath={setPath} /> :
        path === "/negative-space" ? <NegativeSpace setPath={setPath} /> :
          path === "/peer-comparison" ? <PeerComparison setPath={setPath} /> :
            path === "/audit-reports" ? <AuditReports /> :
              path === "/prioritizer" ? <PriorityWorkspace /> :
                <Overview setPath={setPath} />;

  return <Shell path={path} setPath={setPath}>{page}</Shell>;
}

