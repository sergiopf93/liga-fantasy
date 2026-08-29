"""
Genera el informe diario de Fantasy LaLiga.
Incluye: rendimiento del equipo, mercado, cláusulas en riesgo y recomendaciones.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from ..laliga.client import LaLigaFantasyClient
from ..laliga.models import League, Market
from ..strategy.player_scoring import PlayerScoring
from ..strategy.market_strategy import MarketStrategy
from ..strategy.rival_analysis import RivalAnalysis
from ..strategy.clause_risk import ClauseRisk
from ..strategy.portfolio import Portfolio
from ..database.db import Database

logger = logging.getLogger(__name__)


@dataclass
class DailyReportData:
    generated_at: datetime
    league_id: str
    league_name: str
    matchday: int
    portfolio_summary: str
    top_market_opportunities: List[Dict]
    sell_suggestions: List[Dict]
    clause_risks: List[Dict]
    rival_threats: List[Dict]
    top_free_players: List[Dict]
    raw_text: str


class DailyReport:
    """Orquesta el análisis diario completo y genera un informe estructurado."""

    def __init__(self, client: LaLigaFantasyClient, db: Optional[Database] = None):
        self.client = client
        self.db = db or Database()
        self.scorer = PlayerScoring()
        self.rival_analyser = RivalAnalysis(self.scorer)
        self.clause_risk = ClauseRisk()
        self.portfolio = Portfolio(self.scorer)

    def generate(self, league_id: str) -> DailyReportData:
        logger.info("Generando informe diario para liga %s", league_id)

        # 1. Obtener datos
        league = self.client.get_league(league_id)
        market = self.client.get_market(league_id)
        all_players = self.client.get_all_players()

        # Guardar en DB
        self.db.upsert_players(all_players)
        self.db.save_market_snapshot(league_id, market)

        my_team = league.my_team
        budget = my_team.budget if my_team else 0

        # 2. Portfolio
        portfolio_report = self.portfolio.analyze(my_team) if my_team else None

        # 3. Mercado
        market_strategy = MarketStrategy(budget=budget, scorer=self.scorer)
        opportunities = market_strategy.find_opportunities(market, my_team)
        sell_suggestions = market_strategy.suggest_sales(my_team, market) if my_team else []

        # 4. Cláusulas en riesgo
        clause_risks = self.clause_risk.critical_players(league)

        # 5. Rivales
        rival_summary = self.rival_analyser.league_summary(league)

        # 6. Jugadores libres interesantes
        my_ids = {tp.player.id for tp in my_team.players} if my_team else set()
        free_players = [p for p in all_players if p.id not in my_ids and p.is_available]
        top_free = self.scorer.rank_players(free_players)[:10]

        # 7. Construir texto
        text = self._build_text(
            league, portfolio_report, opportunities[:5],
            sell_suggestions[:3], clause_risks, rival_summary, top_free[:5],
        )

        report_data = DailyReportData(
            generated_at=datetime.now(),
            league_id=league_id,
            league_name=league.name,
            matchday=league.matchday,
            portfolio_summary=portfolio_report.summary if portfolio_report else "",
            top_market_opportunities=[
                {
                    "player": o.market_player.player.name,
                    "position": o.market_player.player.position,
                    "price": o.market_player.sell_price,
                    "market_value": o.market_player.player.market_value,
                    "urgency": o.urgency,
                    "reason": o.reason,
                }
                for o in opportunities[:5]
            ],
            sell_suggestions=[
                {
                    "player": s["player"].name,
                    "buy_price": s["buy_price"],
                    "sell_price": s["sell_price"],
                    "profit": s["profit"],
                    "reason": s["reason"],
                }
                for s in sell_suggestions[:3]
            ],
            clause_risks=[
                {
                    "player": r.player.name,
                    "clause": r.clause_value,
                    "risk": r.risk_level,
                    "rivals_can_afford": r.rivals_can_afford,
                    "recommendation": r.recommendation,
                }
                for r in clause_risks
            ],
            rival_threats=[
                {
                    "team": rep.team.name,
                    "threat": rep.threat_level,
                    "key_players": [kp.player.name for kp in rep.key_players],
                }
                for rep in rival_summary["reports"] if rep.threat_level == "HIGH"
            ],
            top_free_players=[
                {
                    "player": s.player.name,
                    "position": s.player.position,
                    "team": s.player.team,
                    "score": s.composite,
                    "recommendation": s.recommendation,
                }
                for s in top_free[:5]
            ],
            raw_text=text,
        )

        self.db.save_report(league_id, "daily", text)
        logger.info("Informe diario generado correctamente.")
        return report_data

    def _build_text(self, league, portfolio, opps, sells, risks, rivals, top_free) -> str:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [
            f"# 📊 Informe Diario Liga Fantasy — {league.name}",
            f"**Jornada {league.matchday} | Generado: {now}**",
            "",
        ]

        if portfolio:
            lines += ["## 🏟 Tu Plantilla", portfolio.summary, ""]

        if opps:
            lines.append("## 💰 Oportunidades de Mercado")
            for o in opps:
                p = o.market_player.player
                lines.append(
                    f"- **[{o.urgency}]** {p.name} ({p.position}) "
                    f"— {o.market_player.sell_price:,}€ (val: {p.market_value:,}€) "
                    f"— {o.reason}"
                )
            lines.append("")

        if sells:
            lines.append("## 📤 Jugadores a Vender")
            for s in sells:
                profit_str = f"+{s['profit']:,}€" if s["profit"] >= 0 else f"{s['profit']:,}€"
                lines.append(f"- {s['player'].name} — {profit_str} — {s['reason']}")
            lines.append("")

        if risks:
            lines.append("## ⚠️ Riesgo de Cláusula")
            for r in risks:
                lines.append(
                    f"- **[{r.risk_level}]** {r.player.name} "
                    f"— Cláusula: {r.clause_value:,}€ "
                    f"— {r.rivals_can_afford} rival(es) pueden pagarla"
                )
            lines.append("")

        if top_free:
            lines.append("## 🌟 Jugadores Libres Recomendados")
            for s in top_free:
                lines.append(
                    f"- {s.player.name} ({s.player.position}, {s.player.team}) "
                    f"— Score: {s.composite:.2f} — {s.recommendation}"
                )
            lines.append("")

        rival_high = [r for r in rivals["reports"] if r.threat_level == "HIGH"]
        if rival_high:
            lines.append("## 🔴 Rivales Peligrosos")
            for r in rival_high:
                names = ", ".join(kp.player.name for kp in r.key_players[:2])
                lines.append(f"- {r.team.name} (Puntos: {r.team.points}) — Claves: {names}")
            lines.append("")

        return "\n".join(lines)
