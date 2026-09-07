"""
src/ctxfw/storage/dashboard_template.py — Interactive Sovereign FinOps Dashboard Template (v3.5.0)
High-aesthetic dark mode UI featuring JetBrains Mono, Space Grotesk, glassmorphism,
real-time KPIs, temporal metrics, team breakdown, and accounting export triggers.
"""
from __future__ import annotations

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>CTXFW FinOps Control Plane // Sovereign Token Economy</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700;800&family=Space+Grotesk:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #090a0f;
      --surface: #11131c;
      --surface-border: #212638;
      --surface-hover: #191c2b;
      --amber: #f59e0b;
      --amber-dim: rgba(245, 158, 11, 0.12);
      --emerald: #10b981;
      --emerald-dim: rgba(16, 185, 129, 0.12);
      --cyan: #06b6d4;
      --cyan-dim: rgba(6, 182, 212, 0.12);
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --text-dark: #6b7280;
      --mono: 'JetBrains Mono', monospace;
      --sans: 'Space Grotesk', sans-serif;
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text);
      font-family: var(--sans);
      line-height: 1.6;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    /* Ambient scanline */
    body::before {
      content: "";
      position: fixed;
      top: 0; left: 0; width: 100vw; height: 100vh;
      background: linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%);
      background-size: 100% 4px;
      z-index: 999;
      pointer-events: none;
      opacity: 0.3;
    }

    .container { max-width: 1280px; margin: 0 auto; padding: 0 24px; width: 100%; }

    /* HEADER */
    header {
      border-bottom: 1px solid var(--surface-border);
      background: rgba(9, 10, 15, 0.9);
      backdrop-filter: blur(12px);
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .header-inner {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px 0;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      font-family: var(--mono);
      font-weight: 800;
      font-size: 1.1rem;
      letter-spacing: -0.5px;
    }
    .badge {
      background: var(--amber);
      color: #000;
      font-size: 0.65rem;
      padding: 2px 8px;
      border-radius: 3px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      font-family: var(--mono);
      font-size: 0.75rem;
      color: var(--emerald);
      background: var(--emerald-dim);
      border: 1px solid rgba(16, 185, 129, 0.3);
      padding: 5px 12px;
      border-radius: 20px;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      background: var(--emerald);
      border-radius: 50%;
      box-shadow: 0 0 10px var(--emerald);
      animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { transform: scale(0.95); opacity: 0.8; }
      50% { transform: scale(1.15); opacity: 1; }
      100% { transform: scale(0.95); opacity: 0.8; }
    }

    /* ACTIONS BAR */
    .actions-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 24px 0 12px;
      flex-wrap: wrap;
      gap: 16px;
    }
    .title-block h1 {
      font-size: 1.8rem;
      font-weight: 800;
      letter-spacing: -0.5px;
    }
    .title-block p {
      color: var(--text-muted);
      font-size: 0.9rem;
    }
    .btn-group {
      display: flex;
      gap: 10px;
    }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      background: var(--surface);
      border: 1px solid var(--surface-border);
      color: var(--text);
      font-family: var(--mono);
      font-size: 0.82rem;
      font-weight: 600;
      padding: 8px 16px;
      border-radius: 6px;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.2s ease;
    }
    .btn:hover {
      background: var(--surface-hover);
      border-color: var(--amber);
      transform: translateY(-1px);
    }
    .btn-primary {
      background: var(--amber);
      color: #000;
      border-color: var(--amber);
      font-weight: 700;
    }
    .btn-primary:hover {
      background: #d97706;
      border-color: #d97706;
      color: #000;
    }

    /* KPI GRID */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .kpi-card {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 8px;
      padding: 20px;
      position: relative;
      overflow: hidden;
      transition: border-color 0.2s;
    }
    .kpi-card:hover { border-color: var(--amber); }
    .kpi-card::after {
      content: "";
      position: absolute;
      top: 0; left: 0; right: 0; height: 3px;
      background: linear-gradient(90deg, var(--amber), transparent);
    }
    .kpi-card.emerald::after {
      background: linear-gradient(90deg, var(--emerald), transparent);
    }
    .kpi-card.cyan::after {
      background: linear-gradient(90deg, var(--cyan), transparent);
    }
    .kpi-label {
      font-family: var(--mono);
      font-size: 0.75rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 8px;
    }
    .kpi-value {
      font-family: var(--mono);
      font-size: 1.8rem;
      font-weight: 800;
      color: var(--text);
    }
    .kpi-sub {
      font-size: 0.78rem;
      color: var(--text-dark);
      margin-top: 4px;
    }

    /* LAYOUT GRIDS */
    .content-grid {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 20px;
      margin-bottom: 24px;
    }
    @media (max-width: 960px) {
      .content-grid { grid-template-columns: 1fr; }
    }

    .panel {
      background: var(--surface);
      border: 1px solid var(--surface-border);
      border-radius: 8px;
      overflow: hidden;
    }
    .panel-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 14px 20px;
      border-bottom: 1px solid var(--surface-border);
      background: rgba(17, 19, 28, 0.6);
    }
    .panel-title {
      font-family: var(--mono);
      font-size: 0.85rem;
      font-weight: 700;
      letter-spacing: 0.5px;
      text-transform: uppercase;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .panel-body { padding: 20px; }

    /* DATA TABLES */
    .table-container { overflow-x: auto; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      text-align: left;
    }
    th {
      font-family: var(--mono);
      font-size: 0.72rem;
      color: var(--text-muted);
      text-transform: uppercase;
      padding: 10px 12px;
      border-bottom: 1px solid var(--surface-border);
      background: rgba(9, 10, 15, 0.4);
    }
    td {
      padding: 12px;
      border-bottom: 1px solid rgba(33, 38, 56, 0.5);
      font-family: var(--mono);
      color: var(--text);
    }
    tr:hover td { background: var(--surface-hover); }

    .tag-team {
      background: rgba(6, 182, 212, 0.15);
      color: var(--cyan);
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .tag-model {
      background: rgba(245, 158, 11, 0.15);
      color: var(--amber);
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
    }

    /* FOOTER */
    footer {
      margin-top: auto;
      border-top: 1px solid var(--surface-border);
      padding: 18px 0;
      text-align: center;
      font-family: var(--mono);
      font-size: 0.75rem;
      color: var(--text-dark);
    }
  </style>
</head>
<body>
  <header>
    <div class="container header-inner">
      <div class="brand">
        <span>// CTXFW</span>
        <span class="badge">FinOps Control Plane</span>
      </div>
      <div class="status-pill">
        <span class="status-dot"></span>
        <span id="sync-status">Sovereign Air-Gapped Network Active</span>
      </div>
    </div>
  </header>

  <main class="container">
    <div class="actions-bar">
      <div class="title-block">
        <h1>Centro de Mando FinOps & Ahorro de Tokens</h1>
        <p>Auditoría centralizada de ROI y telemetría de contexto para flotas de ingeniería.</p>
      </div>
      <div class="btn-group">
        <a href="/api/telemetry/export?format=csv" class="btn" download="finops_ledger.csv">
          <span>↓ Exportar CSV</span>
        </a>
        <a href="/api/telemetry/export?format=json" class="btn" download="finops_ledger.json">
          <span>↓ Exportar JSON</span>
        </a>
        <button class="btn btn-primary" onclick="loadStats()">
          <span>⟳ Actualizar</span>
        </button>
      </div>
    </div>

    <!-- KPI GRID -->
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Ahorro Económico Proyectado</div>
        <div class="kpi-value" id="kpi-usd">$0.000000</div>
        <div class="kpi-sub">Valor de tokens eludidos (@ $3.00/1M)</div>
      </div>
      <div class="kpi-card emerald">
        <div class="kpi-label">Tokens Podados / Eludidos</div>
        <div class="kpi-value" id="kpi-pruned">0</div>
        <div class="kpi-sub" id="kpi-orig-sub">Evaluados: 0 tokens</div>
      </div>
      <div class="kpi-card cyan">
        <div class="kpi-label">Eficiencia Global de Poda</div>
        <div class="kpi-value" id="kpi-pct">0.0%</div>
        <div class="kpi-sub">Reducción sintáctica promedio</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Flota Activa de Ingenieros</div>
        <div class="kpi-value" id="kpi-devs">0</div>
        <div class="kpi-sub" id="kpi-cycles-sub">Ciclos ejecutados: 0</div>
      </div>
    </div>

    <!-- MAIN CONTENT -->
    <div class="content-grid">
      <!-- TEAMS BREAKDOWN -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Desglose de Retorno por Equipos</div>
          <span class="badge" style="background:var(--cyan); color:#000;">Multi-Tenant</span>
        </div>
        <div class="table-container">
          <table id="teams-table">
            <thead>
              <tr>
                <th>Equipo</th>
                <th>Peticiones</th>
                <th>Tokens Ahorrados</th>
                <th>Ahorro USD</th>
              </tr>
            </thead>
            <tbody>
              <tr><td colspan="4" style="text-align:center; color:var(--text-muted);">Cargando telemetría...</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- MODELS BREAKDOWN -->
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Modelos Destino</div>
          <span class="badge">LLM Frontier</span>
        </div>
        <div class="table-container">
          <table id="models-table">
            <thead>
              <tr>
                <th>Modelo</th>
                <th>Ahorro USD</th>
                <th>Peticiones</th>
              </tr>
            </thead>
            <tbody>
              <tr><td colspan="3" style="text-align:center; color:var(--text-muted);">Cargando...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- TEMPORAL AGGREGATES -->
    <div class="panel" style="margin-bottom: 24px;">
      <div class="panel-header">
        <div class="panel-title">Serie Temporal de Ahorro Diario</div>
        <span class="badge">Auditoría WAL</span>
      </div>
      <div class="table-container">
        <table id="timeseries-table">
          <thead>
            <tr>
              <th>Fecha UTC</th>
              <th>Ciclos</th>
              <th>Tokens Originales</th>
              <th>Tokens Podados</th>
              <th>Ahorro Proyectado</th>
            </tr>
          </thead>
          <tbody>
            <tr><td colspan="5" style="text-align:center; color:var(--text-muted);">Cargando histórico...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </main>

  <footer>
    <div class="container">
      Heurístico Lab :: Context Firewall (v3.5.0) — Control Plane Soberano 100% Air-Gapped
    </div>
  </footer>

  <script>
    async function loadStats() {
      try {
        const resp = await fetch('/api/telemetry/stats');
        if (!resp.ok) throw new Error('Error HTTP: ' + resp.status);
        const data = await resp.json();

        // Update KPIs
        document.getElementById('kpi-usd').textContent = '$' + Number(data.total_usd_avoided).toFixed(4);
        document.getElementById('kpi-pruned').textContent = Number(data.total_tokens_pruned).toLocaleString();
        document.getElementById('kpi-orig-sub').textContent = 'Evaluados: ' + Number(data.total_tokens_orig).toLocaleString() + ' tokens';
        document.getElementById('kpi-pct').textContent = Number(data.global_reduction_pct).toFixed(1) + '%';
        document.getElementById('kpi-devs').textContent = Number(data.active_dev_count);
        document.getElementById('kpi-cycles-sub').textContent = 'Ciclos ejecutados: ' + Number(data.total_cycles);

        // Teams table
        const teamsBody = document.querySelector('#teams-table tbody');
        if (data.teams && data.teams.length > 0) {
          teamsBody.innerHTML = data.teams.map(t => `
            <tr>
              <td><span class="tag-team">${t.team}</span></td>
              <td>${t.request_count}</td>
              <td>${Number(t.tokens_pruned).toLocaleString()}</td>
              <td style="color:var(--emerald); font-weight:700;">$${Number(t.usd_avoided).toFixed(4)}</td>
            </tr>
          `).join('');
        } else {
          teamsBody.innerHTML = '<tr><td colspan="4" style="text-align:center; color:var(--text-muted);">Sin registros de equipo aún.</td></tr>';
        }

        // Models table
        const modelsBody = document.querySelector('#models-table tbody');
        if (data.models && data.models.length > 0) {
          modelsBody.innerHTML = data.models.map(m => `
            <tr>
              <td><span class="tag-model">${m.model_target}</span></td>
              <td style="color:var(--emerald); font-weight:700;">$${Number(m.usd_avoided).toFixed(4)}</td>
              <td>${m.request_count}</td>
            </tr>
          `).join('');
        } else {
          modelsBody.innerHTML = '<tr><td colspan="3" style="text-align:center; color:var(--text-muted);">Sin registros de modelo.</td></tr>';
        }

        // Timeseries table
        const tsBody = document.querySelector('#timeseries-table tbody');
        if (data.timeseries && data.timeseries.length > 0) {
          tsBody.innerHTML = data.timeseries.map(s => `
            <tr>
              <td><strong>${s.date}</strong></td>
              <td>${s.count}</td>
              <td>${Number(s.tokens_orig).toLocaleString()}</td>
              <td>${Number(s.tokens_pruned).toLocaleString()}</td>
              <td style="color:var(--emerald); font-weight:700;">$${Number(s.usd_avoided).toFixed(4)}</td>
            </tr>
          `).join('');
        } else {
          tsBody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:var(--text-muted);">Histórico temporal vacío.</td></tr>';
        }

      } catch (err) {
        console.error('Error fetching stats:', err);
      }
    }

    document.addEventListener('DOMContentLoaded', loadStats);
  </script>
</body>
</html>
"""
