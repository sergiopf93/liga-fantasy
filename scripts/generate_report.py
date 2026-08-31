"""
Generador del informe diario de las 20:00
Conecta con la API, analiza y guarda JSON para el dashboard
"""
import os
import sys
import json
import logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.laliga import client
from backend.laliga.models import MyTeam, MarketPlayer, RivalTeam
from backend.strategy.player_scoring import score_market_player, score_my_player_for_sale
from backend.strategy.clause_risk import assess_clause_risk, analyze_goalkeeper_situation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("LALIGA_TOKEN", "")
TEAM_ID = os.environ.get("TEAM_ID", "37889563")
LEAGUE_ID = os.environ.get("LEAGUE_ID", "017948446")
DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")

os.makedirs(DATA_DIR, exist_ok=True)


def save_json(filename: str, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Guardado: {filename}")


def fmt(v: int) -> str:
    return f"{v/1_000_000:.2f}M€"


def run():
    logger.info("Iniciando generación de informe...")

    if not TOKEN:
        logger.error("LALIGA_TOKEN no configurado. Ejecutando en modo degradado (solo datos públicos).")

    # ── Mi equipo ────────────────────────────────────────────────────────
    team_data = None
    money_data = None
    my_team = None

    if TOKEN:
        team_data = client.get_my_team(TOKEN, TEAM_ID)
        money_data = client.get_my_money(TOKEN, TEAM_ID)

    if team_data:
        my_team = MyTeam.from_api(team_data, money_data)
        team_json = {
            "team_id": my_team.team_id,
            "team_value": my_team.team_value,
            "team_value_fmt": fmt(my_team.team_value),
            "team_points": my_team.team_points,
            "budget": my_team.budget,
            "budget_fmt": fmt(my_team.budget) if my_team.budget else "N/D",
            "formation": my_team.formation,
            "updated_at": my_team.updated_at,
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "nickname": p.nickname,
                    "position": p.position,
                    "position_id": p.position_id,
                    "market_value": p.market_value,
                    "market_value_fmt": fmt(p.market_value),
                    "buyout_clause": p.buyout_clause,
                    "buyout_clause_fmt": fmt(p.buyout_clause),
                    "points": p.points,
                    "week_points": p.week_points,
                    "average_points": round(p.average_points, 2),
                    "status": p.status,
                    "image_url": p.image_url,
                }
                for p in my_team.players
            ],
        }
        save_json("team.json", team_json)
    else:
        logger.warning("No se pudo obtener datos del equipo")
        save_json("team.json", {"error": "Sin datos", "updated_at": datetime.now().isoformat()})

    # ── Mercado ──────────────────────────────────────────────────────────
    market_data = None
    market_players = []

    if TOKEN:
        market_data = client.get_league_market(TOKEN, LEAGUE_ID)

    if market_data and isinstance(market_data, list):
        for entry in market_data:
            try:
                mp = MarketPlayer.from_api(entry)
                market_players.append(mp)
            except Exception as e:
                logger.warning(f"Error parseando jugador de mercado: {e}")

        budget = my_team.budget if my_team else 0
        scored = [score_market_player(mp, budget) for mp in market_players]
        scored.sort(key=lambda x: x.score, reverse=True)

        market_json = {
            "updated_at": datetime.now().isoformat(),
            "count": len(scored),
            "players": [
                {
                    "market_id": mp.market_id,
                    "player_id": s.player.id,
                    "name": s.player.name,
                    "nickname": s.player.nickname,
                    "position": s.player.position,
                    "position_id": s.player.position_id,
                    "sale_price": mp.sale_price,
                    "sale_price_fmt": fmt(mp.sale_price),
                    "market_value": s.player.market_value,
                    "market_value_fmt": fmt(s.player.market_value),
                    "buyout_clause": mp.buyout_clause,
                    "score": s.score,
                    "reasons": s.reasons,
                    "recommended_bid": s.recommended_bid,
                    "recommended_bid_fmt": fmt(s.recommended_bid),
                    "max_bid": s.max_bid,
                    "max_bid_fmt": fmt(s.max_bid),
                    "trend": s.trend,
                    "value_ratio": s.value_ratio,
                    "seller": mp.seller_manager,
                    "expiration": mp.expiration_date,
                    "status": s.player.status,
                    "average_points": round(s.player.average_points, 2),
                    "week_points": s.player.week_points,
                    "image_url": s.player.image_url,
                    "is_shielded": mp.is_shielded,
                    "offers": mp.number_of_offers,
                }
                for s, mp in zip(scored, [score_market_player(m, budget) and m for m in market_players])
            ],
        }

        # Reconstruir correctamente
        market_json["players"] = []
        for mp in market_players:
            s = score_market_player(mp, budget)
            market_json["players"].append({
                "market_id": mp.market_id,
                "player_id": mp.player.id,
                "name": mp.player.name,
                "nickname": mp.player.nickname,
                "position": mp.player.position,
                "position_id": mp.player.position_id,
                "sale_price": mp.sale_price,
                "sale_price_fmt": fmt(mp.sale_price),
                "market_value": mp.player.market_value,
                "market_value_fmt": fmt(mp.player.market_value),
                "buyout_clause": mp.buyout_clause,
                "score": s.score,
                "reasons": s.reasons,
                "recommended_bid": s.recommended_bid,
                "recommended_bid_fmt": fmt(s.recommended_bid),
                "max_bid": s.max_bid,
                "max_bid_fmt": fmt(s.max_bid),
                "trend": s.trend,
                "value_ratio": s.value_ratio,
                "seller": mp.seller_manager,
                "expiration": mp.expiration_date,
                "status": mp.player.status,
                "average_points": round(mp.player.average_points, 2),
                "week_points": mp.player.week_points,
                "image_url": mp.player.image_url,
                "is_shielded": mp.is_shielded,
                "offers": mp.number_of_offers,
            })
        market_json["players"].sort(key=lambda x: x["score"], reverse=True)
        save_json("market.json", market_json)
    else:
        logger.warning("No se pudo obtener mercado")
        save_json("market.json", {"error": "Sin datos", "updated_at": datetime.now().isoformat()})

    # ── Rivales ──────────────────────────────────────────────────────────
    rivals = []
    if TOKEN:
        standing_data = client.get_league_standing(TOKEN, LEAGUE_ID)
        if standing_data and isinstance(standing_data, list):
            for entry in standing_data:
                try:
                    r = RivalTeam.from_standing(entry)
                    if r.team_id != TEAM_ID:
                        rivals.append(r)
                except Exception as e:
                    logger.warning(f"Error parseando rival: {e}")

    rivals_json = {
        "updated_at": datetime.now().isoformat(),
        "rivals": [
            {
                "team_id": r.team_id,
                "manager": r.manager_name,
                "team_value": r.team_value,
                "team_value_fmt": fmt(r.team_value),
                "points": r.team_points,
                "budget": r.budget,
                "budget_fmt": fmt(r.budget) if r.budget else "N/D",
            }
            for r in sorted(rivals, key=lambda x: x.team_points, reverse=True)
        ],
    }
    save_json("rivals.json", rivals_json)

    # ── Análisis de clausulazos ──────────────────────────────────────────
    clause_risks = []
    gk_analysis = {}

    if my_team:
        my_goalkeepers = [p for p in my_team.players if p.position_id == 1]
        gk_analysis = analyze_goalkeeper_situation(my_team.players, market_players)

        for p in my_team.players:
            cr = assess_clause_risk(p, rivals, my_goalkeepers)
            clause_risks.append(cr)

        clause_risks.sort(key=lambda x: x.risk_score, reverse=True)

    # ── Ventas recomendadas ──────────────────────────────────────────────
    sell_recs = []
    if my_team:
        for p in my_team.players:
            result = score_my_player_for_sale(p)
            if result["should_sell"]:
                sell_recs.append(result)
        sell_recs.sort(key=lambda x: x["sell_score"], reverse=True)

    # ── Informe completo ─────────────────────────────────────────────────
    top_buys = []
    if market_players:
        budget = my_team.budget if my_team else 0
        all_scored = [(mp, score_market_player(mp, budget)) for mp in market_players]
        affordable = [(mp, s) for mp, s in all_scored if mp.sale_price <= budget * 0.8 or budget == 0]
        affordable.sort(key=lambda x: x[1].score, reverse=True)
        top_buys = affordable[:5]

    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "team_value": my_team.team_value if my_team else 0,
            "team_value_fmt": fmt(my_team.team_value) if my_team else "N/D",
            "budget": my_team.budget if my_team else 0,
            "budget_fmt": fmt(my_team.budget) if my_team and my_team.budget else "N/D",
            "points": my_team.team_points if my_team else 0,
            "goalkeeper_risk": gk_analysis.get("risk", "N/D"),
            "goalkeeper_count": gk_analysis.get("count", 0),
            "goalkeeper_recommendation": gk_analysis.get("recommendation", ""),
        },
        "top_buys": [
            {
                "name": mp.player.name,
                "nickname": mp.player.nickname,
                "position": mp.player.position,
                "sale_price_fmt": fmt(mp.sale_price),
                "market_value_fmt": fmt(mp.player.market_value),
                "score": s.score,
                "recommended_bid_fmt": fmt(s.recommended_bid),
                "max_bid_fmt": fmt(s.max_bid),
                "reasons": s.reasons,
                "status": mp.player.status,
                "average_points": round(mp.player.average_points, 2),
                "image_url": mp.player.image_url,
            }
            for mp, s in top_buys
        ],
        "sell_recommendations": [
            {
                "name": r["player"].name,
                "nickname": r["player"].nickname,
                "position": r["player"].position,
                "market_value_fmt": fmt(r["player"].market_value),
                "sell_score": r["sell_score"],
                "reasons": r["reasons"],
            }
            for r in sell_recs[:3]
        ],
        "clause_risks": [
            {
                "name": cr.player.name,
                "nickname": cr.player.nickname,
                "position": cr.player.position,
                "risk_level": cr.risk_level,
                "risk_score": cr.risk_score,
                "buyout_clause_fmt": fmt(cr.player.buyout_clause),
                "reasons": cr.reasons,
                "recommendation": cr.recommendation,
            }
            for cr in clause_risks[:5]
        ],
        "goalkeeper": gk_analysis.get("recommendation", ""),
    }

    save_json("report.json", report)
    logger.info("Informe generado correctamente")
    return report


if __name__ == "__main__":
    run()
