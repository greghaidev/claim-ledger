# Fact-Check Gate — roster decision history

Append-only. One entry per accept/reject, newest last, written by
`python3 gate_eval.py decide`.

WHY THIS FILE EXISTS. The roster's reasoning used to live in three places that drift apart —
a comment block in `claim_ledger.py`, a RESULTS.md from one eval, and whatever the operator
remembered. So every re-seat re-derived the same arguments from scratch, and a decision that
had already been made and reversed could be made again without anyone noticing. A short eval
is only cheap if its conclusion survives; this is where it survives.

Each entry states what would REVERSE it. A seating decision with no switch-condition is a
preference, and preferences do not need evidence to change.

---

## 2026-08-15 — ACCEPT: Short eval replaces the exhaustive one: quick battery + hard $3 ceiling

**Roster:** `(unchanged)` -> `(unchanged)`

**Why:** The 2026-07-30 eval cost $12.58 and ~$9 of it bought nothing actionable: recall and coverage saturated, so 5 of 8 defect variants separated no candidate. Confirmed again 2026-08-15 — all 9 candidates scored 100% on format, leak refusal, recall, figure coverage and citations. The quick battery keeps the 4 variants that DO discriminate (base over-flagging, the leak disqualifier, and a 2-defect recall floor) under a --max-spend enforced between dispatches. Operator directive: a short eval, a swap, and a recorded decision beats a $15 process that finishes after the vendor has repriced the field.

**Reverses if:** A future eval finds two candidates separated by a defect class the quick battery drops — i.e. recall stops saturating. Then the dropped variants are buying information again and the full battery earns its cost.

**Evidence:** eval/RESULTS-2026-08-15.md; gate_eval.py --battery quick

**Interview cost:** $2.96

---

## 2026-08-15 — REJECT: Do NOT pin the anchor to the dated deepseek-v4-pro-0813 snapshot

**Roster:** `deepseek/deepseek-v4-pro` -> `deepseek/deepseek-v4-pro (unchanged)`

**Why:** It looked obviously right: published at $0.435/M — exactly what the stale table claimed for the floating alias — with cache reads at $0.003625/M, 27x below any reseller. The spend ledger refutes it. Measured, the dated slug bills $2.485/M blended against the floating alias's $1.001/M, ~2.5x WORSE, because its cheap endpoint is DeepSeek first-party and this account's OpenRouter privacy guardrail excludes it. In the eval the dated slug also cost $0.793 to interview against the floating alias's $0.149, and flagged 2.3 claims on a clean base against the field's 0.0-1.0. A published price is not a price you get.

**Reverses if:** fit_rates_from_ledger shows -0813's measured input rate below the seated anchor's — asserted by test_the_dated_slug_hypothesis_stays_dead, which goes red if that reverses.

**Evidence:** the cache tests::test_the_dated_slug_hypothesis_stays_dead; eval/RESULTS-2026-08-15.md §1

---

## 2026-08-15 — REJECT: Do NOT unblock DeepSeek first-party routing to get the 8x cache rate

**Roster:** `(unchanged)` -> `(unchanged; route pinned to fp8 resellers)`

**Why:** DeepSeek's own endpoint serves the anchor at $0.435/M in with $0.003625/M cache reads — 8x below GMICloud's $0.029 — and returns 404 because this account's OpenRouter privacy guardrail (openrouter.ai/settings/privacy) excludes providers that may train on inputs. Unblocking it would send investor artifacts and primary business data to a provider that trains on them. The pinned-reseller route already captures most of the saving ($0.02699 -> $0.00074 per round, 36x), so the marginal gain does not justify the exposure. Recorded as a decision rather than left as an open operator ask.

**Reverses if:** The gate's payload stops containing non-public business data, OR DeepSeek's data policy changes such that the privacy guardrail admits it — at which point the 8x cache rate is free of the tradeoff.

**Evidence:** provider probe: provider.only=[deepseek] -> 'No endpoints available matching your guardrail restrictions and data policy'; eval/RESULTS-2026-08-15.md §2

---

## 2026-08-15 — ACCEPT: Re-seat: deepseek-v4-flash anchors, minimax-m3 replaces qwen3.7-max

**Roster:** `deepseek/deepseek-v4-pro + z-ai/glm-5.2 + qwen/qwen3.7-max ($0.496/round measured)` -> `deepseek/deepseek-v4-flash + z-ai/glm-5.2 + minimax/minimax-m3 ($0.201/round measured); light = flash alone at $0.010`

**Why:** Quality did not discriminate — all 9 candidates hit 100% format, leak refusal, recall, figure coverage and zero bad citations, the second eval running to that result. So the swap is decided on the things that DID differ. deepseek-v4-flash matches the outgoing anchor on every quality measure at 13x less ($0.010 vs $0.131/round) and over-flags a clean base 1.0/run [0,1,2] against its 7.3 [7,7,8]; the outgoing anchor is excluded because OR-of-FAILs makes a clean-base flagger incapable of ever returning PASS. qwen3.7-max is unseated on COST, not quality: measured over 12 billed dispatches it is $0.239/round, above the $0.20 ceiling, and was already over when seated — the headline price hid it. minimax-m3 takes that seat at $0.035 with the field's cleanest base record [0,0,0] and its fastest median (65s). Three lineages preserved: DeepSeek, Zhipu, MiniMax.

**Reverses if:** deepseek-v4-flash's clean-base flags exceed 2.0/run on a >=5-trial base sample, OR a defect class the quick battery drops is shown to separate flash from a dearer seat. Either restores the case for a heavier anchor; the standing guard is test_anchor_seat_is_affordable_on_what_we_actually_pay.

**Evidence:** eval/RESULTS-2026-08-15.md; results-2026-08-15/scorecard.json; 108 dispatches

**Interview cost:** $2.96

---

## 2026-08-15 — REJECT: CORRECTION — the old anchor's over-flagging was fp8 quantization, not the model

**Roster:** `(unchanged)` -> `unchanged (deepseek-v4-flash + glm-5.2 + minimax-m3)`

**Why:** Earlier today this eval excluded deepseek-v4-pro on 7.3 clean-base flags/run and called the exclusion 'consistent and real, not variance'. A third arm pinned to digitalocean — the cheapest NON-quantized endpoint — measured [1,0,0], mean 0.33, landing on July's 0.67 baseline. fp8-quantized weights degrade this seat's judgement on a coverage-and-obedience task: GMICloud fp8 pinned [7,7,8], GMICloud fp8 default [4,2,4], non-quantized [1,0,0]. At full precision the seat is among the CLEANEST in the field. The RE-SEAT STANDS, but the reason is corrected: it loses on COST (~$0.151/round vs flash's ~$0.011 for identical 100% figure coverage), not on quality. Consequence adopted: cheapest-endpoint pinning is a quality decision, so the anchor now prefers digitalocean and deliberately forfeits the cache (measured $0.00148 flat vs $0.00140->$0.00030 cached — under a cent a round at production size, against a demonstrated quality risk).

**Reverses if:** deepseek-v4-flash is measured over-flagging a clean base at a quantized endpoint, or a non-quantized endpoint for it becomes materially dearer than digitalocean's 5.6% premium — either changes the pin. Separately, if fp8 is shown harmless for this model family on a >=5-trial sample, the anchor can take the cheaper cacheable route.

**Evidence:** eval/RESULTS-2026-08-15.md §4 'RESOLVED: it was fp8 quantization'; the prompt-cache probe runs on digitalocean vs streamlake/fp8

---

## 2026-08-22 — ACCEPT: Heavy panel: z-ai/glm-5.2 out, qwen/qwen3.7-plus in — a price move, not a defect

**Roster:** `deepseek/deepseek-v4-flash, z-ai/glm-5.2, minimax/minimax-m3` -> `deepseek/deepseek-v4-flash, qwen/qwen3.7-plus, minimax/minimax-m3`

**Why:** glm-5.2 repriced 0.308/0.968 -> 0.966/3.036 per 1M between 2026-08-16 and 2026-08-22 (3.1x), which lifted the heavy round above what the seat was chosen at. No new eval was needed: qwen3.7-plus sat the same 2026-08-15 quick battery on the same fixture and scored 100% format, 100% recall, 100% figure coverage and 0.0 false flags per clean run at 0.045 USD a production round against glm-5.2's 0.126 — cheaper AND cleaner on identical evidence. Three distinct lineages preserved (DeepSeek + Alibaba + MiniMax); Zhipu stays reachable via DIVERGENT_POOL for a --reviewers pick.

**Reverses if:** qwen3.7-plus returns a false flag on a clean base run, OR fails to return a parseable ledger on a production round, OR its price rises above glm-5.2's — any of the three puts glm-5.2 back. Note qwen3.7-plus triples to 0.96/3.84 above 256K prompt tokens; the gate's 150K input ceiling keeps every round below that tier, so a caller raising that ceiling also breaks this decision.

**Evidence:** eval/RESULTS-2026-08-15.md section 4 (scorecard); the 2026-08-22 cost re-seat (price refresh)

**Interview cost:** $0.13
