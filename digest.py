#!/usr/bin/env python3
"""
MicroMRR weekly digest — run from cron every Monday morning:

    0 8 * * 1 cd /path/to/app && ./.venv/bin/python digest.py

Config via env:
    MICROMRR_SMTP_HOST, MICROMRR_SMTP_PORT (default 587),
    MICROMRR_SMTP_USER, MICROMRR_SMTP_PASS,
    MICROMRR_DIGEST_TO  (recipient), MICROMRR_DIGEST_FROM (default user)

Without SMTP config it runs in dry-run: writes digest_preview.html
and prints the summary. Zero cost either way.
"""
from __future__ import annotations

import os
import smtplib
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db
import metrics
import stripe_client

DAY = 86400


def build_digest() -> dict:
    subs, mode = stripe_client.get_subscriptions()
    now = int(time.time())
    cur = metrics.compute_dashboard(subs, db.get_snapshots(), now=now)
    prev = metrics.compute_dashboard(subs, db.get_snapshots(), now=now - 7 * DAY)

    alerts: list[str] = []
    churned = [s for s in subs
               if s.get("canceled_at") and now - 7 * DAY <= s["canceled_at"] <= now]
    for s in churned:
        alerts.append(
            f"Churn: {s['plan']} ({metrics.fmt_money(s.get('mrr_at_cancel_cents', 0))}/mo) canceled."
        )
    if cur["churn_rate"] and cur["churn_rate"] >= 0.10:
        alerts.append(f"High churn: {cur['churn_rate_display']} revenue churn this period.")
    new_subs = [s for s in subs
                if s.get("started_at") and now - 7 * DAY <= s["started_at"] <= now]
    for s in new_subs:
        alerts.append(f"New: {s['plan']} ({metrics.fmt_money(s['mrr_cents'])}/mo) started.")

    return {
        "mode": mode,
        "week_of": time.strftime("%Y-%m-%d", time.gmtime(now - 7 * DAY)),
        "mrr": cur["mrr"],
        "mrr_delta": metrics.fmt_money(cur["mrr_cents"] - prev["mrr_cents"]),
        "subscribers": cur["subscribers"],
        "subs_delta": cur["subscribers"] - prev["subscribers"],
        "churn": cur["churn_rate_display"],
        "ltv": cur["ltv"],
        "arpa": cur["arpa"],
        "alerts": alerts,
    }


def render_html(d: dict) -> str:
    alerts = "".join(f"<li>{a}</li>" for a in d["alerts"]) or "<li>Quiet week — no churn, no surprises.</li>"
    return f"""<html><body style="font-family:sans-serif;max-width:600px;margin:auto">
<h2>MicroMRR weekly digest — week of {d['week_of']}</h2>
<table cellpadding="8">
<tr><td><b>MRR</b></td><td>{d['mrr']} <span style="color:{'green' if d['mrr_delta'].startswith('$') else 'red'}">({d['mrr_delta']})</span></td></tr>
<tr><td><b>Subscribers</b></td><td>{d['subscribers']} ({d['subs_delta']:+d})</td></tr>
<tr><td><b>Revenue churn</b></td><td>{d['churn']}</td></tr>
<tr><td><b>ARPA</b></td><td>{d['arpa']}</td></tr>
<tr><td><b>LTV</b></td><td>{d['ltv']}</td></tr>
</table>
<h3>Alerts</h3><ul>{alerts}</ul>
<p style="color:#888">Free until $500 MRR. Sent by MicroMRR ({d['mode']} mode).</p>
</body></html>"""


def send(d: dict) -> bool:
    host = os.environ.get("MICROMRR_SMTP_HOST", "").strip()
    to = os.environ.get("MICROMRR_DIGEST_TO", "").strip()
    if not host or not to:
        return False
    port = int(os.environ.get("MICROMRR_SMTP_PORT", "587"))
    user = os.environ.get("MICROMRR_SMTP_USER", "")
    pwd = os.environ.get("MICROMRR_SMTP_PASS", "")
    sender = os.environ.get("MICROMRR_DIGEST_FROM", user or "micromrr@localhost")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"MicroMRR weekly: {d['mrr']} MRR ({d['mrr_delta']})"
    msg["From"] = sender
    msg["To"] = to
    msg.attach(MIMEText(render_html(d), "html"))
    with smtplib.SMTP(host, port, timeout=30) as s:
        s.starttls()
        if user:
            s.login(user, pwd)
        s.sendmail(sender, [to], msg.as_string())
    return True


def main() -> int:
    d = build_digest()
    html = render_html(d)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "digest_preview.html")
    with open(out, "w") as f:
        f.write(html)
    print(f"MRR {d['mrr']} ({d['mrr_delta']}) | subs {d['subscribers']} | churn {d['churn']} | LTV {d['ltv']}")
    print(f"{len(d['alerts'])} alerts. Preview: {out}")
    if send(d):
        print("Digest emailed.")
    else:
        print("SMTP not configured — dry run only (set MICROMRR_SMTP_HOST + MICROMRR_DIGEST_TO).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
