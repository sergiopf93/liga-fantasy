"""Tests para LaLigaFantasyClient — sin llamadas reales a la API."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import sys
sys.path.insert(0, str(Path(__file__).parents[1]))

from backend.laliga.client import LaLigaFantasyClient, AuthError, APIError
from backend.laliga.models import Player, PlayerStats, Team, Market


# ============================================================
# Fixtures
# ============================================================

PLAYER_RAW = {
    "id": "42",
    "name": "Vinicius Jr",
    "teamName": "Real Madrid",
    "positionId": "4",
    "marketValue": 50_000_000,
    "clauseValue": 60_000_000,
    "totalPoints": 150,
    "status": "ok",
    "stats": {
        "totalPoints": 150,
        "averageLast5": 12.4,
        "lastMatchPoints": 14,
        "totalMatches": 25,
        "goals": 18,
        "assists": 7,
        "yellowCards": 2,
        "redCards": 0,
        "minutesPlayed": 2100,
    },
}

TEAM_RAW = {
    "id": "team-1",
    "name": "Los Galácticos",
    "managerName": "Sergio",
    "budget": 10_000_000,
    "teamValue": 180_000_000,
    "points": 312,
    "rank": 2,
    "players": [
        {
            "player": PLAYER_RAW,
            "inLineup": True,
            "isCaptain": True,
            "buyPrice": 48_000_000,
        }
    ],
}

MARKET_RAW = {
    "players": [
        {
            "player": PLAYER_RAW,
            "sellPrice": 45_000_000,
            "timeLeft": 3600,
            "sellerName": "Rival FC",
        }
    ]
}


@pytest.fixture
def tokens_file(tmp_path) -> Path:
    f = tmp_path / ".tokens.json"
    f.write_text(json.dumps({"access_token": "fake-jwt-token", "refresh_token": "fake-refresh"}))
    return f


@pytest.fixture
def client(tokens_file) -> LaLigaFantasyClient:
    return LaLigaFantasyClient(tokens_file=tokens_file)


# ============================================================
# Tests de parsers
# ============================================================

class TestParsers:
    def test_parse_player(self):
        player = LaLigaFantasyClient._parse_player(PLAYER_RAW)
        assert player.id == "42"
        assert player.name == "Vinicius Jr"
        assert player.position == "FWD"
        assert player.market_value == 50_000_000
        assert player.points == 150
        assert player.is_available is True

    def test_parse_player_stats(self):
        stats = LaLigaFantasyClient._parse_player_stats(PLAYER_RAW["stats"])
        assert stats.season_points == 150
        assert stats.last_5_avg == 12.4
        assert stats.goals == 18
        assert stats.points_per_match == pytest.approx(6.0, abs=0.1)

    def test_parse_team(self):
        team = LaLigaFantasyClient._parse_team(TEAM_RAW)
        assert team.name == "Los Galácticos"
        assert team.budget == 10_000_000
        assert len(team.players) == 1
        assert team.players[0].is_captain is True
        assert team.players[0].player.name == "Vinicius Jr"

    def test_parse_market_player(self):
        mp = LaLigaFantasyClient._parse_market_player(MARKET_RAW["players"][0])
        assert mp.sell_price == 45_000_000
        assert mp.time_left == 3600
        assert mp.is_bargain  # 45M < 60M cláusula

    def test_position_mapping(self):
        for raw_pos, expected in [("1", "GK"), ("2", "DEF"), ("3", "MID"), ("4", "FWD")]:
            p = LaLigaFantasyClient._parse_player({**PLAYER_RAW, "positionId": raw_pos})
            assert p.position == expected


# ============================================================
# Tests de autenticación
# ============================================================

class TestAuth:
    def test_load_token_ok(self, tokens_file):
        client = LaLigaFantasyClient(tokens_file=tokens_file)
        assert client._access_token == "fake-jwt-token"

    def test_no_tokens_file_raises(self, tmp_path):
        with pytest.raises(AuthError, match="auth.py"):
            LaLigaFantasyClient(tokens_file=tmp_path / "missing.json")

    def test_invalid_tokens_raises(self, tmp_path):
        f = tmp_path / ".tokens.json"
        f.write_text(json.dumps({"refresh_token": "only-refresh"}))
        with pytest.raises(AuthError, match="access_token"):
            LaLigaFantasyClient(tokens_file=f)


# ============================================================
# Tests de peticiones HTTP (mocked)
# ============================================================

class TestHTTPRequests:
    def test_get_all_players(self, client):
        with patch.object(client, "_get", return_value=[PLAYER_RAW]) as mock_get:
            players = client.get_all_players()
            assert len(players) == 1
            assert isinstance(players[0], Player)
            mock_get.assert_called_once()

    def test_get_my_team(self, client):
        with patch.object(client, "_get", return_value=TEAM_RAW):
            team = client.get_my_team("league-1")
            assert isinstance(team, Team)
            assert team.budget == 10_000_000

    def test_get_market(self, client):
        with patch.object(client, "_get", return_value=MARKET_RAW):
            market = client.get_market("league-1")
            assert isinstance(market, Market)
            assert len(market.players) == 1

    def test_api_error_propagates(self, client):
        mock_resp = MagicMock()
        mock_resp.ok = False
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"
        with patch.object(client._session, "request", return_value=mock_resp):
            with pytest.raises(APIError, match="403"):
                client._request("GET", "https://example.com/test", retry_auth=False)
