"""Modelos de datos para la API de LaLiga Fantasy."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime


@dataclass
class PlayerStats:
    season_points: int = 0
    last_5_avg: float = 0.0
    last_match_points: int = 0
    total_matches: int = 0
    goals: int = 0
    assists: int = 0
    yellow_cards: int = 0
    red_cards: int = 0
    minutes_played: int = 0
    fitness: int = 100  # 0-100

    @property
    def points_per_match(self) -> float:
        if self.total_matches == 0:
            return 0.0
        return round(self.season_points / self.total_matches, 2)


@dataclass
class Player:
    id: str
    name: str
    team: str
    position: str  # "GK", "DEF", "MID", "FWD"
    market_value: int = 0
    clause_value: int = 0
    points: int = 0
    status: str = "ok"  # "ok", "injured", "doubt", "suspended"
    stats: Optional[PlayerStats] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def value_per_point(self) -> float:
        if self.points == 0:
            return float("inf")
        return round(self.market_value / self.points, 2)

    @property
    def is_available(self) -> bool:
        return self.status == "ok"

    def __repr__(self) -> str:
        return f"Player({self.name}, {self.position}, {self.market_value:,}€, {self.points}pts)"


@dataclass
class MarketPlayer:
    player: Player
    sell_price: int = 0
    time_left: int = 0  # seconds
    seller_name: str = ""
    on_sale: bool = True

    @property
    def is_bargain(self) -> bool:
        """True si el precio de venta es menor que el valor de cláusula."""
        return self.sell_price < self.player.clause_value


@dataclass
class Market:
    players: List[MarketPlayer] = field(default_factory=list)
    last_updated: Optional[datetime] = None

    def get_by_position(self, position: str) -> List[MarketPlayer]:
        return [mp for mp in self.players if mp.player.position == position]

    def get_bargains(self) -> List[MarketPlayer]:
        return [mp for mp in self.players if mp.is_bargain]


@dataclass
class TeamPlayer:
    player: Player
    in_lineup: bool = True
    is_captain: bool = False
    buy_price: int = 0


@dataclass
class Team:
    id: str
    name: str
    manager: str = ""
    budget: int = 0
    team_value: int = 0
    players: List[TeamPlayer] = field(default_factory=list)
    points: int = 0
    rank: int = 0

    def get_by_position(self, position: str) -> List[TeamPlayer]:
        return [tp for tp in self.players if tp.player.position == position]

    @property
    def lineup(self) -> List[TeamPlayer]:
        return [tp for tp in self.players if tp.in_lineup]


@dataclass
class League:
    id: str
    name: str
    my_team: Optional[Team] = None
    rival_teams: List[Team] = field(default_factory=list)
    matchday: int = 0
    total_matchdays: int = 38

    @property
    def all_teams(self) -> List[Team]:
        teams = list(self.rival_teams)
        if self.my_team:
            teams.insert(0, self.my_team)
        return teams


@dataclass
class Fixture:
    home_team: str
    away_team: str
    matchday: int
    date: Optional[datetime] = None
    home_difficulty: int = 3  # 1-5
    away_difficulty: int = 3  # 1-5
