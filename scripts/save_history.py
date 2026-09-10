"""
Guarda snapshot diario de patrimonio, puntos y actividad.
Se ejecuta en todos los workflows principales.
"""
import os, sys, json, logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from backend.laliga import client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOKEN     = os.environ.get("LALIGA_TOKEN", "")
TEAM_ID   = os.environ.get("TEAM_ID", "37889563")
LEAGUE_ID = os.environ.get("LEAGUE_ID", "017948446")
DATA_DIR  = os.path.join(os.path.dirname(__file__), "../data")
HIST_DIR  = os.path.join(DATA_DIR, "history")
ACT_DIR   = os.path.join(DATA_DIR, "activity")

os.makedirs(HIST_DIR, exist_ok=True)
os.makedirs(ACT_DIR, exist_ok=True)

TODAY = datetime.now().strftime("%Y-%m-%d")
NOW   = datetime.now().isoformat()


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def fmt(v):
    return f"{v/1_000_000:.2f}M€" if v else "N/D"


def save_daily_snapshot():
    """
    Guarda snapshot diario completo:
    - Mi equipo: valor, puntos, presupuesto, plantilla completa, decisiones del agente
    - Mercado: jugadores en venta con precios
    - Rivales: clasificación, valor, plantillas
    - Precios de todos los jugadores de la liga
    """
    if not TOKEN:
        logger.warning("Sin token — no se puede guardar snapshot")
        return

    snapshot_file = os.path.join(HIST_DIR, f"{TODAY}.json")

    # No sobreescribir si ya existe (solo guardar una vez al día el snapshot principal)
    # Pero sí actualizar el de mercado que cambia continuamente
    market_file = os.path.join(HIST_DIR, f"{TODAY}_market.json")

    # Leer datos actuales ya generados
    team_data    = load_json(os.path.join(DATA_DIR, "team.json"))
    rivals_data  = load_json(os.path.join(DATA_DIR, "rivals.json"))
    market_data  = load_json(os.path.join(DATA_DIR, "market.json"))
    decisions_data = load_json(os.path.join(DATA_DIR, "decisions.json"))

    # ── Snapshot principal (una vez al día) ──────────────────────────────
    if not os.path.exists(snapshot_file):
        snapshot = {
            "date": TODAY,
            "timestamp": NOW,
            "my_team": {
                "team_value": team_data.get("team_value", 0) if team_data else 0,
                "team_value_fmt": team_data.get("team_value_fmt", "N/D") if team_data else "N/D",
                "points": team_data.get("team_points", 0) if team_data else 0,
                "budget": team_data.get("budget", 0) if team_data else 0,
                "budget_fmt": team_data.get("budget_fmt", "N/D") if team_data else "N/D",
                "players": team_data.get("players", []) if team_data else [],
            },
            "rivals": rivals_data.get("rivals", []) if rivals_data else [],
            "my_position": rivals_data.get("my_position") if rivals_data else None,
            "agent_decisions": {
                "summary": decisions_data.get("summary", "") if decisions_data else "",
                "decisions": decisions_data.get("decisions", []) if decisions_data else [],
                "warnings": decisions_data.get("warnings", []) if decisions_data else [],
                "position_needs": decisions_data.get("position_needs", []) if decisions_data else [],
            },
        }

        # Obtener plantillas de rivales
        rival_squads = {}
        if rivals_data:
            for rival in rivals_data.get("rivals", []):
                tid = rival.get("team_id", "")
                if tid and tid != TEAM_ID:
                    try:
                        from backend.laliga import client as laliga_client
                        squad = laliga_client.get_my_squad(TOKEN, tid, LEAGUE_ID)
                        if squad:
                            rival_squads[tid] = {
                                "manager": rival.get("manager", ""),
                                "players": squad[:20],  # Limitar para no hacer el archivo enorme
                            }
                    except Exception as e:
                        logger.warning(f"Error obteniendo plantilla rival {tid}: {e}")

        snapshot["rival_squads"] = rival_squads

        save_json(snapshot_file, snapshot)
        logger.info(f"Snapshot principal guardado: {snapshot_file}")

    # ── Snapshot de mercado (se actualiza en cada ejecución) ─────────────
    if market_data:
        market_snapshot = {
            "date": TODAY,
            "timestamp": NOW,
            "subastas": market_data.get("subastas", []),
            "clausulazos": market_data.get("clausulazos", []),
            "count": market_data.get("count", 0),
        }
        save_json(market_file, market_snapshot)
        logger.info(f"Snapshot mercado guardado: {market_file}")

    return True


def save_activity():
    """Guarda actividad del día desde el endpoint activity-types."""
    if not TOKEN:
        return

    activity_file = os.path.join(ACT_DIR, f"{TODAY}_activity.json")

    # No sobreescribir si ya existe del día
    if os.path.exists(activity_file):
        logger.info("Actividad del día ya guardada")
        return

    activity = client.get_activity_types(TOKEN)
    if not activity:
        logger.warning("Sin datos de actividad")
        return

    save_json(activity_file, {
        "date": TODAY,
        "timestamp": NOW,
        "activity": activity if isinstance(activity, list) else [activity]
    })
    logger.info(f"Actividad guardada: {activity_file}")


def enrich_executed_actions():
    """
    Enriquece las acciones ejecutadas del día anterior
    comparando con la actividad real de la API.
    """
    executed_file = os.path.join(ACT_DIR, "executed_actions.json")
    if not os.path.exists(executed_file):
        return

    executed = load_json(executed_file) or {"actions": []}
    actions  = executed.get("actions", [])
    pending_enrichment = [a for a in actions if a.get("status") == "executed" and not a.get("enriched")]

    if not pending_enrichment:
        return

    # Leer actividad de ayer
    from datetime import date, timedelta
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    activity_file = os.path.join(ACT_DIR, f"{yesterday}_activity.json")
    activity_data = load_json(activity_file)

    if not activity_data:
        logger.info("Sin actividad de ayer para enriquecer")
        return

    activity_list = activity_data.get("activity", [])

    for action in pending_enrichment:
        # Buscar en la actividad real si la operación se completó
        player_name = action.get("player_name", "").lower()
        action_type = action.get("action", "")
        result      = "unknown"
        detail      = ""

        for act in activity_list:
            act_str = json.dumps(act).lower()
            if player_name in act_str:
                act_type = str(act.get("type", "") or act.get("activityType", "")).lower()
                if action_type == "bid" and "market" in act_type:
                    result = "won" if "buy" in act_str or "compra" in act_str else "lost"
                    detail = f"Actividad detectada: {act.get('type', '')}"
                elif action_type == "offer":
                    result = "executed" if "clausula" in act_str or "offer" in act_str else "unknown"
                    detail = f"Actividad detectada: {act.get('type', '')}"
                elif action_type == "sell":
                    result = "sold" if "venta" in act_str or "sell" in act_str else "pending"
                    detail = f"Actividad detectada: {act.get('type', '')}"
                break

        action["enriched"] = True
        action["result"]   = result
        action["result_detail"] = detail
        action["enriched_at"] = NOW
        logger.info(f"Acción enriquecida: {action_type} {player_name} → {result}")

    save_json(executed_file, executed)
    logger.info("Acciones enriquecidas correctamente")


if __name__ == "__main__":
    save_daily_snapshot()
    save_activity()
    enrich_executed_actions()
    logger.info("Histórico guardado")
