"""
Base de datos SQLite local para persistir histórico de jugadores,
precios de mercado y puntuaciones.
"""
from __future__ import annotations

import sqlite3
import json
import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parents[3] / "data" / "fantasy.db"


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        self.path = db_path or DB_PATH
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.path, detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                team        TEXT,
                position    TEXT,
                raw_json    TEXT
            );

            CREATE TABLE IF NOT EXISTS player_snapshots (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id       TEXT NOT NULL REFERENCES players(id),
                ts              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                market_value    INTEGER,
                clause_value    INTEGER,
                points          INTEGER,
                status          TEXT,
                last_5_avg      REAL
            );

            CREATE TABLE IF NOT EXISTS market_snapshots (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                league_id   TEXT NOT NULL,
                player_id   TEXT NOT NULL,
                ts          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sell_price  INTEGER,
                time_left   INTEGER,
                seller_name TEXT
            );

            CREATE TABLE IF NOT EXISTS reports (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                league_id   TEXT,
                report_type TEXT,
                content     TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_snapshots_player
                ON player_snapshots(player_id, ts);
            CREATE INDEX IF NOT EXISTS idx_market_league
                ON market_snapshots(league_id, ts);
            """)

    # ------------------------------------------------------------------ #
    # Players                                                              #
    # ------------------------------------------------------------------ #

    def upsert_player(self, player: "Player") -> None:  # noqa: F821
        with self._conn() as conn:
            conn.execute(
                """INSERT INTO players(id, name, team, position, raw_json)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET
                     name=excluded.name, team=excluded.team,
                     position=excluded.position, raw_json=excluded.raw_json""",
                (player.id, player.name, player.team, player.position, json.dumps(player.raw)),
            )
            conn.execute(
                """INSERT INTO player_snapshots(player_id, market_value, clause_value, points, status, last_5_avg)
                   VALUES(?,?,?,?,?,?)""",
                (
                    player.id, player.market_value, player.clause_value,
                    player.points, player.status,
                    player.stats.last_5_avg if player.stats else None,
                ),
            )

    def upsert_players(self, players: list) -> None:
        for p in players:
            self.upsert_player(p)
        logger.info("Guardados %d jugadores en BD", len(players))

    def get_player_history(self, player_id: str, limit: int = 30) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT ts, market_value, clause_value, points, status, last_5_avg
                   FROM player_snapshots WHERE player_id=? ORDER BY ts DESC LIMIT ?""",
                (player_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_all_players(self) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT p.id, p.name, p.team, p.position,
                          s.market_value, s.clause_value, s.points, s.status, s.last_5_avg, s.ts
                   FROM players p
                   LEFT JOIN player_snapshots s ON s.player_id = p.id
                   WHERE s.id = (
                       SELECT MAX(id) FROM player_snapshots WHERE player_id = p.id
                   )"""
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Market                                                               #
    # ------------------------------------------------------------------ #

    def save_market_snapshot(self, league_id: str, market: "Market") -> None:  # noqa: F821
        with self._conn() as conn:
            for mp in market.players:
                conn.execute(
                    """INSERT INTO market_snapshots(league_id, player_id, sell_price, time_left, seller_name)
                       VALUES(?,?,?,?,?)""",
                    (league_id, mp.player.id, mp.sell_price, mp.time_left, mp.seller_name),
                )
        logger.info("Guardado snapshot de mercado con %d jugadores", len(market.players))

    def get_market_history(self, league_id: str, player_id: str, limit: int = 10) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                """SELECT ts, sell_price, time_left, seller_name
                   FROM market_snapshots WHERE league_id=? AND player_id=?
                   ORDER BY ts DESC LIMIT ?""",
                (league_id, player_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Reports                                                              #
    # ------------------------------------------------------------------ #

    def save_report(self, league_id: str, report_type: str, content: str) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO reports(league_id, report_type, content) VALUES(?,?,?)",
                (league_id, report_type, content),
            )
        return cur.lastrowid

    def get_latest_report(self, league_id: str, report_type: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                """SELECT * FROM reports WHERE league_id=? AND report_type=?
                   ORDER BY ts DESC LIMIT 1""",
                (league_id, report_type),
            ).fetchone()
        return dict(row) if row else None
