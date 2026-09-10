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


if __name__ == "__main__":
    report = generate_report()
    logger.info(f"Analista completado — período: {report['period_days']} días")
