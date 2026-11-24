/**
 * api.js — Capa de acceso a la API de LaLiga Fantasy desde el frontend.
 *
 * El frontend llama a un servidor local Python (o proxy) que expone
 * endpoints REST en http://localhost:8000. En producción se ajusta
 * BASE_URL a la URL del servidor desplegado.
 */

const API = (() => {
  const BASE_URL = window.FANTASY_API_URL || 'http://localhost:8000';

  async function _fetch(path, options = {}) {
    const url = `${BASE_URL}${path}`;
    try {
      const resp = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...options.headers },
        ...options,
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`API ${resp.status}: ${text.slice(0, 200)}`);
      }
      return resp.json();
    } catch (err) {
      console.error(`[API] Error en ${path}:`, err);
      throw err;
    }
  }

  return {
    // ---- Liga y equipo ----
    getLeagueInfo: (leagueId) => _fetch(`/api/league/${leagueId}`),
    getMyTeam:     (leagueId) => _fetch(`/api/league/${leagueId}/team`),
    getStandings:  (leagueId) => _fetch(`/api/league/${leagueId}/standings`),
    getRivals:     (leagueId) => _fetch(`/api/league/${leagueId}/rivals`),

    // ---- Mercado ----
    getMarket:         (leagueId) => _fetch(`/api/league/${leagueId}/market`),
    getOpportunities:  (leagueId) => _fetch(`/api/league/${leagueId}/market/opportunities`),
    getSellSuggestions:(leagueId) => _fetch(`/api/league/${leagueId}/market/sell-suggestions`),

    // ---- Jugadores ----
    getAllPlayers:   () => _fetch('/api/players'),
    getPlayerDetail: (id) => _fetch(`/api/players/${id}`),

    // ---- Análisis ----
    getClauseRisks:  (leagueId) => _fetch(`/api/league/${leagueId}/clause-risks`),
    getDailyReport:  (leagueId) => _fetch(`/api/league/${leagueId}/report`),

    // ---- Actualización ----
    triggerUpdate: (leagueId) =>
      _fetch(`/api/league/${leagueId}/update`, { method: 'POST' }),
  };
})();
