/**
 * charts.js — Utilidades de Chart.js para el dashboard de Fantasy.
 *
 * Paleta y defaults coherentes con el tema oscuro del CSS.
 */

const Charts = (() => {
  // ---- Paleta ----
  const COLORS = {
    GK:  '#f85149',
    DEF: '#58a6ff',
    MID: '#3fb950',
    FWD: '#d29922',
    accent:  '#58a6ff',
    success: '#3fb950',
    warning: '#d29922',
    danger:  '#f85149',
    muted:   '#7d8590',
    border:  '#30363d',
    text:    '#e6edf3',
  };

  // Defaults globales de Chart.js
  Chart.defaults.color = COLORS.muted;
  Chart.defaults.borderColor = COLORS.border;
  Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif';
  Chart.defaults.font.size = 12;

  const _instances = {};

  function _destroy(id) {
    if (_instances[id]) {
      _instances[id].destroy();
      delete _instances[id];
    }
  }

  // ---- Score por posición (Radar o Bar) ----
  function renderPositionScores(canvasId, data) {
    // data = [{ position: 'GK', avgScore: 0.62 }, ...]
    _destroy(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    const positions = data.map(d => d.position);
    const scores    = data.map(d => +(d.avgScore * 100).toFixed(1));
    const bgColors  = positions.map(p => COLORS[p] + '33');
    const borders   = positions.map(p => COLORS[p]);

    _instances[canvasId] = new Chart(ctx, {
      type: 'bar',
      data: {
        labels: positions,
        datasets: [{
          label: 'Score medio (%)',
          data: scores,
          backgroundColor: bgColors,
          borderColor: borders,
          borderWidth: 2,
          borderRadius: 4,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            min: 0, max: 100,
            ticks: { callback: v => v + '%' },
            grid: { color: COLORS.border },
          },
          x: { grid: { display: false } },
        },
      },
    });
  }

  // ---- Evolución valor del equipo (Line) ----
  function renderTeamValueHistory(canvasId, data) {
    // data = [{ date: '2025-08-01', value: 145000000 }, ...]
    _destroy(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    _instances[canvasId] = new Chart(ctx, {
      type: 'line',
      data: {
        labels: data.map(d => d.date),
        datasets: [{
          label: 'Valor (M€)',
          data: data.map(d => +(d.value / 1e6).toFixed(2)),
          borderColor: COLORS.accent,
          backgroundColor: COLORS.accent + '18',
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 3,
          pointHoverRadius: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: { label: ctx => `${ctx.parsed.y} M€` },
          },
        },
        scales: {
          y: {
            ticks: { callback: v => v + 'M' },
            grid: { color: COLORS.border },
          },
          x: { grid: { display: false }, ticks: { maxTicksLimit: 8 } },
        },
      },
    });
  }

  // ---- Composición del equipo por posición (Doughnut) ----
  function renderTeamComposition(canvasId, data) {
    // data = { GK: 1, DEF: 4, MID: 4, FWD: 3 } con valores de mercado sumados
    _destroy(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    const labels = Object.keys(data);
    const values = Object.values(data).map(v => +(v / 1e6).toFixed(2));

    _instances[canvasId] = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels,
        datasets: [{
          data: values,
          backgroundColor: labels.map(l => COLORS[l] + 'cc'),
          borderColor: labels.map(l => COLORS[l]),
          borderWidth: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'right' },
          tooltip: {
            callbacks: { label: ctx => `${ctx.label}: ${ctx.parsed} M€` },
          },
        },
        cutout: '60%',
      },
    });
  }

  // ---- Sparkline de puntos de un jugador ----
  function renderPlayerSparkline(canvasId, pointsHistory) {
    // pointsHistory = [8, 12, 5, 15, 10]
    _destroy(canvasId);
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    _instances[canvasId] = new Chart(ctx, {
      type: 'line',
      data: {
        labels: pointsHistory.map((_, i) => `J${i + 1}`),
        datasets: [{
          data: pointsHistory,
          borderColor: COLORS.success,
          borderWidth: 2,
          fill: false,
          tension: 0.3,
          pointRadius: 2,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: { x: { display: false }, y: { display: false } },
        animation: { duration: 0 },
      },
    });
  }

  return {
    renderPositionScores,
    renderTeamValueHistory,
    renderTeamComposition,
    renderPlayerSparkline,
    COLORS,
  };
})();
