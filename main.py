"""
MicroMRR — free-forever revenue metrics for indie SaaS under $500 MRR.
Run:  ./run.sh        (or: .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8787)
Then: http://127.0.0.1:8787/  (landing)  |  /dashboard  (metrics)
"""
from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

import db
import metrics
import stripe_client

BASE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(BASE, "static")

app = FastAPI(title="MicroMRR", version="0.1.0")


def _load() -> tuple[list[dict], str]:
    try:
        return stripe_client.get_subscriptions()
    except Exception as e:  # live-mode failures must never 500 the dashboard
        return [], f"error: {type(e).__name__}: {e}"


@app.get("/", include_in_schema=False)
def landing():
    return FileResponse(os.path.join(STATIC, "landing.html"))


@app.get("/dashboard", include_in_schema=False)
def dashboard():
    return FileResponse(os.path.join(STATIC, "dashboard.html"))


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "mode": stripe_client.get_mode(),
        "db": db.DB_PATH,
        "free_tier_cap_cents": metrics.FREE_TIER_MRR_CENTS,
        "time": int(time.time()),
    }


@app.get("/api/metrics")
def api_metrics():
    subs, mode = _load()
    if mode.startswith("error"):
        return JSONResponse({"ok": False, "error": mode}, status_code=502)
    dash = metrics.compute_dashboard(subs, db.get_snapshots())
    # lazy daily snapshot so the trend fills itself in
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if not any(s["date"] == today for s in db.get_snapshots(limit=2)):
        db.record_snapshot(dash["mrr_cents"], dash["subscribers"],
                           dash["movement_cents"]["churned_cents"])
    dash["ok"] = True
    dash["mode"] = mode
    dash["subscriptions"] = [
        {
            "id": s["id"],
            "plan": s["plan"],
            "status": s["status"],
            "mrr": metrics.fmt_money(s["mrr_cents"]),
            "mrr_cents": s["mrr_cents"],
        }
        for s in sorted(subs, key=lambda x: x.get("mrr_cents", 0), reverse=True)
    ]
    return dash


@app.post("/api/snapshot")
def api_snapshot():
    subs, mode = _load()
    if mode.startswith("error"):
        return JSONResponse({"ok": False, "error": mode}, status_code=502)
    dash = metrics.compute_dashboard(subs, db.get_snapshots())
    db.record_snapshot(dash["mrr_cents"], dash["subscribers"],
                       dash["movement_cents"]["churned_cents"])
    return {"ok": True, "recorded": True, "mrr_cents": dash["mrr_cents"]}
