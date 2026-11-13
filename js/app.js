/**
 * app.js — Lógica principal del dashboard de LaLiga Fantasy.
 *
 * Gestiona vistas, carga de datos, rendering de tablas/cards
 * y coordinación con api.js y charts.js.
 */

// ============================================================
// Estado global
// ============================================================
const STATE = {
  leagueId: localStorage.getItem('fantasy_league_id') || '',
  team: null,
  market: null,
  players: [],
  opportunities: [],
  standings: [],
  rivals: [],
  clauseRisks: [],
  loading: false,
};

// ============================================================
// Inicialización
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
  setupNavigation();
  setupEventListeners();
  promptLeagueId();
});

function promptLeagueId() {
  if (!STATE.leagueId) {
    const id = prompt(
      '🏆 Introduce el ID de tu liga de LaLiga Fantasy:\n(Puedes encontrarlo en la URL de tu liga)',
    );
    if (id) {
      STATE.leagueId = id.trim();
      localStorage.setItem('fantasy_league_id', STATE.leagueId);
    }
  }
  if (STATE.leagueId) loadAll();
}

// ============================================================
// Navegación
// ============================================================
function setupNavigation() {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const view = btn.dataset.view;
      document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
      document.getElementById(`view-${view}`)?.classList.add('active');
    });
  });
}

// ============================================================
// Event listeners
// ============================================================
function setupEventListeners() {
  document.getElementById('refresh-btn')?.addEventListener('click', loadAll);

  // Filtros de mercado
  document.getElementById('market-search')?.addEventListener('input', renderMarket);
  document.getElementById('market-pos-filter')?.addEventListener('change', renderMarket);
  document.getElementById('market-sort')?.addEventListener('change', renderMarket);

  // Filtros de mi equipo
  document.querySelectorAll('.filter-btn[data-pos]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn[data-pos]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderTeamTable(btn.dataset.pos);
    });
  });

  // Filtros de jugadores libres
  document.getElementById('players-search')?.addEventListener('input', renderPlayersTable);
  document.getElementById('players-pos-filter')?.addEventListener('change', renderPlayersTable);
  document.getElementById('players-team-filter')?.addEventListener('change', renderPlayersTable);
  document.getElementById('players-sort')?.addEventListener('change', renderPlayersTable);

  // Modal close
  document.getElementById('modal-close')?.addEventListener('click', closeModal);
  document.querySelector('.modal__backdrop')?.addEventListener('click', closeModal);
}

// ============================================================
// Carga de datos
// ============================================================
async function loadAll() {
  if (!STATE.leagueId || STATE.loading) return;
  STATE.loading = true;
  showToast('Actualizando datos...', 'info');

  try {
    const [team, market, opportunities, standings, rivals, clauseRisks, players] = await Promise.allSettled([
      API.getMyTeam(STATE.leagueId),
      API.getMarket(STATE.leagueId),
      API.getOpportunities(STATE.leagueId),
      API.getStandings(STATE.leagueId),
      API.getRivals(STATE.leagueId),
      API.getClauseRisks(STATE.leagueId),
      API.getAllPlayers(),
    ]);

    if (team.status === 'fulfilled')         STATE.team           = team.value;
    if (market.status === 'fulfilled')       STATE.market         = market.value;
    if (opportunities.status === 'fulfilled') STATE.opportunities = opportunities.value;
    if (standings.status === 'fulfilled')    STATE.standings      = standings.value;
    if (rivals.status === 'fulfilled')       STATE.rivals         = rivals.value;
    if (clauseRisks.status === 'fulfilled')  STATE.clauseRisks    = clauseRisks.value;
    if (players.status === 'fulfilled')      STATE.players        = players.value;

    renderAll();
    updateLastUpdate();
    showToast('Datos actualizados ✓', 'success');
  } catch (err) {
    showToast(`Error: ${err.message}`, 'error');
  } finally {
    STATE.loading = false;
  }
}

// ============================================================
// Renderizado completo
// ============================================================
function renderAll() {
  renderStats();
  renderOpportunities();
  renderClauseRisks();
  renderTeamTable('ALL');
  renderTeamCompositionChart();
  renderPositionScoresChart();
  renderMarket();
  renderStandings();
  renderRivals();
  renderPlayersTable();
  populateTeamFilter();
}

// ---- Stats cards ----
function renderStats() {
  const t = STATE.team;
  if (!t) return;
  setText('stat-budget',   formatMoney(t.budget));
  setText('stat-value',    formatMoney(t.team_value || t.teamValue));
  setText('stat-points',   t.points ?? '—');
  setText('stat-rank',     t.rank ? `#${t.rank}` : '—');
  // Jornada desde standings si está disponible
  const matchday = STATE.standings[0]?.matchday ?? '—';
  setText('stat-matchday', matchday);
}

// ---- Oportunidades ----
function renderOpportunities() {
  const container = document.getElementById('market-opportunities');
  if (!container) return;
  const opps = STATE.opportunities?.slice(0, 6) || [];
  if (!opps.length) { container.innerHTML = '<p class="empty-state">Sin oportunidades disponibles.</p>'; return; }

  container.innerHTML = opps.map(o => `
    <div class="opportunity-item ${o.urgency}" onclick="openPlayerModal('${o.player_id || ''}')">
      <div class="opp-header">
        <span class="opp-name">${esc(o.player)} <span class="badge badge--${o.position?.toLowerCase()}">${o.position || ''}</span></span>
        <span class="opp-price money">${formatMoney(o.price)}</span>
      </div>
      <div class="opp-reason">${esc(o.reason)} <span class="badge badge--${o.urgency.toLowerCase()}">${o.urgency}</span></div>
    </div>
  `).join('');
}

// ---- Cláusulas en riesgo ----
function renderClauseRisks() {
  const container = document.getElementById('clause-risks');
  if (!container) return;
  const risks = STATE.clauseRisks?.slice(0, 6) || [];
  if (!risks.length) { container.innerHTML = '<p class="empty-state">Sin riesgos de cláusula.</p>'; return; }

  container.innerHTML = risks.map(r => `
    <div class="risk-item ${r.risk}">
      <div class="opp-header">
        <span class="opp-name">${esc(r.player)}</span>
        <span class="badge badge--${r.risk.toLowerCase()}">${r.risk}</span>
      </div>
      <div class="opp-reason">Cláusula: <strong>${formatMoney(r.clause)}</strong> · ${r.rivals_can_afford} rival(es) pueden pagarla</div>
    </div>
  `).join('');
}

// ---- Tabla de mi equipo ----
function renderTeamTable(posFilter = 'ALL') {
  const tbody = document.getElementById('team-tbody');
  if (!tbody || !STATE.team) return;
  const players = (STATE.team.players || [])
    .filter(tp => posFilter === 'ALL' || tp.player?.position === posFilter);

  tbody.innerHTML = players.map(tp => {
    const p = tp.player || {};
    const stats = p.stats || {};
    const score = computeSimpleScore(p);
    return `
      <tr onclick="openPlayerModal('${p.id}')">
        <td><strong>${esc(p.name)}</strong>${tp.is_captain ? ' 🅲' : ''}</td>
        <td><span class="badge badge--${(p.position||'').toLowerCase()}">${p.position || '—'}</span></td>
        <td class="text-muted">${esc(p.team)}</td>
        <td class="money">${formatMoney(p.market_value)}</td>
        <td>${p.points ?? '—'}</td>
        <td>${stats.last_5_avg?.toFixed(1) ?? '—'}</td>
        <td>${renderScoreBar(score)}</td>
        <td><span class="badge badge--${p.status || 'ok'}">${p.status || 'ok'}</span></td>
      </tr>`;
  }).join('') || '<tr><td colspan="8" class="empty-state">Sin jugadores</td></tr>';
}

// ---- Mercado ----
function renderMarket() {
  const container = document.getElementById('market-cards');
  if (!container) return;
  const searchVal = (document.getElementById('market-search')?.value || '').toLowerCase();
  const posFilter = document.getElementById('market-pos-filter')?.value || '';
  const sortVal   = document.getElementById('market-sort')?.value || 'urgency';

  let items = [...(STATE.opportunities || [])];

  if (searchVal) items = items.filter(o => o.player?.toLowerCase().includes(searchVal));
  if (posFilter) items = items.filter(o => o.position === posFilter);

  if (sortVal === 'price_asc')  items.sort((a, b) => a.price - b.price);
  if (sortVal === 'price_desc') items.sort((a, b) => b.price - a.price);
  if (sortVal === 'score')      items.sort((a, b) => (b.score || 0) - (a.score || 0));

  if (!items.length) { container.innerHTML = '<p class="empty-state">Sin resultados.</p>'; return; }

  container.innerHTML = items.map(o => `
    <div class="market-card ${o.urgency}" onclick="openPlayerModal('${o.player_id || ''}')">
      <div class="market-card__header">
        <div>
          <div class="market-card__name">${esc(o.player)}</div>
          <div class="text-muted" style="font-size:12px;margin-top:2px">${esc(o.team || '')}</div>
        </div>
        <span class="market-card__pos">${o.position || ''}</span>
      </div>
      <div class="market-card__price money">${formatMoney(o.price)}</div>
      <div class="market-card__meta">
        <span>Val: ${formatMoney(o.market_value)}</span>
        <span class="badge badge--${o.urgency.toLowerCase()}">${o.urgency}</span>
      </div>
      ${o.reason ? `<div class="market-card__reason">${esc(o.reason)}</div>` : ''}
    </div>
  `).join('');
}

// ---- Clasificación ----
function renderStandings() {
  const tbody = document.getElementById('standings-tbody');
  if (!tbody) return;
  tbody.innerHTML = (STATE.standings || []).map((s, i) => `
    <tr>
      <td>${i + 1}</td>
      <td><strong>${esc(s.name || s.team)}</strong>${s.is_mine ? ' 👈' : ''}</td>
      <td>${s.points ?? '—'}</td>
      <td class="money">${formatMoney(s.team_value || s.teamValue)}</td>
      <td><span class="badge badge--${(s.threat || 'low').toLowerCase()}">${s.threat || '—'}</span></td>
    </tr>
  `).join('') || '<tr><td colspan="5" class="empty-state">Sin datos</td></tr>';
}

// ---- Rivales ----
function renderRivals() {
  const container = document.getElementById('rival-reports');
  if (!container) return;
  container.innerHTML = (STATE.rivals || []).map(r => `
    <div class="rival-card">
      <div class="rival-card__header">
        <span class="rival-card__name">${esc(r.team)}</span>
        <span class="badge badge--${(r.threat_level || 'low').toLowerCase()}">${r.threat_level || '—'}</span>
      </div>
      ${r.strengths?.length ? `<div class="rival-card__strengths">✅ ${r.strengths.map(esc).join(' · ')}</div>` : ''}
      ${r.weaknesses?.length ? `<div class="rival-card__weaknesses">⚠️ ${r.weaknesses.map(esc).join(' · ')}</div>` : ''}
      ${r.key_players?.length ? `<div class="rival-card__keys">🌟 Claves: ${r.key_players.map(esc).join(', ')}</div>` : ''}
    </div>
  `).join('') || '<p class="empty-state">Sin datos de rivales.</p>';
}

// ---- Jugadores libres ----
function renderPlayersTable() {
  const tbody = document.getElementById('players-tbody');
  if (!tbody) return;
  const searchVal = (document.getElementById('players-search')?.value || '').toLowerCase();
  const posFilter = document.getElementById('players-pos-filter')?.value || '';
  const teamFilter = document.getElementById('players-team-filter')?.value || '';
  const sortVal   = document.getElementById('players-sort')?.value || 'score';

  let items = [...STATE.players];
  if (searchVal)  items = items.filter(p => p.name?.toLowerCase().includes(searchVal));
  if (posFilter)  items = items.filter(p => p.position === posFilter);
  if (teamFilter) items = items.filter(p => p.team === teamFilter);

  if (sortVal === 'points') items.sort((a, b) => (b.points || 0) - (a.points || 0));
  else if (sortVal === 'value') items.sort((a, b) => (b.market_value || 0) - (a.market_value || 0));
  else if (sortVal === 'form') items.sort((a, b) => (b.stats?.last_5_avg || 0) - (a.stats?.last_5_avg || 0));
  else items.sort((a, b) => computeSimpleScore(b) - computeSimpleScore(a));

  tbody.innerHTML = items.slice(0, 100).map(p => {
    const stats = p.stats || {};
    const score = computeSimpleScore(p);
    const rec   = scoreToRec(score, p);
    return `
      <tr onclick="openPlayerModal('${p.id}')">
        <td><strong>${esc(p.name)}</strong></td>
        <td><span class="badge badge--${(p.position||'').toLowerCase()}">${p.position || '—'}</span></td>
        <td class="text-muted">${esc(p.team)}</td>
        <td class="money">${formatMoney(p.market_value)}</td>
        <td class="money">${formatMoney(p.clause_value)}</td>
        <td>${p.points ?? '—'}</td>
        <td>${stats.last_5_avg?.toFixed(1) ?? '—'}</td>
        <td>${renderScoreBar(score)}</td>
        <td><span class="badge badge--${rec.toLowerCase()}">${rec}</span></td>
      </tr>`;
  }).join('') || '<tr><td colspan="9" class="empty-state">Sin jugadores</td></tr>';
}

function populateTeamFilter() {
  const sel = document.getElementById('players-team-filter');
  if (!sel) return;
  const teams = [...new Set(STATE.players.map(p => p.team).filter(Boolean))].sort();
  sel.innerHTML = '<option value="">Todos los equipos</option>' +
    teams.map(t => `<option value="${esc(t)}">${esc(t)}</option>`).join('');
}

// ---- Charts ----
function renderPositionScoresChart() {
  if (!STATE.team?.players?.length) return;
  const byPos = {};
  STATE.team.players.forEach(tp => {
    const pos = tp.player?.position;
    if (!pos) return;
    if (!byPos[pos]) byPos[pos] = [];
    byPos[pos].push(computeSimpleScore(tp.player));
  });
  const data = Object.entries(byPos).map(([position, scores]) => ({
    position,
    avgScore: scores.reduce((a, b) => a + b, 0) / scores.length,
  }));
  Charts.renderPositionScores('chart-position-scores', data);
}

function renderTeamCompositionChart() {
  if (!STATE.team?.players?.length) return;
  const byPos = { GK: 0, DEF: 0, MID: 0, FWD: 0 };
  STATE.team.players.forEach(tp => {
    const pos = tp.player?.position;
    if (pos in byPos) byPos[pos] += tp.player.market_value || 0;
  });
  Charts.renderTeamComposition('chart-team-composition', byPos);
}

// ============================================================
// Modal de jugador
// ============================================================
function openPlayerModal(playerId) {
  if (!playerId) return;
  const modal = document.getElementById('modal');
  const body  = document.getElementById('modal-body');
  if (!modal || !body) return;

  const player = STATE.players.find(p => p.id === playerId)
    || STATE.team?.players?.find(tp => tp.player?.id === playerId)?.player;

  if (!player) { showToast('Jugador no encontrado', 'error'); return; }

  const s = player.stats || {};
  body.innerHTML = `
    <h2 style="margin-bottom:12px">${esc(player.name)}</h2>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:16px">
      <div><span class="text-muted">Posición</span><br><strong>${player.position}</strong></div>
      <div><span class="text-muted">Equipo</span><br><strong>${esc(player.team)}</strong></div>
      <div><span class="text-muted">Valor de mercado</span><br><strong class="money">${formatMoney(player.market_value)}</strong></div>
      <div><span class="text-muted">Cláusula</span><br><strong class="money">${formatMoney(player.clause_value)}</strong></div>
      <div><span class="text-muted">Puntos totales</span><br><strong>${player.points}</strong></div>
      <div><span class="text-muted">Media últimas 5</span><br><strong>${s.last_5_avg?.toFixed(1) ?? '—'}</strong></div>
      <div><span class="text-muted">Partidos jugados</span><br><strong>${s.total_matches ?? '—'}</strong></div>
      <div><span class="text-muted">Estado</span><br><span class="badge badge--${player.status || 'ok'}">${player.status || 'ok'}</span></div>
    </div>
    <div style="border-top:1px solid var(--color-border);padding-top:12px">
      <div style="display:flex;gap:12px">
        <span>⚽ Goles: <strong>${s.goals ?? 0}</strong></span>
        <span>🅰️ Asistencias: <strong>${s.assists ?? 0}</strong></span>
        <span>🟨 <strong>${s.yellow_cards ?? 0}</strong></span>
        <span>🟥 <strong>${s.red_cards ?? 0}</strong></span>
      </div>
    </div>`;

  modal.classList.remove('hidden');
}

function closeModal() {
  document.getElementById('modal')?.classList.add('hidden');
}

// ============================================================
// Utilidades
// ============================================================
function computeSimpleScore(player) {
  if (!player) return 0;
  const stats = player.stats || {};
  const valueScore  = player.market_value > 0
    ? Math.min(player.points / (player.market_value / 1e6) / 15, 1)
    : 0;
  const formScore   = Math.min((stats.last_5_avg || 0) / 15, 1);
  const seasonScore = Math.min((stats.season_points || player.points || 0) / 200, 1);
  return 0.25 * valueScore + 0.45 * formScore + 0.30 * seasonScore;
}

function scoreToRec(score, player) {
  if (!player?.status || player.status === 'ok') {
    if (score >= 0.65) return 'BUY';
    if (score <= 0.35) return 'SELL';
    return 'HOLD';
  }
  return player.status === 'injured' ? 'SELL' : 'WATCH';
}

function renderScoreBar(score) {
  const pct = Math.round(score * 100);
  const cls = score >= 0.6 ? 'high' : score >= 0.35 ? 'medium' : 'low';
  return `<div class="score-bar">
    <div class="score-bar__track"><div class="score-bar__fill ${cls}" style="width:${pct}%"></div></div>
    <span class="score-bar__label">${pct}%</span>
  </div>`;
}

function formatMoney(val) {
  if (!val) return '—';
  if (val >= 1e6) return (val / 1e6).toFixed(1) + 'M€';
  if (val >= 1e3) return (val / 1e3).toFixed(0) + 'K€';
  return val + '€';
}

function esc(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? '—';
}

function updateLastUpdate() {
  const el = document.getElementById('last-update');
  if (el) el.textContent = 'Actualizado: ' + new Date().toLocaleTimeString('es-ES');
}

function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => toast.remove(), duration);
}
