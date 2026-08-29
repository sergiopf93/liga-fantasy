"""
Cliente principal para la API de LaLiga Fantasy.
Gestiona autenticación, rate limiting y parsing de respuestas.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .endpoints import DEFAULT_HEADERS, TOKEN_ENDPOINT, LEAGUES, MY_TEAM, MARKET, PLAYERS, PLAYER_STATS, RIVAL_TEAMS, LEAGUE_STANDINGS
from .models import Player, PlayerStats, Team, TeamPlayer, MarketPlayer, Market, League, Fixture

logger = logging.getLogger(__name__)

TOKENS_FILE = Path(__file__).parents[3] / ".tokens.json"


class AuthError(Exception):
    pass


class APIError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"API {status}: {message}")


class LaLigaFantasyClient:
    """Cliente HTTP para la API de LaLiga Fantasy."""

    def __init__(self, access_token: Optional[str] = None, tokens_file: Optional[Path] = None):
        self._tokens_path = tokens_file or TOKENS_FILE
        self._access_token = access_token
        self._session = self._build_session()

        if not self._access_token:
            self._load_token()

    # ------------------------------------------------------------------ #
    # Configuración interna                                                #
    # ------------------------------------------------------------------ #

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.headers.update(DEFAULT_HEADERS)
        return session

    def _load_token(self) -> None:
        if not self._tokens_path.exists():
            raise AuthError(
                f"No se encontró el archivo de tokens en {self._tokens_path}. "
                "Ejecuta 'python scripts/auth.py' para autenticarte."
            )
        data = json.loads(self._tokens_path.read_text(encoding="utf-8"))
        self._access_token = data.get("access_token")
        if not self._access_token:
            raise AuthError("El archivo de tokens no contiene access_token válido.")
        logger.debug("Token cargado desde %s", self._tokens_path)

    def _auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    # ------------------------------------------------------------------ #
    # Método base de petición                                              #
    # ------------------------------------------------------------------ #

    def _request(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict] = None,
        json_body: Optional[Dict] = None,
        retry_auth: bool = True,
    ) -> Any:
        headers = self._auth_headers()
        try:
            resp = self._session.request(method, url, headers=headers, params=params, json=json_body, timeout=30)
        except requests.RequestException as exc:
            raise APIError(0, str(exc)) from exc

        if resp.status_code == 401 and retry_auth:
            logger.info("Token expirado, intentando renovar...")
            self._refresh_token()
            return self._request(method, url, params=params, json_body=json_body, retry_auth=False)

        if not resp.ok:
            raise APIError(resp.status_code, resp.text[:500])

        try:
            return resp.json()
        except ValueError:
            return resp.text

    def _get(self, url: str, **kwargs) -> Any:
        return self._request("GET", url, **kwargs)

    def _post(self, url: str, **kwargs) -> Any:
        return self._request("POST", url, **kwargs)

    def _put(self, url: str, **kwargs) -> Any:
        return self._request("PUT", url, **kwargs)

    # ------------------------------------------------------------------ #
    # Renovación de token                                                  #
    # ------------------------------------------------------------------ #

    def _refresh_token(self) -> None:
        if not self._tokens_path.exists():
            raise AuthError("No hay tokens guardados para renovar.")
        data = json.loads(self._tokens_path.read_text(encoding="utf-8"))
        refresh_token = data.get("refresh_token")
        if not refresh_token:
            raise AuthError("No hay refresh_token disponible. Re-autentica con scripts/auth.py.")

        resp = self._session.get(
            TOKEN_ENDPOINT,
            headers={**DEFAULT_HEADERS, "Authorization": f"Bearer {refresh_token}"},
            timeout=15,
        )
        if not resp.ok:
            raise AuthError(f"No se pudo renovar el token: {resp.status_code} {resp.text[:200]}")

        new_data = resp.json()
        data["access_token"] = new_data.get("access_token", data["access_token"])
        if "refresh_token" in new_data:
            data["refresh_token"] = new_data["refresh_token"]
        data["refreshed_at"] = time.time()
        self._tokens_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        self._access_token = data["access_token"]
        logger.info("Token renovado exitosamente.")

    # ------------------------------------------------------------------ #
    # Leagues                                                              #
    # ------------------------------------------------------------------ #

    def get_leagues(self) -> List[Dict]:
        return self._get(LEAGUES) or []

    def get_league(self, league_id: str) -> League:
        raw = self._get(LEAGUES + f"/{league_id}")
        return self._parse_league(raw, league_id)

    # ------------------------------------------------------------------ #
    # Team                                                                 #
    # ------------------------------------------------------------------ #

    def get_my_team(self, league_id: str) -> Team:
        url = MY_TEAM.format(league_id=league_id)
        raw = self._get(url)
        return self._parse_team(raw)

    def get_rival_teams(self, league_id: str) -> List[Team]:
        url = RIVAL_TEAMS.format(league_id=league_id)
        raw = self._get(url) or []
        return [self._parse_team(t) for t in raw]

    # ------------------------------------------------------------------ #
    # Market                                                               #
    # ------------------------------------------------------------------ #

    def get_market(self, league_id: str) -> Market:
        url = MARKET.format(league_id=league_id)
        raw = self._get(url) or {}
        players_raw = raw.get("players", raw) if isinstance(raw, dict) else raw
        market_players = [self._parse_market_player(p) for p in players_raw]
        return Market(players=market_players)

    def buy_player(self, league_id: str, player_id: str, bid: int) -> Dict:
        from .endpoints import MARKET_BUY
        url = MARKET_BUY.format(league_id=league_id)
        return self._post(url, json_body={"playerId": player_id, "bid": bid})

    def sell_player(self, league_id: str, player_id: str, price: int) -> Dict:
        from .endpoints import MARKET_SELL
        url = MARKET_SELL.format(league_id=league_id)
        return self._post(url, json_body={"playerId": player_id, "price": price})

    def remove_from_market(self, league_id: str, player_id: str) -> Dict:
        from .endpoints import MARKET_REMOVE
        url = MARKET_REMOVE.format(league_id=league_id)
        return self._post(url, json_body={"playerId": player_id})

    # ------------------------------------------------------------------ #
    # Players                                                              #
    # ------------------------------------------------------------------ #

    def get_all_players(self) -> List[Player]:
        raw = self._get(PLAYERS) or []
        return [self._parse_player(p) for p in raw]

    def get_player_stats(self, player_id: str) -> PlayerStats:
        url = PLAYER_STATS.format(player_id=player_id)
        raw = self._get(url) or {}
        return self._parse_player_stats(raw)

    # ------------------------------------------------------------------ #
    # Standings                                                            #
    # ------------------------------------------------------------------ #

    def get_standings(self, league_id: str) -> List[Dict]:
        url = LEAGUE_STANDINGS.format(league_id=league_id)
        return self._get(url) or []

    # ------------------------------------------------------------------ #
    # Parsers                                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_player_stats(raw: Dict) -> PlayerStats:
        return PlayerStats(
            season_points=raw.get("totalPoints", raw.get("season_points", 0)),
            last_5_avg=raw.get("averageLast5", raw.get("last_5_avg", 0.0)),
            last_match_points=raw.get("lastMatchPoints", raw.get("last_match_points", 0)),
            total_matches=raw.get("totalMatches", raw.get("total_matches", 0)),
            goals=raw.get("goals", 0),
            assists=raw.get("assists", 0),
            yellow_cards=raw.get("yellowCards", raw.get("yellow_cards", 0)),
            red_cards=raw.get("redCards", raw.get("red_cards", 0)),
            minutes_played=raw.get("minutesPlayed", raw.get("minutes_played", 0)),
            fitness=raw.get("fitness", 100),
        )

    @classmethod
    def _parse_player(cls, raw: Dict) -> Player:
        pos_map = {"1": "GK", "2": "DEF", "3": "MID", "4": "FWD",
                   "goalkeeper": "GK", "defender": "DEF", "midfielder": "MID", "forward": "FWD"}
        pos_raw = str(raw.get("positionId", raw.get("position", "MID")))
        position = pos_map.get(pos_raw.lower(), pos_raw.upper())

        stats_raw = raw.get("stats", raw.get("playerStats", {}))
        stats = cls._parse_player_stats(stats_raw) if stats_raw else None

        return Player(
            id=str(raw.get("id", raw.get("playerId", ""))),
            name=raw.get("name", raw.get("playerName", "Unknown")),
            team=raw.get("teamName", raw.get("team", {}).get("name", "")),
            position=position,
            market_value=int(raw.get("marketValue", raw.get("value", 0))),
            clause_value=int(raw.get("clauseValue", raw.get("clause", 0))),
            points=int(raw.get("totalPoints", raw.get("points", 0))),
            status=raw.get("status", raw.get("playerStatus", "ok")).lower(),
            stats=stats,
            raw=raw,
        )

    @classmethod
    def _parse_market_player(cls, raw: Dict) -> MarketPlayer:
        player_raw = raw.get("player", raw)
        player = cls._parse_player(player_raw)
        return MarketPlayer(
            player=player,
            sell_price=int(raw.get("sellPrice", raw.get("price", raw.get("bid", 0)))),
            time_left=int(raw.get("timeLeft", raw.get("time_left", 0))),
            seller_name=raw.get("sellerName", raw.get("seller", {}).get("name", "")),
        )

    @classmethod
    def _parse_team(cls, raw: Dict) -> Team:
        if isinstance(raw, list):
            raw = {"players": raw}
        team_players = [
            TeamPlayer(
                player=cls._parse_player(p.get("player", p)),
                in_lineup=p.get("inLineup", p.get("in_lineup", True)),
                is_captain=p.get("isCaptain", p.get("is_captain", False)),
                buy_price=int(p.get("buyPrice", p.get("buy_price", 0))),
            )
            for p in raw.get("players", [])
        ]
        return Team(
            id=str(raw.get("id", raw.get("teamId", ""))),
            name=raw.get("name", raw.get("teamName", "")),
            manager=raw.get("managerName", raw.get("manager", "")),
            budget=int(raw.get("budget", raw.get("money", 0))),
            team_value=int(raw.get("teamValue", raw.get("value", 0))),
            players=team_players,
            points=int(raw.get("points", 0)),
            rank=int(raw.get("rank", 0)),
        )

    @classmethod
    def _parse_league(cls, raw: Dict, league_id: str) -> League:
        my_team_raw = raw.get("myTeam", raw.get("team"))
        rival_raw = raw.get("teams", [])
        return League(
            id=league_id,
            name=raw.get("name", ""),
            my_team=cls._parse_team(my_team_raw) if my_team_raw else None,
            rival_teams=[cls._parse_team(t) for t in rival_raw],
            matchday=int(raw.get("currentMatchday", raw.get("matchday", 0))),
        )
