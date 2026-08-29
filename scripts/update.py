#!/usr/bin/env python3
"""
Actualiza datos de jugadores, mercado y equipo en la base de datos local.

Uso:
  python scripts/update.py --league <league_id>
  python scripts/update.py  # usa league_id de config.yaml
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.laliga.client import LaLigaFantasyClient, AuthError, APIError
from backend.database.db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("update")


def load_config() -> dict:
    import yaml
    cfg_path = ROOT / "config" / "config.yaml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Actualiza datos de LaLiga Fantasy")
    parser.add_argument("--league", "-l", help="ID de la liga")
    parser.add_argument("--no-players", action="store_true", help="No actualizar jugadores globales")
    parser.add_argument("--no-market", action="store_true", help="No actualizar mercado")
    args = parser.parse_args()

    config = load_config()
    league_id = args.league or config.get("league_id") or config.get("default", {}).get("league_id")

    if not league_id:
        print("❌ Especifica el league_id con --league o en config/config.yaml")
        sys.exit(1)

    # Renovar token antes de empezar
    try:
        import subprocess
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "refresh_token.py")], capture_output=True)
        if result.returncode != 0:
            logger.warning("No se pudo renovar el token, continuando con el existente")
    except Exception as e:
        logger.warning("Error en refresh_token: %s", e)

    try:
        client = LaLigaFantasyClient()
        db = Database()

        # Actualizar jugadores globales
        if not args.no_players:
            logger.info("Actualizando jugadores globales...")
            players = client.get_all_players()
            db.upsert_players(players)
            logger.info("✅ %d jugadores actualizados", len(players))

        # Actualizar mercado
        if not args.no_market:
            logger.info("Actualizando mercado de la liga %s...", league_id)
            market = client.get_market(league_id)
            db.save_market_snapshot(league_id, market)
            logger.info("✅ Mercado actualizado (%d jugadores)", len(market.players))

        # Actualizar mi equipo
        logger.info("Actualizando mi equipo...")
        team = client.get_my_team(league_id)
        for tp in team.players:
            db.upsert_player(tp.player)
        logger.info("✅ Equipo actualizado (%d jugadores)", len(team.players))

        logger.info("🏁 Actualización completada.")

    except AuthError as e:
        logger.error("Error de autenticación: %s", e)
        logger.error("Ejecuta: python scripts/auth.py")
        sys.exit(1)
    except APIError as e:
        logger.error("Error de API: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
