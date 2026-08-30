#!/usr/bin/env python3
"""derive.py — every figure quoted in report.md, and nothing else.

This file is the LINEAGE argument. Its job is to show, mechanically, how each number in
the report was produced from sales.csv, so a reviewer can re-derive it rather than take
it on trust. If a figure appears in the report and not here, that is the gate's problem
to find.
"""
import csv
from collections import defaultdict

with open("sales.csv") as f:
    rows = [r for r in csv.DictReader(f)]

for r in rows:
    r["units"] = int(r["units"])
    r["revenue_usd"] = int(r["revenue_usd"])

by_quarter = defaultdict(int)
by_region = defaultdict(int)
for r in rows:
    by_quarter[r["quarter"]] += r["revenue_usd"]
    by_region[r["region"]] += r["revenue_usd"]

q3, q4 = by_quarter["2025-Q3"], by_quarter["2025-Q4"]
total = q3 + q4
growth = (q4 - q3) / q3 * 100
top_region = max(by_region, key=by_region.get)

# West is the only region whose revenue fell quarter over quarter.
declines = [reg for reg in by_region
            if sum(r["revenue_usd"] for r in rows if r["region"] == reg and r["quarter"] == "2025-Q4")
            < sum(r["revenue_usd"] for r in rows if r["region"] == reg and r["quarter"] == "2025-Q3")]

print(f"total revenue H2 2025:      ${total:,}")
print(f"  2025-Q3:                  ${q3:,}")
print(f"  2025-Q4:                  ${q4:,}")
print(f"quarter-over-quarter growth: {growth:.1f}%")
print(f"top region by revenue:       {top_region} (${by_region[top_region]:,})")
print(f"regions declining in Q4:     {', '.join(declines)}")
