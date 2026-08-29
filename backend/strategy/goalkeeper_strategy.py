"""
Estrategia específica para porteros.
Los porteros tienen métricas distintas (porterías a cero, paradas, etc.)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from ..laliga.models import Player, PlayerStats
from .player_scoring import PlayerScoring, ScoredPlayer

logger = logging.getLogger(__name__)


@dataclass
class GKScore:
    player: Player
    base_score: ScoredPlayer
    clean_sheet_ratio: float   # estimado de porterías a cero
    saves_score: float
    attacking_bonus: float     # puntos extra por asistencias/goles raros
    gk_composite: float
    recommendation: str


class GoalkeeperStrategy(PlayerScoring):
    """
    Especialización de PlayerScoring para porteros.
    Ajusta pesos: la forma reciente pesa más que el valor.
    """

    POSITION_WEIGHTS = {
        "GK": {"value_weight": 0.25, "form_weight": 0.50, "season_weight": 0.25}
    }

    # Puntos medios de una portería a cero en LaLiga Fantasy (~7-9 pts)
    CLEAN_SHEET_POINTS = 8.0

    def score_goalkeeper(self, player: Player) -> GKScore:
        if player.position != "GK":
            raise ValueError(f"{player.name} no es portero (posición: {player.position})")

        base = self.score_player(player)
        stats = player.stats or PlayerStats()

        # Estimamos porterías a cero basándonos en la media de puntos
        # Un portero con 10+ pts de media probable tiene muchas P0
        clean_sheet_ratio = min(stats.last_5_avg / (self.CLEAN_SHEET_POINTS * 2), 1.0)

        # Estimamos saves basándonos en minutos jugados / partidos
        saves_score = min(stats.minutes_played / (90 * max(stats.total_matches, 1)), 1.0)

        # Bonus atacante (goles/asistencias de portero son raros pero valiosos)
        attacking_bonus = min((stats.goals + stats.assists) * 0.1, 0.2)

        gk_composite = (
            base.composite * 0.7
            + clean_sheet_ratio * 0.2
            + saves_score * 0.05
            + attacking_bonus * 0.05
        )

        rec = "BUY" if gk_composite >= 0.60 else "HOLD" if gk_composite >= 0.35 else "SELL"
        if not player.is_available:
            rec = "SELL" if player.status == "injured" else "WATCH"

        return GKScore(
            player=player,
            base_score=base,
            clean_sheet_ratio=round(clean_sheet_ratio, 3),
            saves_score=round(saves_score, 3),
            attacking_bonus=round(attacking_bonus, 3),
            gk_composite=round(gk_composite, 4),
            recommendation=rec,
        )

    def rank_goalkeepers(self, players: List[Player]) -> List[GKScore]:
        gks = [p for p in players if p.position == "GK"]
        scored = [self.score_goalkeeper(gk) for gk in gks]
        return sorted(scored, key=lambda s: s.gk_composite, reverse=True)
