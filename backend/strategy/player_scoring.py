"""
Motor de puntuación de jugadores 0-100
Cada recomendación incluye explicación detallada del por qué
"""
import yaml
import os
from dataclasses import dataclass
from typing import List
from backend.laliga.models import Player, MarketPlayer

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "../../config/config.yaml")


def load_weights() -> dict:
    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f)
            return cfg.get("strategy_weights", {})
    except Exception:
        return {
            "revalorizacion": 0.35,
            "rendimiento": 0.25,
            "oportunidad": 0.20,
            "situacion": 0.15,
            "riesgo": 0.30,
            "precio_excesivo": 0.20,
        }


@dataclass
class PlayerScore:
    player: Player
    score: float            # 0-100
    reasons: List[str]
    max_bid: int
    recommended_bid: int
    value_ratio: float      # marketValue / salePrice
    trend: str              # "subiendo", "estable", "bajando"


def score_market_player(mp: MarketPlayer, my_budget: int = 0) -> PlayerScore:
    """
    Puntúa un jugador del mercado de 0 a 100 con explicación completa.
    """
    w = load_weights()
    p = mp.player
    reasons = []
    sale = mp.sale_price
    market_val = p.market_value
    clause = mp.buyout_clause

    # ── 1. Potencial de revalorización (0-100) ──────────────────────────
    if sale > 0 and market_val > 0:
        value_ratio = market_val / sale
    else:
        value_ratio = 1.0

    if value_ratio >= 1.15:
        rev_score = 90
        reasons.append(f"Precio {_fmt(sale)} muy por debajo del valor de mercado {_fmt(market_val)} (+{(value_ratio-1)*100:.1f}%)")
    elif value_ratio >= 1.05:
        rev_score = 65
        reasons.append(f"Precio ligeramente inferior al valor de mercado ({(value_ratio-1)*100:.1f}% de margen)")
    elif value_ratio >= 0.97:
        rev_score = 40
        reasons.append(f"Precio en línea con el valor de mercado")
    else:
        rev_score = 15
        reasons.append(f"Precio superior al valor de mercado — sobrevalorado")

    # ── 2. Rendimiento deportivo (0-100) ────────────────────────────────
    avg = p.average_points
    week = p.week_points

    if avg >= 6:
        rend_score = 90
        reasons.append(f"Rendimiento excelente: {avg:.1f} pts/jornada de media")
    elif avg >= 4:
        rend_score = 70
        reasons.append(f"Buen rendimiento: {avg:.1f} pts/jornada de media")
    elif avg >= 2.5:
        rend_score = 45
        reasons.append(f"Rendimiento moderado: {avg:.1f} pts/jornada")
    else:
        rend_score = 20
        reasons.append(f"Bajo rendimiento: {avg:.1f} pts/jornada")

    if week >= 10:
        rend_score = min(100, rend_score + 15)
        reasons.append(f"Excelente última jornada: {week} pts")
    elif week >= 6:
        rend_score = min(100, rend_score + 8)
        reasons.append(f"Buena última jornada: {week} pts")

    # ── 3. Oportunidad de mercado (0-100) ────────────────────────────────
    opor_score = 50
    if mp.number_of_offers == 0:
        opor_score += 20
        reasons.append("Sin ofertas activas — oportunidad de comprar sin competencia")
    else:
        opor_score -= 10
        reasons.append(f"{mp.number_of_offers} ofertas activas — hay competencia")

    if mp.is_shielded:
        opor_score -= 30
        reasons.append("Jugador blindado — cláusula más cara")

    # ── 4. Situación deportiva (0-100) ──────────────────────────────────
    if p.status == "ok":
        sit_score = 80
    elif p.status == "doubtful":
        sit_score = 40
        reasons.append("Estado dudoso para próxima jornada")
    elif p.status == "injured":
        sit_score = 10
        reasons.append("LESIONADO — riesgo alto")
    elif p.status == "out_of_league":
        sit_score = 0
        reasons.append("FUERA DE LA LIGA — no puntúa")
    else:
        sit_score = 50

    # ── 5. Riesgo (penalización) ─────────────────────────────────────────
    riesgo = 0
    if p.status in ("injured", "out_of_league"):
        riesgo += 60
    if sale > my_budget * 0.5 and my_budget > 0:
        riesgo += 20
        reasons.append("Precio alto en relación al presupuesto disponible")
    if p.position_id == 1 and avg < 3:
        riesgo += 15
        reasons.append("Portero con bajo rendimiento")

    # ── Score final ──────────────────────────────────────────────────────
    score = (
        rev_score * w.get("revalorizacion", 0.35)
        + rend_score * w.get("rendimiento", 0.25)
        + opor_score * w.get("oportunidad", 0.20)
        + sit_score * w.get("situacion", 0.15)
        - riesgo * w.get("riesgo", 0.30)
    )
    score = max(0, min(100, score))

    # ── Puja recomendada ─────────────────────────────────────────────────
    if value_ratio >= 1.1:
        recommended_bid = int(sale * 1.05)
        max_bid = int(market_val * 0.95)
    elif value_ratio >= 1.0:
        recommended_bid = int(sale * 1.02)
        max_bid = int(market_val * 0.90)
    else:
        recommended_bid = int(sale * 0.98)
        max_bid = int(sale * 1.05)

    trend = "subiendo" if value_ratio > 1.05 else ("bajando" if value_ratio < 0.95 else "estable")

    return PlayerScore(
        player=p,
        score=round(score, 1),
        reasons=reasons,
        max_bid=max_bid,
        recommended_bid=recommended_bid,
        value_ratio=round(value_ratio, 3),
        trend=trend,
    )


def score_my_player_for_sale(p: Player) -> dict:
    """
    Evalúa si conviene vender un jugador de mi plantilla.
    Retorna dict con score_venta (0-100) y razones.
    """
    reasons = []
    score = 0

    if p.average_points < 2:
        score += 40
        reasons.append(f"Bajo rendimiento: {p.average_points:.1f} pts/jornada")
    if p.status == "injured":
        score += 35
        reasons.append("Lesionado — ocupando plaza sin puntuar")
    if p.status == "out_of_league":
        score += 50
        reasons.append("Fuera de la liga — no puntúa")
    if p.week_points <= 0 and p.average_points < 3:
        score += 15
        reasons.append(f"Sin puntuar última jornada con media baja")

    return {
        "player": p,
        "sell_score": min(100, score),
        "reasons": reasons,
        "should_sell": score >= 40,
    }


def _fmt(value: int) -> str:
    return f"{value/1_000_000:.2f}M€"
