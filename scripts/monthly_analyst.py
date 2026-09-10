"""
Analista mensual - Se ejecuta el primer lunes del mes a las 20:00
Genera informe completo de evolución y lo guarda como JSON + HTML para PDF
"""
import os, sys, json, logging
from datetime import datetime, date, timedelta
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR    = os.path.join(os.path.dirname(__file__), "../data")
HIST_DIR    = os.path.join(DATA_DIR, "history")
ACT_DIR     = os.path.join(DATA_DIR, "activity")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")

os.makedirs(REPORTS_DIR, exist_ok=True)

TODAY    = date.today()
MONTH    = TODAY.strftime("%Y-%m")
MY_TEAM  = os.environ.get("TEAM_ID", "37889563")


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None


def get_all_snapshots():
    """Lee todos los snapshots históricos ordenados por fecha."""
    snapshots = []
    if not os.path.exists(HIST_DIR):
        return snapshots
    for f in sorted(Path(HIST_DIR).glob("*.json")):
        data = load_json(str(f))
        if data:
            snapshots.append(data)
    return snapshots


def get_executed_actions():
    """Lee todas las acciones ejecutadas manualmente."""
    path = os.path.join(ACT_DIR, "executed_actions.json")
    data = load_json(path)
    return data.get("actions", []) if data else []


def analyze_patrimony(snapshots):
    """Analiza la evolución del patrimonio."""
    if len(snapshots) < 2:
        return {"error": "Insuficientes datos históricos"}

    first = snapshots[0]
    last  = snapshots[-1]

    my_first = first.get("my_team", {}).get("team_value", 0)
    my_last  = last.get("my_team", {}).get("team_value", 0)
    growth   = ((my_last - my_first) / my_first * 100) if my_first else 0

    # Evolución de rivales
    rival_growths = {}
    for snap in snapshots:
        for rival in snap.get("rivals", []):
            mgr = rival.get("manager", "")
            if mgr not in rival_growths:
                rival_growths[mgr] = {"first": rival.get("team_value", 0), "last": 0}
            rival_growths[mgr]["last"] = rival.get("team_value", 0)

    rival_analysis = []
    for mgr, vals in rival_growths.items():
        if vals["first"] > 0:
            g = (vals["last"] - vals["first"]) / vals["first"] * 100
            rival_analysis.append({
                "manager": mgr,
                "first_value": vals["first"],
                "last_value": vals["last"],
                "growth_pct": round(g, 2),
                "first_fmt": f"{vals['first']/1e6:.2f}M€",
                "last_fmt": f"{vals['last']/1e6:.2f}M€",
            })

    rival_analysis.sort(key=lambda x: x["growth_pct"], reverse=True)

    # Mi posición relativa
    my_rank = next((i+1 for i, r in enumerate(rival_analysis) if r["manager"] == "Serpa93"), None)

    return {
        "my_first_value": my_first,
        "my_last_value": my_last,
        "my_growth_pct": round(growth, 2),
        "my_first_fmt": f"{my_first/1e6:.2f}M€",
        "my_last_fmt": f"{my_last/1e6:.2f}M€",
        "my_rank_by_growth": my_rank,
        "rivals": rival_analysis,
        "period_days": len(snapshots),
        "period_start": snapshots[0].get("date", ""),
        "period_end": snapshots[-1].get("date", ""),
    }


def analyze_points(snapshots):
    """Analiza la evolución de puntos."""
    if len(snapshots) < 2:
        return {"error": "Insuficientes datos"}

    first = snapshots[0]
    last  = snapshots[-1]

    my_first_pts = first.get("my_team", {}).get("points", 0)
    my_last_pts  = last.get("my_team", {}).get("points", 0)
    pts_gained   = my_last_pts - my_first_pts
    my_pos_first = first.get("my_position")
    my_pos_last  = last.get("my_position")

    # Evolución de rivales por puntos
    rival_pts = {}
    for snap in snapshots:
        for rival in snap.get("rivals", []):
            mgr = rival.get("manager", "")
            if mgr not in rival_pts:
                rival_pts[mgr] = {"first": rival.get("points", 0), "last": 0}
            rival_pts[mgr]["last"] = rival.get("points", 0)

    rival_pts_analysis = []
    for mgr, vals in rival_pts.items():
        gained = vals["last"] - vals["first"]
        rival_pts_analysis.append({
            "manager": mgr,
            "points_gained": gained,
            "first_points": vals["first"],
            "last_points": vals["last"],
        })
    rival_pts_analysis.sort(key=lambda x: x["points_gained"], reverse=True)

    my_pts_rank = next((i+1 for i, r in enumerate(rival_pts_analysis) if r["manager"] == "Serpa93"), None)

    return {
        "my_first_points": my_first_pts,
        "my_last_points": my_last_pts,
        "my_points_gained": pts_gained,
        "my_position_start": my_pos_first,
        "my_position_end": my_pos_last,
        "position_change": (my_pos_first - my_pos_last) if my_pos_first and my_pos_last else None,
        "my_rank_by_points_gained": my_pts_rank,
        "rivals": rival_pts_analysis,
    }


def analyze_decisions(executed_actions):
    """Analiza las decisiones ejecutadas y sus resultados."""
    if not executed_actions:
        return {"total": 0, "actions": []}

    by_result = {"won": 0, "lost": 0, "sold": 0, "executed": 0, "unknown": 0, "pending": 0}
    for a in executed_actions:
        r = a.get("result", "unknown")
        by_result[r] = by_result.get(r, 0) + 1

    success_rate = 0
    total = len(executed_actions)
    if total > 0:
        successful = by_result.get("won", 0) + by_result.get("sold", 0) + by_result.get("executed", 0)
        success_rate = round(successful / total * 100, 1)

    return {
        "total": total,
        "by_result": by_result,
        "success_rate_pct": success_rate,
        "actions": executed_actions,
    }


def generate_report():
    snapshots = get_all_snapshots()
    executed  = get_executed_actions()

    patrimony = analyze_patrimony(snapshots)
    points    = analyze_points(snapshots)
    decisions = analyze_decisions(executed)

    report = {
        "generated_at": datetime.now().isoformat(),
        "month": MONTH,
        "period_days": len(snapshots),
        "summary": {
            "patrimony_growth_pct": patrimony.get("my_growth_pct", 0),
            "points_gained": points.get("my_points_gained", 0),
            "position_start": points.get("my_position_start"),
            "position_end": points.get("my_position_end"),
            "decisions_executed": decisions.get("total", 0),
            "success_rate": decisions.get("success_rate_pct", 0),
        },
        "patrimony": patrimony,
        "points": points,
        "decisions": decisions,
        "raw_snapshots_count": len(snapshots),
    }

    # Guardar JSON del informe
    report_path = os.path.join(REPORTS_DIR, f"analyst_{MONTH}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"Informe guardado: {report_path}")

    # Actualizar analyst_latest.json para el dashboard
    latest_path = os.path.join(DATA_DIR, "analyst_latest.json")
    with open(latest_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    logger.info("analyst_latest.json actualizado")

    return report


def generate_chatgpt_prompt(report: dict) -> str:
    """Genera el prompt optimizado para ChatGPT que va en la cabecera del PDF."""
    period = f"{report.get('patrimony', {}).get('period_start', '')} al {report.get('patrimony', {}).get('period_end', '')}"
    
    return f"""# INSTRUCCIONES PARA CHATGPT — ANÁLISIS FANTASY LALIGA

Eres un experto analista de Fantasy LaLiga. A continuación tienes el informe mensual completo de un gestor de equipo fantasy. Tu objetivo es:

## 1. ANÁLISIS GENERAL (resumen ejecutivo)
- Evalúa el rendimiento global del período {period}
- Compara la evolución patrimonial y de puntos vs el resto de managers de la liga
- Identifica si la estrategia general ha sido correcta o hay que cambiar el enfoque

## 2. ANÁLISIS DE DECISIONES
- Revisa cada decisión ejecutada y su resultado real (ganada/perdida/vendida)
- Identifica patrones: ¿las pujas fueron demasiado bajas? ¿se vendió en el momento correcto?
- Compara las decisiones que el agente recomendó pero NO se ejecutaron con lo que pasó después

## 3. ANÁLISIS DE MERCADO
- Revisa las oportunidades de mercado que hubo durante el período
- Identifica jugadores que subieron mucho de valor y si el agente los detectó o no
- ¿Hay algún tipo de jugador o posición que el agente infravalora sistemáticamente?

## 4. ANÁLISIS DE RIVALES
- ¿Qué estrategias siguieron los rivales más exitosos?
- ¿Compraron más barato, más caro, se centraron en alguna posición?
- ¿Qué podemos aprender de sus movimientos?

## 5. RECOMENDACIONES PARA MEJORAR EL AGENTE
- Sugiere cambios concretos en los pesos del motor de puntuación
- ¿El umbral de venta del 15% es correcto o debería ajustarse?
- ¿Hay tipos de jugadores que el agente debería priorizar más?
- Da recomendaciones específicas y accionables

## FORMATO DE RESPUESTA ESPERADO
Responde en español. Usa secciones claras. Sé específico con nombres de jugadores y cifras.
Al final incluye una tabla resumen con las 3 principales mejoras recomendadas para el agente.

---
## DATOS DEL INFORME:
"""


def generate_html_report(report: dict) -> str:
    """Genera el HTML del informe para convertir a PDF."""
    prompt = generate_chatgpt_prompt(report)
    s = report.get("summary", {})
    pat = report.get("patrimony", {})
    pts = report.get("points", {})
    dec = report.get("decisions", {})
    month = report.get("month", "")

    # Tabla de patrimonio
    pat_rows = ""
    for r in pat.get("rivals", []):
        is_me = "⭐" if r["manager"] == "Serpa93" else ""
        color = "#2ea043" if r["growth_pct"] >= 0 else "#f85149"
        pat_rows += f"""<tr style="{'font-weight:bold' if is_me else ''}">
            <td>{is_me} {r['manager']}</td>
            <td>{r.get('first_fmt','')}</td>
            <td>{r.get('last_fmt','')}</td>
            <td style="color:{color}">{'+' if r['growth_pct']>=0 else ''}{r['growth_pct']}%</td>
        </tr>"""

    # Tabla de puntos
    pts_rows = ""
    for r in pts.get("rivals", []):
        is_me = "⭐" if r["manager"] == "Serpa93" else ""
        pts_rows += f"""<tr style="{'font-weight:bold' if is_me else ''}">
            <td>{is_me} {r['manager']}</td>
            <td>{r.get('first_points','')}</td>
            <td>{r.get('last_points','')}</td>
            <td style="color:#1a73e8">+{r.get('points_gained','')}</td>
        </tr>"""

    # Tabla de decisiones
    dec_rows = ""
    result_colors = {"won":"#2ea043","sold":"#2ea043","executed":"#2ea043","lost":"#f85149","unknown":"#666","pending":"#d29922"}
    for a in dec.get("actions", []):
        color = result_colors.get(a.get("result","unknown"), "#666")
        dec_rows += f"""<tr>
            <td>{a.get('executed_at','')[:10]}</td>
            <td>{a.get('action','').upper()}</td>
            <td>{a.get('player_name','')}</td>
            <td>{a.get('amount',0)/1e6:.2f}M€</td>
            <td style="color:{color}">{a.get('result','?')}</td>
            <td style="font-size:11px;color:#666">{a.get('result_detail','')}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Informe Analista Fantasy RH - {month}</title>
<style>
  body {{ font-family: -apple-system, Arial, sans-serif; font-size: 13px; color: #1a1a1a; max-width: 900px; margin: 0 auto; padding: 20px; }}
  .prompt-box {{ background: #f0f7ff; border: 2px solid #1a73e8; border-radius: 8px; padding: 20px; margin-bottom: 30px; }}
  .prompt-box h2 {{ color: #1a73e8; margin-top: 0; }}
  .prompt-content {{ background: #fff; border: 1px solid #ddd; border-radius: 6px; padding: 15px; font-size: 12px; white-space: pre-wrap; font-family: monospace; max-height: 300px; overflow-y: auto; }}
  h1 {{ font-size: 22px; color: #1a1a1a; border-bottom: 3px solid #1a73e8; padding-bottom: 8px; }}
  h2 {{ font-size: 16px; color: #333; margin-top: 24px; border-bottom: 1px solid #eee; padding-bottom: 4px; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 16px 0; }}
  .stat {{ background: #f6f8fa; padding: 12px; border-radius: 8px; text-align: center; }}
  .stat-val {{ font-size: 24px; font-weight: 700; }}
  .stat-label {{ font-size: 11px; color: #666; margin-top: 4px; }}
  .green {{ color: #2ea043; }} .red {{ color: #f85149; }} .blue {{ color: #1a73e8; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 12px; }}
  th {{ background: #f6f8fa; padding: 8px; text-align: left; border-bottom: 2px solid #ddd; font-size: 11px; color: #666; text-transform: uppercase; }}
  td {{ padding: 7px 8px; border-bottom: 1px solid #eee; }}
  tr:hover {{ background: #fafafa; }}
  .period {{ color: #666; font-size: 13px; margin-bottom: 20px; }}
  @media print {{
    .prompt-box {{ page-break-after: always; }}
    body {{ padding: 10px; }}
  }}
</style>
</head>
<body>

<!-- PROMPT PARA CHATGPT -->
<div class="prompt-box">
  <h2>🤖 Instrucciones para ChatGPT</h2>
  <p style="font-size:12px;color:#666;margin-bottom:8px">Copia este prompt y pégalo en ChatGPT junto con el informe completo para obtener el análisis:</p>
  <div class="prompt-content">{prompt}</div>
</div>

<!-- INFORME -->
<h1>📊 Informe Analista Fantasy R.H.</h1>
<div class="period">Período: {pat.get('period_start','')} → {pat.get('period_end','')} · {report.get('period_days',0)} días analizados</div>

<h2>Resumen ejecutivo</h2>
<div class="summary-grid">
  <div class="stat">
    <div class="stat-val {'green' if s.get('patrimony_growth_pct',0)>=0 else 'red'}">{'+' if s.get('patrimony_growth_pct',0)>=0 else ''}{s.get('patrimony_growth_pct',0)}%</div>
    <div class="stat-label">Crecimiento patrimonio</div>
  </div>
  <div class="stat">
    <div class="stat-val blue">+{s.get('points_gained',0)}</div>
    <div class="stat-label">Puntos ganados</div>
  </div>
  <div class="stat">
    <div class="stat-val">{s.get('position_start','?')}º → {s.get('position_end','?')}º</div>
    <div class="stat-label">Posición en liga</div>
  </div>
  <div class="stat">
    <div class="stat-val">{pat.get('my_first_fmt','')}</div>
    <div class="stat-label">Patrimonio inicial</div>
  </div>
  <div class="stat">
    <div class="stat-val">{pat.get('my_last_fmt','')}</div>
    <div class="stat-label">Patrimonio final</div>
  </div>
  <div class="stat">
    <div class="stat-val green">{s.get('success_rate',0)}%</div>
    <div class="stat-label">Tasa de éxito operaciones</div>
  </div>
</div>

<h2>💰 Evolución patrimonial comparativa</h2>
<table>
  <tr><th>Manager</th><th>Valor inicial</th><th>Valor final</th><th>Crecimiento</th></tr>
  {pat_rows}
</table>

<h2>🏆 Evolución de puntos comparativa</h2>
<table>
  <tr><th>Manager</th><th>Puntos inicio</th><th>Puntos final</th><th>Ganados período</th></tr>
  {pts_rows}
</table>

<h2>📋 Detalle de decisiones ejecutadas</h2>
<table>
  <tr><th>Fecha</th><th>Tipo</th><th>Jugador</th><th>Importe</th><th>Resultado</th><th>Detalle</th></tr>
  {dec_rows if dec_rows else '<tr><td colspan="6" style="color:#666;text-align:center">Sin decisiones registradas este período</td></tr>'}
</table>

</body>
</html>"""


def generate_report():
    snapshots = get_all_snapshots()
    executed  = get_executed_actions()

    patrimony = analyze_patrimony(snapshots)
    points    = analyze_points(snapshots)
    decisions = analyze_decisions(executed)

    report = {{
        "generated_at": datetime.now().isoformat(),
        "month": MONTH,
        "period_days": len(snapshots),
        "summary": {{
            "patrimony_growth_pct": patrimony.get("my_growth_pct", 0),
            "points_gained": points.get("my_points_gained", 0),
            "position_start": points.get("my_position_start"),
            "position_end": points.get("my_position_end"),
            "decisions_executed": decisions.get("total", 0),
            "success_rate": decisions.get("success_rate_pct", 0),
        }},
        "patrimony": patrimony,
        "points": points,
        "decisions": decisions,
        "raw_snapshots_count": len(snapshots),
    }}

    # Guardar JSON
    report_path = os.path.join(REPORTS_DIR, f"analyst_{{MONTH}}.json")
    with open(report_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    # Guardar HTML (para PDF)
    html_path = os.path.join(REPORTS_DIR, f"analyst_{{MONTH}}.html")
    html_content = generate_html_report(report)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"HTML guardado: {{html_path}}")

    # Actualizar latest
    latest_path = os.path.join(DATA_DIR, "analyst_latest.json")
    with open(latest_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    # Guardar prompt para ChatGPT
    prompt_path = os.path.join(REPORTS_DIR, f"chatgpt_prompt_{{MONTH}}.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(generate_chatgpt_prompt(report))
        f.write("\n\n---\n## DATOS JSON COMPLETOS:\n")
        f.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    logger.info(f"Prompt ChatGPT guardado: {{prompt_path}}")

    logger.info(f"Informe completado")
    return report


if __name__ == "__main__":
    report = generate_report()
    logger.info(f"Analista completado — período: {{report['period_days']}} días")
