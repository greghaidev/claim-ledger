# claim-ledger

A fact-check gate that tells you which of your claims you cannot show a source for.

Give it three things — a finished artifact, the primary data your claims came from, and the
code or notes that got you from one to the other — and it returns a per-claim ledger. Every
load-bearing claim comes back marked **TRACEABLE** (with the source line that supports it),
**UNTRACEABLE**, or **CONTRADICTED**.

The reviewers are models from lineages *other* than the one that drafted your artifact. That
is the entire point, and it is the one design decision everything else follows from.

## What this will not do

Worth saying before you install anything, because it is a gate and not an assistant:

- **It will not check a claim you cannot show it the source for.** No primary data, no
  lineage, no run — it refuses at intake and spends nothing. A summary of your data is not
  your data.
- **It will not rewrite your work,** suggest better phrasing, or tell you the artifact is
  good. It reports what fails to trace. What to do about that is yours.
- **It will not tell you a claim is false.** UNTRACEABLE means unsupported *by what you
  supplied*. That is a different and more useful thing than a truth verdict, and conflating
  them is how automated fact-checkers get a reputation for confident nonsense.
- **It will usually fail your artifact the first time.** Across the author's first 122
  production runs, 92 came back FAIL. That is the instrument working.

If you want something that helps you write, this is the wrong tool. If you want something
that stops you publishing a number you cannot defend, read on.

## Why a different lineage

A model asked to check its own output gives you a **correlated** second opinion, not an
independent one. The framing it found natural while drafting, it finds natural while
reviewing — same blind spots, now wearing a reviewer label. That failure is invisible from
the inside, which is exactly what makes it dangerous.

Lineage diversity is the only real decorrelation lever. So the default roster deliberately
contains no seat from the family that most commonly does the drafting. If you draft with a
model that *is* on the roster, drop it with `--reviewers`.

## Install

Python 3.9+. **No dependencies** — standard library only, on purpose.

```bash
git clone https://github.com/greghaidev/claim-ledger.git
cd claim-ledger
export OPENROUTER_API_KEY=sk-or-...        # or put it in a .env file beside the script
```

Get a key at [openrouter.ai/keys](https://openrouter.ai/keys). You pay your own usage
directly; nothing routes through anyone else's account.

## Run it

```bash
python3 claim_ledger.py \
    --artifact     example/report.md \
    --primary-data example/sales.csv \
    --lineage      example/derive.py \
    --class light \
    --outdir out/example
```

Start with [`example/`](example/) — a small report with a mix of honest and dishonest claims,
written so you can watch the gate separate them. See [`example/README.md`](example/README.md).

Exit code `0` = PASS, `1` = FAIL or BLOCKED, so CI can gate on it.

## The two classes

| | seats | lineages | cost per round | use it |
|---|---|---|---|---|
| `--class light` | 1 | 1 | ~$0.01 | while you iterate — this is the default |
| `--class heavy` | 3 | 3 | ~$0.10–0.20 | once, at ship |

Heavy re-verifies every already-traceable claim at full price, so running it after every
edit is how a $0.13 check becomes a $12 afternoon. Iterate light; spend heavy once.

A round is slow as well as cheap — see the runtime note under Known limits before you
assume a quiet terminal is a hang.

The printed dollar figure is a **floor, not a forecast** — reasoning tokens are billed as
output beyond `--max-tokens`, and real billing runs meaningfully higher. Treat it as an
order-of-magnitude guard, which is what it was built to be.

## How the verdict is reached

Deliberately mechanical, because the alternative is a synthesis step that can launder a
problem into a pass:

- **Intake gate.** Primary data, lineage, and artifact must all be present and non-empty, or
  the run is BLOCKED before any money moves.
- **Payload preflight.** The payload is measured and priced before dispatch. Over the ceiling
  (`--max-input-tokens`, default 150K) it refuses and names the argument to narrow. This
  exists because pointing `--primary-data` at a *directory* once turned a $0.13 run into a
  $1.80 one, silently, from a single argument.
- **Per-claim extraction.** Each reviewer pulls out every load-bearing claim and classifies
  it, citing the primary-source line for anything it calls traceable. Default is
  UNTRACEABLE: a claim earns its classification, it does not get the benefit of the doubt.
- **OR-of-FAILs.** Any reviewer FAIL, any UNTRACEABLE, any CONTRADICTED, any unparseable
  response → the artifact FAILS. No vote, no quorum, no chair. Unchaired is the point: a
  chair could only ever turn a minority FAIL into a soft PASS.

## The roster was interviewed, not assumed

The default seats were chosen by measurement: eight candidates, eight planted defects, 162
dispatches, $12.58. Method, per-seat numbers, and the accept/reject record are in
[`eval/`](eval/) — start with `eval/RESULTS.md`.

What the evaluation actually found, including the parts that argue against a big panel:

- **Defect recall saturated.** Seven of eight candidates caught every planted defect, and all
  eight refused a claim that is true in the world but absent from the bundle — nobody leaked
  outside knowledge into a verdict.
- **So extra seats buy no measured coverage.** At equal depth, one seat verifies as many of
  the artifact's figures as three. What a trio buys is redundancy against one seat's bad day
  and insurance against a correlated blind spot the battery cannot detect — real, but
  unmeasured. Stated plainly rather than dressed up as coverage.
- **What actually separates seats is whether they return a usable ledger at all.** Format
  compliance ran from 100% down to 92.6%.

Prices and availability move. `python3 check_prices.py` diffs the table in `or_peer.py`
against the live OpenRouter catalog; `--seated` checks just the default roster.

## Known limits

- **This is the panel half of a serious fact-check.** The other half is mechanical source
  confirmation — re-deriving a figure in SQL against the database it came from. A standalone
  script cannot do that. If you have an agent harness that can, run it first and pass the
  results via `--db-confirmations`.
- **A reviewer can only see what you hand it.** Narrow `--primary-data` to the sources the
  claims actually trace to; a fat payload is expensive and *worse*, not better.
- **Runs take minutes, not seconds — sometimes many.** The default `--reasoning-effort high`
  is deliberate: the reviewer is the adjudicating seat, and the seat evaluation was
  measured *saturated*, meaning it could not distinguish a safe reduction in effort from an
  undetectable one (see `eval/`). The cost of that caution is wall-clock. A single light
  seat commonly runs two to five minutes and, on a slow provider day, has been observed past
  fifteen. If you are iterating and want a faster loop, `--reasoning-effort medium` is a
  reasonable trade for a draft — just spend the default at ship.
- **The price table is a hand-maintained snapshot** and vendors reprice without notice. A
  stale row makes the cost floor wrong. Run `check_prices.py`.

## License

MIT. Use it, change it, ship it, sell it — no permission needed and no obligation back.
