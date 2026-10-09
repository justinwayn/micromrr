"""
MicroMRR metrics engine — pure deterministic math, zero dependencies.
All money handled in integer cents. No LLM, no paid APIs.
"""
from __future__ import annotations

import time
from typing import Any

DAY = 86400
FREE_TIER_MRR_CENTS = 50_000  # $500 — free-forever cap


def _now() -> int:
    return int(time.time())


def active_statuses() -> set[str]:
    return {"active", "trialing", "past_due"}


def current_mrr_cents(subs: list[dict]) -> int:
    """MRR = sum of normalized monthly recurring across paying statuses."""
    return sum(s.get("mrr_cents", 0) for s in subs if s.get("status") in active_statuses())


def subscriber_count(subs: list[dict]) -> int:
    return sum(1 for s in subs if s.get("status") in active_statuses())


def _in_window(ts: int | None, start: int, end: int) -> bool:
    return ts is not None and start <= ts <= end


def movement(subs: list[dict], period_days: int = 30, now: int | None = None) -> dict:
    """
    MRR movement over the trailing `period_days`, derived from subscription
    lifecycle dates. Deterministic and explainable:
      new         — subs started in window
      expansion   — subs whose mrr_cents grew (previous_mrr_cents < mrr_cents)
      contraction — subs whose mrr_cents shrank
      churned     — subs canceled in window (their mrr at cancel time)
    """
    now = now or _now()
    start = now - period_days * DAY
    new_c = expansion_c = contraction_c = churned_c = 0
    for s in subs:
        if _in_window(s.get("started_at"), start, now):
            new_c += s.get("mrr_cents", 0)
        prev = s.get("previous_mrr_cents")
        cur = s.get("mrr_cents", 0)
        if prev is not None and prev != cur:
            if cur > prev:
                expansion_c += cur - prev
            else:
                contraction_c += prev - cur
        if _in_window(s.get("canceled_at"), start, now):
            churned_c += s.get("mrr_at_cancel_cents", cur)
    return {
        "new_cents": new_c,
        "expansion_cents": expansion_c,
        "contraction_cents": contraction_c,
        "churned_cents": churned_c,
        "net_cents": new_c + expansion_c - contraction_c - churned_c,
    }


def mrr_30d_ago_estimate(subs: list[dict], current: int, mov: dict) -> int:
    """Reconstruct MRR at start of window: current - net movement."""
    return max(0, current - mov["net_cents"])


def churn_rate(mov: dict, mrr_start_cents: int) -> float | None:
    """Revenue churn rate for the period. None when undefined (no starting MRR)."""
    if mrr_start_cents <= 0:
        return None
    return mov["churned_cents"] / mrr_start_cents


def ltv_cents(arpa_cents: int, churn: float | None) -> int | None:
    """LTV = ARPA / churn rate. None when churn is zero/undefined."""
    if churn is None or churn <= 0 or arpa_cents <= 0:
        return None
    return int(arpa_cents / churn)


def fmt_money(cents: int | None) -> str:
    if cents is None:
        return "—"
    sign = "-" if cents < 0 else ""
    c = abs(int(cents))
    return f"{sign}${c // 100:,}.{c % 100:02d}"


def fmt_pct(rate: float | None, digits: int = 1) -> str:
    if rate is None:
        return "—"
    return f"{rate * 100:.{digits}f}%"


def compute_dashboard(subs: list[dict], snapshots: list[dict] | None = None,
                      period_days: int = 30, now: int | None = None) -> dict[str, Any]:
    """Assemble everything the dashboard needs in one call."""
    now = now or _now()
    mrr = current_mrr_cents(subs)
    count = subscriber_count(subs)
    arpa = int(mrr / count) if count else 0
    mov = movement(subs, period_days, now)
    mrr_start = mrr_30d_ago_estimate(subs, mrr, mov)
    churn = churn_rate(mov, mrr_start)
    ltv = ltv_cents(arpa, churn)

    trend = build_trend(subs, snapshots or [], days=30, now=now)

    return {
        "as_of": now,
        "period_days": period_days,
        "mrr_cents": mrr,
        "mrr": fmt_money(mrr),
        "subscribers": count,
        "arpa_cents": arpa,
        "arpa": fmt_money(arpa),
        "movement_cents": mov,
        "movement": {k: fmt_money(v) for k, v in mov.items()},
        "mrr_start_cents": mrr_start,
        "churn_rate": churn,
        "churn_rate_display": fmt_pct(churn),
        "ltv_cents": ltv,
        "ltv": fmt_money(ltv),
        "free_tier": mrr <= FREE_TIER_MRR_CENTS,
        "free_tier_cap_cents": FREE_TIER_MRR_CENTS,
        "trend": trend,  # [{date, mrr_cents}]
    }


def build_trend(subs: list[dict], snapshots: list[dict], days: int = 30,
                now: int | None = None) -> list[dict]:
    """
    Daily MRR points for the trailing `days`. Prefers stored snapshots;
    backfills missing days by deterministically replaying subscription
    start/cancel dates (exact for demo data, approximate for live).
    """
    now = now or _now()
    by_day = {s["date"]: s["mrr_cents"] for s in snapshots if "date" in s}
    points: list[dict] = []
    for d in range(days, -1, -1):
        day_ts = now - d * DAY
        day_key = time.strftime("%Y-%m-%d", time.gmtime(day_ts))
        if day_key in by_day:
            mrr = by_day[day_key]
        else:
            mrr = _replay_mrr_at(subs, day_ts)
        points.append({"date": day_key, "mrr_cents": mrr})
    return points


def _replay_mrr_at(subs: list[dict], ts: int) -> int:
    """MRR as it was at timestamp ts, replaying start/cancel dates."""
    total = 0
    for s in subs:
        started = s.get("started_at")
        canceled = s.get("canceled_at")
        if started is None or started > ts:
            continue
        if canceled is not None and canceled <= ts:
            continue
        # contraction/expansion timing unknown in replay — use current mrr
        total += s.get("mrr_cents", 0)
    return total
