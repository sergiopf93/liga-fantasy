#!/usr/bin/env python3
"""
Renueva el access_token usando el refresh_token guardado.

Uso:
  python scripts/refresh_token.py
  # O automáticamente desde otros scripts
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent
TOKENS_FILE = ROOT / ".tokens.json"

API_BASE = "https://fantasy-api.llt-services.com"
TOKEN_ENDPOINT = f"{API_BASE}/dsp/v3/token"

HEADERS = {
    "X-App": "Fantasy-web",
    "X-Lang": "es",
    "Origin": "https://laligafantasy.relevo.com",
    "Referer": "https://laligafantasy.relevo.com/",
}


def load_tokens() -> dict:
    # Prioridad: variable de entorno > archivo
    env_token = os.environ.get("FANTASY_ACCESS_TOKEN")
    if env_token:
        return {
            "access_token": env_token,
            "refresh_token": os.environ.get("FANTASY_REFRESH_TOKEN", ""),
        }

    if not TOKENS_FILE.exists():
        print(f"❌ No existe {TOKENS_FILE}. Ejecuta 'python scripts/auth.py' primero.")
        sys.exit(1)

    return json.loads(TOKENS_FILE.read_text(encoding="utf-8"))


def is_token_valid(tokens: dict, margin_hours: float = 1.0) -> bool:
    """Retorna True si el token se guardó hace menos de (24h - margin) horas."""
    saved_at = tokens.get("saved_at") or tokens.get("refreshed_at")
    if not saved_at:
        return False
    age_hours = (time.time() - saved_at) / 3600
    return age_hours < (24.0 - margin_hours)


def refresh(tokens: dict) -> dict:
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("❌ No hay refresh_token. Re-autentica con 'python scripts/auth.py'.")
        sys.exit(1)

    print("🔄 Renovando access_token...")
    resp = requests.get(
        TOKEN_ENDPOINT,
        headers={**HEADERS, "Authorization": f"Bearer {refresh_token}"},
        timeout=15,
    )

    if resp.status_code == 200:
        data = resp.json()
        tokens["access_token"] = data.get("access_token") or data.get("accessToken") or tokens["access_token"]
        if "refresh_token" in data or "refreshToken" in data:
            tokens["refresh_token"] = data.get("refresh_token") or data.get("refreshToken")
        tokens["refreshed_at"] = time.time()
        print("✅ Token renovado correctamente.")
        return tokens

    # Algunos servidores devuelven el token directamente en el GET del token endpoint
    # Intentar con POST como alternativa
    print(f"[warning] GET /token devolvió {resp.status_code}, probando POST...")
    resp2 = requests.post(
        TOKEN_ENDPOINT,
        headers=HEADERS,
        json={"refresh_token": refresh_token, "grant_type": "refresh_token"},
        timeout=15,
    )
    if resp2.ok:
        data2 = resp2.json()
        tokens["access_token"] = data2.get("access_token") or data2.get("accessToken") or tokens["access_token"]
        tokens["refreshed_at"] = time.time()
        print("✅ Token renovado (POST).")
        return tokens

    print(f"❌ No se pudo renovar el token ({resp.status_code}). Re-autentica con auth.py.")
    sys.exit(1)


def main() -> None:
    tokens = load_tokens()

    if is_token_valid(tokens):
        print("ℹ️  Token aún válido, no es necesario renovar.")
        return

    new_tokens = refresh(tokens)
    TOKENS_FILE.write_text(json.dumps(new_tokens, indent=2), encoding="utf-8")
    print(f"💾 Tokens actualizados en {TOKENS_FILE}")


if __name__ == "__main__":
    main()
