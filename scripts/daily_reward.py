"""
Reclamación automática de la recompensa diaria
Se ejecuta en los workflows de 12:00 y 20:00

Flujo:
1. GET check-daily-reward → ¿disponible?
2. Si sí → POST daily-reward para reclamar
3. GET daily-reward → confirmar estado final
4. Guardar resultado en data/reward.json
"""
import os, sys, json, logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.laliga import client

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOKEN    = os.environ.get("LALIGA_TOKEN", "")
TEAM_ID  = os.environ.get("TEAM_ID", "37889563")
LEAGUE_ID = os.environ.get("LEAGUE_ID", "017948446")
DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
REWARD_FILE = os.path.join(DATA_DIR, "reward.json")

os.makedirs(DATA_DIR, exist_ok=True)


def load_reward_state() -> dict:
    try:
        with open(REWARD_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_reward_state(data: dict):
    with open(REWARD_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run() -> bool:
    """
    Intenta reclamar la recompensa diaria.
    Devuelve True si se reclamó correctamente, False si no.
    """
    if not TOKEN:
        logger.warning("Sin token — no se puede reclamar recompensa")
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    state = load_reward_state()

    # Si ya se reclamó hoy no hacemos nada
    if state.get("last_claimed_date") == today and state.get("status") == "claimed":
        logger.info(f"Recompensa ya reclamada hoy ({today})")
        return True

    # 1. Comprobar disponibilidad
    logger.info("Comprobando recompensa diaria...")
    logger.info(f"Usando TEAM_ID={TEAM_ID}, LEAGUE_ID={LEAGUE_ID}")
    check = client.check_daily_reward(TOKEN, TEAM_ID, LEAGUE_ID)
    logger.info(f"Check result: HTTP {check.get('status_code')} — disponible: {check.get('available')}")

    if not check.get("available"):
        logger.info("Recompensa ya reclamada hoy (HTTP 400) o no disponible")
        save_reward_state({
            "last_check": datetime.now().isoformat(),
            "status": "not_available",
            "last_claimed_date": state.get("last_claimed_date"),
        })
        return False

    # 2. Reclamar recompensa
    logger.info("Reclamando recompensa diaria...")
    result = client.claim_daily_reward(TOKEN, TEAM_ID, LEAGUE_ID)
    logger.info(f"Claim result: {result}")

    if not result:
        logger.error("Error al reclamar la recompensa")
        save_reward_state({
            "last_check": datetime.now().isoformat(),
            "status": "claim_failed",
            "last_claimed_date": state.get("last_claimed_date"),
        })
        return False

    # 3. Confirmar estado
    status_check = client.get_daily_reward_status(TOKEN)
    logger.info(f"Estado final: {status_check}")

    # El POST devuelve teamMoney (presupuesto tras la recompensa)
    # El GET final devuelve lista de tipos de recompensa disponibles — no usarlo para el amount
    reward_amount = (
        result.get("amount", 0) or
        result.get("reward", 0) or
        result.get("money", 0) or
        0
    )
    # Intentar extraer el amount de la recompensa pública si es lista
    if not reward_amount and isinstance(status_check, list):
        public = next((r for r in status_check if r.get("leagueType") == "public"), None)
        if public:
            reward_amount = public.get("money", 0)

    save_reward_state({
        "last_check": datetime.now().isoformat(),
        "last_claimed_date": today,
        "status": "claimed",
        "reward_amount": reward_amount,
        "reward_amount_fmt": f"{reward_amount/1_000_000:.2f}M€" if reward_amount >= 1000000 else f"{reward_amount:,}€",
        "claim_response": result,
        "status_response": status_check,
    })

    logger.info(f"✅ Recompensa reclamada correctamente. Cantidad: {reward_amount}")
    return True


if __name__ == "__main__":
    success = run()
    sys.exit(0 if success else 1)
