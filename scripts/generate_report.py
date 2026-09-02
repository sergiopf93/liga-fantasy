"""
Generador del informe diario
Lógica correcta: subasta = salePrice < buyoutClause, clausulazo = salePrice ~ buyoutClause
"""
import os, sys, json, logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.laliga import client
from backend.laliga.models import MyTeam, MarketPlayer, RivalTeam
from backend.strategy.player_scoring import score_market_player, score_my_player_for_sale, build_trends
from backend.strategy.clause_risk import assess_clause_risk, analyze_goalkeeper_situation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOKEN     = os.environ.get("LALIGA_TOKEN", "")
TEAM_ID   = os.environ.get("TEAM_ID", "37889563")
LEAGUE_ID = os.environ.get("LEAGUE_ID", "017948446")
DATA_DIR  = os.path.join(os.path.dirname(__file__), "../data")
os.makedirs(DATA_DIR, exist_ok=True)


def save_json(filename, data):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Guardado: {filename}")


def fmt(v):
    if not v: return "N/D"
    return f"{v/1_000_000:.2f}M€"


def is_clausulazo(entry: dict) -> bool:
    """
    Clausulazo real: salePrice == buyoutClause (el rival pone precio de cláusula exacto).
    Subasta: salePrice claramente menor que buyoutClause (el rival pone precio libre).
    """
    sale   = entry.get("salePrice", 0)
    clause = entry.get("playerTeam", {}).get("buyoutClause", 0)
    if clause == 0:
        return False
    ratio = sale / clause
    return ratio >= 0.98   # 98% o más = clausulazo


def _trend_dict(t):
    if not t: return None
    return {
        "max_value": t.max_value,
        "max_value_fmt": fmt(t.max_value),
        "min_value": t.min_value,
        "recent_trend": t.recent_trend,
        "trend_pct": t.trend_pct,
        "recovery_potential": t.recovery_potential,
        "potential_label": t.potential_label,
    }


def run():
    logger.info("Iniciando informe...")

    # ── Historial de precios (público) ────────────────────────────────────
    trends = {}
    fixture_data = client.get_fixture_player_values()
    if fixture_data and isinstance(fixture_data, list):
        trends = build_trends(fixture_data)
        logger.info(f"Historial: {len(trends)} jugadores")

    # ── Mi equipo ─────────────────────────────────────────────────────────
    my_team = None
    if TOKEN:
        team_data  = client.get_my_team(TOKEN, TEAM_ID)
        money_data = client.get_my_money(TOKEN, TEAM_ID)
        if team_data:
            my_team = MyTeam.from_api(team_data, money_data)
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
            logger.warning("No se pudo obtener mi equipo")
    else:
        logger.warning("Sin token — modo degradado")

    # ── Mercado ───────────────────────────────────────────────────────────
    subastas    = []
    clausulazos = []
    all_market  = []

    if TOKEN:
        market_raw = client.get_league_market(TOKEN, LEAGUE_ID)
        if market_raw and isinstance(market_raw, list):
            budget = my_team.budget if my_team else 0
            for entry in market_raw:
                try:
                    mp = MarketPlayer.from_api(entry)
                    t  = trends.get(mp.player.id)
                    s  = score_market_player(mp, budget, t)
                    tipo = "clausulazo" if is_clausulazo(entry) else "subasta"

                    item = {
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
                        "market_type": tipo,
                        "strategy_note": (
                            f"CLAUSULAZO — Precio fijo {fmt(mp.sale_price)}. Pagas al rival directamente."
                            if tipo == "clausulazo" else
                            f"SUBASTA — Precio salida {fmt(mp.sale_price)}. Puja sin superar {fmt(s.max_bid)}."
                        ),
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
                    }
                    all_market.append(item)
                    if tipo == "clausulazo":
                        clausulazos.append(item)
                    else:
                        subastas.append(item)
                except Exception as e:
                    logger.warning(f"Error mercado: {e}")

    # Ordenar por score
    for lst in [all_market, subastas, clausulazos]:
        lst.sort(key=lambda x: x["score"], reverse=True)

    save_json("market.json", {
        "updated_at": datetime.now().isoformat(),
        "count": len(all_market),
        "subastas": subastas,
        "clausulazos": clausulazos,
        "players": all_market,
    })

    # ── Rivales (clasificación) ───────────────────────────────────────────
    rivals_out = []
    if TOKEN:
        standing = client.get_league_standing(TOKEN, LEAGUE_ID)
        logger.info(f"Standing raw type: {type(standing)}, value: {str(standing)[:300]}")
        if standing:
            # Puede ser lista directa o dict con lista dentro
            rows = standing if isinstance(standing, list) else standing.get("teams", standing.get("data", []))
            for entry in rows:
                try:
                    team = entry.get("team", entry)
                    manager = team.get("manager", {})
                    manager_name = manager.get("managerName", "") if isinstance(manager, dict) else ""
                    tid = str(team.get("id", ""))
                    if tid == TEAM_ID:
                        continue
                    rivals_out.append({
                        "team_id": tid,
                        "manager": manager_name,
                        "team_value": team.get("teamValue", 0),
                        "team_value_fmt": fmt(team.get("teamValue", 0)),
                        "points": team.get("teamPoints", entry.get("points", 0)),
                        "budget_fmt": "N/D",
                    })
                except Exception as e:
                    logger.warning(f"Error rival: {e}")
            rivals_out.sort(key=lambda x: x["points"], reverse=True)

    save_json("rivals.json", {
        "updated_at": datetime.now().isoformat(),
        "rivals": rivals_out,
    })

    # ── Clausulazos en mi plantilla ───────────────────────────────────────
    clause_risks = []
    gk_analysis  = {}
    rivals_obj   = []  # para assess_clause_risk necesitamos objetos RivalTeam
    if my_team:
        my_gks = [p for p in my_team.players if p.position_id == 1]
        gk_analysis = analyze_goalkeeper_situation(my_team.players)
        for p in my_team.players:
            cr = assess_clause_risk(p, rivals_obj, my_gks)
            clause_risks.append(cr)
        clause_risks.sort(key=lambda x: x.risk_score, reverse=True)

    # ── Ventas recomendadas ────────────────────────────────────────────────
    sell_recs = []
    if my_team:
        for p in my_team.players:
            r = score_my_player_for_sale(p)
            if r["should_sell"]:
                sell_recs.append(r)
        sell_recs.sort(key=lambda x: x["sell_score"], reverse=True)

    # ── Top compras (subastas primero) ────────────────────────────────────
    budget = my_team.budget if my_team else 0
    top_buys = [
        p for p in all_market
        if p["score"] >= 50 and (p["sale_price"] <= budget * 0.8 or budget == 0)
    ][:5]

    # ── Informe final ─────────────────────────────────────────────────────
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
            "name": p["name"],
            "nickname": p["nickname"],
            "position": p["position"],
            "sale_price_fmt": p["sale_price_fmt"],
            "market_value_fmt": p["market_value_fmt"],
            "score": p["score"],
            "recommended_bid_fmt": p["recommended_bid_fmt"],
            "max_bid_fmt": p["max_bid_fmt"],
            "market_type": p["market_type"],
            "strategy_note": p["strategy_note"],
            "reasons": p["reasons"],
            "status": p["status"],
            "average_points": p["average_points"],
            "trend": p["trend"],
        } for p in top_buys],
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


if __name__ == "__main__":
    run()
