"""
Motor de decisiones del agente Fantasy
Modo DRY RUN por defecto - no ejecuta operaciones reales

Lógica implementada según Lógica_operaciones.docx:
- Siempre mantener 11 activo
- Siempre 2 porteros
- Nunca saldo negativo
- Vender jugadores con tendencia negativa (umbral proporcional 15%)
- Comprar jugadores con potencial de recuperación respecto al máximo de temporada
- Ofertas a rival >= valor de mercado
- Clausulazos al precio exacto de cláusula
"""
import logging
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from backend.laliga.models import Player, MarketPlayer, MyTeam

logger = logging.getLogger(__name__)

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"

# Formaciones válidas de LaLiga Fantasy
VALID_FORMATIONS = [
    [4, 4, 2], [4, 3, 3], [4, 5, 1], [4, 2, 4],
    [3, 4, 3], [3, 5, 2], [3, 3, 4],
    [5, 3, 2], [5, 4, 1], [5, 2, 3],
]

# Umbrales configurables
SELL_DROP_THRESHOLD_PCT = 15.0    # % caída máxima aceptable para vender
MIN_CASH_RESERVE       = 3_000_000  # reserva mínima de dinero
MIN_SALE_RATIO         = 0.85     # vender si mercado ofrece >= 85% del valor


@dataclass
class Decision:
    action: str          # "sell", "bid", "offer", "lineup", "hold"
    player_id: str
    player_name: str
    reason: str
    amount: int = 0
    market_id: str = ""
    priority: int = 5    # 1=crítico, 5=normal, 10=opcional
    dry_run: bool = True


@dataclass
class DecisionReport:
    decisions: List[Decision] = field(default_factory=list)
    blocked: List[dict] = field(default_factory=list)   # acciones bloqueadas por seguridad
    warnings: List[str] = field(default_factory=list)
    summary: str = ""


def _fmt(v: int) -> str:
    return f"{v/1_000_000:.2f}M€"


def check_squad_safety(players: List[Player], selling_player_id: str,
                       buying_position_id: int = None) -> Tuple[bool, str, Optional[list]]:
    """
    Verifica si es seguro vender un jugador.
    Devuelve (safe, reason, alternative_formation)
    """
    remaining = [p for p in players if p.id != selling_player_id]

    gks  = [p for p in remaining if p.position_id == 1]
    defs = [p for p in remaining if p.position_id == 2]
    mids = [p for p in remaining if p.position_id == 3]
    strs = [p for p in remaining if p.position_id == 4]

    # Regla 1: siempre 2 porteros
    if len(gks) < 2:
        return False, f"Quedarías con {len(gks)} portero(s) — mínimo 2 requeridos", None

    # Regla 2: buscar formación válida con los jugadores restantes
    for formation in VALID_FORMATIONS:
        n_def, n_mid, n_str = formation
        if len(defs) >= n_def and len(mids) >= n_mid and len(strs) >= n_str:
            return True, f"Formación {n_def}-{n_mid}-{n_str} viable con la plantilla restante", formation

    return False, "No hay formación válida posible con la plantilla restante tras la venta", None


def evaluate_sell_decisions(my_team: MyTeam, market_players: List[MarketPlayer]) -> List[Decision]:
    """
    Evalúa qué jugadores de mi plantilla conviene vender.
    Criterios:
    1. Tendencia negativa >= 2 jornadas
    2. El mercado ofrece al menos MIN_SALE_RATIO del valor actual
    3. El descuento es proporcional al valor (15% umbral)
    """
    decisions = []
    market_prices = {mp.player.id: mp for mp in market_players}

    # Separar alineados y no alineados (simplificado: todos por ahora)
    for player in my_team.players:
        # Obtener precio de mercado si está en venta por algún rival
        # (para contexto de precio, no para vender nosotros aquí)
        market_val = player.market_value

        # Calcular umbral de caída aceptable proporcional
        # Jugador de 20M: acepta caída de 3M (15%)
        # Jugador de 1M: acepta caída de 150K (15%)
        drop_threshold = market_val * (SELL_DROP_THRESHOLD_PCT / 100)

        # Señales de venta
        sell_signals = []
        sell_score = 0

        if player.status == "out_of_league":
            sell_score += 50
            sell_signals.append("Fuera de la liga — no puntúa")
        if player.status == "injured":
            sell_score += 30
            sell_signals.append("Lesionado")
        if player.average_points < 2.0 and player.position_id != 1:
            sell_score += 25
            sell_signals.append(f"Bajo rendimiento: {player.average_points:.1f} pts/j")
        if player.week_points <= 0 and player.average_points < 3.0:
            sell_score += 15
            sell_signals.append("Sin puntuar última jornada con media baja")

        if sell_score >= 40:
            # Calcular precio de venta recomendado
            # Intentar vender cerca del valor de mercado
            recommended_price = int(market_val * 0.95)

            # Verificar seguridad de la venta
            safe, reason, alt_formation = check_squad_safety(my_team.players, player.id)

            if safe:
                decisions.append(Decision(
                    action="sell",
                    player_id=player.id,
                    player_name=player.nickname,
                    reason=f"VENTA RECOMENDADA: {', '.join(sell_signals)}. Precio sugerido: {_fmt(recommended_price)}",
                    amount=recommended_price,
                    priority=3 if sell_score >= 50 else 5,
                    dry_run=DRY_RUN,
                ))
            else:
                decisions.append(Decision(
                    action="hold",
                    player_id=player.id,
                    player_name=player.nickname,
                    reason=f"BLOQUEADA: {reason}. Señales: {', '.join(sell_signals)}",
                    priority=7,
                    dry_run=DRY_RUN,
                ))

    return decisions


def evaluate_buy_decisions(market_players: List[MarketPlayer],
                           my_budget: int,
                           my_players: List[Player]) -> List[Decision]:
    """
    Evalúa oportunidades de compra.
    Criterios:
    1. Precio <= presupuesto disponible - reserva mínima
    2. Potencial de recuperación respecto al máximo de temporada
    3. Rendimiento deportivo mínimo
    4. Precio razonable respecto al valor de mercado
    """
    decisions = []
    available = my_budget - MIN_CASH_RESERVE

    if available <= 0:
        logger.info("Sin presupuesto disponible para compras tras reserva mínima")
        return decisions

    for mp in market_players:
        p = mp.player
        if p.position_id == 5:  # no entrenadores
            continue
        if p.status in ("injured", "out_of_league"):
            continue
        if mp.sale_price > available:
            continue

        buy_signals = []
        buy_score = 0

        # Potencial de recuperación vs máximo de temporada
        # (viene del trend si está disponible)
        value_ratio = p.market_value / mp.sale_price if mp.sale_price > 0 else 1.0

        if value_ratio >= 1.15:
            buy_score += 40
            buy_signals.append(f"Precio {_fmt(mp.sale_price)} muy por debajo del valor {_fmt(p.market_value)}")
        elif value_ratio >= 1.05:
            buy_score += 20
            buy_signals.append(f"Precio inferior al valor de mercado ({(value_ratio-1)*100:.1f}% margen)")

        if p.average_points >= 6:
            buy_score += 25
            buy_signals.append(f"Rendimiento excelente: {p.average_points:.1f} pts/j")
        elif p.average_points >= 4:
            buy_score += 15
            buy_signals.append(f"Buen rendimiento: {p.average_points:.1f} pts/j")

        if mp.number_of_offers == 0 and mp.market_type == "subasta":
            buy_score += 10
            buy_signals.append("Sin competencia en la puja")

        if buy_score >= 40:
            # Determinar tipo: si tiene seller es clausulazo, si no es subasta
            is_clause = mp.direct_offer or bool(mp.seller_team_id and mp.seller_team_id != "0")

            # Reglas de precio
            if is_clause:
                # Oferta a rival: pagar exactamente el precio de cláusula
                bid_amount = mp.sale_price
                action = "offer"
            else:
                # Subasta: pujar la cantidad recomendada
                bid_amount = min(int(mp.sale_price * 1.05), int(p.market_value * 0.95))
                action = "bid"

            if bid_amount <= available:
                decisions.append(Decision(
                    action=action,
                    player_id=p.id,
                    player_name=p.nickname,
                    reason=f"COMPRA RECOMENDADA ({mp.market_type.upper()}): {', '.join(buy_signals)}",
                    amount=bid_amount,
                    market_id=mp.market_id,
                    priority=3 if buy_score >= 60 else 5,
                    dry_run=DRY_RUN,
                ))

    decisions.sort(key=lambda x: x.priority)
    return decisions


def evaluate_best_lineup(players: List[Player]) -> Optional[dict]:
    """
    Calcula el mejor 11 posible con la plantilla actual.
    Criterio: maximizar la suma de puntos de los titulares.
    Siempre 1 portero. Busca la formación que maximiza puntos totales.
    """
    gks  = sorted([p for p in players if p.position_id == 1], key=lambda x: x.average_points, reverse=True)
    defs = sorted([p for p in players if p.position_id == 2], key=lambda x: x.average_points, reverse=True)
    mids = sorted([p for p in players if p.position_id == 3], key=lambda x: x.average_points, reverse=True)
    strs = sorted([p for p in players if p.position_id == 4], key=lambda x: x.average_points, reverse=True)

    if not gks:
        logger.error("Sin portero — no se puede calcular alineación")
        return None

    best_score = -1
    best_lineup = None

    for formation in VALID_FORMATIONS:
        n_def, n_mid, n_str = formation
        if len(defs) < n_def or len(mids) < n_mid or len(strs) < n_str:
            continue

        lineup_players = (
            [gks[0]] +
            defs[:n_def] +
            mids[:n_mid] +
            strs[:n_str]
        )
        total_score = sum(p.average_points for p in lineup_players)

        if total_score > best_score:
            best_score = total_score
            best_lineup = {
                "formation": formation,
                "goalkeeper": gks[0],
                "defenders": defs[:n_def],
                "midfielders": mids[:n_mid],
                "strikers": strs[:n_str],
                "total_avg_points": round(total_score, 2),
                "bench": [p for p in players if p not in lineup_players],
            }

    return best_lineup


def run_decision_engine(my_team: MyTeam, market_players: List[MarketPlayer]) -> DecisionReport:
    """
    Ejecuta el motor de decisiones completo.
    En modo DRY RUN solo genera el informe sin ejecutar nada.
    """
    report = DecisionReport()
    mode = "DRY RUN" if DRY_RUN else "REAL"
    logger.info(f"Motor de decisiones iniciado — Modo: {mode}")

    # 1. Verificar estado de la plantilla
    gks = [p for p in my_team.players if p.position_id == 1]
    if len(gks) < 2:
        report.warnings.append(f"⚠️ Solo tienes {len(gks)} portero(s). Recomendado: 2 mínimo.")

    # 2. Mejor alineación posible
    best_11 = evaluate_best_lineup(my_team.players)
    if best_11:
        report.summary = (
            f"Mejor formación posible: {best_11['formation']} "
            f"con {best_11['total_avg_points']:.1f} pts/j de media"
        )

    # 3. Evaluar ventas
    sell_decisions = evaluate_sell_decisions(my_team, market_players)
    report.decisions.extend(sell_decisions)

    # 4. Evaluar compras
    buy_decisions = evaluate_buy_decisions(
        market_players, my_team.budget, my_team.players
    )
    report.decisions.extend(buy_decisions)

    # 5. Separar bloqueadas
    report.blocked = [
        {"player": d.player_name, "reason": d.reason}
        for d in report.decisions if d.action == "hold"
    ]
    report.decisions = [d for d in report.decisions if d.action != "hold"]

    logger.info(f"Decisiones generadas: {len(report.decisions)} acciones, {len(report.blocked)} bloqueadas")
    return report
