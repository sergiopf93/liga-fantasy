"""
Sistema de puntuación y valoración de jugadores.
Calcula scores compuestos para comparar jugadores entre posiciones.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..laliga.models import Player, PlayerStats

logger = logging.getLogger(__name__)


@dataclass
class ScoredPlayer:
    player: Player
    raw_score: float
    value_score: float      # puntos / valor de mercado
    form_score: float       # media últimas 5 jornadas
    consistency: float      # desviación estándar (menor = mejor)
    composite: float        # score final ponderado
    recommendation: str     # "BUY" | "HOLD" | "SELL" | "WATCH"
    notes: List[str]


class PlayerScoring:
    """
    Calcula puntuaciones multicritério para jugadores.

    Pesos por defecto (sumatorio = 1.0):
      - value_weight:   rendimiento por precio (eficiencia)
      - form_weight:    forma reciente (últimas 5)
      - season_weight:  puntos totales en la temporada
    """

    POSITION_WEIGHTS = {
        "GK":  {"value_weight": 0.35, "form_weight": 0.40, "season_weight": 0.25},
        "DEF": {"value_weight": 0.30, "form_weight": 0.35, "season_weight": 0.35},
        "MID": {"value_weight": 0.25, "form_weight": 0.40, "season_weight": 0.35},
        "FWD": {"value_weight": 0.20, "form_weight": 0.45, "season_weight": 0.35},
    }

    BUY_THRESHOLD = 0.65
    SELL_THRESHOLD = 0.35

    def __init__(self, custom_weights: Optional[Dict[str, Dict]] = None):
        if custom_weights:
            self.POSITION_WEIGHTS = {**self.POSITION_WEIGHTS, **custom_weights}

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def score_player(self, player: Player) -> ScoredPlayer:
        notes: List[str] = []

        if not player.is_available:
            notes.append(f"Baja/duda: {player.status}")

        stats = player.stats or PlayerStats()
        weights = self.POSITION_WEIGHTS.get(player.position, self.POSITION_WEIGHTS["MID"])

        value_score = self._value_score(player)
        form_score = self._form_score(stats)
        season_score = self._season_score(stats)

        composite = (
            weights["value_weight"] * value_score
            + weights["form_weight"] * form_score
            + weights["season_weight"] * season_score
        )

        if not player.is_available:
            composite *= 0.6

        recommendation = self._recommend(composite, player, notes)

        return ScoredPlayer(
            player=player,
            raw_score=season_score,
            value_score=value_score,
            form_score=form_score,
            consistency=self._consistency(stats),
            composite=round(composite, 4),
            recommendation=recommendation,
            notes=notes,
        )

    def rank_players(self, players: List[Player]) -> List[ScoredPlayer]:
        scored = [self.score_player(p) for p in players]
        return sorted(scored, key=lambda s: s.composite, reverse=True)

    def rank_by_position(self, players: List[Player]) -> Dict[str, List[ScoredPlayer]]:
        result: Dict[str, List[ScoredPlayer]] = {}
        for pos in ("GK", "DEF", "MID", "FWD"):
            pos_players = [p for p in players if p.position == pos]
            result[pos] = self.rank_players(pos_players)
        return result

    def top_picks(self, players: List[Player], n: int = 5) -> Dict[str, List[ScoredPlayer]]:
        by_pos = self.rank_by_position(players)
        return {pos: scored[:n] for pos, scored in by_pos.items()}

    # ------------------------------------------------------------------ #
    # Sub-scores internos                                                  #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _value_score(player: Player) -> float:
        """Puntos por millón de euros de valor de mercado (normalizado 0-1)."""
        if player.market_value == 0:
            return 0.0
        raw = player.points / (player.market_value / 1_000_000)
        # Normalización: ~10 pts/M es muy bueno
        return min(raw / 15.0, 1.0)

    @staticmethod
    def _form_score(stats: PlayerStats) -> float:
        """Media últimas 5 jornadas normalizada (0-1). ~15 pts es excelente."""
        return min(stats.last_5_avg / 15.0, 1.0)

    @staticmethod
    def _season_score(stats: PlayerStats) -> float:
        """Puntos totales normalizados (0-1). ~200 pts es top temporada."""
        return min(stats.season_points / 200.0, 1.0)

    @staticmethod
    def _consistency(stats: PlayerStats) -> float:
        """
        Proxy de consistencia usando puntos por partido.
        Retorna valor 0-1 donde 1 = muy consistente.
        """
        if stats.total_matches == 0:
            return 0.5
        avg = stats.points_per_match
        # Si el jugador puntúa consistentemente ~10 pts/partido → alta consistencia
        if avg == 0:
            return 0.0
        # Aproximamos que la consistencia es inversamente proporcional
        # a la variación estimada (sin histórico de partidos individuales)
        return min(avg / 12.0, 1.0)

    def _recommend(self, composite: float, player: Player, notes: List[str]) -> str:
        if not player.is_available:
            return "SELL" if player.status in ("injured", "suspended") else "WATCH"
        if composite >= self.BUY_THRESHOLD:
            notes.append(f"Score alto ({composite:.2f}) → buen momento de compra")
            return "BUY"
        if composite <= self.SELL_THRESHOLD:
            notes.append(f"Score bajo ({composite:.2f}) → considerar venta")
            return "SELL"
        return "HOLD"
