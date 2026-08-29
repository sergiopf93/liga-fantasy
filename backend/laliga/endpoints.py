"""Constantes de endpoints para la API de LaLiga Fantasy."""

BASE_URL = "https://fantasy-api.llt-services.com"

# Auth
TOKEN_ENDPOINT = f"{BASE_URL}/dsp/v3/token"

# User
ME = f"{BASE_URL}/user/me"

# Leagues
LEAGUES = f"{BASE_URL}/leagues"
LEAGUE_DETAIL = f"{BASE_URL}/leagues/{{league_id}}"

# Team
MY_TEAM = f"{BASE_URL}/leagues/{{league_id}}/team"
RIVAL_TEAM = f"{BASE_URL}/leagues/{{league_id}}/team/{{team_id}}"
RIVAL_TEAMS = f"{BASE_URL}/leagues/{{league_id}}/teams"

# Market
MARKET = f"{BASE_URL}/leagues/{{league_id}}/market"
MARKET_BUY = f"{BASE_URL}/leagues/{{league_id}}/market/buy"
MARKET_SELL = f"{BASE_URL}/leagues/{{league_id}}/market/sell"
MARKET_REMOVE = f"{BASE_URL}/leagues/{{league_id}}/market/remove"

# Players
PLAYERS = f"{BASE_URL}/players"
PLAYER_DETAIL = f"{BASE_URL}/players/{{player_id}}"
PLAYER_STATS = f"{BASE_URL}/players/{{player_id}}/stats"
PLAYER_FIXTURES = f"{BASE_URL}/players/{{player_id}}/fixtures"

# Schedule
SCHEDULE = f"{BASE_URL}/games/schedule"
MATCHDAY = f"{BASE_URL}/games/matchday/{{matchday}}"

# Standings
LEAGUE_STANDINGS = f"{BASE_URL}/leagues/{{league_id}}/standings"
MATCHDAY_STANDINGS = f"{BASE_URL}/leagues/{{league_id}}/standings/{{matchday}}"

# Default headers
DEFAULT_HEADERS = {
    "X-App": "Fantasy-web",
    "X-Lang": "es",
    "Origin": "https://laligafantasy.relevo.com",
    "Referer": "https://laligafantasy.relevo.com/",
    "Content-Type": "application/json",
    "Accept": "application/json",
}
