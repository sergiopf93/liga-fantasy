"""
Script de Scriptable para registrar una acción ejecutada manualmente.
Recibe parámetros via URL scheme: scriptable:///run?scriptName=...&parameter=JSON
"""
import os, sys, json, logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")
ACT_DIR  = os.path.join(DATA_DIR, "activity")
EXECUTED = os.path.join(ACT_DIR, "executed_actions.json")

os.makedirs(ACT_DIR, exist_ok=True)


def load_executed():
    try:
        with open(EXECUTED) as f:
            return json.load(f)
    except:
        return {"actions": []}


def save_executed(data):
    with open(EXECUTED, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def register(action_data: dict):
    executed = load_executed()
    action_data["executed_at"] = datetime.now().isoformat()
    action_data["status"] = "executed"
    action_data["enriched"] = False
    executed["actions"].append(action_data)
    save_executed(executed)
    logger.info(f"Acción registrada: {action_data}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            data = json.loads(sys.argv[1])
            register(data)
        except Exception as e:
            logger.error(f"Error: {e}")
