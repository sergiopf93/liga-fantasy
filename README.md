# Fantasy R.H. — Agente LaLiga Fantasy

Dashboard y agente de análisis para LaLiga Fantasy. Desplegado en GitHub Pages, actualizado automáticamente via GitHub Actions.

## Configuración inicial (una sola vez)

### 1. Sube el código al repositorio

```bash
cd liga-fantasy
git init
git remote add origin https://github.com/sergio.pf93/liga-fantasy.git
git add .
git commit -m "Setup inicial"
git push -u origin main
```

### 2. Activa GitHub Pages

- Ve a tu repositorio en GitHub
- Settings → Pages
- Source: **GitHub Actions**
- Guarda

### 3. Añade los GitHub Secrets

Ve a Settings → Secrets and variables → Actions → New repository secret.

Crea estos secrets exactamente con estos nombres:

| Secret | Valor |
|--------|-------|
| `LALIGA_TOKEN` | El token Bearer que obtuviste del proxy (el texto largo `eyJ...`) |
| `TEAM_ID` | `37889563` |
| `LEAGUE_ID` | `017948446` |
| `TELEGRAM_BOT_TOKEN` | (opcional, dejar vacío por ahora) |
| `TELEGRAM_CHAT_ID` | (opcional, dejar vacío por ahora) |

### 4. Primera ejecución manual

- Ve a Actions → "Informe diario 20:00"
- Pulsa "Run workflow"
- Espera ~1 minuto

### 5. Ver el dashboard

URL: `https://sergio.pf93.github.io/liga-fantasy`

---

## Renovar el token (cada ~30 días)

El token que obtuviste del proxy caduca. Cuando el dashboard deje de mostrar datos:

1. Repite el proceso con el proxy en el Mac
2. Copia el nuevo token Bearer
3. Ve a Settings → Secrets → `LALIGA_TOKEN` → Update

---

## Horarios de actualización automática

| Hora | Acción |
|------|--------|
| 12:00 | Actualización general |
| 20:00 | Informe completo pre-cierre |
| 20:15 | Vigilancia mercado |
| 20:30 | Vigilancia mercado |
| 20:45 | Vigilancia mercado |
| 20:55 | Revisión final |

---

## Estructura del proyecto

```
/
├── frontend/         # Dashboard HTML (GitHub Pages)
├── backend/
│   ├── laliga/       # Cliente API y modelos
│   └── strategy/     # Motor de análisis
├── scripts/          # Scripts ejecutados por Actions
├── config/           # Configuración
├── data/             # JSONs generados (leídos por el dashboard)
└── .github/workflows/
```

---

## Ajustar estrategia

Edita `config/config.yaml` para cambiar los pesos del motor de análisis:

```yaml
strategy_weights:
  revalorizacion: 0.35   # Peso del potencial de subida
  rendimiento: 0.25      # Peso de los puntos
  oportunidad: 0.20      # Peso de la oportunidad de mercado
  situacion: 0.15        # Peso del estado deportivo
```
