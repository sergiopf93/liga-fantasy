"""
Análisis de equipos rivales en la liga.
Identifica amenazas, debilidades y oportunidades tácticas.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..laliga.models import League, Team, TeamPlayer
from .player_scoring import PlayerScoring

logger = logging.getLogger(__name__)


@dataclass
class RivalReport:
    team: Team
    strengths: List[str]
    weaknesses: List[str]
    threat_level: str       # "HIGH" | "MEDIUM" | "LOW"
    key_players: List[TeamPlayer]
    budget_estimate: int
    notes: List[str]


class RivalAnalysis:
    """Analiza los equipos rivales de la liga."""

    def __init__(self, scorer: Optional[PlayerScoring] = None):
        self.scorer = scorer or PlayerScoring()

    def analyze_rival(self, rival: Team, my_team: Optional[Team] = None) -> RivalReport:
        strengths: List[str] = []
        weaknesses: List[str] = []
        notes: List[str] = []

        # Jugadores clave (top 3 por puntos)
        sorted_players = sorted(
            rival.players,
            key=lambda tp: tp.player.points,
            reverse=True,
        )
        key_players = sorted_players[:3]

        # Valor total del equipo
        team_value = sum(tp.player.market_value for tp in rival.players)
        avg_player_value = team_value / len(rival.players) if rival.players else 0

        if avg_player_value > 15_000_000:
            strengths.append(f"Equipo con alto valor medio ({avg_player_value/1e6:.1f}M€/jugador)")
        elif avg_player_value < 8_000_000:
            weaknesses.append("Equipo con bajo valor de plantilla")

        # Análisis de puntos
        if rival.points > 0:
            pts_per_player = rival.points / len(rival.players) if rival.players else 0
            if pts_per_player > 12:
                strengths.append(f"Rendimiento alto ({pts_per_player:.1f} pts/jugador)")
                threat_level = "HIGH"
            elif pts_per_player > 8:
                notes.append(f"Rendimiento medio ({pts_per_player:.1f} pts/jugador)")
                threat_level = "MEDIUM"
            else:
                weaknesses.append(f"Rendimiento bajo ({pts_per_player:.1f} pts/jugador)")
                threat_level = "LOW"
        else:
            threat_level = "MEDIUM"

        # Jugadores lesionados/dudosos
        unavailable = [tp for tp in rival.players if not tp.player.is_available]
        if unavailable:
            names = ", ".join(tp.player.name for tp in unavailable[:3])
            weaknesses.append(f"Bajas importantes: {names}")

        # Comparación con mi equipo
        if my_team:
            my_value = sum(tp.player.market_value for tp in my_team.players)
            if team_value > my_value * 1.2:
                strengths.append(f"Plantilla más valiosa que la tuya ({team_value/1e6:.1f}M€ vs {my_value/1e6:.1f}M€)")
            elif team_value < my_value * 0.8:
                weaknesses.append("Plantilla menos valiosa que la tuya")

        return RivalReport(
            team=rival,
            strengths=strengths,
            weaknesses=weaknesses,
            threat_level=threat_level,
            key_players=key_players,
            budget_estimate=rival.budget,
            notes=notes,
        )

    def analyze_all_rivals(self, league: League) -> List[RivalReport]:
        reports = []
        for rival in league.rival_teams:
            report = self.analyze_rival(rival, league.my_team)
            reports.append(report)
        return sorted(reports, key=lambda r: (0 if r.threat_level == "HIGH" else 1 if r.threat_level == "MEDIUM" else 2))

    def league_summary(self, league: League) -> Dict:
        reports = self.analyze_all_rivals(league)
        return {
            "total_rivals": len(reports),
            "high_threats": sum(1 for r in reports if r.threat_level == "HIGH"),
            "medium_threats": sum(1 for r in reports if r.threat_level == "MEDIUM"),
            "low_threats": sum(1 for r in reports if r.threat_level == "LOW"),
            "reports": reports,
        }
