"""
Gestión de cartera/plantilla.
Evalúa la composición del equipo y sugiere mejoras de conjunto.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..laliga.models import Team, TeamPlayer, Player
from .player_scoring import PlayerScoring, ScoredPlayer
from .market_strategy import MarketOpportunity

logger = logging.getLogger(__name__)


@dataclass
class PortfolioReport:
    team: Team
    total_value: int
    budget_available: int
    avg_score: float
    weakest_players: List[Tuple[TeamPlayer, ScoredPlayer]]
    strongest_players: List[Tuple[TeamPlayer, ScoredPlayer]]
    positional_balance: Dict[str, int]
    upgrade_slots: List[str]       # posiciones que necesitan refuerzo
    sell_candidates: List[Tuple[TeamPlayer, ScoredPlayer]]
    summary: str


class Portfolio:
    """Analiza la plantilla propia y sugiere optimizaciones."""

    # Composición mínima deseable por posición
    IDEAL_COMPOSITION = {"GK": 1, "DEF": 4, "MID": 4, "FWD": 3}
    WEAK_SCORE_THRESHOLD = 0.35

    def __init__(self, scorer: Optional[PlayerScoring] = None):
        self.scorer = scorer or PlayerScoring()

    def analyze(self, team: Team) -> PortfolioReport:
        if not team.players:
            return self._empty_report(team)

        scored_pairs: List[Tuple[TeamPlayer, ScoredPlayer]] = [
            (tp, self.scorer.score_player(tp.player)) for tp in team.players
        ]

        sorted_by_score = sorted(scored_pairs, key=lambda x: x[1].composite, reverse=True)
        strongest = sorted_by_score[:3]
        weakest = sorted_by_score[-3:]

        total_value = sum(tp.player.market_value for tp, _ in scored_pairs)
        avg_score = sum(s.composite for _, s in scored_pairs) / len(scored_pairs)

        positional_balance: Dict[str, int] = {"GK": 0, "DEF": 0, "MID": 0, "FWD": 0}
        for tp, _ in scored_pairs:
            pos = tp.player.position
            if pos in positional_balance:
                positional_balance[pos] += 1

        upgrade_slots = [
            pos for pos, needed in self.IDEAL_COMPOSITION.items()
            if positional_balance.get(pos, 0) < needed
        ]

        sell_candidates = [
            (tp, s) for tp, s in scored_pairs
            if s.composite <= self.WEAK_SCORE_THRESHOLD or s.recommendation == "SELL"
        ]

        lines = [
            f"Valor total: {total_value/1e6:.1f}M€ | Presupuesto: {team.budget/1e6:.1f}M€",
            f"Score medio del equipo: {avg_score:.2f}",
        ]
        if upgrade_slots:
            lines.append(f"Posiciones que necesitan refuerzo: {', '.join(upgrade_slots)}")
        if sell_candidates:
            names = ", ".join(tp.player.name for tp, _ in sell_candidates[:3])
            lines.append(f"Candidatos a vender: {names}")

        return PortfolioReport(
            team=team,
            total_value=total_value,
            budget_available=team.budget,
            avg_score=round(avg_score, 4),
            weakest_players=weakest,
            strongest_players=strongest,
            positional_balance=positional_balance,
            upgrade_slots=upgrade_slots,
            sell_candidates=sell_candidates,
            summary="\n".join(lines),
        )

    def _empty_report(self, team: Team) -> PortfolioReport:
        return PortfolioReport(
            team=team, total_value=0, budget_available=team.budget,
            avg_score=0.0, weakest_players=[], strongest_players=[],
            positional_balance={}, upgrade_slots=list(self.IDEAL_COMPOSITION.keys()),
            sell_candidates=[], summary="Equipo vacío.",
        )
