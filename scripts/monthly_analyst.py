"""
Analista mensual - Primer lunes del mes a las 20:00
Genera informe de evolución con prompt para ChatGPT
"""
import os, sys, json, logging
from datetime import datetime, date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR    = os.path.join(os.path.dirname(__file__), "../data")
HIST_DIR    = os.path.join(DATA_DIR, "history")
ACT_DIR     = os.path.join(DATA_DIR, "activity")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

TODAY = date.today()
MONTH = TODAY.strftime("%Y-%m")
TEAM_ID = os.environ.get("TEAM_ID", "37889563")


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return None


def get_all_snapshots():
    if not os.path.exists(HIST_DIR):
        return []
    snapshots = []
    for f in sorted(Path(HIST_DIR).glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].json")):
        data = load_json(str(f))
        if data:
            snapshots.append(data)
    return snapshots


def get_executed_actions():
    path = os.path.join(ACT_DIR, "executed_actions.json")
    data = load_json(path)
    return data.get("actions", []) if data else []


def fmt(v):
    return f"{v/1_000_000:.2f}M" if v else "0"


def analyze_patrimony(snapshots):
    if not snapshots:
        return {"error": "Sin datos"}

    first = snapshots[0]
    last  = snapshots[-1]

    my_first = first.get("my_team", {}).get("team_value", 0)
    my_last  = last.get("my_team", {}).get("team_value", 0)
    growth   = round((my_last - my_first) / my_first * 100, 2) if my_first else 0

    # Rivales
    rival_map = {}
    for snap in snapshots:
        for r in snap.get("rivals", []):
            mgr = r.get("manager", "")
            if mgr not in rival_map:
                rival_map[mgr] = {"first": r.get("team_value", 0), "last": 0, "points": 0}
            rival_map[mgr]["last"] = r.get("team_value", 0)
            rival_map[mgr]["points"] = r.get("points", 0)

    rivals = []
    for mgr, vals in rival_map.items():
        g = round((vals["last"] - vals["first"]) / vals["first"] * 100, 2) if vals["first"] else 0
        rivals.append({
            "manager": mgr,
            "first_value": vals["first"],
            "last_value": vals["last"],
            "growth_pct": g,
            "first_fmt": fmt(vals["first"]) + "M€",
            "last_fmt": fmt(vals["last"]) + "M€",
        })

    rivals.sort(key=lambda x: x["growth_pct"], reverse=True)

    return {
        "my_first_value": my_first,
        "my_last_value": my_last,
        "my_growth_pct": growth,
        "my_first_fmt": fmt(my_first) + "M€",
        "my_last_fmt": fmt(my_last) + "M€",
        "rivals": rivals,
        "period_start": snapshots[0].get("date", ""),
        "period_end": snapshots[-1].get("date", ""),
        "period_days": len(snapshots),
    }


def analyze_points(snapshots):
    if not snapshots:
        return {"error": "Sin datos"}

    first = snapshots[0]
    last  = snapshots[-1]

    my_first_pts = first.get("my_team", {}).get("points", 0)
    my_last_pts  = last.get("my_team", {}).get("points", 0)

    rival_map = {}
    for snap in snapshots:
        for r in snap.get("rivals", []):
            mgr = r.get("manager", "")
            if mgr not in rival_map:
                rival_map[mgr] = {"first": r.get("points", 0), "last": 0}
            rival_map[mgr]["last"] = r.get("points", 0)

    rivals = []
    for mgr, vals in rival_map.items():
        rivals.append({
            "manager": mgr,
            "first_points": vals["first"],
            "last_points": vals["last"],
            "points_gained": vals["last"] - vals["first"],
        })
    rivals.sort(key=lambda x: x["points_gained"], reverse=True)

    return {
        "my_first_points": my_first_pts,
        "my_last_points": my_last_pts,
        "my_points_gained": my_last_pts - my_first_pts,
        "my_position_start": first.get("my_position"),
        "my_position_end": last.get("my_position"),
        "rivals": rivals,
    }


def analyze_decisions(executed):
    if not executed:
        return {"total": 0, "by_result": {}, "success_rate_pct": 0, "actions": []}

    by_result = {}
    for a in executed:
        r = a.get("result", "unknown")
        by_result[r] = by_result.get(r, 0) + 1

    successful = by_result.get("won", 0) + by_result.get("sold", 0) + by_result.get("executed", 0)
    rate = round(successful / len(executed) * 100, 1) if executed else 0

    return {
        "total": len(executed),
        "by_result": by_result,
        "success_rate_pct": rate,
        "actions": executed,
    }


def generate_chatgpt_prompt(report):
    import json as _json
    pat = report.get("patrimony", {})
    period = pat.get("period_start", "") + " al " + pat.get("period_end", "")

    # Serializar datos clave del informe (sin campos voluminosos)
    data_summary = {
        "month": report.get("month", ""),
        "summary": report.get("summary", {}),
        "patrimony": report.get("patrimony", {}),
        "points": report.get("points", {}),
        "decisions": report.get("decisions", {}),
        "market": report.get("market", {}),
    }

    return (
        "# INSTRUCCIONES PARA CHATGPT — ANÁLISIS FANTASY LALIGA\n\n"
        "Eres un experto analista de Fantasy LaLiga. Analiza el informe mensual del período "
        + period + " y proporciona:\n\n"
        "## 1. ANÁLISIS GENERAL\n"
        "- Rendimiento global: patrimonio y puntos vs rivales\n"
        "- ¿La estrategia general fue correcta?\n\n"
        "## 2. ANÁLISIS DE DECISIONES\n"
        "- Evalúa cada decisión ejecutada y su resultado\n"
        "- ¿Las pujas fueron demasiado bajas? ¿Se vendió en el momento correcto?\n\n"
        "## 3. ANÁLISIS DE RIVALES\n"
        "- ¿Qué estrategias siguieron los más exitosos?\n"
        "- ¿Qué podemos aprender?\n\n"
        "## 4. RECOMENDACIONES PARA MEJORAR EL AGENTE\n"
        "- Cambios concretos en los pesos del motor de puntuación\n"
        "- ¿El umbral de venta del 15% es correcto?\n"
        "- Tabla resumen con las 3 principales mejoras recomendadas\n\n"
        "Responde en español. Sé específico con nombres y cifras.\n\n"
        "---\n## DATOS DEL INFORME:\n"
        + _json.dumps(data_summary, ensure_ascii=False, indent=2)
    )


def generate_html(report):
    s   = report.get("summary", {})
    pat = report.get("patrimony", {})
    pts = report.get("points", {})
    dec = report.get("decisions", {})
    month = report.get("month", "")
    prompt = generate_chatgpt_prompt(report)

    # CSS como string separado (sin f-string)
    css = (
        "body{font-family:-apple-system,Arial,sans-serif;font-size:13px;color:#1a1a1a;"
        "max-width:900px;margin:0 auto;padding:20px}"
        ".prompt-box{background:#f0f7ff;border:2px solid #1a73e8;border-radius:8px;"
        "padding:20px;margin-bottom:30px}"
        ".prompt-box h2{color:#1a73e8;margin-top:0}"
        ".prompt-content{background:#fff;border:1px solid #ddd;border-radius:6px;"
        "padding:15px;font-size:11px;white-space:pre-wrap;font-family:monospace;"
        "max-height:250px;overflow-y:auto}"
        "h1{font-size:22px;border-bottom:3px solid #1a73e8;padding-bottom:8px}"
        "h2{font-size:16px;margin-top:24px;border-bottom:1px solid #eee;padding-bottom:4px}"
        ".grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}"
        ".stat{background:#f6f8fa;padding:12px;border-radius:8px;text-align:center}"
        ".val{font-size:24px;font-weight:700}"
        ".lbl{font-size:11px;color:#666;margin-top:4px}"
        ".green{color:#2ea043}.red{color:#f85149}.blue{color:#1a73e8}"
        "table{width:100%;border-collapse:collapse;margin:12px 0;font-size:12px}"
        "th{background:#f6f8fa;padding:8px;text-align:left;border-bottom:2px solid #ddd}"
        "td{padding:7px 8px;border-bottom:1px solid #eee}"
    )

    # Filas de patrimonio
    pat_rows = ""
    for r in pat.get("rivals", []):
        is_me = r["manager"] == "Serpa93"
        color = "#2ea043" if r.get("growth_pct", 0) >= 0 else "#f85149"
        sign  = "+" if r.get("growth_pct", 0) >= 0 else ""
        star  = "⭐ " if is_me else ""
        bold  = "font-weight:bold;" if is_me else ""
        pat_rows += (
            "<tr style='" + bold + "'><td>" + star + r["manager"] + "</td>"
            "<td>" + r.get("first_fmt", "") + "</td>"
            "<td>" + r.get("last_fmt", "") + "</td>"
            "<td style='color:" + color + "'>" + sign + str(r.get("growth_pct", 0)) + "%</td></tr>"
        )

    # Filas de puntos
    pts_rows = ""
    for r in pts.get("rivals", []):
        is_me = r["manager"] == "Serpa93"
        star  = "⭐ " if is_me else ""
        bold  = "font-weight:bold;" if is_me else ""
        pts_rows += (
            "<tr style='" + bold + "'><td>" + star + r["manager"] + "</td>"
            "<td>" + str(r.get("first_points", "")) + "</td>"
            "<td>" + str(r.get("last_points", "")) + "</td>"
            "<td style='color:#1a73e8'>+" + str(r.get("points_gained", "")) + "</td></tr>"
        )

    # Filas de decisiones
    result_colors = {
        "won": "#2ea043", "sold": "#2ea043", "executed": "#2ea043",
        "lost": "#f85149", "unknown": "#666", "pending": "#d29922"
    }
    dec_rows = ""
    for a in dec.get("actions", []):
        color = result_colors.get(a.get("result", "unknown"), "#666")
        amount = a.get("amount", 0)
        dec_rows += (
            "<tr><td>" + str(a.get("executed_at", ""))[:10] + "</td>"
            "<td>" + a.get("action", "").upper() + "</td>"
            "<td>" + a.get("player_name", "") + "</td>"
            "<td>" + (str(round(amount/1e6, 2)) + "M€" if amount else "-") + "</td>"
            "<td style='color:" + color + "'>" + a.get("result", "?") + "</td>"
            "<td style='font-size:11px;color:#666'>" + a.get("result_detail", "") + "</td></tr>"
        )
    if not dec_rows:
        dec_rows = "<tr><td colspan='6' style='color:#666;text-align:center'>Sin decisiones registradas este período</td></tr>"

    g_pct  = s.get("patrimony_growth_pct", 0)
    g_color = "#2ea043" if g_pct >= 0 else "#f85149"
    g_sign  = "+" if g_pct >= 0 else ""
    pos_s   = str(s.get("position_start", "?"))
    pos_e   = str(s.get("position_end", "?"))

    html = (
        "<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'>"
        "<title>Informe Analista Fantasy RH - " + month + "</title>"
        "<style>" + css + "</style></head><body>"
        "<div class='prompt-box'>"
        "<h2>🤖 Instrucciones para ChatGPT</h2>"
        "<p style='font-size:12px;color:#666;margin-bottom:8px'>Copia este prompt y pégalo en ChatGPT junto con el informe:</p>"
        "<div class='prompt-content'>" + prompt + "</div></div>"
        "<h1>📊 Informe Analista Fantasy R.H.</h1>"
        "<div class='period'>Período: " + pat.get("period_start","") + " → " + pat.get("period_end","") + " · " + str(report.get("period_days",0)) + " días</div>"
        "<h2>Resumen ejecutivo</h2><div class='grid'>"
        "<div class='stat'><div class='val' style='color:" + g_color + "'>" + g_sign + str(g_pct) + "%</div><div class='lbl'>Crecimiento patrimonio</div></div>"
        "<div class='stat'><div class='val blue'>+" + str(s.get("points_gained",0)) + "</div><div class='lbl'>Puntos ganados</div></div>"
        "<div class='stat'><div class='val'>" + pos_s + "º → " + pos_e + "º</div><div class='lbl'>Posición en liga</div></div>"
        "<div class='stat'><div class='val'>" + pat.get("my_first_fmt","") + "</div><div class='lbl'>Patrimonio inicial</div></div>"
        "<div class='stat'><div class='val'>" + pat.get("my_last_fmt","") + "</div><div class='lbl'>Patrimonio final</div></div>"
        "<div class='stat'><div class='val green'>" + str(s.get("success_rate",0)) + "%</div><div class='lbl'>Tasa de éxito</div></div>"
        "</div>"
        "<h2>💰 Evolución patrimonial</h2>"
        "<table><tr><th>Manager</th><th>Inicial</th><th>Final</th><th>Crecimiento</th></tr>"
        + pat_rows + "</table>"
        "<h2>🏆 Evolución de puntos</h2>"
        "<table><tr><th>Manager</th><th>Puntos inicio</th><th>Puntos final</th><th>Ganados</th></tr>"
        + pts_rows + "</table>"
        "<h2>📋 Decisiones ejecutadas</h2>"
        "<table><tr><th>Fecha</th><th>Tipo</th><th>Jugador</th><th>Importe</th><th>Resultado</th><th>Detalle</th></tr>"
        + dec_rows + "</table>"
        "</body></html>"
    )
    return html


def generate_report():
    snapshots = get_all_snapshots()
    executed  = get_executed_actions()

    logger.info(f"Snapshots encontrados: {len(snapshots)}")

    patrimony = analyze_patrimony(snapshots)
    points    = analyze_points(snapshots)
    decisions = analyze_decisions(executed)

    s_pts  = points.get("my_points_gained", 0)
    s_pos1 = points.get("my_position_start")
    s_pos2 = points.get("my_position_end")

    report = {
        "generated_at": datetime.now().isoformat(),
        "month": MONTH,
        "period_days": len(snapshots),
        "summary": {
            "patrimony_growth_pct": patrimony.get("my_growth_pct", 0),
            "points_gained": s_pts,
            "position_start": s_pos1,
            "position_end": s_pos2,
            "decisions_executed": decisions.get("total", 0),
            "success_rate": decisions.get("success_rate_pct", 0),
        },
        "patrimony": patrimony,
        "points": points,
        "decisions": decisions,
    }

    # Guardar JSON
    report_path = os.path.join(REPORTS_DIR, "analyst_" + MONTH + ".json")
    with open(report_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    logger.info("JSON guardado: " + report_path)

    # Guardar HTML
    html_path = os.path.join(REPORTS_DIR, "analyst_" + MONTH + ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(generate_html(report))
    logger.info("HTML guardado: " + html_path)

    # Guardar prompt para ChatGPT
    prompt_path = os.path.join(REPORTS_DIR, "chatgpt_prompt_" + MONTH + ".txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(generate_chatgpt_prompt(report))
        f.write("\n\n---\n## DATOS JSON:\n")
        f.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    logger.info("Prompt ChatGPT guardado: " + prompt_path)

    # Actualizar latest
    latest_path = os.path.join(DATA_DIR, "analyst_latest.json")
    with open(latest_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    logger.info("Informe completado")
    return report


if __name__ == "__main__":
    report = generate_report()
    logger.info(f"Analista completado — período: {report['period_days']} días")
