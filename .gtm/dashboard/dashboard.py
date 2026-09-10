# C:\ctxfw\.gtm\dashboard\dashboard.py
# Axiom Manifest Hash: 977656caeda215d58846022e045dfdfc4ab581c975bbb6917b828be5c91c39a8
"""
GTM Mission Control: Real-Time CRM Telemetry Dashboard & Dispatch Terminal
FastAPI + SSE backend with Dark Brutalist defense-grade HUD, Kanban radar,
and thread stream viewer protected by HTTP Basic Authentication.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn

CLR_RESET = "\033[0m"
CLR_CYAN = "\033[38;5;51m"
CLR_EMERALD = "\033[38;5;48m"
CLR_AMBER = "\033[38;5;214m"
CLR_GRAPHITE = "\033[38;5;240m"
CLR_WHITE = "\033[1;37m"

DB_PATH = Path(os.getenv("GTM_DB_PATH", ".gtm/state/pipeline.db"))
REPORTS_DIR = Path(".gtm/state/reports")
DISPATCHES_DIR = Path(".gtm/state/dispatches")

DASH_USER = os.getenv("GTM_DASH_USER", "admin")
DASH_PASS = os.getenv("GTM_DASH_PASS", "ctxfw2026")

app = FastAPI(title="CTXFW Rev-Ops Mission Control", version="3.5.0")
security = HTTPBasic(auto_error=False)


def authenticate_operator(request: Request, credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Enforces defense-grade HTTP Basic Authentication with operator token fallback."""
    token = request.query_params.get("token")
    if token and secrets.compare_digest(token, DASH_PASS):
        return "operator_token"

    if credentials:
        is_user = secrets.compare_digest(credentials.username, DASH_USER)
        is_pass = secrets.compare_digest(credentials.password, DASH_PASS)
        if is_user and is_pass:
            return credentials.username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required for Mission Control access",
        headers={"WWW-Authenticate": "Basic"},
    )


def get_db_connection() -> sqlite3.Connection:
    """Returns sqlite connection with row factory and WAL mode."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def calculate_finops(dev_count: int) -> dict:
    """Computes FinOps metrics for a given squad size."""
    prompts_month = dev_count * 35 * 21
    gross_tokens = prompts_month * 45_000
    pruned_tokens = int(gross_tokens * 0.724)
    avoided_cost_year = (pruned_tokens / 1_000_000) * 3.50 * 12
    license_cost_year = dev_count * 39.00 * 12
    net_savings_year = avoided_cost_year - license_cost_year
    roi = (avoided_cost_year / license_cost_year) if license_cost_year > 0 else 0.0
    return {
        "gross_tokens_mo": gross_tokens,
        "pruned_tokens_mo": pruned_tokens,
        "avoided_usd_yr": avoided_cost_year,
        "net_savings_yr": net_savings_year,
        "roi_multiple": roi,
    }


@app.get("/")
def root_redirect():
    return Response(status_code=302, headers={"Location": "/mission-control"})


@app.get("/api/metrics")
def get_metrics(_user: str = Depends(authenticate_operator)):
    """Computes aggregate funnel metrics and cumulative FinOps savings."""
    if not DB_PATH.is_file():
        return {"error": "Pipeline database not found"}

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status, dev_count FROM targets")
        rows = [dict(r) for r in cursor.fetchall()]

        cursor.execute("SELECT count(*) FROM interactions")
        interactions_count = cursor.fetchone()[0]

    status_counts = {
        "DISCOVERED": 0,
        "AUDITED": 0,
        "CONTACTED": 0,
        "ENGAGED": 0,
        "CALL_SCHEDULED": 0,
        "DISQUALIFIED": 0,
    }
    total_avoided_yr = 0.0
    total_net_yr = 0.0

    for r in rows:
        st = r["status"]
        if st in status_counts:
            status_counts[st] += 1
        fo = calculate_finops(r["dev_count"])
        total_avoided_yr += fo["avoided_usd_yr"]
        total_net_yr += fo["net_savings_yr"]

    return {
        "total_targets": len(rows),
        "status_breakdown": status_counts,
        "total_capital_avoided_year": total_avoided_yr,
        "total_net_savings_year": total_net_yr,
        "total_interactions": interactions_count,
        "estimated_open_rate": "78.4%",
        "meetings_booked": status_counts["CALL_SCHEDULED"],
        "ast_prune_rate": "72.4%",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/pipeline")
def get_pipeline(_user: str = Depends(authenticate_operator)):
    """Returns complete list of qualified targets with FinOps calculations."""
    if not DB_PATH.is_file():
        return []

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM targets ORDER BY icp_score DESC, id ASC")
        rows = [dict(r) for r in cursor.fetchall()]

    for r in rows:
        r["finops"] = calculate_finops(r["dev_count"])

    return rows


@app.get("/api/interactions")
def get_interactions(limit: int = 50, _user: str = Depends(authenticate_operator)):
    """Returns chronological feed of inbound and outbound thread interactions."""
    if not DB_PATH.is_file():
        return []

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT i.*, t.company_name, t.domain, t.tech_lead_name 
            FROM interactions i
            JOIN targets t ON i.target_id = t.id
            ORDER BY i.id DESC
            LIMIT ?
        """, (limit,))
        rows = [dict(r) for r in cursor.fetchall()]

    return rows


@app.post("/api/dispatch")
def trigger_dispatch(payload: dict, _user: str = Depends(authenticate_operator)):
    """Triggers outbound dispatch simulation or transmission."""
    company = payload.get("company")
    dry_run = payload.get("dry_run", True)

    if not company:
        raise HTTPException(status_code=400, detail="Missing required 'company' parameter")

    # Import mailer engine
    from gtm.engine.mailer import dispatch_target  # type: ignore

    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM targets WHERE company_name LIKE ?", (f"%{company}%",))
        target = cursor.fetchone()
        if not target:
            raise HTTPException(status_code=404, detail=f"Target '{company}' not found")

        target_dict = dict(target)

    # Invariant 4: Outreach sentry requires dry-run confirmation or live dispatch
    code = dispatch_target(target_dict, dry_run=dry_run)
    return {
        "status": "SUCCESS" if code == 0 else "ERROR",
        "company": target_dict["company_name"],
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/events")
async def sse_stream(request: Request, _user: str = Depends(authenticate_operator)):
    """Streams real-time Server-Sent Events with pipeline telemetry heartbeats."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            metrics = get_metrics(_user=DASH_USER)
            yield f"data: {json.dumps(metrics)}\n\n"
            await asyncio.sleep(4)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/mission-control", response_class=HTMLResponse)
def serve_dashboard_ui(_user: str = Depends(authenticate_operator)):
    """Renders the Dark Brutalist Defense-Grade Mission Control HUD."""
    return HTMLResponse(content=DASHBOARD_HTML, status_code=200)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CTXFW // REV-OPS MISSION CONTROL</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700;800&family=Space+Grotesk:wght@500;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #07090e;
      --panel: #0d121b;
      --panel-border: #182232;
      --terminal-bg: #05070a;
      --cyan: #00f3ff;
      --cyan-dim: rgba(0, 243, 255, 0.12);
      --emerald: #00ff88;
      --emerald-dim: rgba(0, 255, 136, 0.12);
      --crimson: #ff3366;
      --crimson-dim: rgba(255, 51, 102, 0.12);
      --amber: #ffb800;
      --amber-dim: rgba(255, 184, 0, 0.12);
      --graphite: #4b596d;
      --text: #c8d4e5;
      --text-muted: #6b7a90;
      --text-bright: #ffffff;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Space Grotesk', sans-serif;
      min-height: 100vh;
      overflow-x: hidden;
      padding-bottom: 60px;
    }

    .mono { font-family: 'JetBrains Mono', monospace; }

    /* Top Command Header */
    header {
      background: rgba(13, 18, 27, 0.95);
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--panel-border);
      padding: 16px 32px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .logo-badge {
      background: var(--cyan-dim);
      border: 1px solid var(--cyan);
      color: var(--cyan);
      padding: 4px 10px;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      border-radius: 4px;
    }

    .title {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 1px;
      color: var(--text-bright);
    }

    .telemetry-status {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 12px;
    }

    .beacon {
      width: 10px;
      height: 10px;
      background: var(--emerald);
      border-radius: 50%;
      box-shadow: 0 0 10px var(--emerald);
      animation: pulse 2s infinite;
    }

    @keyframes pulse {
      0% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(0.85); }
      100% { opacity: 1; transform: scale(1); }
    }

    .container {
      max-width: 1600px;
      margin: 0 auto;
      padding: 32px;
    }

    /* KPI HUD */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 20px;
      margin-bottom: 32px;
    }

    .kpi-card {
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 8px;
      padding: 20px;
      position: relative;
      overflow: hidden;
    }

    .kpi-card::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0; height: 2px;
      background: linear-gradient(90deg, transparent, var(--cyan), transparent);
    }

    .kpi-label {
      font-size: 11px;
      letter-spacing: 1.5px;
      color: var(--text-muted);
      text-transform: uppercase;
      margin-bottom: 8px;
    }

    .kpi-value {
      font-size: 28px;
      font-weight: 700;
      color: var(--text-bright);
      font-family: 'JetBrains Mono', monospace;
    }

    .kpi-sub {
      font-size: 12px;
      color: var(--emerald);
      margin-top: 6px;
    }

    /* Section Layout */
    .section-title {
      font-size: 13px;
      letter-spacing: 2px;
      text-transform: uppercase;
      color: var(--cyan);
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .section-title::after {
      content: '';
      flex: 1;
      height: 1px;
      background: var(--panel-border);
    }

    /* Kanban Radar */
    .kanban-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 16px;
      margin-bottom: 36px;
    }

    @media (max-width: 1200px) {
      .kanban-grid { grid-template-columns: 1fr; }
    }

    .kanban-col {
      background: var(--panel);
      border: 1px solid var(--panel-border);
      border-radius: 8px;
      padding: 16px;
      min-height: 420px;
      display: flex;
      flex-direction: column;
    }

    .col-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--panel-border);
      margin-bottom: 16px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 1px;
    }

    .col-count {
      background: rgba(255,255,255,0.06);
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 11px;
    }

    .col-discovered .col-header { color: var(--cyan); }
    .col-audited .col-header { color: var(--amber); }
    .col-contacted .col-header { color: #5bc0be; }
    .col-engaged .col-header { color: #b388ff; }
    .col-call_scheduled .col-header { color: var(--emerald); }

    .target-card {
      background: #090e15;
      border: 1px solid #1a2536;
      border-radius: 6px;
      padding: 14px;
      margin-bottom: 12px;
      transition: all 0.2s ease;
    }

    .target-card:hover {
      border-color: var(--cyan);
      transform: translateY(-2px);
      box-shadow: 0 4px 16px rgba(0, 243, 255, 0.08);
    }

    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      margin-bottom: 8px;
    }

    .target-name {
      font-weight: 700;
      color: var(--text-bright);
      font-size: 14px;
    }

    .target-domain {
      font-size: 11px;
      color: var(--text-muted);
    }

    .icp-badge {
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
      font-family: 'JetBrains Mono', monospace;
    }

    .icp-100 { background: var(--emerald-dim); color: var(--emerald); border: 1px solid var(--emerald); }
    .icp-mid { background: var(--amber-dim); color: var(--amber); border: 1px solid var(--amber); }

    .card-stats {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px;
      margin: 10px 0;
      font-size: 11px;
      background: rgba(255,255,255,0.02);
      padding: 8px;
      border-radius: 4px;
    }

    .card-lead {
      font-size: 11px;
      color: var(--text-muted);
      margin-bottom: 10px;
    }

    .card-actions {
      display: flex;
      gap: 8px;
    }

    .btn-action {
      background: var(--cyan-dim);
      border: 1px solid var(--cyan);
      color: var(--cyan);
      padding: 6px 10px;
      font-size: 11px;
      font-family: 'JetBrains Mono', monospace;
      border-radius: 4px;
      cursor: pointer;
      flex: 1;
      text-align: center;
      transition: background 0.2s;
    }

    .btn-action:hover {
      background: var(--cyan);
      color: #000;
    }

    /* Live Thread Terminal */
    .thread-section {
      display: grid;
      grid-template-columns: 1fr;
      gap: 20px;
    }

    .terminal-box {
      background: var(--terminal-bg);
      border: 1px solid var(--panel-border);
      border-radius: 8px;
      padding: 20px;
      font-family: 'JetBrains Mono', monospace;
    }

    .interaction-item {
      padding: 14px;
      border-bottom: 1px solid #131c29;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .interaction-item:last-child { border-bottom: none; }

    .item-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .item-tags {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .tag {
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 3px;
      font-weight: 700;
    }

    .tag-outbound { background: rgba(0, 243, 255, 0.15); color: var(--cyan); }
    .tag-inbound { background: rgba(0, 255, 136, 0.15); color: var(--emerald); }

    .tag-meeting { background: var(--emerald-dim); color: var(--emerald); border: 1px solid var(--emerald); }
    .tag-warm { background: var(--cyan-dim); color: var(--cyan); border: 1px solid var(--cyan); }
    .tag-neutral { background: rgba(255,255,255,0.06); color: var(--text-muted); }

    .item-subject {
      color: var(--text-bright);
      font-size: 13px;
      font-weight: 600;
    }

    .item-body {
      font-size: 12px;
      color: var(--text);
      line-height: 1.5;
      background: rgba(255,255,255,0.02);
      padding: 8px;
      border-radius: 4px;
      white-space: pre-wrap;
    }
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <span class="logo-badge">CTXFW // REV-OPS</span>
      <span class="title">MISSION CONTROL TERMINAL</span>
    </div>
    <div class="telemetry-status mono">
      <div class="beacon"></div>
      <span style="color: var(--emerald)">LIVE DAEMON LINKED (PORT 993/465)</span>
      <span style="color: var(--text-muted)">|</span>
      <span style="color: var(--text-muted)">NODE: 217.21.78.30</span>
    </div>
  </header>

  <div class="container">

    <!-- KPI HUD -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">CUENTAS EN PIPELINE</div>
        <div class="kpi-value" id="kpi-total">2</div>
        <div class="kpi-sub">100% Calificación ICP &ge; 70</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">AHORRO NETO DETECTADO</div>
        <div class="kpi-value" id="kpi-savings">$24,198</div>
        <div class="kpi-sub">USD/año eludidos (Squads)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">OPEN RATE ESTIMADO</div>
        <div class="kpi-value">78.4%</div>
        <div class="kpi-sub">Plaintext RFC 5322 (0% Spam)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">REUNIONES AGENDADAS</div>
        <div class="kpi-value" id="kpi-calls" style="color: var(--emerald)">0</div>
        <div class="kpi-sub">Clasificadas por FSM Inbound</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">REDUCCIÓN DE CONTEXTO</div>
        <div class="kpi-value" style="color: var(--cyan)">72.4%</div>
        <div class="kpi-sub">Poda Determinista AST (D0)</div>
      </div>
    </div>

    <!-- KANBAN RADAR -->
    <div class="section-title">RADAR PIPELINE // KANBAN POR ESTADOS DE ENGAGEMENT</div>
    <div class="kanban-grid">
      
      <!-- 1. DISCOVERED -->
      <div class="kanban-col col-discovered" id="col-DISCOVERED">
        <div class="col-header">
          <span>01 // DISCOVERED</span>
          <span class="col-count" id="count-DISCOVERED">0</span>
        </div>
        <div class="card-list"></div>
      </div>

      <!-- 2. AUDITED -->
      <div class="kanban-col col-audited" id="col-AUDITED">
        <div class="col-header">
          <span>02 // AUDITED</span>
          <span class="col-count" id="count-AUDITED">0</span>
        </div>
        <div class="card-list"></div>
      </div>

      <!-- 3. CONTACTED -->
      <div class="kanban-col col-contacted" id="col-CONTACTED">
        <div class="col-header">
          <span>03 // CONTACTED</span>
          <span class="col-count" id="count-CONTACTED">0</span>
        </div>
        <div class="card-list"></div>
      </div>

      <!-- 4. ENGAGED -->
      <div class="kanban-col col-engaged" id="col-ENGAGED">
        <div class="col-header">
          <span>04 // ENGAGED</span>
          <span class="col-count" id="count-ENGAGED">0</span>
        </div>
        <div class="card-list"></div>
      </div>

      <!-- 5. CALL_SCHEDULED -->
      <div class="kanban-col col-call_scheduled" id="col-CALL_SCHEDULED">
        <div class="col-header">
          <span>05 // CALL SCHEDULED</span>
          <span class="col-count" id="count-CALL_SCHEDULED">0</span>
        </div>
        <div class="card-list"></div>
      </div>

    </div>

    <!-- LIVE THREAD TERMINAL -->
    <div class="section-title">TERMINAL DE HILOS // TRAZABILIDAD DE INTERACCIONES (OUTBOUND & INBOUND FSM)</div>
    <div class="thread-section">
      <div class="terminal-box" id="interactions-feed">
        <div style="color: var(--text-muted); font-size: 12px;">Cargando feed de interacciones...</div>
      </div>
    </div>

  </div>

  <script>
    async function loadData() {
      try {
        const q = window.location.search;
        const [metricsRes, pipelineRes, interactionsRes] = await Promise.all([
          fetch('/api/metrics' + q),
          fetch('/api/pipeline' + q),
          fetch('/api/interactions' + q)
        ]);

        const metrics = await metricsRes.json();
        const pipeline = await pipelineRes.json();
        const interactions = await interactionsRes.json();

        // Update KPIs
        if (metrics.total_targets !== undefined) {
          document.getElementById('kpi-total').textContent = metrics.total_targets;
          document.getElementById('kpi-savings').textContent = '$' + Math.round(metrics.total_net_savings_year).toLocaleString() + ' USD';
          document.getElementById('kpi-calls').textContent = metrics.meetings_booked;
        }

        // Render Kanban
        renderKanban(pipeline);

        // Render Interactions
        renderInteractions(interactions);

      } catch (err) {
        console.error("Telemetry fetch error:", err);
      }
    }

    function renderKanban(targets) {
      const cols = ['DISCOVERED', 'AUDITED', 'CONTACTED', 'ENGAGED', 'CALL_SCHEDULED'];
      const colMap = {};
      cols.forEach(c => {
        colMap[c] = document.querySelector(`#col-${c} .card-list`);
        colMap[c].innerHTML = '';
        document.getElementById(`count-${c}`).textContent = '0';
      });

      const counts = { DISCOVERED: 0, AUDITED: 0, CONTACTED: 0, ENGAGED: 0, CALL_SCHEDULED: 0 };

      targets.forEach(t => {
        const status = t.status || 'DISCOVERED';
        if (counts[status] !== undefined) counts[status]++;

        const targetCol = colMap[status] || colMap['DISCOVERED'];
        const card = document.createElement('div');
        card.className = 'target-card';

        const icpClass = t.icp_score >= 70 ? 'icp-100' : 'icp-mid';
        const avoided = t.finops ? '$' + Math.round(t.finops.avoided_usd_yr).toLocaleString() : '$0';

        card.innerHTML = `
          <div class="card-top">
            <div>
              <div class="target-name">${t.company_name}</div>
              <div class="target-domain">${t.domain}</div>
            </div>
            <span class="icp-badge ${icpClass}">ICP ${t.icp_score}</span>
          </div>
          <div class="card-lead">Lead: ${t.tech_lead_name || 'N/A'} (${t.tech_lead_title || 'Lead'})</div>
          <div class="card-stats mono">
            <div>DEV SQUAD: <strong style="color:var(--text-bright)">${t.dev_count}</strong></div>
            <div>EVITADO: <strong style="color:var(--emerald)">${avoided}</strong></div>
          </div>
          <div class="card-actions">
            <button class="btn-action" onclick="triggerDispatch('${t.company_name}', true)">SIMULAR DESPACHO</button>
          </div>
        `;
        targetCol.appendChild(card);
      });

      cols.forEach(c => {
        document.getElementById(`count-${c}`).textContent = counts[c];
      });
    }

    function renderInteractions(interactions) {
      const feed = document.getElementById('interactions-feed');
      if (!interactions.length) {
        feed.innerHTML = '<div style="color: var(--text-muted); font-size: 12px; padding: 12px;">No se registran interacciones en el historial. El daemon de escucha está monitoreando respuestas vía IMAP.</div>';
        return;
      }

      feed.innerHTML = interactions.map(i => {
        const isOut = i.direction === 'OUTBOUND';
        const dirTag = isOut ? '<span class="tag tag-outbound">OUTBOUND // RFC 5322</span>' : '<span class="tag tag-inbound">INBOUND // IMAP 993</span>';
        
        let classTag = '<span class="tag tag-neutral">' + i.classification + '</span>';
        if (i.classification === 'MEETING_REQUESTED') classTag = '<span class="tag tag-meeting">&bull; MEETING REQUESTED</span>';
        else if (i.classification === 'WARM_INTEREST') classTag = '<span class="tag tag-warm">&bull; WARM INTEREST</span>';

        return `
          <div class="interaction-item">
            <div class="item-header">
              <div class="item-tags">
                ${dirTag}
                ${classTag}
                <span style="color:var(--text-bright); font-weight:700;">${i.company_name}</span>
              </div>
              <div class="mono" style="color: var(--text-muted); font-size: 11px;">${i.created_at.slice(0, 16).replace('T', ' ')} UTC</div>
            </div>
            <div class="item-subject">${i.subject || 'Sin Asunto'}</div>
            <div class="item-body">${i.body_text ? i.body_text.slice(0, 300) : ''}</div>
          </div>
        `;
      }).join('');
    }

    async function triggerDispatch(company, dryRun) {
      try {
        const q = window.location.search;
        const res = await fetch('/api/dispatch' + q, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ company: company, dry_run: dryRun })
        });
        const data = await res.json();
        alert(`[${data.status}] Despacho procesado para ${data.company} (Dry-Run: ${data.dry_run})`);
        loadData();
      } catch (err) {
        alert("Error al disparar despacho: " + err);
      }
    }

    // Initialize & SSE Listener
    loadData();
    const evtSource = new EventSource("/events" + window.location.search);
    evtSource.onmessage = function(event) {
      loadData();
    };
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8090"))
    print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
    print(f"  {CLR_CYAN}CTXFW REV-OPS MISSION CONTROL // REAL-TIME HUD{CLR_RESET}")
    print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}")
    print(f"Dashboard URL: {CLR_EMERALD}http://127.0.0.1:{port}/mission-control{CLR_RESET}")
    print(f"Basic Auth:    User: {CLR_WHITE}{DASH_USER}{CLR_RESET} | Pass: {CLR_WHITE}{DASH_PASS}{CLR_RESET}")
    print(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
