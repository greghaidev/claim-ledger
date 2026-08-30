#!/usr/bin/env python3
"""or_budget.py — a CUMULATIVE per-surface OpenRouter budget that ends in a check-in.

A default cumulative ceiling per surface, per session. At the ceiling it stops and asks for
an estimate of what finishing costs, rather than failing or silently continuing.

WHY CUMULATIVE, NOT PER-RUN — this is the whole design, and it is measured, not assumed.
Across 414 real invocations harvested from the session transcripts: median $0.057, p90 $0.61,
and exactly ONE call ever exceeded $3. On the account's two worst days:

    2026-07-29   $37.87 across 31 runs   largest single $2.53   runs a $3/run cap stops: 0
    2026-07-30   $16.45 across 33 runs   largest single $2.39   runs a $3/run cap stops: 0

The account never drained on an expensive call. It drained on thirty cheap ones in a day — the
nine-heavy-round gate grind was $0.51 a round, nowhere near any plausible per-run ceiling. So a
per-invocation cap is the wrong axis: it would have caught 1 of 414 calls and none of the damage.
This budget accumulates over (surface, session), which on 2026-07-29 would have tripped after
about six runs instead of thirty-one.

WHY A CHECK-IN, NOT A HARD STOP. Hitting the ceiling is not an error and not a failure — it is
the designed moment where the operator is told what was bought, what it cost, and what finishing
would cost, and raises the ceiling once. So BudgetExceeded carries the whole briefing, not just
a number.

FAIL-OPEN, LOUDLY. An unreadable or corrupt ledger warns on stderr and allows the dispatch. A
budget that turns its own malfunction into a work stoppage is worse than one that admits it
cannot measure. If you need a hard pre-flight cap, put one in front of this.
"""
from __future__ import annotations

import json
import os
import sys

DEFAULT_BUDGET_USD = 3.00

# `caller` values written into the ledger by or_peer.record_dispatch.
SURFACES = ("claim_ledger",)


class BudgetExceeded(Exception):
    """Cumulative spend for this surface+session has reached the ceiling. Carries the check-in."""


def _ledger_path():
    # Resolved by or_peer so there is exactly one answer, anchored to the main checkout.
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import or_peer
        return or_peer.spend_log_path()
    except Exception:
        return os.environ.get("OR_SPEND_LOG") or ""


def session_id(explicit=None):
    return (explicit or os.environ.get("CLAUDE_CODE_SESSION_ID")
            or os.environ.get("CLAUDE_SESSION_ID") or "")


def budget_usd(explicit=None):
    """Explicit argument > $OR_BUDGET_USD > $3.00. A value <= 0 means 'no ceiling'."""
    if explicit is not None:
        # Never let a junk ceiling crash a dispatch. Callers pass this straight through from
        # argparse namespaces (and, in tests, from Mocks); a budget gate that raises on its own
        # input is a worse failure than one that falls back to the documented default.
        try:
            return float(explicit)
        except (TypeError, ValueError):
            print(f"or_budget: ignoring unusable budget {explicit!r}; using the default",
                  file=sys.stderr)
    env = os.environ.get("OR_BUDGET_USD")
    if env:
        try:
            return float(env)
        except ValueError:
            print(f"or_budget: ignoring unparseable OR_BUDGET_USD={env!r}", file=sys.stderr)
    return DEFAULT_BUDGET_USD


def _rows(caller, session):
    path = _ledger_path()
    if not path or not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except (ValueError, TypeError):
                    # One malformed line is not a reason to stop work OR to silently
                    # under-count — say so and keep reading.
                    print("or_budget: skipping a malformed ledger line", file=sys.stderr)
                    continue
                if rec.get("caller") != caller:
                    continue
                if session and rec.get("session") not in (None, "", session):
                    continue
                out.append(rec)
    except OSError as e:
        print(f"or_budget: cannot read the spend ledger ({e}) — budget NOT enforced this run",
              file=sys.stderr)
        return []
    return out


def spent(caller, session=None):
    """Cumulative USD this surface has spent in this session. Unmeasurable -> 0.0, loudly."""
    return round(sum(float(r.get("cost_usd") or 0.0) for r in _rows(caller, session_id(session))), 6)


def _checkin(caller, session, rows, total, ceiling, about_to_spend):
    by_label = {}
    for r in rows:
        key = r.get("label") or r.get("model") or "(unlabelled)"
        by_label[key] = by_label.get(key, 0.0) + float(r.get("cost_usd") or 0.0)
    top = sorted(by_label.items(), key=lambda kv: -kv[1])[:5]
    per_run = total / len(rows) if rows else 0.0
    lines = [
        f"BUDGET CHECK-IN — {caller} has spent ${total:.2f} of its ${ceiling:.2f} ceiling "
        f"this session, over {len(rows)} run{'s' if len(rows) != 1 else ''}.",
        "",
        "Spent on:",
    ]
    lines += [f"  ${v:>7.2f}  {k}" for k, v in top]
    if len(by_label) > len(top):
        lines.append(f"  … and {len(by_label) - len(top)} more")
    lines += [
        "",
        f"Average ${per_run:.2f} per run" + (
            f"; the next one is projected at ${about_to_spend:.2f}." if about_to_spend
            else "."),
        "",
        "This is a check-in, not a failure — nothing is broken and nothing was lost. Weigh the",
        "above against an estimate of what finishing costs, then set the ceiling.",
        "Raise it for one run:",
        f"    OR_BUDGET_USD=<amount> <your command>",
        "or pass the surface's own --max-spend flag. OR_BUDGET_USD=0 disables the gate entirely.",
    ]
    return "\n".join(lines)


def check(caller, session=None, budget=None, about_to_spend=0.0):
    """Raise BudgetExceeded (carrying the full check-in) if this run would cross the ceiling.

    Call BEFORE dispatching. `about_to_spend` is the projected cost of the run about to start,
    so the ceiling stops the run that WOULD cross it rather than reporting it afterwards.
    """
    ceiling = budget_usd(budget)
    if ceiling <= 0:
        return                      # explicitly disabled — an already-authorized run
    sid = session_id(session)
    rows = _rows(caller, sid)
    total = round(sum(float(r.get("cost_usd") or 0.0) for r in rows), 6)
    if total + float(about_to_spend or 0.0) <= ceiling:
        return
    raise BudgetExceeded(_checkin(caller, sid, rows, total, ceiling, about_to_spend))


def main():
    import argparse
    ap = argparse.ArgumentParser(description="Report cumulative OpenRouter spend per surface.")
    ap.add_argument("--session", default=None)
    ap.add_argument("--all-sessions", action="store_true")
    args = ap.parse_args()
    sid = "" if args.all_sessions else session_id(args.session)
    ceiling = budget_usd()
    scope = "ALL sessions" if args.all_sessions else f"session {sid[:8] or '(none)'}"
    print(f"OpenRouter spend by surface — {scope}   (ceiling ${ceiling:.2f} each)")
    grand = 0.0
    for surface in SURFACES:
        rows = _rows(surface, sid)
        total = sum(float(r.get("cost_usd") or 0.0) for r in rows)
        grand += total
        if not rows:
            continue
        flag = "  <-- OVER" if total >= ceiling else ""
        print(f"  {surface:<14} ${total:>8.2f}  ({len(rows)} runs){flag}")
    print(f"  {'TOTAL':<14} ${grand:>8.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
