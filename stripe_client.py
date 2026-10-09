"""
MicroMRR Stripe client.

Two modes (env MICROMRR_MODE):
  demo — deterministic synthetic indie-SaaS data (~$287 MRR, under the $500 cap)
  live — read-only fetch from Stripe REST API via requests (no stripe lib needed)

Live mode needs MICROMRR_STRIPE_KEY = a Stripe RESTRICTED key with only
read permissions (Subscriptions: read). Never use a full secret key here.
"""
from __future__ import annotations

import os
import random
import time
from typing import Any

DAY = 86400


def get_mode() -> str:
    return os.environ.get("MICROMRR_MODE", "demo").strip().lower()


def get_subscriptions() -> tuple[list[dict], str]:
    """Returns (subscriptions, mode). Raises RuntimeError in live mode on API failure."""
    mode = get_mode()
    if mode == "live":
        return fetch_live_subscriptions(), "live"
    return generate_demo_subscriptions(), "demo"


# ---------------------------------------------------------------- demo data
def generate_demo_subscriptions(now: int | None = None) -> list[dict]:
    """Seeded, deterministic demo portfolio of a ~$287 MRR indie SaaS."""
    now = now or int(time.time())
    rng = random.Random(42)
    plans = [
        ("Starter", 900, "month"),
        ("Pro", 1900, "month"),
        ("Pro", 2900, "month"),
        ("Annual", 19000, "year"),
    ]
    subs: list[dict] = []
    # 16 historical subs: 12 active/past_due/trialing, 4 churned
    for i in range(16):
        name, amount, interval = plans[i % len(plans)]
        qty = 1 if rng.random() > 0.15 else 2
        mrr = _to_mrr_cents(amount, interval) * qty
        started = now - rng.randint(20, 400) * DAY
        status = "active"
        canceled_at = None
        mrr_at_cancel = None
        if i >= 12:  # 4 churned subs
            status = "canceled"
            canceled_at = now - rng.randint(3, 60) * DAY
            mrr_at_cancel = mrr
        elif i == 11:
            status = "past_due"
        elif i == 10:
            status = "trialing"
        sub = {
            "id": f"sub_demo{i:03d}",
            "customer": f"cus_demo{i:03d}",
            "customer_email": f"founder{i}@example.dev",
            "status": status,
            "plan": f"{name} ({interval})",
            "interval": interval,
            "quantity": qty,
            "mrr_cents": 0 if status == "canceled" else mrr,
            "started_at": started,
            "canceled_at": canceled_at,
            "mrr_at_cancel_cents": mrr_at_cancel,
            "previous_mrr_cents": None,
        }
        subs.append(sub)

    # Make 3 subs "new" (started in last 30d) and 1 churned recently
    for idx in (0, 1, 2):
        subs[idx]["started_at"] = now - rng.randint(2, 25) * DAY
    subs[12]["canceled_at"] = now - 9 * DAY  # recent churn
    # One expansion: Starter -> Pro mid-cycle
    subs[3]["previous_mrr_cents"] = _to_mrr_cents(900, "month")
    subs[3]["mrr_cents"] = _to_mrr_cents(1900, "month")
    subs[3]["plan"] = "Pro (month)"
    # One contraction: dropped a seat
    subs[4]["previous_mrr_cents"] = _to_mrr_cents(2900, "month") * 2
    subs[4]["mrr_cents"] = _to_mrr_cents(2900, "month")
    subs[4]["quantity"] = 1
    return subs


def _to_mrr_cents(unit_amount_cents: int, interval: str) -> int:
    if interval == "month":
        return unit_amount_cents
    if interval == "year":
        return unit_amount_cents // 12
    if interval == "week":
        return unit_amount_cents * 52 // 12
    if interval == "day":
        return unit_amount_cents * 30
    return unit_amount_cents


# ---------------------------------------------------------------- live mode
def fetch_live_subscriptions() -> list[dict]:
    import requests  # local import: only needed in live mode

    key = os.environ.get("MICROMRR_STRIPE_KEY", "").strip()
    if not key:
        raise RuntimeError("Live mode needs MICROMRR_STRIPE_KEY (a read-only restricted key).")
    if key.startswith("sk_live_") and not os.environ.get("MICROMRR_ALLOW_LIVE_KEY"):
        raise RuntimeError(
            "Refusing to use a full live secret key. Create a restricted key "
            "(Subscriptions: Read only) in the Stripe dashboard instead."
        )

    headers = {"Authorization": f"Bearer {key}"}
    subs: list[dict] = []
    starting_after: str | None = None
    for _ in range(20):  # max 2000 subs
        params: dict[str, Any] = {
            "status": "all",
            "limit": 100,
            "expand[]": ["data.items.data.price.product"],
        }
        if starting_after:
            params["starting_after"] = starting_after
        r = requests.get("https://api.stripe.com/v1/subscriptions",
                         headers=headers, params=params, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Stripe API error {r.status_code}: {r.text[:300]}")
        data = r.json()
        for s in data.get("data", []):
            subs.append(_normalize_stripe_sub(s))
        if not data.get("has_more"):
            break
        starting_after = data["data"][-1]["id"]
    return subs


def _normalize_stripe_sub(s: dict) -> dict:
    mrr = 0
    plan_label = "?"
    interval = "month"
    qty = 0
    for item in s.get("items", {}).get("data", []):
        price = item.get("price", {}) or {}
        unit = price.get("unit_amount") or 0
        rec = price.get("recurring", {}) or {}
        interval = rec.get("interval", "month")
        q = item.get("quantity") or 1
        qty += q
        mrr += _to_mrr_cents(unit, interval) * q
        prod = price.get("product", {}) or {}
        plan_label = prod.get("name") or price.get("nickname") or price.get("id", "?")
    status = s.get("status", "unknown")
    canceled_at = s.get("canceled_at")
    return {
        "id": s.get("id"),
        "customer": s.get("customer"),
        "customer_email": None,
        "status": status,
        "plan": f"{plan_label} ({interval})",
        "interval": interval,
        "quantity": qty,
        "mrr_cents": 0 if status == "canceled" else mrr,
        "started_at": s.get("start_date") or s.get("created"),
        "canceled_at": canceled_at,
        "mrr_at_cancel_cents": mrr if canceled_at else None,
        "previous_mrr_cents": None,  # expansion/contraction via snapshot diff
    }
