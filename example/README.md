# The worked example

A deliberately small artifact with a deliberately mixed set of claims, so you can watch
the gate work before you point it at anything of your own.

- **`sales.csv`** — the primary data. Eight rows. This is the only permitted proof.
- **`derive.py`** — the lineage. Run it (`python3 derive.py`) to see every figure the
  report should be quoting, computed from the CSV.
- **`report.md`** — the artifact. Five paragraphs, and they are not all honest.

Run the gate on it from the repository root:

```bash
python3 claim_ledger.py \
    --artifact     example/report.md \
    --primary-data example/sales.csv \
    --lineage      example/derive.py \
    --class light \
    --outdir out/example
```

It costs about a cent and it will FAIL. That is the correct outcome. Three of the
report's claims trace cleanly to the CSV; two do not, and they fail in the two
different ways the ledger distinguishes:

- One paragraph states a figure the data **contradicts** — the report claims 18%
  quarter-over-quarter growth, and `derive.py` computes 5.8% from the same rows. This is
  the failure mode that survives a careful human read, because 18% is plausible, the
  sentence is well-formed, and nothing about it looks wrong.
- The closing paragraph makes two claims the data cannot speak to at all — customer
  satisfaction, and a market-share percentage. Nothing in `sales.csv` measures either.
  They are **untraceable**: not disproven, just unsupported. The gate does not give them
  the benefit of the doubt, and that default is the whole point.

Read the ledger it writes to `out/example/`. Each claim comes back with a
classification and, for the ones that pass, the primary-source line that carries it.

Then try the instructive failure: drop `--primary-data` and run it again. It BLOCKS at
the intake gate, spends nothing, and tells you what is missing. A fact-check with no
primary data is not a cheaper fact-check — it is a different, useless thing, and the
gate refuses rather than pretending.
