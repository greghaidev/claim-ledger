# The worked example

A deliberately small artifact with a deliberately mixed set of claims, so you can watch the
gate work before pointing it at anything of your own.

- **`sales.csv`** — the primary data. Eight rows. This is the only permitted proof.
- **`derive.py`** — the lineage. Run `python3 example/derive.py` to see every figure the
  report *should* be quoting, computed from the CSV.
- **`report.md`** — the artifact. Five paragraphs, and they are not all honest.

## Run it

```bash
python3 claim_ledger.py \
    --artifact     example/report.md \
    --primary-data example/sales.csv \
    --lineage      example/derive.py \
    --outdir out/example
```

It will **FAIL**, which is the correct outcome. Read the ledger it writes to
`out/example/ledger.md`.

> **On runtime.** The default anchor seat is thorough and slow — on a bad provider day a
> single light round has been observed running past fifteen minutes with nothing printed
> but the dispatch line. If you want a fast first look, add
> `--reviewers minimax/minimax-m3`, which produced the run below in **228 seconds for
> $0.0037**. See the runtime note in the top-level README before assuming a quiet
> terminal is a hang.

## What it actually found

Sixteen load-bearing claims extracted from five short paragraphs. Eleven traced cleanly —
each with the source line *and* the arithmetic:

| Claim | Class | Note |
|---|---|---|
| Second-half revenue totaled $2,546,000 | TRACEABLE | 1,237,000 + 1,309,000 = 2,546,000 |
| North closed the half at $890,500 | TRACEABLE | 412,600 + 477,900 = 890,500; max of by_region |
| North is roughly a third of total revenue | TRACEABLE | 890,500 / 2,546,000 = 34.97% |
| West's average selling price held steady | TRACEABLE | ASP $224.01 → $223.32; ~0.3% change |

That last row is worth dwelling on. Nothing in `derive.py` computes average selling price —
the reviewer derived it from the CSV itself to check a qualitative word ("steady"), and
showed its work. That is the behavior you are paying for.

Five claims did not survive, and they failed in the two different ways the ledger
distinguishes:

**One is CONTRADICTED** — the report claims 18% quarter-over-quarter growth; the data says
5.82%. This is the failure mode that survives a careful human read. The figure is plausible,
the sentence is well-formed, and nothing about it looks wrong. You cannot catch this by
proofreading; you catch it by re-deriving, which is what the gate does.

**Four are UNTRACEABLE** — customer satisfaction "improving," a causal claim resting on it,
a market-share percentage, and a "12% we guided to" benchmark. None is disproven. The data
simply cannot speak to any of them, and the gate does not extend the benefit of the doubt.
That default is the whole design: an unsupported claim and a supported one must not come
back looking the same.

## Then try the instructive failure

```bash
python3 claim_ledger.py --artifact example/report.md --lineage example/derive.py
```

It BLOCKS at the intake gate, spends nothing, and names what is missing. A fact-check
without primary data is not a cheaper fact-check — it is a different and useless thing, and
the gate refuses rather than pretending otherwise.

## Then fix it and re-run

Correct the 18% to 5.8%, delete the closing paragraph, and run it again. Watching an
artifact go from FAIL to PASS on evidence you supplied is the loop this tool exists for.
