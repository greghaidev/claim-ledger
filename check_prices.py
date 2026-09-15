#!/usr/bin/env python3
"""check_prices.py — diff or_peer.PRICES against the LIVE OpenRouter catalog.

The price table in or_peer.py is a hand-maintained snapshot, and vendors reprice without
notice. A stale row does not break anything loudly — it quietly makes the pre-flight cost
FLOOR wrong, which is the number you decide to dispatch on. Run this before trusting a
budget derived from the table, and after any vendor announcement.

    python3 check_prices.py            # report drift
    python3 check_prices.py --seated   # only the models on the default rosters

Costs nothing: the catalog endpoint is public and needs no API key.

CAVEATS, both real:
  * OpenRouter reports the CHEAPEST endpoint of the moment. That is not necessarily the
    endpoint you get, and it is frequently a quantized one — see PROVIDER_PREFS in
    or_peer.py. A row matching the catalog is not proof your dispatch is priced that way.
  * Some models are priced differently in peak windows. A 2x disagreement at a predictable
    hour is a peak rate, not drift.

Exit 0 = table agrees with the catalog (within tolerance), 1 = drift found, 2 = fetch failed.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import or_peer  # noqa: E402

CATALOG = "https://openrouter.ai/api/v1/models"
TOLERANCE = 0.005  # fraction; below this a difference is rounding, not a reprice


def fetch_catalog(timeout=30):
    req = urllib.request.Request(CATALOG, headers={"User-Agent": "claim-ledger/check_prices"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))["data"]


def live_prices(catalog):
    """{slug: (input $/M, output $/M)} — the API quotes dollars PER TOKEN."""
    out = {}
    for m in catalog:
        p = m.get("pricing") or {}
        try:
            out[m["id"]] = (float(p["prompt"]) * 1e6, float(p["completion"]) * 1e6)
        except (KeyError, TypeError, ValueError):
            continue
    return out


def drifted(ours, theirs, tol=TOLERANCE):
    """True when the two differ by more than `tol` on either leg."""
    for a, b in zip(ours, theirs):
        if a == 0 and b == 0:
            continue
        if abs(a - b) / max(a, b, 1e-9) > tol:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seated", action="store_true",
                    help="check only models on the default light/heavy rosters")
    args = ap.parse_args()

    try:
        live = live_prices(fetch_catalog())
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        print(f"check_prices: could not reach the OpenRouter catalog: {e}", file=sys.stderr)
        return 2

    seated = set(or_peer.PRICES)
    if args.seated:
        import claim_ledger
        seated = set(claim_ledger.HEAVY_DEFAULT) | {claim_ledger.ANCHOR}

    rows, missing, ok = [], [], 0
    for slug in sorted(seated):
        ours = or_peer.PRICES.get(slug)
        if ours is None:
            continue
        theirs = live.get(slug)
        if theirs is None:
            missing.append(slug)
            continue
        if drifted(ours, theirs):
            rows.append((slug, ours, theirs))
        else:
            ok += 1

    print(f"checked {ok + len(rows)} priced models against the live catalog "
          f"— {ok} agree, {len(rows)} drifted, {len(missing)} not in the catalog\n")

    if rows:
        print(f"{'model':38s} {'table (in/out)':>22s}   {'live (in/out)':>22s}")
        print("-" * 88)
        for slug, (oi, oo), (li, lo) in rows:
            fi = li / oi if oi else float("inf")
            print(f"{slug:38s} {oi:9.4f} /{oo:9.4f}   {li:9.4f} /{lo:9.4f}   in x{fi:.2f}")
        print("\nUpdate or_peer.PRICES with the LIVE values, at full precision — do not round.")
        print("Check the peak-window caveat above before treating an exact 2x as drift.")

    if missing:
        print("\nNot in the catalog (deprecated, renamed, or never public):")
        for slug in missing:
            print(f"  {slug}")
        print("A seated model that disappears from the catalog needs re-seating, not a price edit.")

    return 1 if rows else 0


if __name__ == "__main__":
    # Windows writes the ANSI code page to a pipe or console by default; a printed arrow or
    # em dash in a claim would otherwise crash the run.
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
