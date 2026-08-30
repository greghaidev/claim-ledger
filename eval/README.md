> **Provenance — read this first.**
>
> These four documents are the record of a real reviewer-seat evaluation run against a real
> artifact in the repository this tool was extracted from. They are included because they are
> the evidence behind the default roster in `claim_ledger.py`: the seats were interviewed and
> measured, not chosen by reputation.
>
> Two honest caveats. **The eval harness itself (`gate_eval.py`) is not included here** — it
> was wired into the origin repository's fixtures and spend controls, and shipping it without
> those would be shipping something that cannot run. Commands below that invoke it are quoted
> as the historical method, not as something you can execute in this repo. And the prices,
> model slugs and availability quoted throughout were current on the dates given; several have
> moved since (run `check_prices.py`). The *method* is the transferable part.
>
> Read `RESULTS.md` first if you only read one.

---

# Fact-Check Gate — seat profile and re-seating evaluation

**Status: FOR OPERATOR REVIEW. Nothing has been run against a candidate. No money spent.**

Two things here: what the QA records say a good seat on this gate looks like, and the
process for re-seating the roster on evidence instead of reputation. The harness is
`gate_eval.py`; only its `run` subcommand spends.

---

## 1. What the records actually say

37 recorded runs, 4,132 claim ledgers across three seats. Three findings, ordered by how
much they change the seating decision.

### The panel was not decorrelating judgment — it was buying the same opinion three times

On claims that two seats both extracted, they agreed on the TRACEABLE/not call **94.5–97%**
of the time. That number is stable across every fuzzy-match threshold from 0.20 to 0.75, so
it is not an artifact of how claims were matched.

| pair | agreement | co-reviewed claims |
|---|---|---|
| deepseek-v4-pro vs glm-5.2 | 97.0% | 507 |
| grok-4.5 vs glm-5.2 | 96.9% | 578 |
| deepseek-v4-pro vs grok-4.5 | 96.5% | 316 |

The charter seated three lineages to break correlated error. On this task the lineages do
not disagree. Cross-lineage seating still matters for the *drafting* correlation the charter
names — no seat may share the author's lineage — but it buys almost nothing in verdict
diversity, so it cannot be the basis for choosing among non-Claude candidates.

### What the seats DO differ on is coverage

On one clean artifact all three PASSED, the same payload, the same prompt:

| seat | claims extracted from the identical artifact |
|---|---|
| glm-5.2 | 55 |
| deepseek-v4-pro | 42 |
| grok-4.5 | 35 |

Across all runs, claims per live seat: glm-5.2 **47.2**, grok-4.5 **46.2**,
deepseek-v4-pro **33.9**. DeepSeek — the anchor, and now the only seat in `--class light` —
extracts about 28% fewer claims than the other two. A claim never extracted is never
checked, and the gate reports PASS on the ones it did check. **That is the gate's real
exposure, and it is invisible in every verdict it has ever produced.**

I could not measure per-seat recall precisely from the records: identifying "the same claim"
across seats is a fuzzy-match problem, and solo-find counts swing from 81% to 35% purely
with the threshold. That limitation is why the eval below plants its own defects instead of
inferring recall from agreement.

### Citation discipline is uniformly good, reliability is not

All three cite a source on 91–93% of claims, and 96–98% of those citations name a real
file/row locator rather than hand-waving. No differentiation there. But dead ledgers
(unparseable, empty, or truncated) run **grok-4.5 4/34, deepseek 2/37, glm-5.2 1/34** — and
in a fail-closed gate a dead seat is an automatic FAIL, so an 11.8% death rate is an 11.8%
false-FAIL rate bolted onto whatever the seat actually thinks.

Latency, for scheduling: grok-4.5 103s, deepseek 283s, glm-5.2 299s.

---

## 2. The seat profile

What this job actually is: extract every load-bearing claim from a document, locate each one
in a large supplied payload, and refuse to certify anything you cannot point at. It is a
**coverage-and-obedience** task, not a reasoning task. Ranked by what the records show
matters:

1. **Claim-extraction recall.** The dominant differentiator, and the one thing no gate
   verdict reveals. A seat that finds 35 of 55 claims silently narrows the gate.
2. **Obedience over knowledge.** The prompt says trust ONLY the payload. A model with strong
   priors about Missouri tax law can "know" a claim is true and mark it TRACEABLE without
   support. This is the only failure mode that puts a false claim in front of an investor
   *carrying a PASS*, so it is a disqualifier, not a score.
3. **Format reliability at length.** A 40-claim ledger in valid JSON, every time, without
   truncating. Flakiness converts directly into false FAILs.
4. **Citation honesty.** Cites a real locator that actually contains the number. Mechanically
   checkable, which makes it the cheapest real signal available.
5. **Long-context fidelity.** The payload runs 100–200K tokens. A seat that skims the middle
   marks claims UNTRACEABLE because it did not read the source — a false FAIL that looks
   exactly like a real catch.
6. **Cost per round at 150K input.** Input-dominated. This is a hard constraint, not a
   preference: see the affordability filter below.

### Better

- **Cheap, long-context, high-recall, instruction-literal models.** Input price is the
  binding constraint because the payload is read once per seat per round.
- **Models that follow a rubric literally rather than reasoning around it.** The gate wants a
  clerk with a checklist, not a strategist. This is the one place where a model being *less*
  clever is an advantage.
- **Complementary extractors.** Given 96% verdict agreement, a second seat is worth its cost
  only if it extracts claims the first one misses. Seat for union coverage.

### Worse

- **Premium reasoning models.** They lose on the only axis that binds. `gpt-5.6-sol` costs
  **$1.11 per seat-round** at 150K input — 14x the anchor — and the task is not
  reasoning-hard. Paying reasoning prices for a coverage problem is how the gate reached $52
  in two days.
- **Models with strong domain priors and weak instruction-following.** Highest risk of the
  leak failure, which is the one that actually reaches a customer.
- **Anything with a short or lossy context window** at 150K.
- **Claude, at any price.** Charter constraint: the drafter is Claude-lineage, so a Claude
  seat is single-lineage self-review. Not re-litigated here.
- **Chronic over-flaggers.** Every false FAIL costs a fix round at full panel price, and the
  2026-07-28 grind shows where that ends.

---

## 3. The evaluation process

Six commands. Only `run` spends money.

```
python3 gate_eval.py build    # fixture + planted defects, all assertions   $0
python3 gate_eval.py plan     # affordability filter + exact cost           $0
python3 gate_eval.py run      # dispatch candidates, under a hard cap  SPENDS
python3 gate_eval.py score    # mechanical scorecard                       $0
python3 gate_eval.py seat     # roster selection by union recall           $0
python3 gate_eval.py decide   # append the accept/reject to DECISIONS.md   $0
```

### The eval is SHORT by default (operator directive, 2026-08-15)

> *"I would rather have a short eval, make a swap, then record the decision history than have
> an exhaustive eval process where the limit for doing the evaluation is $15."*

The first re-seating cost $12.58 and roughly $9 of that bought an answer nobody could act on:
recall and coverage **saturated** — every candidate caught every planted defect — so five of
the eight defect variants separated nobody. Worse, it took long enough that the vendor
repriced the field underneath it (see §6).

So `run` now defaults to `--battery quick` and a hard `--max-spend 3.00`:

| kept | why |
|---|---|
| `base` | the only source of the **production-fatal** metric — flags on a clean base. OR-of-FAILs means one such seat can never return PASS. Also carries figure coverage and the citation audit. |
| `leak` | the hard disqualifier. Inferable from no other variant. |
| `arithmetic_break` | recall floor, catchable inside the artifact alone |
| `source_contradiction` | recall floor, requires actually reading the primary data |

Dropped: `statute_rate_wrong`, `prose_table_conflict`, `self_refuting_headline`,
`unsourced_superlative`, `phantom_precision` — 100% caught by the entire field in 2026-07-30.

**What the short battery gives up, stated plainly.** Two defects is a recall *floor*, not a
recall measurement: it catches a seat that has stopped reading, and it cannot tell you which
seat catches the subtlest defect. `score` prints a `PARTIAL BATTERY` banner so that limit
travels with the numbers. Run `--battery full` when the question is "which of these two seats
is genuinely sharper" rather than "is this new version fit to sit."

**The ceiling is real, not a report.** Dispatches go out in waves of `--concurrency` and the
spend is checked between waves, so overshoot is bounded by one wave. Jobs are ordered
trial-major, so hitting the cap costs trial *depth* uniformly instead of leaving the
last-sorted candidates at zero trials — an unequal-depth comparison is the failure mode that
made a seat look flawless at n=1 in the first eval.

### Decisions are recorded, not remembered

`decide` appends to [DECISIONS.md](DECISIONS.md): the roster before and after, why, the
evidence, and **the falsifiable condition that would reverse it**. The roster's reasoning used
to live in a comment block, a RESULTS.md and the operator's memory, which is why every re-seat
re-derived it from scratch. A cheap eval is only cheap if its conclusion survives.

### The fixture

Real work, not a synthetic probe: **section 06 of the tax-sale report** plus the exact
sources its claims trace to (DB confirmations, `facts.json`, the RSMo 140.340 text, the
lineage note) — ~10,500 tokens all in.

Section 06 was chosen on measurement, not convenience. 96% of its figures are present in
that compact source set. Section 05's are not: its money figures trace to a 117K-token
bid-level CSV, and no compact bundle covered more than 54% of them — which would have made
half the base artifact legitimately untraceable and turned every over-flag metric into a
measurement of my fixture rather than of the seat.

### The battery: eight planted defects, one per variant

Each variant differs from the base by exactly one edit at a known location, so a miss
attributes to one defect class. The classes span how an investor-facing number actually goes
wrong, not eight flavours of changed digit.

| variant | class | what a correct seat does |
|---|---|---|
| `source_contradiction` | headline count contradicts the supplied DB confirmation | flag |
| `arithmetic_break` | subgroups no longer sum to the stated total | flag |
| `statute_rate_wrong` | rate contradicts the statute text in the bundle | flag |
| `prose_table_conflict` | prose now contradicts the table it is reading | flag |
| `self_refuting_headline` | summary refuted by the figure it summarises | flag |
| `unsourced_superlative` | comparative reaching outside the payload entirely | flag |
| `phantom_precision` | a median stated to the cent | flag |
| `leak` | **true in the world, absent from the bundle** | flag — TRACEABLE here is a **hard disqualification** |
| `base` | unmutated control | — |

`build` refuses to produce a fixture unless **every anchor matches exactly once** and the
leak trap's key term appears **nowhere in the payload**. A battery that silently stops
mutating is the worst outcome available: every seat scores flawless against an unmodified
file and the scorecard looks completely normal.

### What is scored, and how it avoids needing a judge

| dimension | how | ground truth |
|---|---|---|
| **Format reliability** | valid, non-truncated, non-empty ledgers / trials | none needed |
| **Leak** | TRACEABLE on the leak variant | by construction, machine-asserted |
| **Defect recall** | planted defects flagged / planted | by construction |
| **Coverage miss** | planted claim never extracted at all | by construction |
| **Bad citations** | TRACEABLE citing a file or number absent from the payload | mechanical |
| **Over-flagging** | flags on the unmutated base, split solo vs consensus | relative only |
| **Cost / latency** | billed cost and wall time | measured |

Two deliberate choices in that table:

- **No Claude in the scoring path, and no adjudication anywhere.** A defect is flagged or it
  is not. The moment a judgment seat scores the candidates, the eval inherits exactly the
  correlated-error problem the gate exists to break.
- **Flags on the base are NOT scored as false positives.** Proving a flag wrong requires
  adjudication. They are reported as solo vs consensus over-flags and matched by the
  *numeric tokens* a claim carries — exact-match, not prose similarity, because the audit
  showed prose-similarity clustering is threshold-dependent to the point of uselessness.
  Section 06's one historically contested claim has been edited out and `build` asserts its
  absence, but the base is "as clean as the record can establish," not "provably clean," and
  the metric is labelled accordingly.

### Hard gates before ranking

A candidate failing either is unseatable regardless of recall:

1. **Format ≥ 95%** valid ledgers. A fail-closed gate cannot be flaky.
2. **Zero leaks.** A seat substituting its own knowledge for the record defeats the only
   thing the gate is for.

### Selection: rank ROSTERS, not models

This follows directly from the 96% agreement finding. Three individually-strong seats can
buy the same coverage three times. `seat` enumerates subsets, scores each by **union defect
recall**, breaks ties on cost, and names any defect class **no** candidate catches — because
silence there would read as "the roster is fine" when the class ships regardless of who is
seated.

A seat only "covers" a defect if it catches it in a **majority of trials** (`--require
any|majority|all`). The first implementation used `any`, and a seat catching one trial in
three scored as covering the defect — a 76%-recall seat came out at 100% union recall. For a
fail-closed gate, a catch you get a third of the time is a coin flip on whether a false
claim reaches an investor.

---

## 4. The affordability filter, and what it costs to run this

`plan` prices each candidate's **production** cost per seat-round at 150K input *before* any
dispatch, and refuses to evaluate what the gate could never afford to run. This is the
single largest cost lever in the whole design — it took the eval from ~$105 billed to ~$7.

```
candidate                       $/prod round    verdict  $ eval sweep  $ x3 trials
deepseek/deepseek-v4-pro               0.076   eligible         0.136       0.407
moonshotai/kimi-k2.6                   0.144   eligible         0.435       1.305
z-ai/glm-5.2                           0.155   eligible         0.359       1.077
qwen/qwen3.7-max                       0.274 PRICED OUT         0.619       1.858
x-ai/grok-4.5                          0.372 PRICED OUT         0.840       2.519
google/gemini-3.1-pro-preview          0.444 PRICED OUT         1.488       4.463
moonshotai/kimi-k3                     0.630 PRICED OUT         1.908       5.723
openai/gpt-5.6-sol                     1.110 PRICED OUT         3.719      11.158
```

**Eligible: 3 of 8. Eval floor $2.79, expect ~$7 billed** (reasoning tokens run 2–3x the
floor — that ratio is measured, from 10 production runs).

The `$0.20` ceiling is derived from your grok decision: grok was dropped at $0.372/round, so
anything above that is unseatable by the same argument. **The ceiling is the one number in
this design that is a policy call rather than a measurement, and it is yours.** It is also
the whole result: at $0.20 only three candidates qualify and two are already seated, so the
eval mainly asks whether `kimi-k2.6` earns a seat. At $0.30 you add qwen; at $0.40, grok and
gemini come back into contention.

---

## 5. What I would do next, and what needs you

**Needs your decision:**

1. **The affordability ceiling** (`--max-prod-cost`, default $0.20). Sets the candidate
   field, and therefore what the eval can possibly conclude.
2. **Approve the ~$7 spend** for `run --trials 3` over the eligible three. Three trials is
   the minimum that makes the format-reliability and majority-coverage metrics mean
   anything.
3. **Whether to pay ~$12 more** to evaluate qwen, grok and gemini at a $0.45 ceiling — worth
   it only if you would actually seat a $0.30+/round seat.

**Known weakness, stated plainly:** this is a **single-fixture** eval. Seats are scored on
one section of one report, so it measures fitness for *this* document's failure modes. The
harness is structured for a second battery (`qa/artifact-field-shape.md` measures 95% figure
coverage at ~7,200 tokens and would serve), and I would add it before treating a score as a
durable roster decision rather than a re-seating input. I did not build it yet because the
first battery is what you need to review, and a second one doubles the review surface
without changing the design.

**Not started, and deliberately so:** no candidate has been dispatched. Re-seating is the
next phase and it needs the numbers this process produces, plus your ceiling.

---

## Provenance

- Audit source: all 37 ledgers under `the production ledgers`.
- Harness: `gate_eval.py`. Tests: `the eval tests` (30, spend-free,
  covering detection, citation audit, numeric identity, both hard gates, the affordability
  filter, the reliability rule, and that the production prompt is imported rather than
  copied — an eval running its own prompt would measure a task the gate never performs).
- Gate charter and the operating harness it ran inside: the origin repository (not included here).
