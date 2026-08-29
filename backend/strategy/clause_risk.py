"""
Análisis de riesgo de cláusula de liberación.
Evalúa si un jugador propio puede ser adquirido por rivales.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..laliga.models import League, Player, Team, TeamPlayer

logger = logging.getLogger(__name__)


@dataclass
class ClauseRiskResult:
    player: Player
    clause_value: int
    risk_level: str      # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    rivals_can_afford: int
    recommendation: str
    notes: List[str]


class ClauseRisk:
    """
    Evalúa el riesgo de que un rival active la cláusula de un jugador propio.

    Criterios:
    - ¿Cuántos rivales tienen presupuesto suficiente para la cláusula?
    - ¿Está el jugador en un buen momento de forma? (tentador para rivales)
    - ¿Vale la pena reducir el precio de venta para dificultar la compra?
    """

    CRITICAL_THRESHOLD = 3   # Si +3 rivales pueden permitírselo → CRITICAL
    HIGH_THRESHOLD = 2
    MEDIUM_THRESHOLD = 1

    def assess_player(self, tp: TeamPlayer, league: League) -> ClauseRiskResult:
        player = tp.player
        clause = player.clause_value
        notes: List[str] = []

        rivals_can_afford = sum(
            1 for rival in league.rival_teams
            if rival.budget >= clause
        )

        if rivals_can_afford >= self.CRITICAL_THRESHOLD:
            risk_level = "CRITICAL"
            recommendation = (
                f"Reduce el precio de venta urgentemente. "
                f"{rivals_can_afford} rivales pueden activar la cláusula ({clause:,}€)."
            )
        elif rivals_can_afford >= self.HIGH_THRESHOLD:
            risk_level = "HIGH"
            recommendation = f"Considera reducir cláusula. {rivals_can_afford} rivales con fondos suficientes."
        elif rivals_can_afford >= self.MEDIUM_THRESHOLD:
            risk_level = "MEDIUM"
            recommendation = f"Vigilar. 1 rival puede permitirse la cláusula ({clause:,}€)."
        else:
            risk_level = "LOW"
            recommendation = "Sin riesgo significativo de cláusula a corto plazo."

        if player.stats and player.stats.last_5_avg > 10:
            notes.append(f"En buena forma ({player.stats.last_5_avg:.1f} pts/jornada) → más atractivo para rivales")

        if player.market_value > 0 and clause < player.market_value * 1.5:
            notes.append("Cláusula relativamente baja respecto al valor de mercado")

        return ClauseRiskResult(
            player=player,
            clause_value=clause,
            risk_level=risk_level,
            rivals_can_afford=rivals_can_afford,
            recommendation=recommendation,
            notes=notes,
        )

    def assess_team(self, league: League) -> List[ClauseRiskResult]:
        if not league.my_team:
            return []
        results = [self.assess_player(tp, league) for tp in league.my_team.players]
        order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        return sorted(results, key=lambda r: order[r.risk_level])

    def critical_players(self, league: League) -> List[ClauseRiskResult]:
        return [r for r in self.assess_team(league) if r.risk_level in ("CRITICAL", "HIGH")]
