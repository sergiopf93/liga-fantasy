"""
Generador del informe diario
Incluye tendencias históricas y diferenciación subasta/clausulazo
"""
import os, sys, json, logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.laliga import client
from backend.laliga.models import MyTeam, MarketPlayer, RivalTeam
from backend.strategy.player_scoring import (
    score_market_player, score_my_player_for_sale, build_trends
)
from backend.strategy.clause_risk import assess_clause_risk, analyze_goalkeeper_situation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOKEN    = os.environ.get("LALIGA_TOKEN", "")
TEAM_ID  = os.environ.get("TEAM_ID", "37889563")
LEAGUE_ID = os.environ.get("LEAGUE_ID", "017948446")
DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
os.makedirs(DATA_DIR, exist_ok=True)


def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Guardado: {filename}")


def fmt(v):
    if not v: return "N/D"
    return f"{v/1_000_000:.2f}M€"


def run():
    logger.info("Iniciando informe...")

    # ── Historial de precios (público, sin token) ────────────────────────
    trends = {}
    fixture_data = client.get_fixture_player_values()
    if fixture_data and isinstance(fixture_data, list):
        trends = build_trends(fixture_data)
        logger.info(f"Historial cargado: {len(trends)} jugadores")
    else:
        logger.warning("Sin historial de precios")

    # ── Mi equipo ────────────────────────────────────────────────────────
    my_team = None
    if TOKEN:
        team_data = client.get_my_team(TOKEN, TEAM_ID)
        money_data = client.get_my_money(TOKEN, TEAM_ID)
        if team_data:
            my_team = MyTeam.from_api(team_data, money_data)

    if my_team:
        save_json("team.json", {
            "team_id": my_team.team_id,
            "team_value": my_team.team_value,
            "team_value_fmt": fmt(my_team.team_value),
            "team_points": my_team.team_points,
            "budget": my_team.budget,
            "budget_fmt": fmt(my_team.budget) if my_team.budget else "N/D",
            "formation": my_team.formation,
            "updated_at": my_team.updated_at,
            "players": [{
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
                "trend": _trend_dict(trends.get(p.id)),
            } for p in my_team.players],
        })
    else:
        # Mantener datos anteriores si existen
        team_path = os.path.join(DATA_DIR, "team.json")
        if not os.path.exists(team_path):
            save_json("team.json", {"error": "Sin token válido", "updated_at": datetime.now().isoformat()})

    # ── Mercado ──────────────────────────────────────────────────────────
    market_players = []
    if TOKEN:
        market_data = client.get_league_market(TOKEN, LEAGUE_ID)
        if market_data and isinstance(market_data, list):
            for entry in market_data:
                try:
                    mp = MarketPlayer.from_api(entry)
                    # Detectar tipo: clausulazo si salePrice == buyoutClause
                    sale = entry.get("salePrice", 0)
                    clause = entry.get("playerTeam", {}).get("buyoutClause", 0)
                    direct = entry.get("directOffer", False)
                    mp.direct_offer = direct or (clause > 0 and sale >= clause * 0.99)
                    market_players.append(mp)
                except Exception as e:
                    logger.warning(f"Error mercado: {e}")

    budget = my_team.budget if my_team else 0
    market_json_players = []
    for mp in market_players:
        t = trends.get(mp.player.id)
        s = score_market_player(mp, budget, t)
        is_clause = getattr(mp, 'direct_offer', False)
        market_json_players.append({
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
            "buyout_clause_fmt": fmt(mp.buyout_clause),
            "score": s.score,
            "reasons": s.reasons,
            "recommended_bid": s.recommended_bid,
            "recommended_bid_fmt": fmt(s.recommended_bid),
            "max_bid": s.max_bid,
            "max_bid_fmt": fmt(s.max_bid),
            "market_type": s.market_type,        # "subasta" o "clausulazo"
            "strategy_note": s.strategy_note,
            "seller": mp.seller_manager,
            "seller_team_id": mp.seller_team_id,
            "expiration": mp.expiration_date,
            "status": mp.player.status,
            "average_points": round(mp.player.average_points, 2),
            "week_points": mp.player.week_points,
            "image_url": mp.player.image_url,
            "is_shielded": mp.is_shielded,
            "offers": mp.number_of_offers,
            "trend": _trend_dict(t),
        })

    market_json_players.sort(key=lambda x: x["score"], reverse=True)
    save_json("market.json", {
        "updated_at": datetime.now().isoformat(),
        "count": len(market_json_players),
        "subastas": [p for p in market_json_players if p["market_type"] == "subasta"],
        "clausulazos": [p for p in market_json_players if p["market_type"] == "clausulazo"],
        "players": market_json_players,
    })

    # ── Rivales ──────────────────────────────────────────────────────────
    rivals = []
    if TOKEN:
        standing = client.get_league_standing(TOKEN, LEAGUE_ID)
        if standing and isinstance(standing, list):
            for entry in standing:
                try:
                    r = RivalTeam.from_standing(entry)
                    if r.team_id != TEAM_ID:
                        rivals.append(r)
                except Exception as e:
                    logger.warning(f"Error rival: {e}")

    save_json("rivals.json", {
        "updated_at": datetime.now().isoformat(),
        "rivals": [{
            "team_id": r.team_id,
            "manager": r.manager_name,
            "team_value": r.team_value,
            "team_value_fmt": fmt(r.team_value),
            "points": r.team_points,
            "budget_fmt": "N/D",
        } for r in sorted(rivals, key=lambda x: x.team_points, reverse=True)],
    })

    # ── Clausulazos ──────────────────────────────────────────────────────
    clause_risks = []
    gk_analysis = {}
    if my_team:
        my_gks = [p for p in my_team.players if p.position_id == 1]
        gk_analysis = analyze_goalkeeper_situation(my_team.players, market_players)
        for p in my_team.players:
            cr = assess_clause_risk(p, rivals, my_gks)
            clause_risks.append(cr)
        clause_risks.sort(key=lambda x: x.risk_score, reverse=True)

    # ── Ventas ───────────────────────────────────────────────────────────
    sell_recs = []
    if my_team:
        for p in my_team.players:
            r = score_my_player_for_sale(p)
            if r["should_sell"]:
                sell_recs.append(r)
        sell_recs.sort(key=lambda x: x["sell_score"], reverse=True)

    # ── Top compras (subastas primero, luego clausulazos) ─────────────────
    top_buys = []
    if market_players:
        all_scored = []
        for mp in market_players:
            t = trends.get(mp.player.id)
            s = score_market_player(mp, budget, t)
            all_scored.append((mp, s))
        affordable = [(mp, s) for mp, s in all_scored
                      if mp.sale_price <= budget * 0.8 or budget == 0]
        affordable.sort(key=lambda x: x[1].score, reverse=True)
        top_buys = affordable[:5]

    # ── Informe ───────────────────────────────────────────────────────────
    save_json("report.json", {
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
        "top_buys": [{
            "name": mp.player.name,
            "nickname": mp.player.nickname,
            "position": mp.player.position,
            "sale_price_fmt": fmt(mp.sale_price),
            "market_value_fmt": fmt(mp.player.market_value),
            "score": s.score,
            "recommended_bid_fmt": fmt(s.recommended_bid),
            "max_bid_fmt": fmt(s.max_bid),
            "market_type": s.market_type,
            "strategy_note": s.strategy_note,
            "reasons": s.reasons,
            "status": mp.player.status,
            "average_points": round(mp.player.average_points, 2),
            "trend": _trend_dict(trends.get(mp.player.id)),
        } for mp, s in top_buys],
        "sell_recommendations": [{
            "name": r["player"].name,
            "nickname": r["player"].nickname,
            "position": r["player"].position,
            "market_value_fmt": fmt(r["player"].market_value),
            "sell_score": r["sell_score"],
            "reasons": r["reasons"],
        } for r in sell_recs[:3]],
        "clause_risks": [{
            "name": cr.player.name,
            "nickname": cr.player.nickname,
            "position": cr.player.position,
            "risk_level": cr.risk_level,
            "risk_score": cr.risk_score,
            "buyout_clause_fmt": fmt(cr.player.buyout_clause),
            "reasons": cr.reasons,
            "recommendation": cr.recommendation,
        } for cr in clause_risks[:5]],
        "goalkeeper": gk_analysis.get("recommendation", ""),
    })

    logger.info("Informe completado")


def _trend_dict(t):
    if not t:
        return None
    return {
        "max_value": t.max_value,
        "max_value_fmt": f"{t.max_value/1_000_000:.2f}M€",
        "min_value": t.min_value,
        "recent_trend": t.recent_trend,
        "trend_pct": t.trend_pct,
        "recovery_potential": t.recovery_potential,
        "potential_label": t.potential_label,
    }


if __name__ == "__main__":
    run()
