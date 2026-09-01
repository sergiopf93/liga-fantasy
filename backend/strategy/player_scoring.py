"""
Motor de puntuación de jugadores 0-100
Incluye análisis de tendencia histórica y diferenciación de tipo de mercado
"""
import yaml
import os
from dataclasses import dataclass
from typing import List, Dict, Optional
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
            "tendencia": 0.25,
            "riesgo": 0.30,
        }


@dataclass
class PlayerTrend:
    player_id: str
    current_value: int
    max_value: int
    min_value: int
    values_history: List[int]       # ordenado de más antiguo a más reciente
    recent_trend: str               # "subiendo", "bajando", "estable"
    trend_pct: float                # % cambio últimas 3 jornadas
    recovery_potential: float       # (max - current) / current * 100
    potential_label: str            # "ALTO", "MEDIO", "BAJO"


@dataclass
class PlayerScore:
    player: Player
    score: float
    reasons: List[str]
    max_bid: int
    recommended_bid: int
    value_ratio: float
    trend: Optional[PlayerTrend]
    market_type: str                # "subasta" o "clausulazo"
    strategy_note: str              # nota de estrategia específica


def build_trends(fixture_values: List[dict]) -> Dict[str, PlayerTrend]:
    """
    Construye un diccionario playerId -> PlayerTrend
    a partir del endpoint /classic/v1/competition/1/fixture-player-values
    """
    # Agrupar por playerId
    by_player: Dict[str, List[dict]] = {}
    for entry in fixture_values:
        pid = str(entry.get("playerId", ""))
        if pid not in by_player:
            by_player[pid] = []
        by_player[pid].append(entry)

    trends = {}
    for pid, entries in by_player.items():
        # Ordenar por fixtureId (formato "2627-04" → ordenable como string)
        entries.sort(key=lambda x: x.get("fixtureId", ""))
        values = [e["marketValue"] for e in entries if e.get("marketValue")]
        if not values:
            continue

        current = values[-1]
        max_val = max(values)
        min_val = min(values)

        # Tendencia últimas 3 jornadas
        recent = values[-3:] if len(values) >= 3 else values
        if len(recent) >= 2:
            trend_pct = (recent[-1] - recent[0]) / recent[0] * 100 if recent[0] > 0 else 0
            if trend_pct >= 3:
                recent_trend = "subiendo"
            elif trend_pct <= -3:
                recent_trend = "bajando"
            else:
                recent_trend = "estable"
        else:
            trend_pct = 0.0
            recent_trend = "estable"

        # Potencial de recuperación respecto al máximo histórico
        recovery = (max_val - current) / current * 100 if current > 0 else 0

        if recovery >= 100:
            potential_label = "ALTO"
        elif recovery >= 30:
            potential_label = "MEDIO"
        else:
            potential_label = "BAJO"

        trends[pid] = PlayerTrend(
            player_id=pid,
            current_value=current,
            max_value=max_val,
            min_value=min_val,
            values_history=values,
            recent_trend=recent_trend,
            trend_pct=round(trend_pct, 1),
            recovery_potential=round(recovery, 1),
            potential_label=potential_label,
        )

    return trends


def score_market_player(mp: MarketPlayer, my_budget: int = 0,
                         trend: Optional[PlayerTrend] = None) -> PlayerScore:
    w = load_weights()
    p = mp.player
    reasons = []
    sale = mp.sale_price
    market_val = p.market_value
    clause = mp.buyout_clause

    # ── Tipo de mercado ──────────────────────────────────────────────────
    # directOffer=True o salePrice==buyoutClause → clausulazo (precio fijo)
    is_clause = mp.direct_offer or (sale >= clause * 0.99)
    market_type = "clausulazo" if is_clause else "subasta"

    if is_clause:
        strategy_note = (
            f"CLAUSULAZO — Precio fijo {_fmt(clause)}. "
            f"Solo comprar si el jugador vale claramente más. Sin negociación posible."
        )
    else:
        strategy_note = (
            f"SUBASTA — Precio salida {_fmt(sale)}. "
            f"Puja inteligente: no superar el valor real del jugador."
        )

    # ── 1. Revalorización precio actual vs valor ─────────────────────────
    value_ratio = market_val / sale if sale > 0 else 1.0

    if value_ratio >= 1.15:
        rev_score = 90
        reasons.append(f"Precio {_fmt(sale)} muy por debajo del valor {_fmt(market_val)} (+{(value_ratio-1)*100:.1f}%)")
    elif value_ratio >= 1.05:
        rev_score = 65
        reasons.append(f"Precio ligeramente inferior al valor ({(value_ratio-1)*100:.1f}% margen)")
    elif value_ratio >= 0.97:
        rev_score = 40
        reasons.append(f"Precio en línea con el valor de mercado")
    else:
        rev_score = 15
        reasons.append(f"Precio superior al valor — sobrevalorado")

    # ── 2. Tendencia histórica ───────────────────────────────────────────
    trend_score = 50
    if trend:
        max_val = trend.max_value
        recovery = trend.recovery_potential

        if recovery >= 200:
            trend_score = 95
            reasons.append(
                f"Potencial histórico EXCEPCIONAL: máximo {_fmt(max_val)} "
                f"vs valor actual {_fmt(market_val)} (+{recovery:.0f}% de recuperación posible)"
            )
        elif recovery >= 100:
            trend_score = 80
            reasons.append(
                f"Gran potencial histórico: máximo {_fmt(max_val)}, "
                f"actualmente al {100-recovery:.0f}% de su pico"
            )
        elif recovery >= 30:
            trend_score = 60
            reasons.append(
                f"Potencial moderado: máximo histórico {_fmt(max_val)} "
                f"({recovery:.0f}% por encima del valor actual)"
            )
        else:
            trend_score = 30
            reasons.append(
                f"Potencial limitado: ya cerca de su máximo histórico {_fmt(max_val)}"
            )

        if trend.recent_trend == "subiendo":
            trend_score = min(100, trend_score + 15)
            reasons.append(f"Tendencia reciente: subiendo {trend.trend_pct:+.1f}% últimas jornadas")
        elif trend.recent_trend == "bajando":
            trend_score = max(0, trend_score - 15)
            reasons.append(f"Tendencia reciente: bajando {trend.trend_pct:.1f}% últimas jornadas")
        else:
            reasons.append(f"Tendencia reciente: estable")
    else:
        reasons.append("Sin historial de precios disponible")

    # ── 3. Rendimiento deportivo ─────────────────────────────────────────
    avg = p.average_points
    if avg >= 6:
        rend_score = 90
        reasons.append(f"Rendimiento excelente: {avg:.1f} pts/jornada")
    elif avg >= 4:
        rend_score = 70
        reasons.append(f"Buen rendimiento: {avg:.1f} pts/jornada")
    elif avg >= 2.5:
        rend_score = 45
        reasons.append(f"Rendimiento moderado: {avg:.1f} pts/jornada")
    else:
        rend_score = 20
        reasons.append(f"Bajo rendimiento: {avg:.1f} pts/jornada")

    if p.week_points >= 10:
        rend_score = min(100, rend_score + 15)
        reasons.append(f"Excelente última jornada: {p.week_points} pts")
    elif p.week_points >= 6:
        rend_score = min(100, rend_score + 8)

    # ── 4. Oportunidad de mercado ────────────────────────────────────────
    opor_score = 50
    if mp.number_of_offers == 0 and not is_clause:
        opor_score += 20
        reasons.append("Sin ofertas — oportunidad sin competencia")
    elif mp.number_of_offers > 0:
        opor_score -= 10
        reasons.append(f"{mp.number_of_offers} ofertas activas")

    if mp.is_shielded:
        opor_score -= 20
        reasons.append("Jugador blindado")

    # ── 5. Estado ────────────────────────────────────────────────────────
    if p.status == "ok":
        sit_score = 80
    elif p.status == "doubtful":
        sit_score = 40
        reasons.append("Estado dudoso")
    elif p.status == "injured":
        sit_score = 10
        reasons.append("LESIONADO")
    elif p.status == "out_of_league":
        sit_score = 0
        reasons.append("FUERA DE LA LIGA")
    else:
        sit_score = 50

    # ── 6. Riesgo ────────────────────────────────────────────────────────
    riesgo = 0
    if p.status in ("injured", "out_of_league"):
        riesgo += 60
    if sale > my_budget * 0.6 and my_budget > 0:
        riesgo += 20
        reasons.append("Precio alto respecto al presupuesto")

    # ── Score final ──────────────────────────────────────────────────────
    score = (
        rev_score * w.get("revalorizacion", 0.35)
        + trend_score * w.get("tendencia", 0.25)
        + rend_score * w.get("rendimiento", 0.20)
        + opor_score * w.get("oportunidad", 0.15)
        + sit_score * w.get("situacion", 0.10)
        - riesgo * w.get("riesgo", 0.25)
    )
    score = max(0, min(100, score))

    # ── Puja ─────────────────────────────────────────────────────────────
    if is_clause:
        recommended_bid = clause
        max_bid = clause
    elif value_ratio >= 1.1:
        recommended_bid = int(sale * 1.05)
        max_bid = int(market_val * 0.95)
    else:
        recommended_bid = int(sale * 1.02)
        max_bid = int(market_val * 0.90)

    return PlayerScore(
        player=p,
        score=round(score, 1),
        reasons=reasons,
        max_bid=max_bid,
        recommended_bid=recommended_bid,
        value_ratio=round(value_ratio, 3),
        trend=trend,
        market_type=market_type,
        strategy_note=strategy_note,
    )


def score_my_player_for_sale(p: Player) -> dict:
    reasons = []
    score = 0
    if p.average_points < 2:
        score += 40
        reasons.append(f"Bajo rendimiento: {p.average_points:.1f} pts/jornada")
    if p.status == "injured":
        score += 35
        reasons.append("Lesionado")
    if p.status == "out_of_league":
        score += 50
        reasons.append("Fuera de la liga")
    if p.week_points <= 0 and p.average_points < 3:
        score += 15
        reasons.append("Sin puntuar última jornada con media baja")
    return {
        "player": p,
        "sell_score": min(100, score),
        "reasons": reasons,
        "should_sell": score >= 40,
    }


def _fmt(value: int) -> str:
    return f"{value/1_000_000:.2f}M€"
