#!/usr/bin/env python3
"""
Genera el informe diario y opcionalmente lo envía por Telegram.

Uso:
  python scripts/generate_report.py --league <id>
  python scripts/generate_report.py --league <id> --telegram
  python scripts/generate_report.py --league <id> --output report.md
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from backend.laliga.client import LaLigaFantasyClient, AuthError, APIError
from backend.analysis.daily_report import DailyReport
from backend.database.db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("generate_report")


def load_config() -> dict:
    import yaml
    cfg_path = ROOT / "config" / "config.yaml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Genera informe diario de LaLiga Fantasy")
    parser.add_argument("--league", "-l", help="ID de la liga")
    parser.add_argument("--telegram", "-t", action="store_true", help="Enviar por Telegram")
    parser.add_argument("--output", "-o", help="Guardar informe en archivo .md")
    args = parser.parse_args()

    config = load_config()
    league_id = args.league or config.get("league_id") or config.get("default", {}).get("league_id")

    if not league_id:
        print("❌ Especifica el league_id con --league o en config/config.yaml")
        sys.exit(1)

    try:
        client = LaLigaFantasyClient()
        db = Database()
        reporter = DailyReport(client=client, db=db)

        logger.info("Generando informe para liga %s...", league_id)
        report = reporter.generate(league_id)

        # Mostrar en consola
        print("\n" + report.raw_text)

        # Guardar a archivo
        if args.output:
            Path(args.output).write_text(report.raw_text, encoding="utf-8")
            logger.info("Informe guardado en %s", args.output)

        # Enviar por Telegram
        if args.telegram:
            tg_config = config.get("telegram", {})
            token = tg_config.get("token") or __import__("os").environ.get("TELEGRAM_TOKEN", "")
            chat_id = tg_config.get("chat_id") or __import__("os").environ.get("TELEGRAM_CHAT_ID", "")

            if not token or not chat_id:
                logger.error("Falta TELEGRAM_TOKEN o TELEGRAM_CHAT_ID en config.yaml o variables de entorno")
                sys.exit(1)

            from backend.notifications.telegram import TelegramNotifier
            notifier = TelegramNotifier(token=token, chat_id=chat_id)
            ok = notifier.send_report(report.raw_text)
            if ok:
                logger.info("✅ Informe enviado por Telegram")
            else:
                logger.error("❌ Error enviando por Telegram")

    except AuthError as e:
        logger.error("Auth error: %s", e)
        logger.error("Ejecuta: python scripts/auth.py")
        sys.exit(1)
    except APIError as e:
        logger.error("API error: %s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
