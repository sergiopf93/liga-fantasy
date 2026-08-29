"""
Monitor de mercado en tiempo real.
Detecta nuevas incorporaciones, bajadas de precio y gangas.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, List, Optional

from ..laliga.client import LaLigaFantasyClient
from ..laliga.models import Market, MarketPlayer
from ..strategy.market_strategy import MarketStrategy, MarketOpportunity
from ..database.db import Database

logger = logging.getLogger(__name__)


@dataclass
class MarketAlert:
    alert_type: str       # "NEW_PLAYER" | "PRICE_DROP" | "BARGAIN" | "EXPIRING"
    market_player: MarketPlayer
    old_price: Optional[int]
    change_pct: Optional[float]
    message: str


AlertCallback = Callable[[MarketAlert], None]


class MarketMonitor:
    """
    Monitoriza el mercado y genera alertas sobre cambios relevantes.

    Uso típico:
        monitor = MarketMonitor(client, league_id)
        monitor.add_callback(lambda alert: print(alert.message))
        monitor.run(interval_seconds=300)
    """

    EXPIRING_THRESHOLD = 1800   # segundos: alerta si quedan < 30 min
    PRICE_DROP_THRESHOLD = 0.05 # 5% de bajada → alerta

    def __init__(
        self,
        client: LaLigaFantasyClient,
        league_id: str,
        budget: int = 0,
        db: Optional[Database] = None,
    ):
        self.client = client
        self.league_id = league_id
        self.budget = budget
        self.db = db or Database()
        self._callbacks: List[AlertCallback] = []
        self._last_market: Optional[Dict[str, MarketPlayer]] = None
        self._strategy = MarketStrategy(budget=budget)

    def add_callback(self, cb: AlertCallback) -> None:
        self._callbacks.append(cb)

    def _emit(self, alert: MarketAlert) -> None:
        for cb in self._callbacks:
            try:
                cb(alert)
            except Exception as exc:
                logger.error("Error en callback: %s", exc)

    def check_once(self) -> List[MarketAlert]:
        """Realiza una comprobación del mercado y devuelve alertas."""
        market = self.client.get_market(self.league_id)
        self.db.save_market_snapshot(self.league_id, market)

        alerts = self._compare(market)
        for alert in alerts:
            self._emit(alert)

        # Actualizar estado previo
        self._last_market = {mp.player.id: mp for mp in market.players}
        return alerts

    def _compare(self, market: Market) -> List[MarketAlert]:
        alerts: List[MarketAlert] = []

        for mp in market.players:
            pid = mp.player.id

            # Jugador nuevo en mercado
            if self._last_market is not None and pid not in self._last_market:
                opp = self._strategy._evaluate(mp)
                if opp and opp.urgency in ("HIGH", "MEDIUM"):
                    alerts.append(MarketAlert(
                        alert_type="NEW_PLAYER",
                        market_player=mp,
                        old_price=None,
                        change_pct=None,
                        message=(
                            f"🆕 {mp.player.name} ({mp.player.position}) en mercado "
                            f"por {mp.sell_price:,}€ — {opp.urgency}: {opp.reason}"
                        ),
                    ))

            # Bajada de precio
            if self._last_market and pid in self._last_market:
                old_price = self._last_market[pid].sell_price
                if mp.sell_price < old_price:
                    drop = (old_price - mp.sell_price) / old_price
                    if drop >= self.PRICE_DROP_THRESHOLD:
                        alerts.append(MarketAlert(
                            alert_type="PRICE_DROP",
                            market_player=mp,
                            old_price=old_price,
                            change_pct=-round(drop * 100, 1),
                            message=(
                                f"📉 {mp.player.name} bajó de precio: "
                                f"{old_price:,}€ → {mp.sell_price:,}€ (-{drop*100:.1f}%)"
                            ),
                        ))

            # Expirando pronto
            if 0 < mp.time_left <= self.EXPIRING_THRESHOLD:
                if self.budget == 0 or mp.sell_price <= self.budget:
                    opp = self._strategy._evaluate(mp)
                    if opp:
                        alerts.append(MarketAlert(
                            alert_type="EXPIRING",
                            market_player=mp,
                            old_price=None,
                            change_pct=None,
                            message=(
                                f"⏰ {mp.player.name} expira en {mp.time_left//60}min "
                                f"— Precio: {mp.sell_price:,}€"
                            ),
                        ))

        return alerts

    def run(self, interval_seconds: int = 300, max_iterations: Optional[int] = None) -> None:
        """Bucle de monitorización continua."""
        logger.info("Iniciando monitorización de mercado (intervalo: %ds)", interval_seconds)
        iteration = 0
        while True:
            try:
                alerts = self.check_once()
                logger.info("[%s] %d alertas detectadas", datetime.now().strftime("%H:%M:%S"), len(alerts))
            except Exception as exc:
                logger.error("Error en monitorización: %s", exc)

            iteration += 1
            if max_iterations and iteration >= max_iterations:
                break
            time.sleep(interval_seconds)
