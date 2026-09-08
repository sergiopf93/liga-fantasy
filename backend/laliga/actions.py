"""
Capa de escritura de la API de LaLiga Fantasy
Todos los endpoints verificados el 04/09/2026 via Proxyman

IMPORTANTE: Todas las funciones tienen un parámetro dry_run=True por defecto.
En modo dry_run no se ejecuta ninguna operación real.
"""
import requests
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

BASE_URL = "https://fantasy-api.llt-services.com"
LEAGUE_ID = os.environ.get("LEAGUE_ID", "017948446")
TEAM_ID   = os.environ.get("TEAM_ID", "37889563")

HEADERS_BASE = {
    "X-App": "Fantasy-iOS",
    "X-Version": "10.0.5",
    "X-Lang": "es",
    "accept": "*/*",
    "accept-language": "es-ES;q=1.0",
    "user-agent": "LaLigaFantasy/10.0.5 (com.lfp.laligafantasy; build:2; iOS 26.5.0) Alamofire/5.10.2",
    "content-type": "application/json",
}

DRY_RUN = os.environ.get("DRY_RUN", "true").lower() != "false"


def _headers(token: str) -> dict:
    h = HEADERS_BASE.copy()
    h["authorization"] = f"Bearer {token}"
    return h


def _post(token: str, path: str, body: dict, dry_run: bool = True) -> Optional[dict]:
    url = f"{BASE_URL}{path}"
    if dry_run:
        logger.info(f"[DRY RUN] POST {url} body={body}")
        return {"dry_run": True, "url": url, "body": body}
    try:
        r = requests.post(url, headers=_headers(token), json=body, timeout=15)
        logger.info(f"POST {url} → {r.status_code}")
        if r.status_code in (200, 201):
            return r.json() if r.content else {"ok": True}
        else:
            logger.error(f"Error {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Error en POST {path}: {e}")
        return None


def _delete(token: str, path: str, dry_run: bool = True) -> bool:
    url = f"{BASE_URL}{path}"
    if dry_run:
        logger.info(f"[DRY RUN] DELETE {url}")
        return True
    try:
        r = requests.delete(url, headers=_headers(token), timeout=15)
        logger.info(f"DELETE {url} → {r.status_code}")
        return r.status_code in (200, 204)
    except Exception as e:
        logger.error(f"Error en DELETE {path}: {e}")
        return False


def _put(token: str, path: str, body: dict, dry_run: bool = True) -> Optional[dict]:
    url = f"{BASE_URL}{path}"
    if dry_run:
        logger.info(f"[DRY RUN] PUT {url} body={body}")
        return {"dry_run": True, "url": url, "body": body}
    try:
        r = requests.put(url, headers=_headers(token), json=body, timeout=15)
        logger.info(f"PUT {url} → {r.status_code}")
        if r.status_code in (200, 201):
            return r.json() if r.content else {"ok": True}
        else:
            logger.error(f"Error {r.status_code}: {r.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Error en PUT {path}: {e}")
        return None


# ── VENTAS ────────────────────────────────────────────────────────────────────

def sell_player(token: str, player_id: str, sale_price: int,
                dry_run: bool = True) -> Optional[dict]:
    """
    Pone un jugador en venta en el mercado.
    sale_price: precio de venta en euros (entero)
    player_id: el id del jugador (ej: "2324"), NO el playerTeamId
    """
    logger.info(f"{'[DRY Run] ' if dry_run else ''}VENTA: jugador {player_id} por {sale_price/1e6:.2f}M€")
    return _post(
        token,
        f"/api/v1/competition/1/league/{LEAGUE_ID}/market/sell?x-lang=es",
        {"playerId": player_id, "salePrice": sale_price},
        dry_run=dry_run,
    )


# ── COMPRAS EN MERCADO GENERAL (subasta) ─────────────────────────────────────

def bid_market(token: str, market_id: str, amount: int,
               dry_run: bool = True) -> Optional[dict]:
    """
    Realiza una puja en el mercado general.
    market_id: id de la entrada de mercado
    amount: cantidad a pujar en euros
    """
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}PUJA: market {market_id} por {amount/1e6:.2f}M€")
    return _post(
        token,
        f"/api/v1/competition/1/league/{LEAGUE_ID}/market/{market_id}/bid?x-lang=es",
        {"money": amount},
        dry_run=dry_run,
    )


def cancel_bid(token: str, market_id: str, bid_id: str,
               dry_run: bool = True) -> bool:
    """Cancela una puja existente en mercado general."""
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}CANCELAR PUJA: market {market_id} bid {bid_id}")
    return _delete(
        token,
        f"/api/v1/competition/1/league/{LEAGUE_ID}/market/{market_id}/bid/{bid_id}/cancel?x-lang=es",
        dry_run=dry_run,
    )


# ── COMPRAS A RIVALES (clausulazo) ───────────────────────────────────────────

def offer_rival(token: str, market_id: str, amount: int,
                dry_run: bool = True) -> Optional[dict]:
    """
    Ejecuta una oferta de clausulazo a un rival.
    amount debe ser >= market_value del jugador (regla de negocio).
    """
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}OFERTA RIVAL: market {market_id} por {amount/1e6:.2f}M€")
    return _post(
        token,
        f"/api/v1/competition/1/league/{LEAGUE_ID}/market/{market_id}/offer?x-lang=es",
        {"money": amount},
        dry_run=dry_run,
    )


def cancel_offer(token: str, market_id: str, offer_id: str,
                 dry_run: bool = True) -> bool:
    """Cancela una oferta a rival."""
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}CANCELAR OFERTA: market {market_id} offer {offer_id}")
    return _delete(
        token,
        f"/api/v1/competition/1/league/{LEAGUE_ID}/market/{market_id}/offer/{offer_id}/cancel?x-lang=es",
        dry_run=dry_run,
    )


# ── ALINEACIÓN ───────────────────────────────────────────────────────────────

def set_lineup(token: str, goalkeeper: str, defenders: list,
               midfielders: list, strikers: list, formation: list,
               dry_run: bool = True) -> Optional[dict]:
    """
    Guarda la alineación y formación.
    Todos los IDs son playerTeamId (los números largos tipo 20594518).
    formation: lista de 3 enteros [4,4,2], [4,3,3], [4,5,1], etc.

    Validaciones de seguridad:
    - goalkeeper: exactamente 1
    - sum(formation) debe ser 10 (outfield players)
    - len(defenders) == formation[0]
    - len(midfielders) == formation[1]
    - len(strikers) == formation[2]
    """
    # Validar formación
    if sum(formation) != 10:
        logger.error(f"Formación inválida: {formation} suma {sum(formation)}, debe ser 10")
        return None
    if len(defenders) != formation[0]:
        logger.error(f"Número de defensas incorrecto: {len(defenders)} vs {formation[0]}")
        return None
    if len(midfielders) != formation[1]:
        logger.error(f"Número de centros incorrecto: {len(midfielders)} vs {formation[1]}")
        return None
    if len(strikers) != formation[2]:
        logger.error(f"Número de delanteros incorrecto: {len(strikers)} vs {formation[2]}")
        return None

    body = {
        "goalkeeper": int(goalkeeper),
        "defender": [int(x) for x in defenders],
        "midfield": [int(x) for x in midfielders],
        "striker": [int(x) for x in strikers],
        "tactical_formation": formation,
    }

    logger.info(f"{'[DRY RUN] ' if dry_run else ''}ALINEACIÓN: {formation} - GK:{goalkeeper} DEF:{defenders} MID:{midfielders} STR:{strikers}")
    return _put(
        token,
        f"/api/v1/competition/1/teams/{TEAM_ID}/lineup?x-lang=es",
        body,
        dry_run=dry_run,
    )


# ── RECOMPENSA DIARIA (pendiente de verificar endpoint) ──────────────────────

def claim_daily_reward(token: str, dry_run: bool = True) -> Optional[dict]:
    """
    Recoge la recompensa diaria.
    PENDIENTE: endpoint no verificado aún.
    """
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}RECOMPENSA DIARIA: pendiente de verificar endpoint")
    return {"pending": True, "message": "Endpoint de recompensa diaria pendiente de verificar"}
