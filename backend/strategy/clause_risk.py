"""
Análisis de riesgo de clausulazo
Niveles: BAJO, MEDIO, ALTO, CRÍTICO
Atención especial a porteros (positionId == 1)
"""
from typing import List
from backend.laliga.models import Player, RivalTeam, ClauseRisk


LEVELS = {
    (0, 25): "BAJO",
    (25, 50): "MEDIO",
    (50, 75): "ALTO",
    (75, 101): "CRÍTICO",
}


def get_risk_level(score: float) -> str:
    for (low, high), label in LEVELS.items():
        if low <= score < high:
            return label
    return "BAJO"


def assess_clause_risk(player: Player, rivals: List[RivalTeam], my_goalkeepers: List[Player]) -> ClauseRisk:
    """
    Calcula el riesgo de clausulazo de un jugador de mi plantilla.
    """
    score = 0.0
    reasons = []
    rec = ""

    clause = player.buyout_clause
    market_val = player.market_value

    # ── 1. Portero único → riesgo estructural ────────────────────────────
    is_goalkeeper = player.position_id == 1
    only_goalkeeper = is_goalkeeper and len(my_goalkeepers) == 1

    if only_goalkeeper:
        score += 35
        reasons.append("ALERTA: Es tu único portero. Quedarte sin portero implica penalización grave")

    if is_goalkeeper:
        score += 15
        reasons.append("Portero: posición especialmente sensible a clausulazos tácticos de rivales")

    # ── 2. Relación precio/valor ─────────────────────────────────────────
    if clause > 0 and market_val > 0:
        ratio = clause / market_val
        if ratio <= 1.05:
            score += 25
            reasons.append(f"Cláusula {_fmt(clause)} muy cercana al valor de mercado {_fmt(market_val)} — fácil de ejecutar")
        elif ratio <= 1.20:
            score += 12
            reasons.append(f"Cláusula {_fmt(clause)} razonablemente ejecutable")
        else:
            reasons.append(f"Cláusula {_fmt(clause)} elevada respecto al valor {_fmt(market_val)} — protección moderada")

    # ── 3. Dinero disponible de rivales ──────────────────────────────────
    rivals_who_can_afford = [
        r for r in rivals
        if r.budget > clause * 0.9 and r.team_id != "37889563"
    ]
    if rivals_who_can_afford:
        score += min(20, len(rivals_who_can_afford) * 7)
        names = ", ".join(r.manager_name for r in rivals_who_can_afford[:3])
        reasons.append(f"{len(rivals_who_can_afford)} rival(es) con dinero suficiente: {names}")

    # ── 4. Rendimiento del jugador ───────────────────────────────────────
    if player.average_points >= 6:
        score += 15
        reasons.append(f"Alto rendimiento ({player.average_points:.1f} pts/j) — jugador codiciado")
    elif player.average_points >= 4:
        score += 8

    # ── 5. Estado del jugador ────────────────────────────────────────────
    if player.status in ("injured", "out_of_league"):
        score = max(0, score - 20)
        reasons.append("Lesión/baja reduce el interés rival temporalmente")

    score = min(100, score)
    level = get_risk_level(score)

    if level == "CRÍTICO":
        rec = f"Acción inmediata recomendada. Blindar o buscar alternativa antes del cierre de mercado."
    elif level == "ALTO":
        rec = f"Vigilar activamente. Considera blindar si tienes presupuesto."
    elif level == "MEDIO":
        rec = f"Monitorizar diariamente. Sin urgencia inmediata."
    else:
        rec = f"Riesgo bajo. Sin acción necesaria."

    if only_goalkeeper:
        rec = "⚠️ URGENTE: Compra un segundo portero. Sin portero tu equipo no puede puntuar."

    return ClauseRisk(
        player=player,
        risk_level=level,
        risk_score=round(score, 1),
        reasons=reasons,
        recommendation=rec,
    )


def analyze_goalkeeper_situation(my_players: List[Player], market_players=None) -> dict:
    """
    Análisis específico de la situación de porteros.
    """
    my_goalkeepers = [p for p in my_players if p.position_id == 1]
    result = {
        "count": len(my_goalkeepers),
        "goalkeepers": my_goalkeepers,
        "risk": "BAJO",
        "recommendation": "",
        "alternatives": [],
    }

    if len(my_goalkeepers) == 0:
        result["risk"] = "CRÍTICO"
        result["recommendation"] = "No tienes portero. El equipo no puede puntuar. Compra uno inmediatamente."
    elif len(my_goalkeepers) == 1:
        gk = my_goalkeepers[0]
        clause = gk.buyout_clause
        result["risk"] = "ALTO"
        result["recommendation"] = (
            f"Solo tienes a {gk.nickname} (cláusula {_fmt(clause)}). "
            f"Un rival puede ejecutar la cláusula y dejarte sin portero. "
            f"Considera comprar un segundo portero de bajo coste como seguro."
        )
        if market_players:
            gk_market = [mp for mp in market_players if mp.player.position_id == 1]
            cheap_gks = sorted(gk_market, key=lambda x: x.sale_price)[:3]
            result["alternatives"] = cheap_gks
    else:
        result["risk"] = "BAJO"
        result["recommendation"] = f"Tienes {len(my_goalkeepers)} porteros. Situación segura."

    return result


def _fmt(value: int) -> str:
    return f"{value/1_000_000:.2f}M€"
