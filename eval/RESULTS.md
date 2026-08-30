# Fact-Check Gate — seat interviews, results

Eight candidates interviewed under the production reviewer prompt against a real bundle with
eight planted defects. Stage 1: all 8, one trial, 72 dispatches, $8.47. Stage 2: three trials
on the five plausible seats.

**Roster recommendation is at the bottom.** Read the corrections section first — five bugs in
the harness were found and fixed during the run, every one before a candidate was ranked by
it, and three of them would have produced a confident, wrong hire.

---

## 1. What did not discriminate

**Both hard gates were passed by every candidate on the defect battery.** All eight extracted
the planted Jackson County claim — true under Missouri law, absent from the bundle — and all
eight refused it as UNTRACEABLE. Not one substituted its own knowledge for the record. That is
the failure mode that would put a false claim in front of an investor carrying a PASS, and the
field is clean on it.

**Defect recall saturated at 100% for seven of eight.** Only `gemini-3.1-pro-preview` missed
one (`unsourced_superlative` — it never extracted the planted marketing claim at all).

That is a real result about the field, not a broken fixture: frontier models all catch blatant
planted defects. It also means union defect recall cannot rank a roster, which is what the
process document assumed it would do.

**Figure coverage did not discriminate either, once trial depth was equal.** Of the 54 distinct
figures the base artifact asserts, all four finalists verify 52 (96%). At ONE trial
`qwen3.7-max` looked weak at 46 and `kimi-k3` at 49 — the same n=1 trap flagged elsewhere in
this document, not a real gap, and I briefly used it to argue against qwen. The only figure no
seat verified is `$200,000`, a rhetorical illustration in "a yield buyer bidding on $200,000
houses", correctly ignored by all eight as decorative rather than load-bearing.

**Union coverage saturates at one seat.** Every trio, every pair, and `deepseek-v4-pro` alone
all reach the same 52 figures. On this fixture, a second and third seat buy no measurable
coverage.

---

## 2. What actually discriminated

### Over-flagging a clean base — the production-fatal one

Rates per clean-base run, at full trial depth where available:

| seat | base runs | flags/run |
|---|---|---|
| `openai/gpt-5.6-sol` | 1 | **32.0** |
| `moonshotai/kimi-k2.6` | 3 | 3.67 |
| `z-ai/glm-5.2` | 3 | 1.33 |
| `deepseek/deepseek-v4-pro` | 3 | 0.67 |
| `x-ai/grok-4.5`, `qwen3.7-max` | 3 | 0.00 |
| `gemini-3.1-pro-preview`, `kimi-k3` | 1 | 0.00 — **unmeasured, not proven** |

Aggregation is OR-of-FAILs: any seat's flag fails the artifact. A seat that flags a clean base
does not add noise — it makes the panel incapable of ever returning PASS, however good its
co-seats are. gpt-5.6-sol flagged the document's own header ("The prose was extracted from
report-draft.md after the 2026-07-29 merge") and its cross-references ("Section 01 said this
market is buying property") as untraceable factual claims. kimi-k2.6 flagged rhetoric the
prompt explicitly excludes — "you own a vacant lot", "bidding against people who are not doing
arithmetic".

**Correction — this metric cannot rank the finalists, and I initially claimed it could.** Two
things undid the first reading:

*The "six of eight flagged nothing" consensus was an n=1 artifact.* At three trials the rates
are gpt-5.6-sol 32.0/run, kimi-k2.6 3.67, glm-5.2 1.33, deepseek-v4-pro 0.67, grok-4.5 0.00,
qwen3.7-max 0.00. More trials, more flags — so a single clean base run proves nothing, and the
three seats still at n=1 have an *unmeasured* rate, not a zero one.

*The flags are defensible on inspection.* glm flagged a negative-existence claim ("no public
St. Louis County record we have found answers it"), two product promises about the interactive
guide with no primary data behind them, and a universal quantifier. deepseek flagged two
unsupported causal claims ("uncontested **because** the rest of the market looked at them and
passed"). The reviewer prompt explicitly lists "causal or superlative assertions" as
load-bearing, so those are the seat doing its job.

Which leaves the dimension genuinely two-sided and unresolvable without adjudication: if the
base holds unsupported claims, then flagging them is rigor and **a seat flagging zero is
missing them** — grok and qwen's clean sheets read as under-flagging rather than precision.
Deciding between those readings requires a judgment seat, which is the one thing this harness
refuses to put in its scoring path.

So the gate is kept, but only for what it can honestly do: **exclude an extreme outlier.**
gpt-5.6-sol at 32/run is 10x the next highest and qualitatively different — it flagged the
document's own provenance header ("The prose was extracted from report-draft.md after the
2026-07-29 merge") as an untraceable factual claim. Nothing in the roster decision below rests
on the threshold, and kimi-k2.6 fails the format gate independently, so no outcome hinges on
it.

One thing this dimension did settle. The value-band table sums to 2,176 against a stated total
of 2,181, which looks like an uncaught arithmetic defect that every seat missed. It is not: the
supplied source states it outright — *"2,176 of 2,181 rows carry a county appraised value; 5 do
not and fall outside every band."* Passing it was correct.

### Reliability, and it is not where stage 1 suggested

Stage 1 at n=1 showed `deepseek-v4-pro` — the cheapest seat, the current anchor, and the only
seat in `--class light` — at a flawless 100% on every axis. Three trials changed that.

Reliability is a **hard gate**, not a ranking factor: a fail-closed gate cannot be flaky,
because a dead seat is an automatic FAIL on an artifact nobody has examined.

### Latency tails

| seat | median | max | tail |
|---|---|---|---|
| `grok-4.5` | 64s | 89s | 1.4x |
| `glm-5.2` | 80s | 499s | 6.2x |
| `qwen3.7-max` | 116s | 216s | 1.9x |
| `deepseek-v4-pro` | 143s | **1,185s** | **8.3x** |
| `kimi-k2.6` | 519s | 1,608s | 3.1x |

(`gemini-3.1-pro-preview` 62s/71s and `kimi-k3` 167s/875s, at one trial only.)

A 34-minute dispatch is provider-endpoint degradation, not the model thinking. It matters
because it is unpredictable, and because the seats with the tightest tails are also the ones
that cost 5–6x the cheapest.

---

## 3. Corrections made during the run

Five harness bugs, all found before any candidate was ranked by them. Three would have produced
a confident and wrong hire. They are listed because the harness's credibility rests on them
being visible, not on there having been none.

| # | bug | effect if unfixed |
|---|---|---|
| 1 | Detection accepted pre-mutation tokens; `"8%"` occurs 10x in the base | **Recall was inflatable by flagging freely** — the over-flaggers would have ranked highest |
| 2 | Citation check compared a full path against a bare basename, backwards | gpt-5.6-sol scored **100% fabricated citations** when it was citing more precisely than anyone. Penalised the best behaviour |
| 3 | Coverage counted claim identities | Measured **how finely a seat decomposes its ledger**, not what it checked. Put the biggest emitter — the worst over-flagger — top of the roster ranking |
| 4 | Roster sort inverted | Listed the **most expensive** qualifying roster first |
| 5 | Dispatch reimplemented instead of delegating to `claim_ledger.dispatch_one` | Skipped the empty-completion retry, so a **transport artifact** counted against a seat's format score on a hard gate — production retries it and never sees it |

Bug 3 is worth dwelling on: I reported a "3x coverage spread" between seats and it was an
artifact of claim granularity. `deepseek` emits `"under $25,000 band: 185 parcels"` as its own
claim where `glm` bundles the whole table row into one carrying five figures. Identical
checking, different decomposition. The fix — measuring coverage against the artifact's fixed
set of figures — is granularity-independent and reversed the ranking.

The general shape: **every one of these measured the shape of a model's output rather than the
thing the output is about.** That is the failure this harness exists to prevent, committed five
times by the harness.

---

## 4. Method notes and limits

- Candidates ran under `claim_ledger.REVIEWER_SYSTEM` and `claim_ledger.dispatch_one` — the
  production prompt and the production dispatch path, imported, never copied. A test asserts
  there is no second dispatch path.
- Ground truth is constructed, not judged. No Claude anywhere in the scoring path.
- The `leak` trap's validity is machine-asserted: `build` refuses if its key term appears
  anywhere in the payload.
- **Single fixture.** Seats are scored on one section of one report. The battery saturating is
  itself evidence the fixture is not hard enough to separate frontier models on recall — a
  harder or larger artifact would likely re-open coverage differences that saturate here.
- **Provider variance is a confound.** OpenRouter routes to multiple endpoints per model and
  their health varies hour to hour. The reliability and latency numbers are a measurement of
  model-plus-endpoint at this moment, not a durable property of the model.

---

## 5. Pre-flight for whatever roster is hired

Checked before the hire rather than discovered by a red test:

- **`claim_ledger.LINEAGE` does not cover three of the eight candidates** —
  `qwen/qwen3.7-max`, `google/gemini-3.1-pro-preview` and `moonshotai/kimi-k2.6` are all
  absent. `test_heavy_is_distinct_lineages` computes `{LINEAGE[s] for s in seats}`, so seating
  any of them without extending the map is a `KeyError`, not a soft fallback. Any hire that
  reaches outside the current five must add its lineage key in the same change.
- **`kimi-k2.6` and `kimi-k3` are the same lineage (Moonshot).** Seating both would silently
  break the distinct-lineage property the panel is built on.
- The seating change itself is `ANCHOR` + `HEAVY_DEFAULT` in `claim_ledger.py`, plus
  the panel-size assertions in `the panel tests` (currently pinned to a
  two-seat heavy panel).

---

## 6. The hire

**Heavy panel (ship gate, three seats): `deepseek-v4-pro` + `glm-5.2` + `qwen3.7-max`.**
Three distinct lineages (DeepSeek / Zhipu / Alibaba), $0.505 per round at 150K input.

**Light class (every iteration round, one seat): `deepseek-v4-pro` unchanged.** $0.076 a round,
the cheapest seat that clears every gate, with the lowest clean-base flag rate of the two seats
that flag anything.

The four finalists over 27 dispatches each:

| seat | format | recall | figures | flags/clean run | $/round | median | max |
|---|---|---|---|---|---|---|---|
| `deepseek-v4-pro` | 96.3% | 100% | 96% | 0.67 | **0.076** | 143s | 1185s |
| `glm-5.2` | **100%** | 100% | 96% | 1.33 | 0.155 | 80s | 499s |
| `qwen3.7-max` | **100%** | 100% | 96% | 0.00 | 0.274 | 116s | 216s |
| `grok-4.5` | **100%** | 100% | 96% | 0.00 | 0.372 | **64s** | **89s** |

### Why these three

They are indistinguishable on the things the gate exists to do — all four hit 100% defect
recall, 96% figure coverage, and zero leaks. So the hire turns on reliability, price and speed,
and on that basis: deepseek is 2–5x cheaper than anyone and anchors the light class where cost
compounds; glm is the fastest of the two cheapest and never failed; qwen is the cheapest seat
with a perfect format record and no clean-base flags.

**grok-4.5 stays off, and it earned better.** It was the most predictable seat in the field —
27/27, a 64s median and an 89s worst case against deepseek's 1,185s. But qwen matches it on
format, recall, coverage and clean-base flags for 26% less. The original drop was a cost call
on old evidence; this is a cost call on new evidence that happens to agree. Re-seat it with
`--reviewers deepseek/deepseek-v4-pro,z-ai/glm-5.2,x-ai/grok-4.5` when latency predictability
is worth the premium.

**Excluded:** `kimi-k2.6` failed the format gate (92.6% — two dropped connections and a
malformed ledger). `gpt-5.6-sol` flagged 32 claims on a clean base including the document's own
provenance header; in an OR-of-FAILs panel that seat alone can never return PASS, at $1.11 a
round. `gemini-3.1-pro-preview` and `kimi-k3` were screened at one trial only — not rejected,
**unmeasured**.

### What the third seat actually buys — stated plainly

Not coverage. Union coverage is identical for one seat, two, or three. The third seat buys
redundancy against a single seat's bad day, and insurance against a correlated blind spot that
a battery every candidate passes cannot detect. That benefit is real and it is **unmeasured**;
if you want the panel justified by evidence rather than by prudence, the evidence supports one
seat, and the honest answer is that this fixture is not hard enough to find where they differ.

### Cost of the interviews

$12.58 total — $8.47 stage 1 (8 candidates x 9 variants), $4.11 stage 2 (5 candidates x 2 more
trials). The affordability pre-filter would have cut this to ~$3 by never interviewing the four
seats priced out of production; it was overridden deliberately, because "would we seat it" and
"is it any good" are different questions and the second one is worth $9 to answer once.
