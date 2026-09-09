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
    logger.info(f"Check result: {check}")

    if not check:
        # HTTP 400 generalmente significa que ya fue reclamada hoy
        logger.info("Check devolvió vacío/error — probablemente ya reclamada hoy")
        save_reward_state({
            "last_check": datetime.now().isoformat(),
            "status": "claimed" if state.get("last_claimed_date") == today else "not_available",
            "last_claimed_date": state.get("last_claimed_date"),
            "note": "HTTP 400 — posiblemente ya reclamada"
        })
        return False

    # Interpretar respuesta del check
    available = (
        check.get("available", False) or
        check.get("canClaim", False) or
        check.get("dailyRewardAvailable", False) or
        check.get("hasReward", False) or
        (isinstance(check, dict) and check.get("status") not in ("claimed", "already_claimed", "not_available"))
    )

    logger.info(f"Recompensa disponible: {available}")

    if not available:
        logger.info("Recompensa no disponible o ya reclamada hoy")
        save_reward_state({
            "last_check": datetime.now().isoformat(),
            "status": "not_available",
            "last_claimed_date": state.get("last_claimed_date"),
            "check_response": check,
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

    reward_amount = (
        result.get("amount", 0) or
        result.get("reward", 0) or
        result.get("money", 0) or
        status_check.get("amount", 0) if status_check else 0
    )

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
