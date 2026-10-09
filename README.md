# MicroMRR — MVP (prod_1791465489)

Free-forever revenue metrics for indie SaaS under $500 MRR.
Deterministic Stripe math. Zero paid APIs. Zero LLM calls.

## Run it

```bash
cd ~/workspace/agent-army/builds/prod_1791465489/app
./run.sh
```

Then open:
- **Landing:** http://127.0.0.1:8787/
- **Dashboard:** http://127.0.0.1:8787/dashboard
- **API:** http://127.0.0.1:8787/api/metrics

First run creates `.venv/` and installs `fastapi` + `uvicorn` (free, open source).

## Modes

| Mode | Env | What happens |
|---|---|---|
| `demo` (default) | — | Deterministic synthetic portfolio (~$287 MRR). Nothing leaves your machine. |
| `live` | `MICROMRR_MODE=live MICROMRR_STRIPE_KEY=rk_...` | Read-only fetch from Stripe REST API. Use a **restricted key** (Subscriptions: Read). Full `sk_live_` keys are refused unless `MICROMRR_ALLOW_LIVE_KEY=1` is set. |

## What's implemented

- **MRR engine** (`metrics.py`) — current MRR, new/expansion/contraction/churned breakdown, revenue churn rate, ARPA, LTV, 30-day trend (snapshot-backed, replay backfill)
- **Stripe client** (`stripe_client.py`) — demo generator + live fetch via `requests` (interval-normalized: month/year/week/day)
- **SQLite snapshots** (`db.py`) — daily rows power the trend; recorded lazily on first metrics hit each day
- **Dashboard** (`static/dashboard.html`) — cards, SVG trend chart, movement table, subscription list, free-tier banner (flips to $9/mo upsell over $500)
- **Landing page** (`static/landing.html`) — the brief's copy, CTA into the demo
- **Weekly digest** (`digest.py`) — cron-friendly; SMTP via env or dry-run to `digest_preview.html`

Cron example (Mondays 8am):

```
0 8 * * 1 cd ~/workspace/agent-army/builds/prod_1791465489/app && ./.venv/bin/python digest.py
```

## Before it can ship

1. **Stripe OAuth** — MVP uses restricted-key paste (documented, working). One-click OAuth needs a Stripe app + public redirect URL; the callback handler is the remaining ~40 lines.
2. **Customer email lookup** — live mode doesn't resolve `customer_email` (needs an extra expand); digest "who churned" alerts are plan-level until then.
3. **Auth** — no login yet; fine for self-hosted single founder, needed before multi-tenant hosting.
4. **Snapshot seeding for live users** — trend backfills by replay on day one; gets exact after ~30 days of daily snapshots.
5. **Host it** — Render free tier / Hugging Face Spaces / Oracle Always-Free all fit the zero-budget rule.
