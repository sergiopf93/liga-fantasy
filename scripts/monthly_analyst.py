"""
Analista mensual - Primer lunes del mes a las 20:00
Genera informe completo con prompt enriquecido para ChatGPT
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

TODAY   = date.today()
MONTH   = TODAY.strftime("%Y-%m")
TEAM_ID = os.environ.get("TEAM_ID", "37889563")
MY_USER_ID = 1715449
MANAGER_NAME = "Serpa93"

# ── Reglas y estrategias implementadas en el agente ──────────────────────────
AGENT_RULES = {
    "scoring_weights": {
        "revalorizacion": 0.35,
        "tendencia_historica": 0.25,
        "rendimiento_deportivo": 0.20,
        "oportunidad_mercado": 0.15,
        "situacion_jugador": 0.10,
        "penalizacion_riesgo": 0.25,
    },
    "sell_rules": {
        "umbral_caida_proporcional_pct": 15,
        "vender_si_fuera_de_liga": True,
        "vender_si_lesionado_y_bajo_rendimiento": True,
        "score_minimo_para_venta": 40,
        "nunca_vender_portero_si_quedan_menos_de_2": True,
        "nunca_vender_sin_formacion_valida_posible": True,
    },
    "buy_rules": {
        "reserva_minima_euros": 3000000,
        "max_gasto_por_operacion_pct_presupuesto": 80,
        "score_minimo_para_compra": 50,
        "priorizar_jugadores_bajo_maximo_temporada": True,
        "no_comprar_lesionados_o_dudosos": True,
        "no_comprar_entrenadores": True,
    },
    "offer_rules": {
        "oferta_rival_minimo_valor_mercado": True,
        "clausulazo_precio_exacto_clausula": True,
    },
    "lineup_rules": {
        "excluir_lesionados_y_dudosos_como_titulares": True,
        "buscar_formacion_optima_por_puntos": True,
        "formaciones_validas": ["4-4-2","4-3-3","4-5-1","3-4-3","3-5-2","5-3-2","5-4-1"],
        "top_3_alineaciones_mostradas": True,
    },
    "protection_rules": {
        "minimo_porteros_plantilla": 2,
        "reserva_minima_presupuesto_euros": 3000000,
        "nunca_saldo_negativo": True,
        "verificar_formacion_viable_antes_vender": True,
    },
    "market_type_logic": {
        "sin_seller_es_subasta_mercado_general": True,
        "con_seller_es_clausulazo_precio_fijo": True,
    },
    "reward_rules": {
        "reclamar_recompensa_diaria_automaticamente": True,
        "horario_principal": "12:00",
        "horario_fallback": "20:00",
    },
    "schedule": {
        "actualizacion_manana": "07:00",
        "actualizacion_mediodia": "12:00",
        "informe_tarde": "20:00",
        "vigilancia_mercado": "20:15,20:30,20:45,20:55",
        "ajuste_alineacion": "jueves 22:00",
        "analista_mensual": "primer lunes del mes 20:00",
    }
}


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


def get_all_market_snapshots():
    if not os.path.exists(HIST_DIR):
        return []
    markets = []
    for f in sorted(Path(HIST_DIR).glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_market.json")):
        data = load_json(str(f))
        if data:
            markets.append(data)
    return markets


def get_all_activity():
    if not os.path.exists(ACT_DIR):
        return []
    activities = []
    for f in sorted(Path(ACT_DIR).glob("[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]_activity.json")):
        data = load_json(str(f))
        if data:
            activities.append(data)
    return activities


def get_executed_actions():
    path = os.path.join(ACT_DIR, "executed_actions.json")
    data = load_json(path)
    return data.get("actions", []) if data else []


def fmt(v):
    if not v:
        return "0M€"
    return str(round(v/1_000_000, 2)) + "M€"


def analyze_patrimony(snapshots):
    if not snapshots:
        return {"error": "Sin datos"}
    first = snapshots[0]
    last  = snapshots[-1]
    my_first = first.get("my_team", {}).get("team_value", 0)
    my_last  = last.get("my_team", {}).get("team_value", 0)
    growth   = round((my_last - my_first) / my_first * 100, 2) if my_first else 0

    rival_map = {}
    for snap in snapshots:
        for r in snap.get("rivals", []):
            mgr = r.get("manager", "")
            if mgr not in rival_map:
                rival_map[mgr] = {"first": r.get("team_value", 0), "last": 0}
            rival_map[mgr]["last"] = r.get("team_value", 0)

    rivals = []
    for mgr, vals in rival_map.items():
        g = round((vals["last"] - vals["first"]) / vals["first"] * 100, 2) if vals["first"] else 0
        rivals.append({
            "manager": mgr,
            "first_value": vals["first"],
            "last_value": vals["last"],
            "growth_pct": g,
            "first_fmt": fmt(vals["first"]),
            "last_fmt": fmt(vals["last"]),
        })
    rivals.sort(key=lambda x: x["growth_pct"], reverse=True)

    return {
        "my_first_value": my_first,
        "my_last_value": my_last,
        "my_growth_pct": growth,
        "my_first_fmt": fmt(my_first),
        "my_last_fmt": fmt(my_last),
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


def analyze_market_history(markets, snapshots, executed):
    """
    Cruza el historial de mercado con las decisiones del agente
    para identificar oportunidades aprovechadas y perdidas.
    """
    # Construir mapa de precios por jugador por día
    player_price_evolution = {}
    for market in markets:
        date_str = market.get("date", "")
        for p in market.get("subastas", []) + market.get("clausulazos", []):
            pid = p.get("player_id", "")
            if pid not in player_price_evolution:
                player_price_evolution[pid] = {
                    "name": p.get("nickname", ""),
                    "position": p.get("position", ""),
                    "prices": [],
                }
            player_price_evolution[pid]["prices"].append({
                "date": date_str,
                "sale_price": p.get("sale_price", 0),
                "market_value": p.get("market_value", 0),
                "score": p.get("score", 0),
                "type": p.get("market_type", ""),
            })

    # Jugadores con mayor subida de precio durante el período
    top_risers = []
    for pid, data in player_price_evolution.items():
        prices = data["prices"]
        if len(prices) >= 2:
            first_price = prices[0].get("market_value", 0)
            last_price  = prices[-1].get("market_value", 0)
            if first_price > 0:
                change = round((last_price - first_price) / first_price * 100, 1)
                top_risers.append({
                    "player_id": pid,
                    "name": data["name"],
                    "position": data["position"],
                    "first_value": first_price,
                    "last_value": last_price,
                    "change_pct": change,
                    "first_fmt": fmt(first_price),
                    "last_fmt": fmt(last_price),
                    "max_agent_score": max((p.get("score", 0) for p in prices), default=0),
                })
    top_risers.sort(key=lambda x: x["change_pct"], reverse=True)

    # Oportunidades perdidas: jugadores que subieron mucho y el agente detectó (score alto)
    # pero no se ejecutó la compra
    executed_player_ids = {a.get("player_id", "") for a in executed}
    missed_opportunities = [
        r for r in top_risers
        if r["change_pct"] > 5
        and r["max_agent_score"] >= 55
        and r["player_id"] not in executed_player_ids
    ][:10]

    return {
        "player_price_evolution_count": len(player_price_evolution),
        "top_risers": top_risers[:10],
        "missed_opportunities": missed_opportunities,
    }


def analyze_rival_strategies(snapshots, activities):
    """
    Analiza las estrategias de los rivales basándose en
    sus movimientos de mercado y evolución de plantilla.
    """
    rival_ops = {}
    for activity in activities:
        for op in activity.get("rival_activity", []):
            u1 = op.get("user1Id", 0)
            if u1 == MY_USER_ID:
                continue
            key = str(u1)
            if key not in rival_ops:
                rival_ops[key] = {
                    "user_id": u1,
                    "buys": 0,
                    "sells": 0,
                    "total_spent": 0,
                    "total_earned": 0,
                    "operations": [],
                }
            type_id = op.get("activityTypeId", 0)
            amount  = op.get("amount", 0)
            if type_id in (1, 31):
                rival_ops[key]["buys"] += 1
                rival_ops[key]["total_spent"] += amount
            elif type_id == 33:
                rival_ops[key]["sells"] += 1
                rival_ops[key]["total_earned"] += amount
            rival_ops[key]["operations"].append(op)

    # Enriquecer con nombre del manager desde snapshots
    manager_map = {}
    if snapshots:
        for r in snapshots[-1].get("rivals", []):
            manager_map[r.get("manager", "")] = r

    return {
        "rival_activity_summary": list(rival_ops.values()),
        "most_active_rivals": sorted(
            rival_ops.values(),
            key=lambda x: x["buys"] + x["sells"],
            reverse=True
        )[:5],
    }


def generate_chatgpt_prompt(report):
    pat  = report.get("patrimony", {})
    dec  = report.get("decisions", {})
    mkt  = report.get("market_analysis", {})
    rules = report.get("agent_rules", {})
    period = pat.get("period_start", "") + " al " + pat.get("period_end", "")

    missed = mkt.get("missed_opportunities", [])
    missed_txt = ""
    if missed:
        missed_txt = "\nOportunidades detectadas por el agente pero no ejecutadas:\n"
        for m in missed[:5]:
            missed_txt += (
                "- " + m["name"] + " (" + m["position"] + "): "
                "subió " + str(m["change_pct"]) + "% durante el período. "
                "Score agente: " + str(m["max_agent_score"]) + "/100\n"
            )

    actions_txt = ""
    if dec.get("actions"):
        actions_txt = "\nDecisiones ejecutadas por el usuario:\n"
        for a in dec["actions"][:10]:
            actions_txt += (
                "- " + a.get("action","").upper() + " " + a.get("player_name","") +
                " por " + fmt(a.get("amount",0)) +
                " → resultado: " + a.get("result","desconocido") +
                " (" + a.get("result_detail","") + ")\n"
            )

    rules_txt = json.dumps(rules, ensure_ascii=False, indent=2)

    prompt = (
        "# INSTRUCCIONES PARA CHATGPT — ANÁLISIS FANTASY LALIGA\n\n"
        "Eres un experto analista de Fantasy LaLiga. A continuación tienes el informe "
        "mensual completo del período " + period + " del manager Serpa93.\n\n"

        "## INFORMACIÓN DISPONIBLE EN ESTE INFORME\n\n"
        "Antes de analizar, ten en cuenta exactamente qué datos tienes disponibles:\n\n"
        "**1. HISTÓRICO DIARIO DE PATRIMONIO Y PUNTOS** (`budget_evolution`)\n"
        "Valor de plantilla, presupuesto disponible, puntos acumulados y posición en la "
        "clasificación para cada día del período. Te permite ver la evolución real día a día.\n\n"
        "**2. EVOLUCIÓN DE VALOR DE JUGADORES EN MI PLANTILLA** (`player_evolution`)\n"
        "Para cada jugador que tuve en plantilla: valor de mercado, cláusula, puntos de la "
        "jornada, media de puntos y estado (ok/lesionado/dudoso) en cada día del período. "
        "Con esto puedes ver si vendí en el momento correcto o si debería haber esperado.\n\n"
        "**3. HISTORIAL DE SUGERENCIAS DEL AGENTE** (`agent_suggestions_history`)\n"
        "Cada día: qué acciones recomendó el agente (comprar, vender, clausulazo), "
        "con qué prioridad, el motivo y el importe sugerido. "
        "Esto permite evaluar si el agente tomó buenas decisiones.\n\n"
        "**4. CRUCE SUGERENCIAS VS EJECUCIÓN VS REALIDAD** (`decision_analysis`)\n"
        "Para cada sugerencia del agente: si se ejecutó manualmente, el resultado "
        "(ganó la puja, la perdió, vendió bien), y si hubo actividad real en la liga "
        "con ese jugador al día siguiente. Es el dato más valioso para evaluar el agente.\n\n"
        "**5. OPERACIONES REALES DE TODA LA LIGA** (`all_league_operations`)\n"
        "Todas las compras, ventas, blindajes y clausulazos de todos los managers "
        "durante el período, con fecha, importe y jugador. "
        "Puedes ver qué hicieron los rivales y compararlo con mis decisiones.\n\n"
        "**6. EVOLUCIÓN DE RIVALES** (`rival_evolution`)\n"
        "Valor de plantilla y puntos de cada rival día a día. "
        "Permite identificar qué estrategias funcionaron mejor.\n\n"
        "**7. MERCADO DIARIO** (`market_evolution`)\n"
        "Los jugadores disponibles en el mercado cada día con su score del agente (0-100), "
        "precio de venta y valor de mercado. Permite identificar oportunidades que "
        "existieron y no se aprovecharon.\n\n"
        "**8. OPORTUNIDADES PERDIDAS** (calculado)\n"
        "Jugadores que el agente puntuó alto (score ≥55), estaban disponibles en el mercado, "
        "no se compraron, y que subieron de valor durante el período.\n\n"
        "**9. ACCIONES EJECUTADAS MANUALMENTE** (`executed_actions`)\n"
        "Las operaciones que el manager marcó como ejecutadas en la app, "
        "con el resultado real detectado por la actividad de la liga.\n\n"
        "**10. REGLAS ACTUALES DEL AGENTE** (`agent_rules`)\n"
        "Todos los pesos, umbrales y lógicas implementadas en el motor de decisiones. "
        "Son los parámetros que puedes sugerir modificar para mejorar el rendimiento.\n\n"
        "---\n\n"

        "## TU ANÁLISIS (basado exclusivamente en los datos anteriores)\n\n"
        "### 1. RESUMEN EJECUTIVO\n"
        "- Rendimiento global del período vs rivales (patrimonio y puntos)\n"
        "- Las 3 principales fortalezas y las 3 principales debilidades\n"
        "- Veredicto: ¿la estrategia general fue correcta?\n\n"

        "### 2. ANÁLISIS DE DECISIONES\n"
        "Usa `decision_analysis` para evaluar cada sugerencia del agente:\n"
        "- ¿Las sugerencias ejecutadas tuvieron buen resultado?\n"
        "- ¿Hay sugerencias no ejecutadas que habrían sido rentables?\n"
        "- ¿Las pujas fueron demasiado bajas? ¿Hay un patrón de pérdidas?\n"
        + actions_txt + "\n"

        "### 3. OPORTUNIDADES PERDIDAS\n"
        "Usa `market_evolution` y `missed_opportunities` para identificar:\n"
        "- Jugadores que el agente detectó pero no se compraron y que después subieron\n"
        "- Estima el impacto económico de no haberlos comprado\n"
        + missed_txt + "\n"

        "### 4. ESTRATEGIAS DE RIVALES\n"
        "Usa `all_league_operations` y `rival_evolution` para responder:\n"
        "- ¿Qué hicieron diferente los managers con mayor crecimiento patrimonial?\n"
        "- ¿Compraron más, vendieron más, o apostaron por jugadores específicos?\n"
        "- ¿Qué posiciones o perfiles de jugador resultaron más rentables?\n\n"

        "### 5. EVALUACIÓN DE REGLAS DEL AGENTE\n"
        "Usa `agent_rules` junto con los resultados del período para evaluar:\n\n"
        "```json\n" + rules_txt + "\n```\n\n"
        "Para cada regla que debería cambiar, indica exactamente:\n"
        "- **Regla:** nombre del parámetro\n"
        "- **Valor actual:** el valor que tiene ahora\n"
        "- **Valor sugerido:** el nuevo valor recomendado\n"
        "- **Justificación:** dato concreto del período que lo justifica\n\n"

        "### 6. TABLA DE MEJORAS PRIORITARIAS\n"
        "Cierra con una tabla de las 5 mejoras más importantes ordenadas por impacto esperado:\n"
        "| # | Área | Cambio | Impacto esperado | Urgencia |\n"
        "|---|------|--------|------------------|----------|\n\n"

        "## IMPORTANTE\n"
        "- Responde en español\n"
        "- Sé específico: usa nombres de jugadores, fechas y cifras reales del informe\n"
        "- No hagas suposiciones — si un dato no está en el informe, indícalo\n"
        "- Prioriza las recomendaciones por impacto económico esperado\n\n"
        "---\n"
        "## DATOS COMPLETOS DEL INFORME (JSON):\n"
    )
    return prompt


def generate_html(report):
    s    = report.get("summary", {})
    pat  = report.get("patrimony", {})
    pts  = report.get("points", {})
    dec  = report.get("decisions", {})
    mkt  = report.get("market_analysis", {})
    month = report.get("month", "")
    prompt = generate_chatgpt_prompt(report)

    css = (
        "body{font-family:-apple-system,Arial,sans-serif;font-size:13px;color:#1a1a1a;"
        "max-width:960px;margin:0 auto;padding:20px}"
        ".prompt-box{background:#f0f7ff;border:2px solid #1a73e8;border-radius:8px;"
        "padding:20px;margin-bottom:30px;page-break-after:always}"
        ".prompt-box h2{color:#1a73e8;margin-top:0}"
        ".prompt-content{background:#fff;border:1px solid #ddd;border-radius:6px;"
        "padding:15px;font-size:11px;white-space:pre-wrap;font-family:monospace;"
        "max-height:300px;overflow-y:auto}"
        "h1{font-size:22px;border-bottom:3px solid #1a73e8;padding-bottom:8px}"
        "h2{font-size:16px;margin-top:24px;border-bottom:1px solid #eee;padding-bottom:4px}"
        ".grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}"
        ".stat{background:#f6f8fa;padding:12px;border-radius:8px;text-align:center}"
        ".val{font-size:24px;font-weight:700}"
        ".lbl{font-size:11px;color:#666;margin-top:4px}"
        ".green{color:#2ea043}.red{color:#f85149}.blue{color:#1a73e8}.amber{color:#d29922}"
        "table{width:100%;border-collapse:collapse;margin:12px 0;font-size:12px}"
        "th{background:#f6f8fa;padding:8px;text-align:left;border-bottom:2px solid #ddd;"
        "font-size:11px;color:#666;text-transform:uppercase}"
        "td{padding:7px 8px;border-bottom:1px solid #eee}"
        ".rules-box{background:#fff8e1;border:1px solid #d29922;border-radius:8px;"
        "padding:16px;margin:12px 0;font-size:12px}"
        ".rules-box pre{margin:0;white-space:pre-wrap;font-size:11px}"
        ".missed{background:#fff0f0;border-left:3px solid #f85149;padding:8px 12px;"
        "margin:6px 0;border-radius:0 6px 6px 0;font-size:12px}"
    )

    # Filas patrimonio
    pat_rows = ""
    for r in pat.get("rivals", []):
        is_me = r["manager"] == MANAGER_NAME
        color = "#2ea043" if r.get("growth_pct", 0) >= 0 else "#f85149"
        sign  = "+" if r.get("growth_pct", 0) >= 0 else ""
        bold  = "font-weight:bold;" if is_me else ""
        star  = "⭐ " if is_me else ""
        pat_rows += (
            "<tr style='" + bold + "'>"
            "<td>" + star + r["manager"] + "</td>"
            "<td>" + r.get("first_fmt", "") + "</td>"
            "<td>" + r.get("last_fmt", "") + "</td>"
            "<td style='color:" + color + "'>" + sign + str(r.get("growth_pct", 0)) + "%</td>"
            "</tr>"
        )

    # Filas puntos
    pts_rows = ""
    for r in pts.get("rivals", []):
        is_me = r["manager"] == MANAGER_NAME
        bold  = "font-weight:bold;" if is_me else ""
        star  = "⭐ " if is_me else ""
        pts_rows += (
            "<tr style='" + bold + "'>"
            "<td>" + star + r["manager"] + "</td>"
            "<td>" + str(r.get("first_points", "")) + "</td>"
            "<td>" + str(r.get("last_points", "")) + "</td>"
            "<td style='color:#1a73e8'>+" + str(r.get("points_gained", "")) + "</td>"
            "</tr>"
        )

    # Filas decisiones
    result_colors = {
        "won":"#2ea043","sold":"#2ea043","executed":"#2ea043",
        "lost":"#f85149","unknown":"#666","pending":"#d29922"
    }
    dec_rows = ""
    for a in dec.get("actions", []):
        color  = result_colors.get(a.get("result", "unknown"), "#666")
        amount = a.get("amount", 0)
        dec_rows += (
            "<tr>"
            "<td>" + str(a.get("executed_at", ""))[:10] + "</td>"
            "<td>" + a.get("action", "").upper() + "</td>"
            "<td>" + a.get("player_name", "") + "</td>"
            "<td>" + (str(round(amount/1e6, 2)) + "M€" if amount else "-") + "</td>"
            "<td style='color:" + color + "'>" + a.get("result", "?") + "</td>"
            "<td style='font-size:11px;color:#666'>" + a.get("result_detail", "") + "</td>"
            "</tr>"
        )
    if not dec_rows:
        dec_rows = "<tr><td colspan='6' style='color:#666;text-align:center'>Sin decisiones registradas</td></tr>"

    # Oportunidades perdidas
    missed_html = ""
    for m in mkt.get("missed_opportunities", [])[:8]:
        sign = "+" if m.get("change_pct", 0) >= 0 else ""
        missed_html += (
            "<div class='missed'>"
            "<strong>" + m.get("name", "") + "</strong> (" + m.get("position", "") + ") — "
            "Subió <strong style='color:#f85149'>" + sign + str(m.get("change_pct", 0)) + "%</strong> · "
            "Score agente: <strong>" + str(m.get("max_agent_score", 0)) + "/100</strong> · " +
            m.get("first_fmt", "") + " → " + m.get("last_fmt", "") +
            "</div>"
        )
    if not missed_html:
        missed_html = "<p style='color:#666'>Sin oportunidades perdidas detectadas este período.</p>"

    # Top jugadores que subieron
    risers_rows = ""
    for r in mkt.get("top_risers", [])[:8]:
        sign  = "+" if r.get("change_pct", 0) >= 0 else ""
        color = "#2ea043" if r.get("change_pct", 0) >= 0 else "#f85149"
        risers_rows += (
            "<tr>"
            "<td>" + r.get("name", "") + "</td>"
            "<td>" + r.get("position", "") + "</td>"
            "<td>" + r.get("first_fmt", "") + "</td>"
            "<td>" + r.get("last_fmt", "") + "</td>"
            "<td style='color:" + color + "'>" + sign + str(r.get("change_pct", 0)) + "%</td>"
            "<td>" + str(r.get("max_agent_score", 0)) + "/100</td>"
            "</tr>"
        )
    if not risers_rows:
        risers_rows = "<tr><td colspan='6' style='color:#666;text-align:center'>Sin datos de mercado suficientes</td></tr>"

    g_pct   = s.get("patrimony_growth_pct", 0)
    g_color = "#2ea043" if g_pct >= 0 else "#f85149"
    g_sign  = "+" if g_pct >= 0 else ""

    rules_json = json.dumps(report.get("agent_rules", {}), ensure_ascii=False, indent=2)

    parts = []
    parts.append("<!DOCTYPE html><html lang='es'><head><meta charset='UTF-8'>")
    parts.append("<title>Informe Analista Fantasy RH - " + month + "</title>")
    parts.append("<style>" + css + "</style></head><body>")
    parts.append("<div class='prompt-box'>")
    parts.append("<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:8px'>")
    parts.append("<h2 style='margin:0'>🤖 Prompt para ChatGPT</h2>")
    parts.append("<button id='copy-btn' onclick='copyPrompt()' style='background:#1a73e8;color:#fff;border:none;border-radius:6px;padding:7px 16px;font-size:12px;font-weight:600;cursor:pointer'>📋 Copiar todo</button>")
    parts.append("</div>")
    parts.append("<p style='font-size:12px;color:#666;margin-bottom:8px'>Copia el prompt + datos y pégalo en ChatGPT:</p>")
    parts.append("<div id='prompt-text' class='prompt-content'>" + prompt + json.dumps(report, ensure_ascii=False, indent=2, default=str) + "</div>")
    parts.append("</div>")
    parts.append("<script>"
        "function copyPrompt(){"
        "  const text=document.getElementById('prompt-text').innerText;"
        "  navigator.clipboard.writeText(text).then(function(){"
        "    const btn=document.getElementById('copy-btn');"
        "    btn.textContent='\u2705 Copiado!';btn.style.background='#2ea043';"
        "    setTimeout(function(){btn.textContent='\U0001f4cb Copiar todo';btn.style.background='#1a73e8';},2500);"
        "  }).catch(function(){"
        "    const ta=document.createElement('textarea');"
        "    ta.value=text;ta.style.position='fixed';ta.style.opacity='0';"
        "    document.body.appendChild(ta);ta.select();document.execCommand('copy');document.body.removeChild(ta);"
        "    const btn=document.getElementById('copy-btn');"
        "    btn.textContent='\u2705 Copiado!';btn.style.background='#2ea043';"
        "    setTimeout(function(){btn.textContent='\U0001f4cb Copiar todo';btn.style.background='#1a73e8';},2500);"
        "  });"
        "}"
        "</script>")
    parts.append("<h1>📊 Informe Analista Fantasy R.H. — " + month + "</h1>")
    parts.append("<p style='color:#666'>Período: " + pat.get("period_start","") + " → " + pat.get("period_end","") + " · " + str(report.get("period_days",0)) + " días</p>")
    parts.append("<h2>Resumen ejecutivo</h2><div class='grid'>")
    parts.append("<div class='stat'><div class='val' style='color:" + g_color + "'>" + g_sign + str(g_pct) + "%</div><div class='lbl'>Crecimiento patrimonio</div></div>")
    parts.append("<div class='stat'><div class='val blue'>+" + str(s.get("points_gained",0)) + "</div><div class='lbl'>Puntos ganados</div></div>")
    parts.append("<div class='stat'><div class='val'>" + str(s.get("position_start","?")) + "º → " + str(s.get("position_end","?")) + "º</div><div class='lbl'>Posición en liga</div></div>")
    parts.append("<div class='stat'><div class='val'>" + pat.get("my_first_fmt","") + "</div><div class='lbl'>Patrimonio inicial</div></div>")
    parts.append("<div class='stat'><div class='val'>" + pat.get("my_last_fmt","") + "</div><div class='lbl'>Patrimonio final</div></div>")
    parts.append("<div class='stat'><div class='val green'>" + str(s.get("success_rate",0)) + "%</div><div class='lbl'>Tasa de éxito</div></div>")
    parts.append("</div>")
    parts.append("<h2>💰 Evolución patrimonial comparativa</h2>")
    parts.append("<table><tr><th>Manager</th><th>Valor inicial</th><th>Valor final</th><th>Crecimiento</th></tr>" + pat_rows + "</table>")
    parts.append("<h2>🏆 Evolución de puntos comparativa</h2>")
    parts.append("<table><tr><th>Manager</th><th>Puntos inicio</th><th>Puntos final</th><th>Ganados período</th></tr>" + pts_rows + "</table>")
    parts.append("<h2>📈 Jugadores con mayor subida de valor en el período</h2>")
    parts.append("<table><tr><th>Jugador</th><th>Posición</th><th>Valor inicial</th><th>Valor final</th><th>Subida</th><th>Score agente</th></tr>" + risers_rows + "</table>")
    parts.append("<h2>🎯 Oportunidades detectadas no aprovechadas</h2>" + missed_html)
    parts.append("<h2>📋 Decisiones ejecutadas por el manager</h2>")
    parts.append("<table><tr><th>Fecha</th><th>Tipo</th><th>Jugador</th><th>Importe</th><th>Resultado</th><th>Detalle</th></tr>" + dec_rows + "</table>")
    parts.append("<h2>⚙️ Reglas actuales del agente</h2>")
    parts.append("<div class='rules-box'><p style='color:#d29922;font-weight:600;margin-bottom:8px'>ChatGPT debe evaluar estas reglas y sugerir mejoras:</p>")
    parts.append("<pre>" + rules_json + "</pre></div>")
    # Datos en crudo para análisis IA
    raw = report.get("raw_data", {})

    # Decisiones del agente vs realidad
    dec_analysis_rows = ""
    for d in raw.get("decision_analysis", [])[:20]:
        executed_icon = "✅" if d.get("was_executed") else "❌"
        result = d.get("execution_result") or ("-" if not d.get("was_executed") else "?")
        real = "Sí" if d.get("real_activity_found") else "No"
        dec_analysis_rows += (
            "<tr>"
            "<td>" + d.get("suggested_date","") + "</td>"
            "<td>" + (d.get("action","")).upper() + "</td>"
            "<td>" + d.get("player_name","") + "</td>"
            "<td>" + d.get("suggested_amount_fmt","") + "</td>"
            "<td>" + str(d.get("priority","")) + "</td>"
            "<td style='text-align:center'>" + executed_icon + "</td>"
            "<td>" + result + "</td>"
            "<td>" + real + "</td>"
            "</tr>"
        )
    if not dec_analysis_rows:
        dec_analysis_rows = "<tr><td colspan='8' style='color:#666;text-align:center'>Sin sugerencias registradas</td></tr>"

    # Evolución de presupuesto
    budget_rows = ""
    for b in raw.get("budget_evolution", []):
        budget_rows += (
            "<tr>"
            "<td>" + b.get("date","") + "</td>"
            "<td>" + fmt(b.get("team_value",0)) + "</td>"
            "<td>" + fmt(b.get("budget",0)) + "</td>"
            "<td>" + str(b.get("points",0)) + "</td>"
            "<td>" + str(b.get("position","?")) + "º</td>"
            "</tr>"
        )

    parts.append("<h2>🔬 Datos en crudo para análisis IA</h2>")

    parts.append("<h3>Cruce: sugerencias del agente vs ejecución vs realidad</h3>")
    parts.append(
        "<table><tr><th>Fecha</th><th>Acción</th><th>Jugador</th><th>Importe</th>"
        "<th>Prioridad</th><th>Ejecutada</th><th>Resultado</th><th>Actividad real</th></tr>"
        + dec_analysis_rows + "</table>"
    )

    parts.append("<h3>Evolución diaria de mi equipo</h3>")
    parts.append(
        "<table><tr><th>Fecha</th><th>Valor plantilla</th><th>Presupuesto</th>"
        "<th>Puntos</th><th>Posición</th></tr>"
        + budget_rows + "</table>"
    )

    # Evolución de jugadores de mi plantilla
    parts.append("<h3>Evolución de valor de jugadores en plantilla</h3>")
    for player in raw.get("player_evolution", []):
        if len(player.get("history", [])) < 2:
            continue
        h = player["history"]
        first_val = h[0].get("market_value", 0)
        last_val  = h[-1].get("market_value", 0)
        change    = round((last_val - first_val) / first_val * 100, 1) if first_val else 0
        color     = "#2ea043" if change >= 0 else "#f85149"
        sign      = "+" if change >= 0 else ""
        parts.append(
            "<div style='display:flex;justify-content:space-between;padding:6px 0;"
            "border-bottom:1px solid #eee;font-size:12px'>"
            "<span><strong>" + player.get("name","") + "</strong> (" + player.get("position","") + ")</span>"
            "<span>" + fmt(first_val) + " → " + fmt(last_val) +
            " <strong style='color:" + color + "'>" + sign + str(change) + "%</strong></span>"
            "</div>"
        )

    parts.append("</body></html>")
    html = "".join(parts)
    return html


def collect_raw_data(snapshots, markets, activities, executed):
    """
    Recopila todos los datos en crudo para el análisis de IA.
    Incluye evolución de jugadores, acciones sugeridas, operaciones reales.
    """

    # 1. Evolución diaria de valores de jugadores en mi plantilla
    player_evolution = {}
    for snap in snapshots:
        date_str = snap.get("date", "")
        for p in snap.get("my_team", {}).get("players", []):
            pid  = p.get("id", "")
            name = p.get("nickname", "")
            if pid not in player_evolution:
                player_evolution[pid] = {"name": name, "position": p.get("position",""), "history": []}
            player_evolution[pid]["history"].append({
                "date": date_str,
                "market_value": p.get("market_value", 0),
                "market_value_fmt": p.get("market_value_fmt", ""),
                "buyout_clause": p.get("buyout_clause", 0),
                "week_points": p.get("week_points", 0),
                "average_points": p.get("average_points", 0),
                "status": p.get("status", "ok"),
            })

    # 2. Historial de acciones sugeridas por el agente cada día
    agent_suggestions_history = []
    for snap in snapshots:
        date_str = snap.get("date", "")
        agent = snap.get("agent_decisions", {})
        if agent.get("decisions"):
            agent_suggestions_history.append({
                "date": date_str,
                "summary": agent.get("summary", ""),
                "decisions": agent.get("decisions", []),
                "warnings": agent.get("warnings", []),
                "position_needs": agent.get("position_needs", []),
            })

    # 3. Historial completo de operaciones reales de la liga
    all_operations = []
    for activity in activities:
        date_str = activity.get("date", "")
        for op in activity.get("activity", []):
            all_operations.append({
                "date": date_str,
                **op
            })

    # 4. Evolución del presupuesto diario
    budget_evolution = []
    for snap in snapshots:
        budget_evolution.append({
            "date": snap.get("date", ""),
            "budget": snap.get("my_team", {}).get("budget", 0),
            "team_value": snap.get("my_team", {}).get("team_value", 0),
            "points": snap.get("my_team", {}).get("points", 0),
            "position": snap.get("my_position"),
        })

    # 5. Evolución de presupuesto de rivales
    rival_evolution = {}
    for snap in snapshots:
        for r in snap.get("rivals", []):
            mgr = r.get("manager", "")
            if mgr not in rival_evolution:
                rival_evolution[mgr] = []
            rival_evolution[mgr].append({
                "date": snap.get("date", ""),
                "team_value": r.get("team_value", 0),
                "points": r.get("points", 0),
            })

    # 6. Jugadores en mercado cada día con score del agente
    market_evolution = []
    for market in markets:
        market_evolution.append({
            "date": market.get("date", ""),
            "subastas_count": len(market.get("subastas", [])),
            "clausulazos_count": len(market.get("clausulazos", [])),
            "top_scored": sorted(
                market.get("subastas", []) + market.get("clausulazos", []),
                key=lambda x: x.get("score", 0),
                reverse=True
            )[:5],
        })

    # 7. Cruce: sugerencias del agente vs operaciones reales vs resultado
    decision_analysis = []
    for suggestion_day in agent_suggestions_history:
        date_str = suggestion_day["date"]
        for dec in suggestion_day.get("decisions", []):
            # Buscar si se ejecutó
            executed_match = next(
                (e for e in executed
                 if e.get("player_id") == dec.get("player_id")
                 and e.get("action") == dec.get("action")),
                None
            )
            # Buscar actividad real del día siguiente
            next_day_activity = next(
                (a for a in all_operations
                 if a.get("date", "") > date_str
                 and str(a.get("playerMasterId", "")) == str(dec.get("player_id", ""))),
                None
            )
            decision_analysis.append({
                "suggested_date": date_str,
                "action": dec.get("action"),
                "player_name": dec.get("player_name"),
                "player_id": dec.get("player_id"),
                "suggested_amount": dec.get("amount", 0),
                "suggested_amount_fmt": dec.get("amount_fmt", ""),
                "priority": dec.get("priority"),
                "reason": dec.get("reason"),
                "was_executed": executed_match is not None,
                "execution_result": executed_match.get("result") if executed_match else None,
                "real_activity_found": next_day_activity is not None,
                "real_activity": next_day_activity,
            })

    return {
        "player_evolution": list(player_evolution.values()),
        "agent_suggestions_history": agent_suggestions_history,
        "all_league_operations": all_operations,
        "budget_evolution": budget_evolution,
        "rival_evolution": rival_evolution,
        "market_evolution": market_evolution,
        "decision_analysis": decision_analysis,
        "executed_actions": executed,
    }


def generate_report():
    snapshots  = get_all_snapshots()
    markets    = get_all_market_snapshots()
    activities = get_all_activity()
    executed   = get_executed_actions()

    logger.info(f"Snapshots: {len(snapshots)}, Mercados: {len(markets)}, Actividades: {len(activities)}")

    patrimony       = analyze_patrimony(snapshots)
    points          = analyze_points(snapshots)
    decisions       = analyze_decisions(executed)
    market_analysis  = analyze_market_history(markets, snapshots, executed)
    rival_strategies = analyze_rival_strategies(snapshots, activities)
    raw_data         = collect_raw_data(snapshots, markets, activities, executed)

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
        "market_analysis": market_analysis,
        "rival_strategies": rival_strategies,
        "agent_rules": AGENT_RULES,
        "raw_data": raw_data,
    }

    # JSON
    report_path = os.path.join(REPORTS_DIR, "analyst_" + MONTH + ".json")
    with open(report_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    logger.info("JSON: " + report_path)

    # HTML
    html_path = os.path.join(REPORTS_DIR, "analyst_" + MONTH + ".html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(generate_html(report))
    logger.info("HTML: " + html_path)

    # Prompt TXT
    prompt_path = os.path.join(REPORTS_DIR, "chatgpt_prompt_" + MONTH + ".txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(generate_chatgpt_prompt(report))
        f.write("\n\n---\n## DATOS JSON COMPLETOS:\n")
        f.write(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    logger.info("Prompt: " + prompt_path)

    # Latest
    latest_path = os.path.join(DATA_DIR, "analyst_latest.json")
    with open(latest_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"Analista completado — {len(snapshots)} días, {len(markets)} mercados, {len(activities)} actividades")
    return report


if __name__ == "__main__":
    report = generate_report()
