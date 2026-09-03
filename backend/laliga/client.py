"""
Cliente API LaLiga Fantasy
Endpoints verificados a 31/08/2026 via proxy
Base: https://fantasy-api.llt-services.com
"""
import requests
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://fantasy-api.llt-services.com"

HEADERS_BASE = {
    "X-App": "Fantasy-iOS",
    "X-Version": "10.0.5",
    "X-Lang": "es",
    "accept": "*/*",
    "accept-language": "es-ES;q=1.0",
    "user-agent": "LaLigaFantasy/10.0.5 (com.lfp.laligafantasy; build:2; iOS 26.5.0) Alamofire/5.10.2",
}


def _headers(token: Optional[str] = None) -> dict:
    h = HEADERS_BASE.copy()
    if token:
        h["authorization"] = f"Bearer {token}"
    return h


def _get(path: str, token: Optional[str] = None, params: Optional[dict] = None, retries: int = 3) -> Optional[dict]:
    url = f"{BASE_URL}{path}"
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=_headers(token), params=params, timeout=15)
            if r.status_code == 200:
                return r.json()
            elif r.status_code == 401:
                logger.error("Token inválido o caducado (401)")
                return None
            elif r.status_code == 429:
                wait = 2 ** attempt
                logger.warning(f"Rate limit (429), esperando {wait}s")
                time.sleep(wait)
            else:
                logger.warning(f"HTTP {r.status_code} en {path}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Error de red en {path}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


# ── Datos públicos (sin token) ──────────────────────────────────────────────

def get_competition_config() -> Optional[dict]:
    return _get("/api/v1/competition/1/config")

def get_all_players() -> Optional[list]:
    """Todos los jugadores con precios y estadísticas"""
    data = _get("/api/v1/competition/1/players", params={"x-lang": "es"})
    return data if isinstance(data, list) else None

def get_fixture_player_values() -> Optional[list]:
    """Historial de valores de mercado por jornada"""
    return _get("/classic/v1/competition/1/fixture-player-values", params={"x-lang": "es"})

def get_calendar(week: int = 3) -> Optional[dict]:
    return _get(f"/api/v1/competition/1/calendar", params={"weekNumber": week, "x-lang": "es"})

def get_league_definitions() -> Optional[list]:
    return _get("/classic/v1/competition/1/league-definitions", params={"x-lang": "es"})


# ── Datos privados (requieren token) ────────────────────────────────────────

def get_my_team(token: str, team_id: str = "37889563") -> Optional[dict]:
    """Plantilla completa con jugadores, formación y valor"""
    return _get(f"/api/v1/competition/1/teams/{team_id}/lineup", token=token, params={"x-lang": "es"})

def get_my_money(token: str, team_id: str = "37889563") -> Optional[dict]:
    """Dinero disponible del equipo"""
    return _get(f"/api/v1/competition/1/teams/{team_id}/money", token=token, params={"x-lang": "es"})

def get_league_standing(token: str, league_id: str = "017948446") -> Optional[list]:
    """Clasificación de la liga"""
    return _get(f"/api/v1/competition/1/leagues/{league_id}/standing/3", token=token, params={"x-lang": "es"})

def get_league_market(token: str, league_id: str = "017948446") -> Optional[list]:
    """Mercado privado de la liga"""
    return _get(f"/api/v1/competition/1/league/{league_id}/market", token=token, params={"x-lang": "es"})

def get_team_lineup(token: str, team_id: str) -> Optional[dict]:
    """Plantilla de cualquier equipo de la liga"""
    return _get(f"/api/v1/competition/1/teams/{team_id}/lineup", token=token, params={"x-lang": "es"})

def get_team_money(token: str, team_id: str) -> Optional[dict]:
    """Dinero de cualquier equipo"""
    return _get(f"/api/v1/competition/1/teams/{team_id}/money", token=token, params={"x-lang": "es"})

def get_league_formations(token: str) -> Optional[dict]:
    """Formaciones disponibles"""
    return _get("/api/v4/teams/lineup/formations", token=token, params={"option": "free", "x-lang": "es"})

def get_favourite_players(token: str, team_id: str = "37889563") -> Optional[list]:
    """Jugadores favoritos del equipo"""
    return _get(f"/api/v1/competition/1/teams/{team_id}/favourite-players", token=token, params={"x-lang": "es"})

def get_player_market_value_history(player_id: str) -> Optional[list]:
    """
    Historial completo de valor de mercado de un jugador desde inicio de temporada.
    Endpoint verificado: /api/v1/competition/1/player/{id}/market-value
    Respuesta: [{date, bids, marketValue, lfpId}, ...]
    """
    return _get(f"/api/v1/competition/1/player/{player_id}/market-value", params={"x-lang": "es"})
