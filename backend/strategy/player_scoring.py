"""
Motor de puntuación de jugadores 0-100
Tendencias basadas en historial real de precios por jugador (market-value history)
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
            "tendencia": 0.25,
            "rendimiento": 0.20,
            "oportunidad": 0.15,
            "situacion": 0.10,
            "riesgo": 0.25,
        }


@dataclass
class PlayerTrend:
    player_id: str
    current_value: int
    max_season_value: int       # máximo real desde inicio de temporada
    min_season_value: int       # mínimo real desde inicio de temporada
    first_season_value: int     # valor al inicio de temporada (29/06)
    max_value: int = 0          # alias de max_season_value para compatibilidad
    min_value: int = 0          # alias de min_season_value para compatibilidad
    values_history: List[int]   # todos los valores ordenados por fecha
    recent_trend: str           # "subiendo", "bajando", "estable"
    trend_pct: float            # % cambio últimas entradas
    recovery_potential: float   # (max_season - current) / max_season * 100
    growth_from_start: float    # % crecimiento desde inicio temporada
    potential_label: str        # "ALTO", "MEDIO", "BAJO"


def build_trend_from_history(player_id: str, history: list, current_value: int) -> Optional[PlayerTrend]:
    """
    Construye PlayerTrend desde el historial real del endpoint
    /api/v1/competition/1/player/{id}/market-value
    Cada entry: {date, bids, marketValue, lfpId}
    """
    if not history:
        return None

    # Ordenar por fecha (ya vienen ordenados pero por seguridad)
    sorted_history = sorted(history, key=lambda x: x.get("date", ""))
    values = [e["marketValue"] for e in sorted_history if e.get("marketValue")]

    if not values:
        return None

    max_val   = max(values)
    min_val   = min(values)
    first_val = values[0]
    cur       = current_value or values[-1]

    # Tendencia reciente: últimas 5 entradas
    recent = values[-5:] if len(values) >= 5 else values
    if len(recent) >= 2:
        trend_pct = (recent[-1] - recent[0]) / recent[0] * 100 if recent[0] > 0 else 0
        if trend_pct >= 2:
            recent_trend = "subiendo"
        elif trend_pct <= -2:
            recent_trend = "bajando"
        else:
            recent_trend = "estable"
    else:
        trend_pct    = 0.0
        recent_trend = "estable"

    # Potencial de recuperación respecto al máximo de temporada
    recovery = (max_val - cur) / max_val * 100 if max_val > 0 else 0

    # Crecimiento desde inicio de temporada
    growth = (cur - first_val) / first_val * 100 if first_val > 0 else 0

    if recovery >= 40:
        potential_label = "ALTO"
    elif recovery >= 15:
        potential_label = "MEDIO"
    else:
        potential_label = "BAJO"

    return PlayerTrend(
        player_id=player_id,
        current_value=cur,
        max_season_value=max_val,
        min_season_value=min_val,
        first_season_value=first_val,
        max_value=max_val,
        min_value=min_val,
        values_history=values,
        recent_trend=recent_trend,
        trend_pct=round(trend_pct, 1),
        recovery_potential=round(recovery, 1),
        growth_from_start=round(growth, 1),
        potential_label=potential_label,
    )


def build_trends(fixture_values: List[dict]) -> Dict[str, "PlayerTrend"]:
    """
    Fallback: construye tendencias desde fixture-player-values
    (menos preciso que el historial por jugador)
    """
    by_player: Dict[str, List[dict]] = {}
    for entry in fixture_values:
        pid = str(entry.get("playerId", ""))
        if pid not in by_player:
            by_player[pid] = []
        by_player[pid].append(entry)

    trends = {}
    for pid, entries in by_player.items():
        entries.sort(key=lambda x: x.get("fixtureId", ""))
        values = [e["marketValue"] for e in entries if e.get("marketValue")]
        if not values:
            continue
        cur     = values[-1]
        max_val = max(values)
        min_val = min(values)
        recent  = values[-3:] if len(values) >= 3 else values
        trend_pct = (recent[-1] - recent[0]) / recent[0] * 100 if len(recent) >= 2 and recent[0] > 0 else 0
        recent_trend = "subiendo" if trend_pct >= 2 else "bajando" if trend_pct <= -2 else "estable"
        recovery = (max_val - cur) / max_val * 100 if max_val > 0 else 0
        growth   = (cur - values[0]) / values[0] * 100 if values[0] > 0 else 0
        potential_label = "ALTO" if recovery >= 40 else "MEDIO" if recovery >= 15 else "BAJO"

        trends[pid] = PlayerTrend(
            player_id=pid,
            current_value=cur,
            max_season_value=max_val,
            min_season_value=min_val,
            first_season_value=values[0],
            max_value=max_val,
            min_value=min_val,
            values_history=values,
            recent_trend=recent_trend,
            trend_pct=round(trend_pct, 1),
            recovery_potential=round(recovery, 1),
            growth_from_start=round(growth, 1),
            potential_label=potential_label,
        )
    return trends


@dataclass
class PlayerScore:
    player: Player
    score: float
    reasons: List[str]
    max_bid: int
    recommended_bid: int
    value_ratio: float
    trend: Optional[PlayerTrend]
    market_type: str
    strategy_note: str


def score_market_player(mp: MarketPlayer, my_budget: int = 0,
                        trend: Optional[PlayerTrend] = None) -> PlayerScore:
    w = load_weights()
    p = mp.player
    reasons = []
    sale = mp.sale_price
    market_val = p.market_value
    is_clause = mp.direct_offer

    market_type = "clausulazo" if is_clause else "subasta"
    if is_clause:
        strategy_note = f"CLAUSULAZO — Pagas {_fmt(sale)} directamente al rival. Precio fijo."
    else:
        strategy_note = f"SUBASTA — Precio salida {_fmt(sale)}."

    # ── 1. Revalorización precio vs valor actual ──────────────────────────
    value_ratio = market_val / sale if sale > 0 else 1.0
    if value_ratio >= 1.15:
        rev_score = 90
        reasons.append(f"Precio {_fmt(sale)} muy por debajo del valor {_fmt(market_val)} (+{(value_ratio-1)*100:.1f}%)")
    elif value_ratio >= 1.05:
        rev_score = 65
        reasons.append(f"Precio inferior al valor de mercado ({(value_ratio-1)*100:.1f}% de margen)")
    elif value_ratio >= 0.97:
        rev_score = 40
        reasons.append(f"Precio en línea con el valor de mercado")
    else:
        rev_score = 15
        reasons.append(f"Precio superior al valor — sobrevalorado")

    # ── 2. Potencial respecto al máximo de temporada ───────────────────────
    trend_score = 50
    if trend:
        recovery = trend.recovery_potential
        max_s    = trend.max_season_value

        if recovery >= 50:
            trend_score = 95
            reasons.append(f"Muy por debajo de su máximo de temporada {_fmt(max_s)} — potencial de recuperación {recovery:.0f}%")
        elif recovery >= 30:
            trend_score = 80
            reasons.append(f"Por debajo de su máximo de temporada {_fmt(max_s)} — recuperación potencial {recovery:.0f}%")
        elif recovery >= 15:
            trend_score = 60
            reasons.append(f"Moderadamente por debajo de su máximo {_fmt(max_s)} ({recovery:.0f}% de recuperación posible)")
        else:
            trend_score = 25
            reasons.append(f"Cerca de su máximo de temporada {_fmt(max_s)} — poco margen de subida")

        if trend.recent_trend == "subiendo":
            trend_score = min(100, trend_score + 15)
            reasons.append(f"Tendencia reciente al alza: +{trend.trend_pct:.1f}%")
        elif trend.recent_trend == "bajando":
            trend_score = max(0, trend_score - 10)
            reasons.append(f"Tendencia reciente a la baja: {trend.trend_pct:.1f}%")

        if trend.growth_from_start > 0:
            reasons.append(f"Ha subido {trend.growth_from_start:.1f}% desde inicio de temporada")
        elif trend.growth_from_start < -5:
            reasons.append(f"Ha bajado {abs(trend.growth_from_start):.1f}% desde inicio de temporada")
    else:
        reasons.append("Sin historial de precios disponible")

    # ── 3. Rendimiento deportivo ──────────────────────────────────────────
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
        reasons.append(f"Gran última jornada: {p.week_points} pts")
    elif p.week_points >= 6:
        rend_score = min(100, rend_score + 8)

    # ── 4. Oportunidad ────────────────────────────────────────────────────
    opor_score = 50
    if mp.number_of_offers == 0 and not is_clause:
        opor_score += 20
        reasons.append("Sin ofertas activas — oportunidad sin competencia")
    elif mp.number_of_offers > 0:
        opor_score -= 10

    if mp.is_shielded:
        opor_score -= 20

    # ── 5. Estado ─────────────────────────────────────────────────────────
    if p.status == "ok":          sit_score = 80
    elif p.status == "doubtful":  sit_score = 40; reasons.append("Estado dudoso")
    elif p.status == "injured":   sit_score = 10; reasons.append("LESIONADO")
    elif p.status == "out_of_league": sit_score = 0; reasons.append("FUERA DE LA LIGA")
    else:                         sit_score = 50

    # ── 6. Riesgo ─────────────────────────────────────────────────────────
    riesgo = 0
    if p.status in ("injured", "out_of_league"): riesgo += 60
    if sale > my_budget * 0.6 and my_budget > 0:
        riesgo += 20
        reasons.append("Precio alto respecto al presupuesto disponible")

    # ── Score final ───────────────────────────────────────────────────────
    score = (
        rev_score   * w.get("revalorizacion", 0.35)
        + trend_score * w.get("tendencia", 0.25)
        + rend_score  * w.get("rendimiento", 0.20)
        + opor_score  * w.get("oportunidad", 0.15)
        + sit_score   * w.get("situacion", 0.10)
        - riesgo      * w.get("riesgo", 0.25)
    )
    score = max(0, min(100, score))

    # ── Puja recomendada ──────────────────────────────────────────────────
    if is_clause:
        recommended_bid = sale
        max_bid = sale
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
        score += 35; reasons.append("Lesionado")
    if p.status == "out_of_league":
        score += 50; reasons.append("Fuera de la liga")
    if p.week_points <= 0 and p.average_points < 3:
        score += 15; reasons.append("Sin puntuar última jornada con media baja")
    return {"player": p, "sell_score": min(100, score), "reasons": reasons, "should_sell": score >= 40}


def _fmt(value: int) -> str:
    return f"{value/1_000_000:.2f}M€"
