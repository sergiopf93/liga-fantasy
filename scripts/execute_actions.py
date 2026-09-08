"""
Ejecutor de acciones pendientes
Lee data/pending_actions.json y ejecuta las acciones aprobadas via API de LaLiga
Se ejecuta desde GitHub Actions con el token en secrets
"""
import os, sys, json, logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.laliga.actions import sell_player, bid_market, offer_rival

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOKEN     = os.environ.get("LALIGA_TOKEN", "")
DATA_DIR  = os.path.join(os.path.dirname(__file__), "../data")
PENDING   = os.path.join(DATA_DIR, "pending_actions.json")
RESULTS   = os.path.join(DATA_DIR, "action_results.json")


def run():
    if not TOKEN:
        logger.error("Sin token — no se pueden ejecutar acciones")
        return

    if not os.path.exists(PENDING):
        logger.info("Sin acciones pendientes")
        return

    with open(PENDING) as f:
        data = json.load(f)

    actions = data.get("actions", [])
    pending = [a for a in actions if a.get("status") == "pending"]

    if not pending:
        logger.info("Sin acciones pendientes")
        return

    logger.info(f"Ejecutando {len(pending)} acciones pendientes")
    results = []

    for action in pending:
        aid    = action.get("id", "")
        atype  = action.get("action", "")
        player = action.get("player_name", "")
        amount = action.get("amount", 0)
        pid    = action.get("player_id", "")
        mid    = action.get("market_id", "")

        logger.info(f"Ejecutando: {atype} — {player} — {amount/1e6:.2f}M€")
        result = {"id": aid, "action": atype, "player": player, "timestamp": datetime.now().isoformat()}

        try:
            if atype == "sell":
                res = sell_player(TOKEN, pid, amount, dry_run=False)
            elif atype == "bid":
                res = bid_market(TOKEN, mid, amount, dry_run=False)
            elif atype == "offer":
                res = offer_rival(TOKEN, mid, amount, dry_run=False)
            else:
                res = None

            if res is not None:
                result["status"] = "ok"
                result["message"] = "Ejecutado correctamente"
                action["status"] = "done"
                logger.info(f"✅ {atype} {player} — OK")
            else:
                result["status"] = "error"
                result["message"] = "La API devolvió error"
                action["status"] = "error"
                logger.error(f"❌ {atype} {player} — Error en API")

        except Exception as e:
            result["status"] = "error"
            result["message"] = str(e)
            action["status"] = "error"
            logger.error(f"❌ {atype} {player} — Excepción: {e}")

        results.append(result)

    # Guardar resultados
    with open(RESULTS, "w") as f:
        json.dump({
            "updated_at": datetime.now().isoformat(),
            "results": results
        }, f, ensure_ascii=False, indent=2)

    # Limpiar acciones ejecutadas del pending
    data["actions"] = [a for a in actions if a.get("status") == "pending"]
    data["last_run"] = datetime.now().isoformat()

    with open(PENDING, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Completado: {len(results)} acciones procesadas")


if __name__ == "__main__":
    run()
