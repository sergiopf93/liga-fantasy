"""
Renovación automática del token de LaLiga Fantasy
usando el flujo ROPC (Resource Owner Password Credentials) de Azure B2C con Google OAuth.

PROBLEMA: El login es con Google, no con email/password directo.
El flujo ROPC estándar de B2C no funciona con proveedores externos (Google).

SOLUCIÓN: Usar el endpoint de token de LaLiga que vimos en el proxy
(/dsp/v3/token) con las cabeceras correctas para obtener un token anónimo,
y luego intentar el flujo de refresh con los parámetros del JWT capturado.

Parámetros extraídos del JWT real:
- tenant: 335316eb-f606-4361-bb86-35a7edcdcec1
- client_id (aud): af88bcff-1157-40a0-b579-030728aacf0b
- policy (acr): b2c_1a_5ulaip_parametrized_signin
- issuer: https://login.laliga.es/335316eb-.../v2.0/
"""
import requests
import json
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Parámetros extraídos del JWT real (verificados 03/09/2026)
TENANT_ID  = "335316eb-f606-4361-bb86-35a7edcdcec1"
CLIENT_ID  = "af88bcff-1157-40a0-b579-030728aacf0b"
POLICY     = "b2c_1a_5ulaip_parametrized_signin"
B2C_HOST   = "login.laliga.es"

# URL base del token endpoint de Azure B2C
TOKEN_URL = f"https://{B2C_HOST}/{TENANT_ID}/oauth2/v2.0/token?p={POLICY}"

HEADERS_APP = {
    "X-App": "Fantasy-iOS",
    "X-Version": "10.0.5",
    "X-Lang": "es",
    "accept": "*/*",
    "accept-language": "es-ES;q=1.0",
    "user-agent": "LaLigaFantasy/10.0.5 (com.lfp.laligafantasy; build:2; iOS 26.5.0) Alamofire/5.10.2",
}


def test_b2c_discovery():
    """Test 1: Verificar que el tenant B2C es accesible y tiene ROPC habilitado"""
    logger.info("=== TEST 1: Discovery endpoint Azure B2C ===")
    
    discovery_url = f"https://{B2C_HOST}/{TENANT_ID}/v2.0/.well-known/openid-configuration?p={POLICY}"
    
    try:
        r = requests.get(discovery_url, timeout=10)
        logger.info(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            logger.info(f"Token endpoint: {data.get('token_endpoint')}")
            logger.info(f"Grant types: {data.get('grant_types_supported', [])}")
            has_ropc = "password" in data.get("grant_types_supported", [])
            logger.info(f"ROPC habilitado: {has_ropc}")
            return data
        else:
            logger.error(f"Error: {r.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Error: {e}")
        return None


def test_ropc_login(email: str, password: str):
    """
    Test 2: Intentar login ROPC directo con email/password
    NOTA: Probablemente falle porque el login es con Google
    pero vale la pena intentarlo
    """
    logger.info("=== TEST 2: ROPC login con email/password ===")
    
    payload = {
        "grant_type": "password",
        "client_id": CLIENT_ID,
        "scope": f"openid {CLIENT_ID} offline_access",
        "username": email,
        "password": password,
        "response_type": "token id_token",
    }
    
    try:
        r = requests.post(TOKEN_URL, data=payload, timeout=15)
        logger.info(f"Status: {r.status_code}")
        data = r.json()
        
        if r.status_code == 200 and "access_token" in data:
            logger.info("✅ LOGIN EXITOSO con email/password")
            logger.info(f"Token expira en: {data.get('expires_in')} segundos")
            return data
        else:
            logger.warning(f"❌ Login fallido: {data.get('error')}: {data.get('error_description', '')[:200]}")
            return None
    except Exception as e:
        logger.error(f"Error: {e}")
        return None


def test_refresh_token(refresh_token: str):
    """
    Test 3: Renovar token usando refresh_token
    (Si conseguimos un refresh_token, esto funciona automáticamente)
    """
    logger.info("=== TEST 3: Refresh token ===")
    
    payload = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
        "scope": f"openid {CLIENT_ID} offline_access",
    }
    
    try:
        r = requests.post(TOKEN_URL, data=payload, timeout=15)
        logger.info(f"Status: {r.status_code}")
        data = r.json()
        
        if r.status_code == 200 and "access_token" in data:
            logger.info("✅ REFRESH EXITOSO")
            logger.info(f"Nuevo token expira en: {data.get('expires_in')} segundos")
            return data
        else:
            logger.warning(f"❌ Refresh fallido: {data.get('error')}: {data.get('error_description', '')[:200]}")
            return None
    except Exception as e:
        logger.error(f"Error: {e}")
        return None


def test_laliga_api_token():
    """
    Test 4: El endpoint /dsp/v3/token de LaLiga que vimos en el proxy
    Devuelve un token anónimo público - útil para datos sin auth
    """
    logger.info("=== TEST 4: LaLiga DSP token (público) ===")
    
    try:
        r = requests.get(
            "https://fantasy-api.llt-services.com/dsp/v3/token",
            headers=HEADERS_APP,
            timeout=10
        )
        logger.info(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            logger.info(f"Respuesta: {json.dumps(data)[:300]}")
            return data
        else:
            logger.warning(f"Respuesta: {r.text[:200]}")
            return None
    except Exception as e:
        logger.error(f"Error: {e}")
        return None


def test_current_token(token: str):
    """
    Test 5: Verificar que el token actual sigue siendo válido
    """
    logger.info("=== TEST 5: Validar token actual ===")
    
    try:
        r = requests.get(
            "https://fantasy-api.llt-services.com/api/v4/user/me",
            headers={**HEADERS_APP, "authorization": f"Bearer {token}"},
            params={"x-lang": "es"},
            timeout=10
        )
        logger.info(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            logger.info(f"✅ Token válido. Manager: {data.get('managerName')}")
            return True
        else:
            logger.warning(f"❌ Token inválido o caducado: {r.text[:100]}")
            return False
    except Exception as e:
        logger.error(f"Error: {e}")
        return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("TEST DE RENOVACIÓN AUTOMÁTICA DE TOKEN - LaLiga Fantasy")
    print("="*60 + "\n")

    # Test 1: Discovery
    discovery = test_b2c_discovery()
    print()

    # Test 2: ROPC (puede fallar si solo acepta Google)
    email    = os.environ.get("LALIGA_EMAIL", "sergio.pf93@gmail.com")
    password = os.environ.get("LALIGA_PASSWORD", "")
    
    if password:
        result = test_ropc_login(email, password)
        print()
    else:
        logger.info("=== TEST 2: Omitido (no hay LALIGA_PASSWORD configurado) ===\n")

    # Test 3: Refresh token (si existe)
    refresh = os.environ.get("LALIGA_REFRESH_TOKEN", "")
    if refresh:
        test_refresh_token(refresh)
        print()
    else:
        logger.info("=== TEST 3: Omitido (no hay LALIGA_REFRESH_TOKEN configurado) ===\n")

    # Test 4: Token público
    test_laliga_api_token()
    print()

    # Test 5: Token actual
    token = os.environ.get("LALIGA_TOKEN", "")
    if token:
        test_current_token(token)
    else:
        logger.info("=== TEST 5: Omitido (no hay LALIGA_TOKEN configurado) ===")

    print("\n" + "="*60)
    print("RESUMEN:")
    print("- Si Test 1 muestra 'password' en grant_types: ROPC está habilitado")
    print("- Si Test 2 funciona: login automático posible con email/password")  
    print("- Si Test 3 funciona: renovación automática posible con refresh_token")
    print("="*60)
