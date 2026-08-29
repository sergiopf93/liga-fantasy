#!/usr/bin/env python3
"""
Autenticación con LaLiga Fantasy vía Google OAuth (Azure B2C).

Flujo:
  1. Abre el navegador con Playwright (modo visible).
  2. El usuario hace login con Google en la página de LaLiga Fantasy.
  3. Tras el login, el script captura el JWT de localStorage/cookies.
  4. Guarda el token en .tokens.json (gitignored).

Uso:
  python scripts/auth.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
TOKENS_FILE = ROOT / ".tokens.json"
FANTASY_URL = "https://laligafantasy.relevo.com/"
API_BASE = "https://fantasy-api.llt-services.com"


def check_playwright() -> None:
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        print("❌ Playwright no instalado. Ejecuta:")
        print("   pip install playwright")
        print("   playwright install chromium")
        sys.exit(1)


def get_token_from_storage(page) -> dict | None:
    """Intenta extraer el JWT del localStorage y sessionStorage."""
    for storage_type in ("localStorage", "sessionStorage"):
        try:
            keys = page.evaluate(f"Object.keys({storage_type})")
            for key in keys:
                value = page.evaluate(f"{storage_type}.getItem('{key}')")
                if not value:
                    continue
                # Buscar el access token
                if any(kw in key.lower() for kw in ("token", "auth", "access", "jwt", "msal")):
                    try:
                        parsed = json.loads(value)
                        if isinstance(parsed, dict):
                            # MSAL guarda tokens anidados
                            token = _extract_msal_token(parsed) or parsed.get("accessToken") or parsed.get("access_token")
                            if token:
                                print(f"✅ Token encontrado en {storage_type}[{key}]")
                                return {"access_token": token, "refresh_token": parsed.get("refreshToken", parsed.get("refresh_token", ""))}
                    except (json.JSONDecodeError, TypeError):
                        if len(value) > 100 and "." in value:
                            # Podría ser un JWT directo
                            return {"access_token": value, "refresh_token": ""}
        except Exception as e:
            print(f"[debug] Error leyendo {storage_type}: {e}")
    return None


def _extract_msal_token(data: dict) -> str | None:
    """Navega la estructura de caché MSAL para extraer el accessToken."""
    for key, value in data.items():
        if isinstance(value, dict):
            if "secret" in value and value.get("credentialType") == "AccessToken":
                return value["secret"]
            result = _extract_msal_token(value)
            if result:
                return result
    return None


def get_token_from_cookies(context) -> dict | None:
    """Busca tokens en las cookies del contexto del navegador."""
    cookies = context.cookies()
    for cookie in cookies:
        if any(kw in cookie["name"].lower() for kw in ("token", "auth", "access", "jwt")):
            if len(cookie["value"]) > 50:
                print(f"✅ Token encontrado en cookie: {cookie['name']}")
                return {"access_token": cookie["value"], "refresh_token": ""}
    return None


def wait_for_login(page, context, timeout: int = 180) -> dict | None:
    """
    Espera a que el usuario complete el login comprobando periódicamente
    si aparece un token en el almacenamiento.
    """
    print(f"\n⏳ Esperando login (máximo {timeout}s)...")
    deadline = time.time() + timeout
    while time.time() < deadline:
        # Verificar si ya estamos logueados (el dashboard carga)
        try:
            current_url = page.url
            if "laligafantasy.relevo.com" in current_url and "#" not in current_url and "login" not in current_url.lower():
                time.sleep(2)
                token = get_token_from_storage(page) or get_token_from_cookies(context)
                if token and token.get("access_token"):
                    return token
        except Exception:
            pass

        # Intentar capturar token de red (interceptando respuestas XHR)
        time.sleep(2)

    return None


def intercept_token_from_network(playwright_page) -> dict | None:
    """
    Alternativa: intercepta respuestas de red buscando el token.
    Se activa como listener antes de navegar.
    """
    captured = {}

    def handle_response(response):
        try:
            if API_BASE in response.url and response.status == 200:
                try:
                    body = response.json()
                    if isinstance(body, dict):
                        access = body.get("access_token") or body.get("accessToken") or body.get("token")
                        refresh = body.get("refresh_token") or body.get("refreshToken", "")
                        if access:
                            captured["access_token"] = access
                            captured["refresh_token"] = refresh
                            print(f"✅ Token capturado de respuesta de red: {response.url}")
                except Exception:
                    pass
        except Exception:
            pass

    playwright_page.on("response", handle_response)
    return captured


def run_auth() -> None:
    check_playwright()
    from playwright.sync_api import sync_playwright

    print("=" * 60)
    print("  LaLiga Fantasy — Autenticación con Google OAuth")
    print("=" * 60)
    print(f"\n🌐 Abriendo navegador en: {FANTASY_URL}")
    print("📋 Instrucciones:")
    print("   1. Haz clic en 'Entrar' y selecciona 'Google'")
    print("   2. Completa el login con tu cuenta de Google")
    print("   3. Una vez en el dashboard, el script capturará el token")
    print("   4. NO cierres el navegador hasta que veas el mensaje de éxito\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="es-ES",
        )
        page = context.new_page()

        # Configurar interceptor de red
        network_token: dict = {}

        def handle_response(response):
            try:
                if API_BASE in response.url and response.status == 200:
                    try:
                        body = response.json()
                        if isinstance(body, dict):
                            access = (
                                body.get("access_token")
                                or body.get("accessToken")
                                or body.get("token")
                            )
                            refresh = body.get("refresh_token") or body.get("refreshToken", "")
                            if access and not network_token.get("access_token"):
                                network_token["access_token"] = access
                                network_token["refresh_token"] = refresh
                                print(f"\n✅ Token capturado de red: ...{access[-20:]}")
                    except Exception:
                        pass
            except Exception:
                pass

        page.on("response", handle_response)

        try:
            page.goto(FANTASY_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"[warning] Error cargando página inicial: {e}")

        # Esperar hasta obtener el token (red o almacenamiento)
        deadline = time.time() + 180
        token = None

        while time.time() < deadline:
            if network_token.get("access_token"):
                token = network_token
                break

            # Intentar desde almacenamiento
            try:
                storage_token = get_token_from_storage(page)
                if storage_token and storage_token.get("access_token"):
                    token = storage_token
                    break
            except Exception:
                pass

            time.sleep(3)

        browser.close()

    if not token or not token.get("access_token"):
        print("\n❌ No se pudo capturar el token.")
        print("   Asegúrate de completar el login antes del timeout de 3 minutos.")

        # Modo manual como fallback
        print("\n🔑 Modo manual: Pega aquí tu access_token (del DevTools → Application → localStorage):")
        manual_token = input("access_token: ").strip()
        manual_refresh = input("refresh_token (opcional): ").strip()
        if not manual_token:
            sys.exit(1)
        token = {"access_token": manual_token, "refresh_token": manual_refresh}

    # Guardar tokens
    import time as _time
    token["saved_at"] = _time.time()
    TOKENS_FILE.write_text(json.dumps(token, indent=2), encoding="utf-8")
    print(f"\n✅ Token guardado en {TOKENS_FILE}")
    print("   Expira en ~24 horas. Usa 'python scripts/refresh_token.py' para renovarlo.")


if __name__ == "__main__":
    run_auth()
