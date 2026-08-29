"""
Estrategia de mercado: identifica oportunidades de compra/venta.
Compara precios de mercado con valores reales y tendencias.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ..laliga.models import Market, MarketPlayer, Player, Team
from .player_scoring import PlayerScoring, ScoredPlayer

logger = logging.getLogger(__name__)


@dataclass
class MarketOpportunity:
    market_player: MarketPlayer
    scored: ScoredPlayer
    price_ratio: float       # sell_price / market_value  (<1 = ganga)
    urgency: str             # "HIGH" | "MEDIUM" | "LOW"
    reason: str


class MarketStrategy:
    """
    Analiza el mercado y genera recomendaciones de compra.

    Criterios de compra:
    - Precio de venta < valor de cláusula  → ahorro garantizado
    - Precio de venta < valor de mercado  → precio por debajo del valor
    - Score compuesto del jugador > umbral → buen rendimiento
    """

    BARGAIN_RATIO = 0.85    # precio < 85% del valor de mercado → oportunidad
    GOOD_DEAL_RATIO = 0.95  # precio < 95% del valor de mercado → buen precio

    def __init__(self, budget: int = 0, scorer: Optional[PlayerScoring] = None):
        self.budget = budget
        self.scorer = scorer or PlayerScoring()

    # ------------------------------------------------------------------ #
    # API pública                                                          #
    # ------------------------------------------------------------------ #

    def find_opportunities(
        self,
        market: Market,
        my_team: Optional[Team] = None,
    ) -> List[MarketOpportunity]:
        """Devuelve lista de oportunidades ordenadas por urgencia y ratio de precio."""
        my_player_ids = set()
        if my_team:
            my_player_ids = {tp.player.id for tp in my_team.players}

        opportunities: List[MarketOpportunity] = []
        for mp in market.players:
            if mp.player.id in my_player_ids:
                continue  # ya lo tengo
            if self.budget > 0 and mp.sell_price > self.budget:
                continue  # sin presupuesto

            opp = self._evaluate(mp)
            if opp:
                opportunities.append(opp)

        # Ordenar: primero los HIGH, luego por ratio de precio
        return sorted(
            opportunities,
            key=lambda o: (0 if o.urgency == "HIGH" else 1 if o.urgency == "MEDIUM" else 2, o.price_ratio),
        )

    def suggest_sales(self, my_team: Team, market: Market) -> List[Dict]:
        """Sugiere jugadores de mi equipo que debería vender."""
        suggestions = []
        market_prices = {mp.player.id: mp.sell_price for mp in market.players}

        for tp in my_team.players:
            p = tp.player
            scored = self.scorer.score_player(p)

            if scored.recommendation == "SELL":
                market_price = market_prices.get(p.id, p.clause_value)
                profit = market_price - tp.buy_price
                suggestions.append({
                    "player": p,
                    "scored": scored,
                    "buy_price": tp.buy_price,
                    "sell_price": market_price,
                    "profit": profit,
                    "reason": f"Score bajo ({scored.composite:.2f}). " + "; ".join(scored.notes),
                })

        return sorted(suggestions, key=lambda s: s["scored"].composite)

    # ------------------------------------------------------------------ #
    # Evaluación interna                                                   #
    # ------------------------------------------------------------------ #

    def _evaluate(self, mp: MarketPlayer) -> Optional[MarketOpportunity]:
        player = mp.player
        scored = self.scorer.score_player(player)

        if player.market_value == 0:
            return None

        price_ratio = mp.sell_price / player.market_value

        reasons = []

        if mp.is_bargain:
            reasons.append(f"Precio ({mp.sell_price:,}€) < cláusula ({player.clause_value:,}€)")

        if price_ratio <= self.BARGAIN_RATIO:
            reasons.append(f"Precio {(1-price_ratio)*100:.0f}% por debajo del valor de mercado")

        if scored.recommendation == "BUY":
            reasons.append(f"Jugador en buena forma (score {scored.composite:.2f})")

        if not reasons:
            return None

        # Determinar urgencia
        if price_ratio <= self.BARGAIN_RATIO and scored.composite >= 0.55:
            urgency = "HIGH"
        elif price_ratio <= self.GOOD_DEAL_RATIO or scored.recommendation == "BUY":
            urgency = "MEDIUM"
        else:
            urgency = "LOW"

        return MarketOpportunity(
            market_player=mp,
            scored=scored,
            price_ratio=round(price_ratio, 3),
            urgency=urgency,
            reason=" | ".join(reasons),
        )
