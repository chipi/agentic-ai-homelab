"""Langfuse dashboards + saved views for the homelab projects (rerunnable: same name = replaced).

podcast-prod — the podcast pipeline / player / summarizer through the prod gateway.
agents       — the homelab gateway: triage fleet, bugfix fleet, eval runs, other callers.
"""
import json
import sys

from lfui import B, login, project_ids, trpc

# Projects by NAME: their ids are per instance and are looked up at run time.
PROJECTS = ("podcast-prod", "agents")
TOKENIZE = "litellm-pass_through_endpoint"
NOT_MODEL = [TOKENIZE, "litellm-/v1/models", "litellm-/health"]


def f_none(col, vals):
    return {"type": "stringOptions", "column": col, "operator": "none of", "value": vals}


def f_any(col, vals):
    return {"type": "stringOptions", "column": col, "operator": "any of", "value": vals}


def f_contains(col, val):
    return {"type": "string", "column": col, "operator": "contains", "value": val}


GEN = {"type": "string", "column": "type", "operator": "=", "value": "GENERATION"}


def w(name, desc, view, dims, metric, agg, chart, filters, **cfg):
    return {"name": name, "description": desc, "view": view,
            "dimensions": [{"field": d} for d in dims], "metrics": [{"measure": metric, "agg": agg}],
            "filters": filters, "chartType": chart, "chartConfig": {"type": chart, **cfg}}


MODEL_CALLS = [GEN, f_none("name", NOT_MODEL)]

DASHBOARDS = {
    "podcast-prod": ("Podcast LLM traffic",
                     "Every model call the prod gateway made for the pipeline, player and board "
                     "summarizer. Model calls exclude /tokenize token counts (shown on their own).", [
        # row 1: the four numbers
        w("Model calls", "LLM generations (no token counts)", "observations", [], "count", "count", "NUMBER", MODEL_CALLS),
        w("Tokens", "Total tokens across model calls", "observations", [], "totalTokens", "sum", "NUMBER", MODEL_CALLS),
        w("Cost (USD)", "Gateway-priced cost; local DGX models cost 0", "observations", [], "totalCost", "sum", "NUMBER", MODEL_CALLS),
        w("Errors", "Generations at level ERROR", "observations", [], "count", "count", "NUMBER", [{"type": "stringOptions", "column": "level", "operator": "any of", "value": ["ERROR"]}]),
        # row 2
        w("Model calls by stage", "kg / gi / cleaning / summarization / storyline_summary / …", "observations", ["name"], "count", "count", "BAR_TIME_SERIES", MODEL_CALLS),
        w("Tokens by stage", "Where the tokens go", "observations", ["name"], "totalTokens", "sum", "HORIZONTAL_BAR", MODEL_CALLS, row_limit=15),
        # row 3
        w("p95 latency by stage (ms)", "Slowest stages", "observations", ["name"], "latency", "p95", "HORIZONTAL_BAR", MODEL_CALLS, row_limit=15),
        w("Calls by model", "Which models served the calls", "observations", ["providedModelName"], "count", "count", "PIE", MODEL_CALLS),
        # row 4
        w("Errors by stage", "Which stage failed", "observations", ["name"], "count", "count", "HORIZONTAL_BAR", [{"type": "stringOptions", "column": "level", "operator": "any of", "value": ["ERROR"]}], row_limit=15),
        w("Token counts (/tokenize) per day", "Not model calls: the pipeline's token counting through the gateway, kept on purpose", "observations", [], "count", "count", "BAR_TIME_SERIES", [f_any("name", [TOKENIZE])]),
        # row 5
        w("Traces by environment", "prod since the 2026-10-15 gateway deploy; default before", "traces", ["environment"], "count", "count", "PIE", []),
        w("Traces per day by name", "episode <id> traces (one per OTel trace) and the rest", "traces", ["name"], "count", "count", "BAR_TIME_SERIES", [f_none("name", NOT_MODEL)]),
    ]),
    "agents": ("Fleets & homelab gateway",
               "The homelab gateway's traffic: triage fleet decisions (one trace each, gateway turns "
               "inside), bugfix fleet, eval runs and other callers.", [
        w("Model calls", "LLM generations through the homelab gateway", "observations", [], "count", "count", "NUMBER", MODEL_CALLS),
        w("Cost (USD)", "Gateway-priced cost", "observations", [], "totalCost", "sum", "NUMBER", MODEL_CALLS),
        w("Triage decisions", "One trace per triage (triage-fleet/triage/<source>)", "traces", [], "count", "count", "NUMBER", [f_contains("name", "triage-fleet/triage")]),
        w("Errors", "Generations at level ERROR", "observations", [], "count", "count", "NUMBER", [{"type": "stringOptions", "column": "level", "operator": "any of", "value": ["ERROR"]}]),
        w("Cost by model per day", "Spend by upstream model", "observations", ["providedModelName"], "totalCost", "sum", "BAR_TIME_SERIES", MODEL_CALLS),
        w("Cost by call name", "triage-turn-N, litellm:<key>, eval …", "observations", ["name"], "totalCost", "sum", "HORIZONTAL_BAR", MODEL_CALLS, row_limit=15),
        w("Triage decisions per day by source", "glitchtip / grafana / …", "traces", ["name"], "count", "count", "BAR_TIME_SERIES", [f_contains("name", "triage-fleet/triage")]),
        w("Triage cost per decision (p95, USD)", "Trace cost, gateway turns included", "traces", ["name"], "totalCost", "p95", "HORIZONTAL_BAR", [f_contains("name", "triage-fleet/triage")], row_limit=10),
        w("Calls by model", "Which models served the calls", "observations", ["providedModelName"], "count", "count", "PIE", MODEL_CALLS),
        w("p95 latency by model (ms)", "Slowest upstreams", "observations", ["providedModelName"], "latency", "p95", "HORIZONTAL_BAR", MODEL_CALLS, row_limit=15),
        w("Traces by environment", "operations since the 2026-10-15 gateway change", "traces", ["environment"], "count", "count", "PIE", []),
        w("Calls per day by call name", "Volume by caller", "observations", ["name"], "count", "count", "BAR_TIME_SERIES", MODEL_CALLS),
    ]),
}

# (table, name, filters, orderBy, list procedure to verify with)
VIEWS = {
    "podcast-prod": [
        ("traces", "Model traces (no token counts)", [f_none("name", NOT_MODEL)], {"column": "timestamp", "order": "DESC"}),
        ("observations", "Model calls by stage", MODEL_CALLS, {"column": "startTime", "order": "DESC"}),
        ("observations", "Errors", [{"type": "stringOptions", "column": "level", "operator": "any of", "value": ["ERROR"]}], {"column": "startTime", "order": "DESC"}),
        ("observations", "Slowest calls", MODEL_CALLS, {"column": "latency", "order": "DESC"}),
        ("observations", "Storyline summaries", [GEN, f_any("name", ["storyline_summary"])], {"column": "startTime", "order": "DESC"}),
        ("observations", "Token counts (/tokenize)", [f_any("name", [TOKENIZE])], {"column": "startTime", "order": "DESC"}),
        ("sessions", "Pipeline runs", [], {"column": "createdAt", "order": "DESC"}),
    ],
    "agents": [
        ("traces", "Triage decisions", [f_contains("name", "triage-fleet/triage")], {"column": "timestamp", "order": "DESC"}),
        ("observations", "Triage turns (gateway, with cost)", [GEN, f_contains("name", "triage-turn")], {"column": "startTime", "order": "DESC"}),
        ("traces", "Gateway calls outside the fleets", [f_any("name", ["litellm-acompletion"])], {"column": "timestamp", "order": "DESC"}),
        ("observations", "Errors", [{"type": "stringOptions", "column": "level", "operator": "any of", "value": ["ERROR"]}], {"column": "startTime", "order": "DESC"}),
        ("observations", "Most expensive calls", MODEL_CALLS, {"column": "totalCost", "order": "DESC"}),
    ],
}

# 12-column grid, 4 per row for the numbers, then pairs.
LAYOUT = [(0, 0, 3, 2), (3, 0, 3, 2), (6, 0, 3, 2), (9, 0, 3, 2),
          (0, 2, 6, 5), (6, 2, 6, 5), (0, 7, 6, 5), (6, 7, 6, 5),
          (0, 12, 6, 5), (6, 12, 6, 5), (0, 17, 6, 5), (6, 17, 6, 5)]


def build(pkey, pid):
    title, desc, widgets = DASHBOARDS[pkey]
    existing = trpc("dashboard.allDashboards", {"projectId": pid, "page": 0, "limit": 100,
                                                "orderBy": {"column": "updatedAt", "order": "DESC"}}, mutation=False)
    for d in existing["dashboards"]:
        if d["projectId"] == pid and d["name"] == title:
            # Dashboard first: Langfuse refuses to delete a widget a dashboard still uses.
            trpc("dashboard.delete", {"projectId": pid, "dashboardId": d["id"]})
            for it in d["definition"].get("widgets", []):
                if it.get("widgetId"):
                    trpc("dashboardWidgets.delete", {"projectId": pid, "widgetId": it["widgetId"]})
            print(f"  replaced old '{title}'")
    dash = trpc("dashboard.createDashboard", {"projectId": pid, "name": title, "description": desc})
    did = dash["id"]
    items = []
    for i, spec in enumerate(widgets):
        wd = trpc("dashboardWidgets.create", {"projectId": pid, **spec})["widget"]
        x, y, xs, ys = LAYOUT[i]
        items.append({"type": "widget", "id": f"{did}-{i}", "widgetId": wd["id"], "x": x, "y": y, "x_size": xs, "y_size": ys})
    trpc("dashboard.updateDashboardDefinition", {"projectId": pid, "dashboardId": did, "definition": {"widgets": items}})
    print(f"  dashboard '{title}' {did}: {len(items)} widgets")

    for table, name, filters, order in VIEWS[pkey]:
        for p in trpc("TableViewPresets.getByTableName", {"projectId": pid, "tableName": table}, mutation=False):
            if p["name"] == name:
                trpc("TableViewPresets.delete", {"projectId": pid, "tableViewPresetsId": p["id"]})
        v = trpc("TableViewPresets.create", {"projectId": pid, "name": name, "tableName": table, "filters": filters,
                                              "columnOrder": [], "columnVisibility": {}, "orderBy": order, "searchQuery": ""})
        print(f"  view [{table}] '{name}' {v.get('id')}")
    return did


if __name__ == "__main__":
    login()
    ids = project_ids()
    wanted = sys.argv[1:] or list(PROJECTS)
    missing = [p for p in wanted if p not in ids]
    if missing:
        sys.exit(f"{B}: no project named {missing}; it has {sorted(ids)}. Create it first.")
    out = {}
    for pkey in wanted:
        print(f"{pkey} ({ids[pkey]}) on {B}")
        out[pkey] = build(pkey, ids[pkey])
    json.dump(out, open("built.json", "w"))
