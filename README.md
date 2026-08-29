# ⚽ LaLiga Fantasy — Herramienta de gestión

Sistema completo de análisis y automatización para **LaLiga Fantasy** (laligafantasy.relevo.com).

## Características

- 🔐 **Autenticación OAuth** con Google via Azure B2C (Playwright)
- 📊 **Dashboard web** con Chart.js y tema oscuro
- 🧠 **Análisis estratégico**: scoring de jugadores, oportunidades de mercado, riesgo de cláusula
- 📈 **Informes diarios** automáticos con recomendaciones personalizadas
- 🔔 **Notificaciones Telegram** de alertas y reportes
- 🗄️ **Base de datos local** SQLite con histórico de precios y puntuaciones
- 🤖 **GitHub Actions** para actualización automática y reportes diarios

---

## Inicio rápido

### 1. Instalar dependencias

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Autenticarse

```bash
python scripts/auth.py
```

Se abrirá un navegador. Haz login con Google en LaLiga Fantasy. El token se guardará en `.tokens.json`.

### 3. Configurar la liga

Edita `config/config.yaml` y rellena tu `league_id` (encuéntralo en la URL de tu liga).

```yaml
league_id: "TU_LEAGUE_ID_AQUI"
```

### 4. Actualizar datos

```bash
python scripts/update.py
```

### 5. Generar informe

```bash
# Solo consola
python scripts/generate_report.py

# Guardar a archivo
python scripts/generate_report.py --output informe.md

# Enviar por Telegram
python scripts/generate_report.py --telegram
```

### 6. Abrir el dashboard

Abre `frontend/index.html` en tu navegador. Necesita un servidor backend local en `localhost:8000`.

---

## Estructura del proyecto

```
liga-fantasy/
├── frontend/            # Dashboard web (HTML/CSS/JS + Chart.js)
├── backend/
│   ├── laliga/          # Cliente API, modelos, endpoints
│   ├── strategy/        # Scoring, mercado, rivales, cláusulas, porteros
│   ├── analysis/        # Informe diario, monitor de mercado
│   ├── notifications/   # Bot de Telegram
│   └── database/        # SQLite local
├── scripts/
│   ├── auth.py          # Login OAuth con Google
│   ├── refresh_token.py # Renovar token
│   ├── update.py        # Actualizar datos en BD
│   └── generate_report.py # Generar e enviar informe
├── tests/               # Tests unitarios (pytest)
├── config/config.yaml   # Configuración principal
└── .github/workflows/   # Automatización con GitHub Actions
```

---

## Configuración de Telegram (opcional)

1. Crea un bot en [@BotFather](https://t.me/BotFather) y obtén el token.
2. Obtén el `chat_id` de tu chat/grupo.
3. Añádelos en `config/config.yaml`:

```yaml
telegram:
  token: "123456:ABC-DEF..."
  chat_id: "-100123456789"
```

---

## GitHub Actions

### Secretos necesarios (Settings → Secrets and variables → Actions)

| Secret | Descripción |
|--------|-------------|
| `FANTASY_ACCESS_TOKEN` | Token de acceso de la API |
| `FANTASY_REFRESH_TOKEN` | Token de renovación |
| `TELEGRAM_TOKEN` | Token del bot de Telegram |
| `TELEGRAM_CHAT_ID` | ID del chat destino |

Los workflows se activarán automáticamente:
- **update.yml**: Cada hora (8:00-23:00 UTC), actualiza jugadores y mercado.
- **daily_report.yml**: Todos los días a las 10:00 Madrid, genera y envía el informe.

---

## Ejecutar tests

```bash
pytest tests/ -v
pytest tests/ -v --cov=backend
```

---

## API Reference

La API de LaLiga Fantasy usa:
- **Base URL**: `https://fantasy-api.llt-services.com`
- **Headers requeridos**: `X-App: Fantasy-web`, `X-Lang: es`, `Origin`, `Referer`
- **Auth**: Bearer token (JWT), duración ~24h
- **Token endpoint**: `GET /dsp/v3/token`
