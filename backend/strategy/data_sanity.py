"""
Validador de sanidad de datos usando el historial real de snapshots.
Compara los valores actuales de cada jugador contra su histórico reciente
para detectar bugs de la API (avg_points masivos a 0, valores imposibles, etc.)

Uso:
    from backend.strategy.data_sanity import validate_api_data
    ok, report = validate_api_data(my_team, market_players, history_dir)
    if not ok:
        return report  # no generar decisiones
"""
import os
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple, Dict, Optional
from backend.laliga.models import MarketPlayer, MyTeam

logger = logging.getLogger(__name__)

DATA_DIR    = os.path.join(os.path.dirname(__file__), "../../data")
HISTORY_DIR = os.path.join(DATA_DIR, "history")

# ── Umbrales ─────────────────────────────────────────────────────────────────

# Días de historial a mirar hacia atrás para comparar
HISTORY_LOOKBACK_DAYS = 7

# Si un jugador tenía avg > este umbral en el historial y ahora tiene 0 → bug
AVG_POINTS_MIN_HISTORICAL = 1.0

# % máximo de jugadores que pueden tener avg=0 siendo que antes tenían avg>umbral
# Si se supera → bug masivo de API
MAX_ZEROED_AVG_PCT = 0.40   # más del 40% afectados = bug confirmado

# Caída máxima de market_value en un día considerada imposible (%)
MAX_VALUE_DROP_PCT_PER_DAY = 25.0  # >25% en un día = bug

# Subida máxima de market_value en un día considerada imposible (%)
MAX_VALUE_SPIKE_PCT_PER_DAY = 50.0  # >50% en un día = bug

# Número mínimo de snapshots históricos para poder validar
MIN_SNAPSHOTS_FOR_VALIDATION = 1


# ── Carga de historial ────────────────────────────────────────────────────────

def _load_recent_snapshots(history_dir: str, n: int = HISTORY_LOOKBACK_DAYS) -> list:
    """Carga los últimos N snapshots diarios ordenados por fecha."""
    hist_path = Path(history_dir)
    if not hist_path.exists():
        return []
    files = sorted(hist_path.glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json"))
    recent = files[-n:] if len(files) >= n else files
    snapshots = []
    for f in recent:
        try:
            with open(f) as fp:
                data = json.load(fp)
                snapshots.append(data)
        except Exception:
            pass
    return snapshots


def _build_player_history(snapshots: list) -> Dict[str, list]:
    """
    Construye un dict {player_id: [{date, avg, value}, ...]}
    con el historial de cada jugador en los últimos N días.
    """
    history: Dict[str, list] = {}
    for snap in snapshots:
        date = snap.get("date", "")
        for p in snap.get("my_team", {}).get("players", []):
            pid = str(p.get("id", ""))
            if not pid:
                continue
            if pid not in history:
                history[pid] = []
            history[pid].append({
                "date":           date,
                "nickname":       p.get("nickname", ""),
                "average_points": p.get("average_points", 0),
                "market_value":   p.get("market_value", 0),
            })
    return history


# ── Validaciones ─────────────────────────────────────────────────────────────

@dataclass
class SanityReport:
    passed: bool = True
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    summary: str = ""
    skip_decisions: bool = False


def validate_api_data(
    my_team: MyTeam,
    market_players: Optional[List[MarketPlayer]] = None,
    history_dir: str = HISTORY_DIR,
) -> Tuple[bool, SanityReport]:
    """
    Valida los datos actuales contra el historial real.
    Devuelve (passed, SanityReport).
    passed=False → el motor de decisiones debe abortarse.
    """
    report = SanityReport()
    players = my_team.players if my_team else []

    # ── Cargar historial ─────────────────────────────────────────────────────
    snapshots = _load_recent_snapshots(history_dir)
    if len(snapshots) < MIN_SNAPSHOTS_FOR_VALIDATION:
        report.warnings.append(
            f"⚠️ Sin historial suficiente para validación ({len(snapshots)} snapshots). "
            "Ejecutando motor sin protección histórica."
        )
        # Sin historial no podemos validar, pero tampoco bloqueamos
        _run_basic_checks(players, market_players, report)
        _finalize(report)
        return report.passed, report

    player_history = _build_player_history(snapshots)

    # ── Check 1: average_points masivo a 0 comparado con historial ───────────
    zeroed_players = []      # jugadores con avg>0 antes y ahora 0
    value_anomalies = []     # jugadores con caída/subida imposible de valor

    for p in players:
        pid = str(p.id)
        hist = player_history.get(pid, [])

        if not hist:
            continue  # jugador nuevo, no hay con qué comparar

        # Últimos avg_points conocidos (excluir el de hoy)
        hist_avgs = [h["average_points"] for h in hist if h["average_points"] > 0]
        hist_values = [h["market_value"] for h in hist if h["market_value"] > 0]

        # Check avg: tenía historial positivo y ahora es 0
        if hist_avgs and p.average_points == 0:
            recent_avg = hist_avgs[-1]
            if recent_avg >= AVG_POINTS_MIN_HISTORICAL:
                zeroed_players.append({
                    "nickname":   p.nickname,
                    "avg_before": recent_avg,
                    "avg_now":    p.average_points,
                })

        # Check value: caída o subida imposible en un día
        if hist_values and p.market_value > 0:
            last_value = hist_values[-1]
            if last_value > 0:
                change_pct = (p.market_value - last_value) / last_value * 100
                if change_pct < -MAX_VALUE_DROP_PCT_PER_DAY:
                    value_anomalies.append({
                        "nickname":   p.nickname,
                        "val_before": last_value,
                        "val_now":    p.market_value,
                        "change_pct": round(change_pct, 1),
                    })
                elif change_pct > MAX_VALUE_SPIKE_PCT_PER_DAY:
                    value_anomalies.append({
                        "nickname":   p.nickname,
                        "val_before": last_value,
                        "val_now":    p.market_value,
                        "change_pct": round(change_pct, 1),
                    })

    # ── Evaluar gravedad del bug de average_points ───────────────────────────
    comparable_players = [
        p for p in players
        if str(p.id) in player_history and player_history[str(p.id)]
    ]
    if comparable_players and zeroed_players:
        zeroed_pct = len(zeroed_players) / len(comparable_players)
        names = ", ".join(z["nickname"] for z in zeroed_players[:4])

        if zeroed_pct >= MAX_ZEROED_AVG_PCT:
            # Bug masivo — bloquear
            report.issues.append(
                f"🐛 BUG API — average_points=0 en {len(zeroed_players)}/{len(comparable_players)} "
                f"jugadores ({zeroed_pct*100:.0f}%) que tenían media positiva en el historial. "
                f"Ejemplos: {names}. "
                f"El motor NO generará decisiones para evitar ventas erróneas."
            )
            report.passed = False
            report.skip_decisions = True
        elif zeroed_pct >= 0.20:
            # Afectación parcial — aviso pero no bloquear
            report.warnings.append(
                f"⚠️ {len(zeroed_players)} jugadores con average_points=0 que antes tenían media "
                f"positiva ({zeroed_pct*100:.0f}%). Posible bug parcial de API. "
                f"Las decisiones de venta pueden estar sesgadas. Ejemplos: {names}."
            )

    # ── Evaluar anomalías de valor de mercado ────────────────────────────────
    if value_anomalies:
        drops = [a for a in value_anomalies if a["change_pct"] < 0]
        spikes = [a for a in value_anomalies if a["change_pct"] > 0]

        if len(drops) >= 3:
            names = ", ".join(a["nickname"] for a in drops[:4])
            report.issues.append(
                f"🐛 BUG API — {len(drops)} jugadores con caída de valor >25% en un día. "
                f"Imposible en condiciones normales. Ejemplos: {names}."
            )
            report.passed = False
            report.skip_decisions = True
        elif drops:
            for a in drops:
                report.warnings.append(
                    f"⚠️ {a['nickname']}: valor cayó {a['change_pct']}% en un día "
                    f"({a['val_before']/1e6:.2f}M€ → {a['val_now']/1e6:.2f}M€). Verifica."
                )

        if len(spikes) >= 3:
            names = ", ".join(a["nickname"] for a in spikes[:4])
            report.issues.append(
                f"🐛 BUG API — {len(spikes)} jugadores con subida de valor >50% en un día. "
                f"Imposible en condiciones normales. Ejemplos: {names}."
            )
            report.passed = False
            report.skip_decisions = True

    # ── Checks básicos adicionales (sin historial necesario) ─────────────────
    _run_basic_checks(players, market_players, report)

    # ── Resumen final ─────────────────────────────────────────────────────────
    _finalize(report)
    return report.passed, report


def _run_basic_checks(players, market_players, report: SanityReport):
    """Checks que no necesitan historial: plantilla mínima, presupuesto, etc."""
    if len(players) < 11:
        report.issues.append(
            f"Plantilla incompleta: {len(players)} jugadores recibidos (mínimo 11)."
        )
        report.passed = False
        report.skip_decisions = True

    no_value = [p for p in players if p.market_value < 1_000 and p.position_id != 1]
    if len(no_value) > 5:
        names = ", ".join(p.nickname for p in no_value[:4])
        report.issues.append(
            f"{len(no_value)} jugadores de campo sin valor de mercado: {names}."
        )
        report.passed = False
        report.skip_decisions = True


def _finalize(report: SanityReport):
    if not report.passed:
        issues_txt = "\n  · ".join(report.issues)
        report.summary = (
            f"🚨 VALIDACIÓN FALLIDA — Motor de decisiones ABORTADO.\n"
            f"Problemas detectados:\n  · {issues_txt}\n\n"
            f"La API de LaLiga Fantasy puede estar experimentando un bug. "
            f"El agente no tomará ninguna acción hasta que los datos se normalicen."
        )
        logger.warning(report.summary)
    else:
        warns = f" | Avisos: {len(report.warnings)}" if report.warnings else ""
        report.summary = f"✅ Validación OK{warns}"
        logger.info(report.summary)
