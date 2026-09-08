"""
Script de ajuste de alineación - Jueves 22:00
Calcula el mejor 11 posible y en modo DRY RUN lo muestra sin ejecutar.
En modo real lo aplica via API.
"""
import os, sys, json, logging
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.laliga import client
from backend.laliga.models import MyTeam
from backend.strategy.decision_engine import evaluate_best_lineup
from backend.laliga.actions import set_lineup

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TOKEN    = os.environ.get("LALIGA_TOKEN", "")
TEAM_ID  = os.environ.get("TEAM_ID", "37889563")
LEAGUE_ID = os.environ.get("LEAGUE_ID", "017948446")
DRY_RUN  = os.environ.get("DRY_RUN", "true").lower() != "false"
DATA_DIR = os.path.join(os.path.dirname(__file__), "../data")


def run():
    logger.info(f"Ajuste de alineación jueves — Modo: {'DRY RUN' if DRY_RUN else 'REAL'}")

    if not TOKEN:
        logger.error("Sin token")
        return

    team_data  = client.get_my_team(TOKEN, TEAM_ID)
    money_data = client.get_my_money(TOKEN, TEAM_ID)

    if not team_data:
        logger.error("No se pudo obtener la plantilla")
        return

    my_team = MyTeam.from_api(team_data, money_data)
    best = evaluate_best_lineup(my_team.players)

    if not best:
        logger.error("No se pudo calcular alineación óptima")
        return

    formation = best["formation"]
    gk        = best["goalkeeper"]
    defs      = best["defenders"]
    mids      = best["midfielders"]
    strs      = best["strikers"]

    logger.info(f"Mejor alineación: {formation[0]}-{formation[1]}-{formation[2]}")
    logger.info(f"Portero: {gk.nickname}")
    logger.info(f"Defensas: {[p.nickname for p in defs]}")
    logger.info(f"Centros: {[p.nickname for p in mids]}")
    logger.info(f"Delanteros: {[p.nickname for p in strs]}")
    logger.info(f"Media total: {best['total_avg_points']:.2f} pts/j")

    # Guardar en JSON para el dashboard
    lineup_json = {
        "generated_at": datetime.now().isoformat(),
        "dry_run": DRY_RUN,
        "formation": formation,
        "total_avg_points": best["total_avg_points"],
        "goalkeeper": {"id": gk.id, "name": gk.nickname, "avg_pts": gk.average_points},
        "defenders": [{"id": p.id, "name": p.nickname, "avg_pts": p.average_points} for p in defs],
        "midfielders": [{"id": p.id, "name": p.nickname, "avg_pts": p.average_points} for p in mids],
        "strikers": [{"id": p.id, "name": p.nickname, "avg_pts": p.average_points} for p in strs],
        "bench": [{"id": p.id, "name": p.nickname, "position": p.position} for p in best["bench"]],
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "best_lineup.json"), "w") as f:
        json.dump(lineup_json, f, ensure_ascii=False, indent=2)

    # Ejecutar si no es DRY RUN
    if not DRY_RUN:
        # Necesitamos los playerTeamId, no los player id
        # Los playerTeamId vienen del lineup de la API
        formation_data = team_data.get("formation", {})

        def get_player_team_id(player_id: str) -> str:
            for pos in ["goalkeeper", "defender", "midfield", "striker"]:
                entries = formation_data.get(pos, [])
                if isinstance(entries, list):
                    for e in entries:
                        if str(e.get("playerMaster", {}).get("id", "")) == player_id:
                            return str(e.get("playerTeamId", ""))
                elif isinstance(entries, dict):
                    if str(entries.get("playerMaster", {}).get("id", "")) == player_id:
                        return str(entries.get("playerTeamId", ""))
            return player_id  # fallback

        result = set_lineup(
            token=TOKEN,
            goalkeeper=get_player_team_id(gk.id),
            defenders=[get_player_team_id(p.id) for p in defs],
            midfielders=[get_player_team_id(p.id) for p in mids],
            strikers=[get_player_team_id(p.id) for p in strs],
            formation=formation,
            dry_run=False,
        )
        if result:
            logger.info("✅ Alineación guardada correctamente en LaLiga Fantasy")
        else:
            logger.error("❌ Error al guardar la alineación")
    else:
        logger.info("[DRY RUN] Alineación calculada pero no aplicada. Cambia DRY_RUN=false para ejecutar.")


if __name__ == "__main__":
    run()
