"""
Modelos de datos basados en la estructura JSON real de la API (verificada 31/08/2026)
"""
from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class Player:
    id: str
    name: str
    nickname: str
    position: str          # "Portero", "Defensa", "Centrocampista", "Delantero"
    position_id: int       # 1=POR, 2=DEF, 3=MID, 4=DEL
    team_id: int
    market_value: int      # valor de mercado en €
    points: int            # puntos totales temporada
    week_points: int       # puntos última jornada
    average_points: float
    last_season_points: int
    status: str            # "ok", "injured", "out_of_league", "doubtful"
    image_url: str = ""
    buyout_clause: int = 0
    player_team_id: str = ""

    @classmethod
    def from_lineup_entry(cls, entry: dict) -> "Player":
        pm = entry.get("playerMaster", {})
        images = pm.get("images", {}).get("transparent", {})
        return cls(
            id=pm.get("id", ""),
            name=pm.get("name", ""),
            nickname=pm.get("nickname", ""),
            position=pm.get("position", ""),
            position_id=pm.get("positionId", 0),
            team_id=pm.get("teamId", 0),
            market_value=pm.get("marketValue", 0),
            points=pm.get("points", 0),
            week_points=entry.get("weekPoints", 0) or pm.get("weekPoints", 0),
            average_points=pm.get("averagePoints", 0.0),
            last_season_points=pm.get("lastSeasonPoints", 0),
            status=pm.get("playerStatus", "ok"),
            image_url=images.get("256x256", ""),
            buyout_clause=entry.get("buyoutClause", 0),
            player_team_id=entry.get("playerTeamId", ""),
        )


@dataclass
class MyTeam:
    team_id: str
    team_value: int
    team_points: int
    budget: int
    players: List[Player] = field(default_factory=list)
    formation: List[int] = field(default_factory=list)
    updated_at: str = ""

    @classmethod
    def from_api(cls, data: dict, money_data: Optional[dict] = None) -> "MyTeam":
        team = data.get("team", {})
        formation_data = data.get("formation", {})
        players = []
        for pos in ["goalkeeper", "defender", "midfield", "striker"]:
            for entry in formation_data.get(pos, []):
                players.append(Player.from_lineup_entry(entry))
        budget = 0
        if money_data:
            budget = money_data.get("teamMoney", 0) or money_data.get("money", 0)
        return cls(
            team_id=team.get("id", ""),
            team_value=team.get("teamValue", 0),
            team_points=team.get("teamPoints", 0),
            budget=budget,
            players=players,
            formation=data.get("formation", {}).get("tacticalFormation", []),
            updated_at=data.get("updatedAt", ""),
        )


@dataclass
class MarketPlayer:
    market_id: str
    player: Player
    sale_price: int
    buyout_clause: int
    expiration_date: str
    seller_manager: str
    seller_team_id: str
    seller_team_value: int
    seller_team_points: int
    is_shielded: bool
    number_of_offers: int

    @classmethod
    def from_api(cls, entry: dict) -> "MarketPlayer":
        pm = entry.get("playerMaster", {})
        pt = entry.get("playerTeam", {})
        seller = entry.get("sellerTeam", {})
        manager = seller.get("manager", {})
        images = pm.get("images", {}).get("transparent", {})
        player = Player(
            id=pm.get("id", ""),
            name=pm.get("name", ""),
            nickname=pm.get("nickname", ""),
            position=pm.get("position", ""),
            position_id=pm.get("positionId", 0),
            team_id=pm.get("teamId", 0),
            market_value=pm.get("marketValue", 0),
            points=pm.get("points", 0),
            week_points=0,
            average_points=pm.get("averagePoints", 0.0),
            last_season_points=pm.get("lastSeasonPoints", 0),
            status=pm.get("playerStatus", "ok"),
            image_url=images.get("256x256", ""),
            buyout_clause=pt.get("buyoutClause", 0),
            player_team_id=pt.get("playerTeamId", ""),
        )
        return cls(
            market_id=str(entry.get("id", "")),
            player=player,
            sale_price=entry.get("salePrice", 0),
            buyout_clause=pt.get("buyoutClause", 0),
            expiration_date=entry.get("expirationDate", ""),
            seller_manager=manager.get("managerName", ""),
            seller_team_id=str(seller.get("id", "")),
            seller_team_value=seller.get("teamValue", 0),
            seller_team_points=seller.get("teamPoints", 0),
            is_shielded=pt.get("isShielded", False),
            number_of_offers=entry.get("numberOfOffers", 0),
        )


@dataclass
class RivalTeam:
    team_id: str
    manager_name: str
    manager_id: str
    team_value: int
    team_points: int
    budget: int = 0
    players: List[Player] = field(default_factory=list)

    @classmethod
    def from_standing(cls, entry: dict) -> "RivalTeam":
        manager = entry.get("manager", {})
        return cls(
            team_id=str(entry.get("id", "")),
            manager_name=manager.get("managerName", entry.get("managerName", "")),
            manager_id=str(entry.get("managerId", "")),
            team_value=entry.get("teamValue", 0),
            team_points=entry.get("teamPoints", 0),
        )


@dataclass
class ClauseRisk:
    player: Player
    risk_level: str       # "BAJO", "MEDIO", "ALTO", "CRÍTICO"
    risk_score: float     # 0-100
    reasons: List[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class MarketPlayerV2(MarketPlayer):
    """Versión extendida con tipo de mercado"""
    direct_offer: bool = False

    @classmethod
    def from_api(cls, entry: dict) -> "MarketPlayerV2":
        base = super().from_api(entry)
        pt = entry.get("playerTeam", {})
        sale = entry.get("salePrice", 0)
        clause = pt.get("buyoutClause", 0)
        direct = entry.get("directOffer", False)
        # Si salePrice == buyoutClause también es clausulazo
        is_clause = direct or (clause > 0 and sale >= clause * 0.99)
        obj = cls(
            market_id=base.market_id,
            player=base.player,
            sale_price=base.sale_price,
            buyout_clause=base.buyout_clause,
            expiration_date=base.expiration_date,
            seller_manager=base.seller_manager,
            seller_team_id=base.seller_team_id,
            seller_team_value=base.seller_team_value,
            seller_team_points=base.seller_team_points,
            is_shielded=base.is_shielded,
            number_of_offers=base.number_of_offers,
            direct_offer=is_clause,
        )
        return obj
