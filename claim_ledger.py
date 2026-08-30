#!/usr/bin/env python3
"""claim_ledger.py — a cross-lineage fact-check gate for anything you publish.

Give it a finished artifact, the primary data the claims came from, and the code or
notes that derived one from the other. It dispatches a panel of reviewers from model
lineages OTHER than the one that drafted the artifact, and returns a per-claim ledger:
every load-bearing claim marked TRACEABLE (with the primary-source line that supports
it), UNTRACEABLE, or CONTRADICTED.

It does not rewrite your work and it does not tell you your work is good. It tells you
which of your claims you cannot show a source for. That is the whole product.

WHAT THIS IS NOT. This is the reviewer-panel engine, and a panel is only half of a
serious fact-check. The other half is mechanical source confirmation — re-deriving a
figure in SQL against the database it came from, retrieving the lineage a claim actually
depends on. A standalone Python process cannot do that for you. If you have an agent
harness that can, run those first and feed the results in via --db-confirmations and
additional --primary-data. What ships here owns the model panel and the aggregation.

WHY THE REVIEWERS ARE A DIFFERENT LINEAGE. A model asked to check its own output returns
a CORRELATED second opinion, not an independent one: the framing it found natural while
drafting, it finds natural while reviewing. Same blind spots, now wearing a reviewer
label. Lineage diversity is the decorrelation lever, so the default roster deliberately
contains no seat from the family that most often does the drafting. If you draft with a
model on this roster, drop it with --reviewers.

THE BAR — "correct without exception" is operationalized here, not asserted:
  * Intake gate: primary data + lineage + final artifact must ALL be present, or the
    verdict is BLOCKED (= FAIL). A summary of your primary data is not primary data.
  * Each reviewer extracts every load-bearing claim and returns TRACEABLE (with a cited
    primary-source line) / UNTRACEABLE / CONTRADICTED. Default-to-UNTRACEABLE: a claim
    gets no benefit of the doubt just because it sounds right.
  * Aggregation is a deterministic OR-of-FAILs — ANY reviewer FAIL, any UNTRACEABLE, any
    CONTRADICTED, any BLOCKED, any unparseable verdict → the artifact FAILS. There is no
    vote, no quorum, no synthesis. It is unchaired by design: a chair could only ever
    launder a minority FAIL into a soft PASS, which is the failure this exists to stop.

Expect to fail. Across the author's first 122 production runs, 92 returned FAIL. That is
the gate working; an artifact that passes first try usually means the payload was too
thin to check.

COST. You pay your own OpenRouter bill — set OPENROUTER_API_KEY in a .env beside this
file. A light round (one anchor seat) runs about a cent; a heavy round (three seats,
three lineages) about ten to twenty. Iterate with --class light and spend --class heavy
once, at ship. The printed dollar figure is a FLOOR, not a forecast (see --help).

Exit code: 0 = PASS, 1 = FAIL/BLOCKED — so CI and scripts can gate on it.

Usage:
  python3 claim_ledger.py \
      --artifact       example/report.md \
      --primary-data   example/sales.csv \
      --lineage        example/derive.py \
      --class light \
      --outdir out/example
"""
import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time

# Reuse the proven OpenRouter plumbing rather than reinventing it.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import or_budget  # noqa: E402
import or_peer  # noqa: E402

# --- Reviewer pool ---------------------------------------------------------
# Non-Claude lineages only. DeepSeek-V4-Pro is the standing cross-lineage verifier and
# anchors both classes. The premium seats (gpt-5.6-sol, kimi-k3) and grok-4.5 stay
# reachable via --reviewers for the highest-stakes artifacts.
#
# THE ROSTER WAS INTERVIEWED, NOT ASSUMED (2026-07-30). Eight candidates ran the production
# reviewer prompt over a real bundle with eight planted defects, 3 trials each for the five
# plausible seats — 162 dispatches, $12.58. Full method + per-seat numbers:
# eval/{README,RESULTS}.md; raw ledgers under .../results/.
#
# What the interviews settled, and it is not what the charter assumed:
#   * EVERY candidate passed both hard gates on the defect battery. All eight extracted the
#     planted claim that is true in the world and absent from the bundle, and all eight
#     refused it. Nobody leaked outside knowledge.
#   * Defect recall saturated — 100% for seven of eight (gemini missed one). Figure coverage
#     saturated too: at equal trial depth all four finalists verify 96% of the artifact's
#     figures, and union coverage is the same for a trio, a pair, or ONE seat.
#   * So extra seats buy no measured coverage. What they buy is redundancy against one seat's
#     bad day, and insurance against a correlated blind spot a battery everyone passes cannot
#     detect. That is a real but unmeasured benefit, and it is why this is three seats and not
#     one — stated honestly rather than dressed up as coverage.
#
# The seats, over 27 dispatches each (format = production-fatal failures only; an empty
# 200-response is retried by dispatch_one and does not count):
#   deepseek-v4-pro  96.3%  100% recall  96% figs  0.67 flags/clean-run  $0.076  143s med, 1185s max
#   glm-5.2         100.0%  100% recall  96% figs  1.33 flags/clean-run  $0.155   80s med,  499s max
#   qwen3.7-max     100.0%  100% recall  96% figs  0.00 flags/clean-run  $0.274  116s med,  216s max
#   grok-4.5        100.0%  100% recall  96% figs  0.00 flags/clean-run  $0.372   64s med,   89s max
#   kimi-k2.6        92.6% — FAILS the format gate. gpt-5.6-sol flagged 32 claims on a CLEAN
#     base including the document's own provenance header; in an OR-of-FAILs panel that seat
#     alone can never return PASS, at $1.11 a round.
#
# grok-4.5 STAYS OFF the default panel. It interviewed well — the most predictable seat in the
# field by a distance — but qwen3.7-max matches it on every quality measure at 26% less, so
# nothing here justifies reversing the 2026-07-30 cost decision. Seat it deliberately when
# latency predictability is worth the premium (89s worst case against qwen's 216s):
# `--reviewers deepseek/deepseek-v4-pro,z-ai/glm-5.2,x-ai/grok-4.5`.
# RE-SEATED 2026-08-15 (eval: eval/RESULTS-2026-08-15.md, $2.96, 108
# dispatches). deepseek-v4-flash replaces deepseek-v4-pro as the anchor:
#
#   seat                 base flags/run   claims/trial   fig cover   $/prod round
#   deepseek-v4-flash    1.0  [0,1,2]         37.2          100%        0.010
#   deepseek-v4-pro      0.33 [1,0,0] *       43.3          100%        0.151 *
#                        (* at a NON-quantized endpoint — see the correction below)
#
# 13-14x cheaper for the same measured quality: identical 100% on format, leak refusal, recall
# and figure coverage. Same DeepSeek lineage, so the heavy panel's cross-lineage property is
# unchanged.
#
# THE OUTGOING ANCHOR IS UNSEATED ON COST, NOT ON QUALITY. Correcting an earlier reading in
# this same branch: it appeared to fail the over-flag gate at 7.3 clean-base flags/run, and that
# turned out to be an artifact of the ENDPOINT, not the model. Measured across three routings of
# the identical model, prompt and fixture:
#
#   GMICloud fp8, route pinned      [7, 7, 8]   7.3
#   GMICloud fp8, default routing   [4, 2, 4]   3.3
#   DigitalOcean, NOT quantized     [1, 0, 0]   0.33   <- matches July's 0.67 baseline
#
# fp8-quantized weights measurably degrade this seat's judgment on a coverage-and-obedience
# task. At full precision deepseek-v4-pro is among the CLEANEST seats in the field. It is still
# not seated, because at DigitalOcean rates it costs ~$0.151/round against flash's ~$0.011 —
# 14x — for the same 100% figure coverage. That is a COST decision and must not be misremembered
# as a quality one.
#
# STANDING WARNING FOR EVERY ROUTING PIN BELOW: the cheapest endpoints are fp8/fp4 quantized,
# and quantization is a QUALITY variable on judgment work, not only a price one. Prefer the
# cheapest NON-quantized endpoint when the premium is small; accept fp8 only where the premium
# is large AND that seat has been measured clean at fp8. A/B a pin with
# OR_PEER_NO_PROVIDER_PIN=1 plus an explicit non-quantized pin — default routing alone does
# NOT isolate this, because it usually picks the same cheap quantized endpoint.
ANCHOR = "deepseek/deepseek-v4-flash"  # cheapest seat that clears every gate; anchors light

# ROUTING PREFERENCES — measured 2026-08-15. On a multi-provider slug this is worth more than
# the slug: `deepseek/deepseek-v4-pro` has 18 endpoints spanning $0.348-$1.910 per 1M input,
# and OpenRouter's default routing moved us between GMICloud and Novita on CONSECUTIVE
# requests. That is expensive twice over. A prompt cache is per-provider, so a payload that
# bounces between backends can never reuse its own prefix — and the gate's payload is mostly
# stable sources, which is exactly the thing worth caching.
#
# Measured on the real gate prompt, same sources, edited artifact between rounds:
#   unpinned            21,804 tok,      0 cached,  $0.02699   (round 2 landed on Novita)
#   pinned gmicloud/fp8 21,810 tok, 21,760 cached,  $0.00074   — 36x cheaper
#
# allow_fallbacks stays TRUE deliberately. The gate is fail-closed, so an unavailable endpoint
# under `allow_fallbacks: False` converts directly into a FAIL on an artifact nobody reviewed
# — trading a cost saving for a correctness failure. Falling back loses the cache and keeps the
# verdict, which is the right way round. The listed endpoints are the cheapest that also price
# cache reads; ordering is by measured input price, then by 1-day uptime.
#
# NOT USED, and it is a judgment call rather than an oversight: DeepSeek's OWN endpoint is
# cheaper still ($0.435/M in, and $0.003625/M cache reads — 8x below GMICloud's). It is blocked
# by this account's OpenRouter privacy guardrail, which filters providers that may train on
# inputs. Unblocking it would send investor artifacts and primary business data to a provider
# that trains on them. The saving does not justify that, and the pinned reseller route already
# captures most of it.
# ROUTING PREFERENCES MOVED TO or_peer.PROVIDER_PREFS (2026-08-16). They were measured here, on
# this gate's own prompt, but they applied only to this caller — so every other caller in the
# harness routed blind, and OpenRouter's price-chasing default sent
# them to quantized endpoints. Two copies of a quality-critical routing table is one copy too
# many; this is now a re-export so the evidence and the map live in one place.
#
# The measurements behind each entry are recorded at the definition site. The kill-switch is
# unchanged and still honors OR_PEER_NO_PROVIDER_PIN=1.
PROVIDER_PREFS = or_peer.PROVIDER_PREFS
provider_prefs = or_peer.provider_prefs
# DeepSeek + Alibaba + MiniMax — three distinct lineages.
#
# HISTORY. The panel was [deepseek-v4-pro, glm-5.2, qwen3.7-max] at $0.496 a round until
# 2026-08-15, when qwen3.7-max was unseated on cost (not quality): measured over 12 billed
# dispatches it cost $0.239 a round, above the $0.20 affordability ceiling it had been seated
# under — the headline price hid it. minimax-m3 took that seat at $0.035 with the cleanest
# clean-base record in the field ([0,0,0]) and the fastest median in the eval (65s).
#
# 2026-08-22 — glm-5.2 OUT, qwen3.7-plus IN, on a price move rather than a defect. Between
# 08-16 and 08-22 glm-5.2 went $0.308/$0.968 -> $0.966/$3.036 per 1M (3.1x), which lifted the
# heavy round it sits in above what it was seated at. No new eval was needed to replace it:
# qwen3.7-plus sat the SAME 2026-08-15 quick battery and scored 100% format, 100% recall, 100%
# figure coverage and 0.0 false flags per clean run at $0.045 a production round against
# glm-5.2's $0.126 — cheaper and cleaner on the identical fixture (eval/
# RESULTS-2026-08-15.md §4). Lineage count is unchanged at three; Zhipu leaves the default
# panel and stays reachable in DIVERGENT_POOL for a --reviewers pick.
#
# Caveat carried forward from the price table: qwen3.7-plus triples to $0.96/$3.84 above 256K
# prompt tokens. The gate's own --max-input-tokens ceiling is 150K, so no gate round can reach
# that tier; a caller that raises the ceiling past 256K breaks the assumption.
HEAVY_DEFAULT = [ANCHOR, "qwen/qwen3.7-plus", "minimax/minimax-m3"]
DIVERGENT_POOL = [
    "z-ai/glm-5.2",       # Zhipu (CN)
    "x-ai/grok-4.5",      # xAI (US) — off the default panel, see above; --reviewers only
    "openai/gpt-5.6-sol", # OpenAI (US) — premium
    "moonshotai/kimi-k3", # Moonshot (CN) — premium
]
# Lineage keys so --drafted-by can exclude a correlated seat.
LINEAGE = {
    "deepseek/deepseek-v4-pro": "deepseek",
    "z-ai/glm-5.2": "zhipu",
    "x-ai/grok-4.5": "xai",
    "openai/gpt-5.6-sol": "openai",
    "moonshotai/kimi-k3": "moonshot",
    # Every interviewed candidate is mapped, seated or not: choose_reviewers' backfill can
    # reach any pool member, and the distinct-lineage test indexes this dict directly, so an
    # unmapped seat is a KeyError rather than a soft fallback.
    "qwen/qwen3.7-max": "alibaba",
    # 2026-08-15 seats + interviewed candidates. deepseek-v4-flash shares the DeepSeek lineage
    # with deepseek-v4-pro by construction — never seat both and call it decorrelated.
    "deepseek/deepseek-v4-flash": "deepseek",
    "deepseek/deepseek-v4-pro-0813": "deepseek",
    "minimax/minimax-m3": "minimax",
    "qwen/qwen3.7-plus": "alibaba",
    "x-ai/grok-4.6": "xai",
    "z-ai/glm-5": "zhipu",
    "z-ai/glm-4.7": "zhipu",
    "google/gemini-3.1-pro-preview": "google",
    "moonshotai/kimi-k2.6": "moonshot",  # SAME lineage as kimi-k3 — never seat both
    # drafting-orchestrator lineages that must never sit as a verdict seat:
    "claude": "anthropic", "claude-opus": "anthropic", "opus": "anthropic",
    "sonnet": "anthropic", "anthropic": "anthropic",
}

REVIEWER_SYSTEM = """You are an adversarial FACT-CHECKER on an ad hoc Quality team. The artifact
you are given is INVESTOR- or CUSTOMER-FACING and must be factually correct WITHOUT EXCEPTION. Your
job is not to improve it, praise it, or judge its writing — only to establish whether every
load-bearing factual claim in it is TRUE, TRACEABLE to the supplied primary data, and CONSISTENT
with the final output.

You are given three things, in this order: (1) the PRIMARY DATA the artifact should derive from,
(2) the DATA LINEAGE (how numbers were produced), and (3) LAST, at the end of this message, the
FINAL ARTIFACT under review. The sources come first so you read them before the claims; the
artifact is the last thing in the message and it is the thing you are checking. Trust ONLY these
three. Do not use outside knowledge to "fill in" support for a claim — if the support is not in
the supplied primary data / lineage, the claim is UNTRACEABLE.

Procedure:
1. Extract EVERY load-bearing factual claim: specific numbers, dates, named entities, relationships,
   comparisons, causal or superlative assertions. Decorative language is not a claim.
2. For each claim, find the specific primary-source location (file + line/row, query result,
   document section) that supports it, and check the lineage step that produced it.
3. Classify each claim:
   - TRACEABLE  — supported by a cited primary-source location AND consistent with lineage + the
     final output. You MUST cite the source; a TRACEABLE with no citation is invalid.
   - UNTRACEABLE — you cannot connect it to the supplied primary data/lineage, or the lineage is
     incomplete. Default here when unsure. No benefit of the doubt.
   - CONTRADICTED — it conflicts with the primary data, the lineage, or another claim in the artifact.

Rules:
- Default-to-UNTRACEABLE. A claim you merely "believe is probably right" is UNTRACEABLE, not TRACEABLE.
- "Looks fine" / "no issues" with no per-claim ledger is a prohibited output.
- No exclamation marks. No marketing language. Terse and specific.

Return your answer as a single JSON object, and NOTHING else after it, in exactly this shape:

{
  "claims": [
    {"claim": "<verbatim or tight paraphrase>", "classification": "TRACEABLE|UNTRACEABLE|CONTRADICTED",
     "cited_source": "<file:line / row / section, or empty>", "note": "<one line>"}
  ],
  "verdict": "PASS|FAIL",
  "reason": "<one line: PASS iff every claim TRACEABLE; else name the first blocking claim>"
}

verdict is PASS if and only if every claim is TRACEABLE. Any UNTRACEABLE or CONTRADICTED claim = FAIL.
"""


# Build junk a directory walk must never bill a reviewer to read. These hold no primary
# data and no lineage by construction — a claim cannot trace to compiled bytecode.
SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules", ".pytest_cache",
             ".mypy_cache", ".ruff_cache", ".ipynb_checkpoints", "dist", ".next"}
# Binary formats a text reviewer cannot use. errors="replace" made these LOOK readable:
# they became megabytes of U+FFFD billed at full input price.
BINARY_EXTS = {".pyc", ".pyo", ".so", ".o", ".a", ".dylib", ".dll", ".exe", ".bin",
               ".zip", ".gz", ".bz2", ".xz", ".tar", ".7z", ".rar", ".whl",
               ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".ico",
               ".pdf", ".woff", ".woff2", ".ttf", ".otf", ".eot",
               ".mp4", ".mov", ".webm", ".mp3", ".wav",
               ".parquet", ".db", ".sqlite", ".sqlite3", ".xlsx", ".xls", ".pkl", ".npy"}


def _looks_binary(fp):
    """A NUL byte in the first 8KB. Catches the extensionless/misnamed cases the
    extension list cannot."""
    try:
        with open(fp, "rb") as fh:
            return b"\x00" in fh.read(8192)
    except OSError:
        return False


def read_source(path):
    """Read a file, or concatenate a directory's TEXT files, labeled by path.

    A directory expands to every file under it, which is the documented sharp edge that
    caused the 2026-07-29 spend incident. The 2026-07-30 audit found the edge was worse
    than "big": passing `analysis/` read 505,859 tokens, and 159,820 of them (32%) were
    `__pycache__/*.pyc` — compiled bytecode, decoded with errors="replace" into a wall
    of replacement characters, shipped to three reviewers at full input price, every
    round. Skipping it is free: no factual claim traces to a .pyc.

    Every skip is LABELED in the payload rather than silently dropped, so a reviewer
    that needs a source can see it was withheld and mark the claim UNTRACEABLE.
    """
    chunks = []
    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in sorted(dirs) if d not in SKIP_DIRS]
            for fn in sorted(files):
                fp = os.path.join(root, fn)
                if os.path.splitext(fn)[1].lower() in BINARY_EXTS or _looks_binary(fp):
                    chunks.append(f"----- {fp} (SKIPPED: binary, not reviewable text) -----")
                    continue
                if os.path.getsize(fp) > 400_000:
                    chunks.append(f"----- {fp} (SKIPPED: >400KB) -----")
                    continue
                try:
                    with open(fp, "r", encoding="utf-8", errors="replace") as fh:
                        chunks.append(f"----- {fp} -----\n{fh.read()}")
                except OSError as e:
                    chunks.append(f"----- {fp} (UNREADABLE: {e}) -----")
    else:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            chunks.append(f"----- {path} -----\n{fh.read()}")
    return "\n\n".join(chunks)


# --- Payload preflight -----------------------------------------------------
# WHY THIS EXISTS (incident 2026-07-29, $52 in two days). read_source() expands a
# DIRECTORY into every file under it. On 2026-07-27 the gate was called with two
# primary-data FILES: ~38K input tokens per reviewer, $0.13 a run. On 2026-07-28 the
# same gate was called with `--primary-data <dir>`: ~495K input tokens per reviewer,
# $1.80 a run — a 13x payload increase from one argument, with no warning, no printed
# size, and no ceiling. Run COUNT barely moved (26 -> 25 a day); cost per run went 8x.
# The run that finally stopped it was OpenRouter returning HTTP 403 "Key limit exceeded".
# So: the payload is measured and priced BEFORE any money is spent, and a payload over
# the ceiling refuses to dispatch rather than silently billing for it.
def estimate_tokens(text):
    """Cheap, provider-agnostic token estimate. Deliberately not a tokenizer: this
    guards an order of magnitude, and ~4 chars/token is right to within ~15%."""
    return len(text) // 4


def source_sizes(paths):
    """[(path, tokens)] per supplied source, biggest first — so an over-budget message
    names the argument to fix instead of just reporting a total."""
    out = [(p, estimate_tokens(read_source(p))) for p in paths]
    out.sort(key=lambda t: -t[1])
    return out


def estimate_cost(reviewers, input_tokens, max_tokens):
    """Worst-case USD for one panel round: every seat reads the whole payload and
    writes a full-length ledger. Uses or_peer's price table (an estimate — the billed
    number comes back in the response), which is what a preflight needs."""
    total = 0.0
    for m in reviewers:
        pin, pout = or_peer.PRICES.get(m, (0.0, 0.0))
        total += (input_tokens / 1e6) * pin + (max_tokens / 1e6) * pout
    return total


def _resolve_spend_log():
    """The spend ledger must be ONE file for the whole repo, not one per CWD.

    WHY (audit 2026-07-30). This was the relative string
    "out/_spend.jsonl", so it resolved against whatever CWD the caller
    happened to have. On 2026-07-29 the six most expensive runs of the day — ~$10 of
    $12.95 — ran from a worktree, and every part of the guard built the day before went
    blind at once: `spend_history()` read an empty ledger, so the counter printed
    "round 1" on an artifact already 4 rounds and $1.83 deep, the 4+-heavy-rounds nudge
    never fired, and each run's own spend was appended to a file that died with the
    worktree. The main ledger's mtime is frozen at 19:07 while six later ledger.json
    files sit on disk. A CWD-relative guard cannot hold in a repo whose own rules
    MANDATE worktree isolation — the isolation the rules require is the thing that
    breaks it.

    `git rev-parse --git-common-dir` resolves to the MAIN checkout's .git even from
    inside a linked worktree, which is exactly the shared anchor this needs. Anchored on
    the script's own directory (not CWD) so the answer cannot depend on the caller.
    """
    override = os.environ.get("CLAIM_LEDGER_SPEND_LOG")
    if override:
        return override
    return os.path.join(_repo_root(), "out", "_spend.jsonl")


def _repo_root():
    """The MAIN checkout's root, resolved from this file's own directory rather than CWD."""
    root = None
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=10,
            cwd=os.path.dirname(os.path.abspath(__file__)))
        if out.returncode == 0 and out.stdout.strip():
            root = os.path.dirname(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    if not root:  # not a git checkout at all — fall back to this file's repo layout
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return root


SPEND_LOG = _resolve_spend_log()


def spend_log_path():
    """Re-read the override each call so tests can redirect the ledger without reimport."""
    return os.environ.get("CLAIM_LEDGER_SPEND_LOG") or SPEND_LOG


def surface_key(artifact, surface=None):
    """The STABLE identity the round counter keys on — the surface, not the file path.

    WHY (observed 2026-08-05). The counter matched on the artifact's BASENAME. Gating
    `report-draft.md` printed "round 5 — $1.83 already spent"; the same report, correctly
    repointed at its rendered `report-prose.md`, printed nothing at all — a fresh artifact,
    round 1, $0. So the round-counter guard ("four or more heavy rounds on one artifact
    means the loop is wrong, not the artifact") was defeated by renaming or repointing the
    file, which is exactly what a session does when it FIXES the surface. Same shape as the
    2026-07-30 CWD-anchored ledger bug: a counter that resets precisely when you do the
    right thing.

    The default key is the artifact's containing DIRECTORY relative to the repo root, which
    is what actually survives a rename or a repoint within one surface — a draft and its
    rendered prose sit side by side, so they now count as the same artifact with nothing to
    remember. `--surface` overrides it when one directory genuinely holds several unrelated
    artifacts. The failure this trades into is a counter that fires EARLY on a multi-artifact
    directory, which is the safe direction for a spend nudge.
    """
    if surface:
        return surface.strip().lower()
    d = os.path.dirname(os.path.abspath(artifact)) or "."
    root = _repo_root()
    try:
        rel = os.path.relpath(d, root)
    except ValueError:  # different drive on win32
        rel = d
    if rel.startswith(".."):  # outside the checkout — key on the absolute directory
        rel = d
    return rel.replace(os.sep, "/").strip("./").lower() or "."


def spend_history(artifact, surface=None):
    """(rounds_already_run, usd_already_spent) for this artifact's SURFACE. The 2026-07-28
    grind put NINE full heavy panels over one section pair — each re-verifying ~100 already-
    TRACEABLE claims at full price to surface the last handful — and nothing anywhere
    printed that it was round nine."""
    rounds, spent = 0, 0.0
    key = surface_key(artifact, surface)
    basename = os.path.basename(artifact)
    try:
        with open(spend_log_path(), "r", encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Rows written before 2026-08-23 carry no "surface" — derive it from the
                # recorded path so the history of an in-flight artifact is not zeroed by
                # the very change that stops it resetting.
                rec_key = rec.get("surface") or surface_key(rec.get("artifact", ""))
                # A UNION of the two identities, not a swap. The basename arm is the
                # original rule and it catches an artifact that MOVED between directories;
                # the surface arm catches one that was RENAMED or repointed within one.
                # Either alone leaves a way to reset the counter by doing something
                # reasonable, and the two failure directions are not symmetric: an
                # over-count makes a spend nudge noisy, an under-count is what paid for
                # nine heavy rounds on one section pair. Skip the basename arm when the
                # caller named a surface explicitly — an explicit identity is authoritative.
                same_name = (not surface
                             and os.path.basename(rec.get("artifact", "")) == basename)
                if rec_key == key or same_name:
                    rounds += 1
                    spent += rec.get("cost_usd") or 0.0
    except OSError:
        pass
    return rounds, spent


def record_spend(artifact, cls, reviewers, input_tokens, cost_usd, verdict, surface=None):
    path = spend_log_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "artifact": artifact,
                "surface": surface_key(artifact, surface),
                "class": cls, "reviewers": reviewers, "input_tokens": input_tokens,
                "cost_usd": round(cost_usd, 4), "verdict": verdict,
            }) + "\n")
    except OSError as e:  # a ledger-write failure must never fail a gate verdict
        print(f"  (warning: could not append to {path}: {e})", file=sys.stderr)


# ── a FAIL is the operator's to disposition, so the gate holds for them ────────────────────
#
# WHY (audit 2026-08-03). A FAIL exited 1 and left the agent to decide what came next. Paired
# with the Stop guard's signal 3 the observed behavior was ANOTHER ROUND: one post-block
# segment on 2026-07-29 ran nine dispatches, and that day printed $34.73 of OpenRouter spend —
# the worst in the account's history. The gate's own charter already says a QA-failed artifact
# must not reach an investor or customer as-is and that the disposition (fix + re-run, or
# override on record) is an OPERATOR gate. So the hold is recorded here, by the gate, not left
# to the agent: an agent-remembered declaration is a human-remembered discipline by proxy.
#
# This does NOT halt or loop the pipeline — fail-closed is a verdict rule. The gate still
# completes, still prints the QA-FAILED note, still exits 1. The hold cannot change any of
# that, and neither can a hold-write failure.
CONTINUATION = os.path.join(os.path.dirname(os.path.abspath(__file__)), "continuation.py")


def _run_hold(session_id, message):
    """Record the hold via the same CLI the agent uses. Returns True on success."""
    proc = subprocess.run(
        [sys.executable, CONTINUATION, "--session", session_id, "hold", message],
        capture_output=True, text=True, timeout=30,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if proc.returncode != 0:
        print(f"  (warning: could not record hold: {proc.stderr.strip()[:200]})",
              file=sys.stderr)
    return proc.returncode == 0


def record_fail_hold(verdict, artifact, reason, rounds=0, spent=0.0):
    """On a dispatched FAIL only, record what the operator must disposition. Never raises.

    OPTIONAL AGENT-HARNESS INTEGRATION, inert on its own. If an agent harness is driving
    this gate and exports CLAUDE_CODE_SESSION_ID, the FAIL is written into that session's
    work queue via a sibling `continuation.py`, so the session cannot quietly end on a
    failed gate. With no such variable — a human at a shell, or CI — this returns
    immediately and changes nothing. A missing continuation.py is caught and warned about,
    never raised: a bookkeeping failure must not alter a verdict.

    Deliberately NOT on BLOCKED. A BLOCKED verdict is an invocation error — missing primary
    data/lineage, or a payload over the token ceiling — which the agent can fix in one step
    and re-run at $0. Holding there would stall a session that can resolve itself, which is
    an unnecessary interruption of a session that can fix itself. Only a FAIL,
    where the panel actually ran and found untraceable or contradicted claims, is the
    operator's call.
    """
    if verdict != "FAIL":
        return
    session_id = (os.environ.get("CLAUDE_CODE_SESSION_ID")
                  or os.environ.get("CLAUDE_SESSION_ID") or "")
    if not session_id:
        return  # CI / script context: no session to hold, and that is not an error
    message = (f"QA-FAILED ({verdict}) on {os.path.basename(artifact)} — round {rounds + 1}, "
               f"${spent:.2f} spent on this artifact so far. First blocking item: {reason} "
               f"Your call: fix every claim in the ledger and re-run (--class light while "
               f"iterating), or override with this failure on record. Do NOT re-run the panel "
               f"to try for a different verdict.")
    try:
        _run_hold(session_id, message)
    except Exception as e:  # noqa: BLE001 — a hold failure must never change a gate verdict
        print(f"  (warning: could not record hold: {e})", file=sys.stderr)


def _has_content(path):
    """True if the file (or any file under the dir) holds non-whitespace content."""
    text = read_source(path)
    # Strip the "----- <path> -----" labels read_source inserts, then check for real content.
    stripped = re.sub(r"^----- .+ -----$", "", text, flags=re.MULTILINE)
    return bool(stripped.strip())


def choose_reviewers(cls, drafted_by, override):
    if override:
        seats = [s.strip() for s in override.split(",") if s.strip()]
    elif cls == "light":
        seats = [ANCHOR]
    else:  # heavy
        seats = list(HEAVY_DEFAULT)
    # Exclude any seat sharing the drafting orchestrator's lineage.
    if drafted_by:
        draft_lin = LINEAGE.get(drafted_by.strip().lower(), drafted_by.strip().lower())
        kept = [s for s in seats if LINEAGE.get(s, s) != draft_lin]
        if len(kept) < len(seats):
            # Backfill from the pool to preserve panel size, still excluding the lineage.
            for cand in [ANCHOR] + DIVERGENT_POOL:
                if len(kept) >= len(seats):
                    break
                if cand not in kept and LINEAGE.get(cand, cand) != draft_lin:
                    kept.append(cand)
        seats = kept
    # De-dup, preserve order.
    seen, out = set(), []
    for s in seats:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def parse_ledger(content):
    """Tolerantly extract the reviewer's JSON ledger. Returns (dict|None, error)."""
    if not content or not content.strip():
        return None, "empty completion"
    text = _FENCE.sub("", content).strip()
    # Grab the last {...} block (models sometimes prepend prose despite instructions).
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None, "no JSON object found"
    blob = text[start:end + 1]
    try:
        d = json.loads(blob)
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"
    if "verdict" not in d or "claims" not in d:
        return None, "ledger missing 'verdict' or 'claims'"
    return d, None


def normalize_verdict(ledger):
    """Enforce the bar independently of the model's self-reported verdict: any
    non-TRACEABLE claim => FAIL, regardless of what the model wrote in 'verdict'."""
    claims = ledger.get("claims") or []
    bad = [c for c in claims
           if str(c.get("classification", "")).upper() != "TRACEABLE"]
    # A TRACEABLE claim with no citation is not actually traceable.
    uncited = [c for c in claims
               if str(c.get("classification", "")).upper() == "TRACEABLE"
               and not str(c.get("cited_source", "")).strip()]
    if bad or uncited:
        return "FAIL", bad, uncited
    if not claims:
        # No load-bearing claims extracted is itself suspect for a published artifact.
        return "FAIL", [], []
    return "PASS", [], []


TRUNCATION_CEILING = or_peer.TRUNCATION_CEILING_TOKENS


def dispatch_one(model, system, user, max_tokens, effort, key, empty_retries=2,
                 truncation_retries=2, truncation_ceiling=TRUNCATION_CEILING,
                 label=None):
    """Dispatch one reviewer.

    TRUNCATION IS NOT HANDLED HERE. It is handled once, in or_peer.dispatch_chat, for
    every caller. This function only OPTS IN — it asks for
    ``truncation_retries=2`` because a ~40-claim ledger genuinely needs the room, where
    most callers do not. It used to carry its own doubling loop; that loop was correct and
    it was still the wrong place for it, because other callers could not reuse it
    and shipped a brief cut off mid-word to a board record the very next day.

    An EMPTY 200-response IS still retried here, and that is a deliberate distinction: an
    empty completion is a transport artifact (or_peer's own `retries` covers exceptions,
    not a successful response with blank content — without this, ~40% of runs lose a
    reviewer to noise). It is not a ceiling problem, so it must NOT raise the budget.

    Malformed-but-COMPLETE output is not retried at all: that is a real signal about the
    reviewer and is passed through to FAIL untouched.

    Safety property preserved: if the response is still truncated after the shared layer's
    retries, the verdict is FAIL. A truncated ledger never PASSes — this widens what gets
    a second chance, never what gets through.
    """
    t0 = time.time()
    cost_total = 0.0
    empty_attempts = 0
    while True:
        try:
            data = or_peer.dispatch_chat(
                model, system=system, user=user, max_tokens=max_tokens,
                temperature=0.2, reasoning_effort=effort, key=key,
                retries=2, timeout=300,
                truncation_retries=truncation_retries,
                truncation_ceiling_tokens=truncation_ceiling,
                caller="claim_ledger", label=label,
                provider=provider_prefs(model),
            )
        except Exception as e:  # noqa: BLE001 — a dispatch failure blocks, but it is NOT a content verdict
            # A transport failure means the artifact was never evaluated. It still
            # BLOCKS (fail-closed is the charter), but it must never render as a
            # content FAIL: an agent skimming the verdict line would otherwise record
            # "the claims failed fact-checking" when nothing was ever checked.
            return {"model": model, "ok": False, "error": str(e), "dt": time.time() - t0,
                    "cost": cost_total, "ledger": None, "verdict": "ERROR",
                    "error_kind": "transport",
                    "reason": f"dispatch error (artifact NOT evaluated): {e}",
                    "bad": [], "uncited": [], "content": ""}
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message", {}) or {}).get("content") or ""
        cost_total += or_peer.cost(model, data.get("usage", {}) or {})

        if not content.strip() and empty_attempts < empty_retries:
            empty_attempts += 1
            print(f"  … {model}: empty completion, re-dispatching "
                  f"(attempt {empty_attempts + 1}/{empty_retries + 1})", flush=True)
            continue

        break
    dt = time.time() - t0
    usage = data.get("usage", {}) or {}
    c = cost_total
    truncated = or_peer.was_truncated(choice)
    ledger, err = parse_ledger(content)
    if ledger is None:
        reason = f"unparseable ledger ({err})" + (" [TRUNCATED]" if truncated else "")
        return {"model": model, "ok": False, "error": err, "dt": dt, "cost": c,
                "ledger": None, "verdict": "FAIL", "reason": reason,
                "bad": [], "uncited": [], "content": content}
    verdict, bad, uncited = normalize_verdict(ledger)
    if truncated:
        verdict, reason = "FAIL", "reviewer output TRUNCATED — verdict not trustworthy"
    else:
        reason = ledger.get("reason", "")
    return {"model": model, "ok": True, "error": None, "dt": dt, "cost": c,
            "ledger": ledger, "verdict": verdict, "reason": reason,
            "bad": bad, "uncited": uncited, "content": content,
            # The vendor's own token counts, passed through. Any caller comparing what a
            # dispatch COST against what the price table PREDICTED needs the actual
            # completion count: reasoning tokens are billed as output and routinely dwarf a
            # fixed assumption, so a "measured vs table" ratio computed from an assumed
            # output length silently measures verbosity and reports it as a price error.
            "usage": {"prompt_tokens": usage.get("prompt_tokens"),
                      "completion_tokens": usage.get("completion_tokens"),
                      "cached_tokens": (usage.get("prompt_tokens_details") or {})
                      .get("cached_tokens"),
                      "provider": data.get("provider")}}


def build_user_prompt(artifact, primary, lineage, db_conf):
    """Sources FIRST, artifact LAST — a deliberately cacheable prefix (2026-08-15).

    WHY THE ORDER CHANGED. Prompt caching keys on an EXACT prefix: everything from the start of
    the request up to the first byte that differs is what a provider can serve from cache. The
    artifact is the one part that changes between iteration rounds — it is what you just edited
    — and the sources are the part that does not. With the artifact first, the very first
    section differed on every round, so NOTHING after it could ever be cached and every round
    re-read the whole payload at cold price. Putting the stable sources first makes the bulk of
    the payload a shared prefix across every round on one artifact, across every seat sharing a
    provider, and across the eval's repeated trials.

    The saving is not marginal. The payload is input-dominated (the primary data dwarfs the
    artifact), and on the pinned anchor deepseek/deepseek-v4-pro-0813 a cached input token bills
    at $0.003625/M against $0.435/M cold — 120x. glm-5.2 discounts 5.4x, qwen3.7-plus 5x. Every
    iteration round after the first on the same sources is close to free on its input half.

    Two properties this must not break:
      * The prefix is only stable if the SOURCES are byte-identical round to round. Reordering
        the primary-data files, or letting a directory walk return them in a different order,
        silently costs the whole discount and nothing visibly fails. record_dispatch logs
        cached_prompt_tokens so a broken prefix is observable rather than merely expensive.
      * The reviewer still has to know what it is checking. The artifact is now last, so the
        system prompt states the order explicitly and the artifact keeps its own loud header —
        an unlabelled document at the end of 100K tokens of sources reads as more source.
    """
    parts = [
        "# PRIMARY DATA (source of record — trace every claim to here)\n",
        primary,
        "\n\n# DATA LINEAGE (how the numbers were produced)\n",
        lineage,
    ]
    if db_conf:
        parts += ["\n\n# db-agent SOURCE CONFIRMATIONS (ground-truth SQL results from the DB)\n",
                  db_conf]
    parts += [
        "\n\n# FINAL ARTIFACT (the investor/customer-facing output under review)\n"
        "# Everything above is SOURCE. Everything below is the output you are fact-checking:\n"
        "# extract its claims and trace each one back up into the sources above.\n",
        artifact,
    ]
    return "".join(parts)


def main():
    ap = argparse.ArgumentParser(description="claim-ledger — a cross-lineage fact-check gate. Returns a per-claim "
                    "ledger: TRACEABLE (with a cited source line), UNTRACEABLE, or "
                    "CONTRADICTED. Exit 0 = PASS, 1 = FAIL/BLOCKED.")
    ap.add_argument("--artifact", required=True, help="REQUIRED. The finished artifact whose claims are being checked.")
    ap.add_argument("--primary-data", action="append", default=[],
                    help="REQUIRED by the intake gate. The source-of-record data the claims "
                         "trace to; repeatable. A summary is not primary data. Narrow this "
                         "to the files the claims actually use — a directory expands to "
                         "every file under it, per seat, per round.")
    ap.add_argument("--lineage", action="append", default=[],
                    help="REQUIRED by the intake gate. How the numbers were produced from the "
                         "primary data — the script, query, or notes; repeatable.")
    ap.add_argument("--surface", default=None,
                    help="stable identity for the round counter (default: the artifact's "
                         "directory relative to the repo root, so a draft and its rendered "
                         "output count as ONE artifact across a repoint)")
    ap.add_argument("--db-confirmations", default=None,
                    help="Optional. A file of mechanical source confirmations (e.g. figures "
                         "re-derived in SQL against the source database) to hand the panel.")
    # DEFAULT IS light (changed 2026-07-30, operator call). Heavy is 12.6x light on the
    # same payload — measured $1.67 vs $0.13 a round at ~130K tokens — and the 2026-07-28
    # grind paid for NINE heavy rounds over one section pair, each re-verifying ~100
    # already-TRACEABLE claims at full price. Defaulting to heavy meant every iteration
    # round bought the ship gate. Heavy is now what you ask for, explicitly, at ship.
    ap.add_argument("--class", dest="cls", choices=["heavy", "light"], default="light")
    ap.add_argument("--drafted-by", default=None,
                    help="model/lineage that produced the artifact — excluded from the panel")
    ap.add_argument("--reviewers", default=None,
                    help="comma-separated model slugs to override the default panel")
    ap.add_argument("--outdir", default=None, help="write ledger.json + ledger.md here")
    ap.add_argument("--max-tokens", type=int, default=12000)
    ap.add_argument("--reasoning-effort", default="high")
    ap.add_argument("--max-spend", type=float, default=None,
                    help="cumulative USD ceiling for this surface THIS SESSION before a "
                         "check-in (default $3.00, or $OR_BUDGET_USD; 0 disables).")
    ap.add_argument("--max-input-tokens", type=int, default=150_000,
                    help="refuse to dispatch a payload larger than this (per reviewer). "
                         "The gate reads its whole payload once per seat per round, so an "
                         "oversized --primary-data/--lineage directory multiplies by the "
                         "panel size and again by every fix round. Default 150K.")
    ap.add_argument("--force-oversize", action="store_true",
                    help="dispatch anyway despite --max-input-tokens. Costs real money; "
                         "prefer narrowing --primary-data/--lineage to the files the claims "
                         "actually trace to.")
    args = ap.parse_args()

    # ---- Intake gate: all three or BLOCKED=FAIL --------------------------
    missing = []
    if not os.path.exists(args.artifact):
        missing.append(f"final artifact ({args.artifact} not found)")
    if not args.primary_data:
        missing.append("primary data (none supplied)")
    if not args.lineage:
        missing.append("data lineage (none supplied)")
    for p in args.primary_data + args.lineage:
        if not os.path.exists(p):
            missing.append(f"path not found: {p}")
    # An empty final output is not an artifact; empty sources are not evidence. Catch these
    # here so the gate BLOCKs rather than paying for a dispatch over nothing.
    if os.path.isfile(args.artifact) and not _has_content(args.artifact):
        missing.append(f"final artifact is empty ({args.artifact})")
    if args.primary_data and all(
            os.path.exists(p) and not _has_content(p) for p in args.primary_data):
        missing.append("primary data is empty (no content in any supplied source)")
    if args.lineage and all(
            os.path.exists(p) and not _has_content(p) for p in args.lineage):
        missing.append("data lineage is empty (no content in any supplied source)")

    if missing:
        result = {"verdict": "BLOCKED", "gate": "intake",
                  "reason": "The team demands ALL THREE: primary data, lineage, final output. "
                            "Summaries are not primary data.",
                  "missing": missing, "reviewers": [], "cost_usd": 0.0}
        emit(result, args.outdir)
        print("VERDICT: BLOCKED (intake gate) = FAIL", file=sys.stderr)
        for m in missing:
            print(f"  missing: {m}", file=sys.stderr)
        sys.exit(1)

    artifact = read_source(args.artifact)
    primary = "\n\n".join(read_source(p) for p in args.primary_data)
    lineage = "\n\n".join(read_source(p) for p in args.lineage)
    db_conf = read_source(args.db_confirmations) if args.db_confirmations else None
    user = build_user_prompt(artifact, primary, lineage, db_conf)

    reviewers = choose_reviewers(args.cls, args.drafted_by, args.reviewers)
    or_peer.assert_priced(reviewers)  # fail fast if a slug has no price (would print $0 silently)

    # ---- Payload preflight: measure and price BEFORE spending ------------
    in_tok = estimate_tokens(user)
    est = estimate_cost(reviewers, in_tok, args.max_tokens)
    rounds, spent = spend_history(args.artifact, args.surface)

    print(f"Fact-Check Gate — class={args.cls}, panel={reviewers}", file=sys.stderr)
    # The estimate is a FLOOR, not a forecast. Measured against 10 runs with recorded
    # payload sizes (audit 2026-07-30) it under-reported the billed cost by 2.4-3.2x:
    # reasoning tokens at --reasoning-effort high are billed as output beyond
    # --max-tokens, and glm-5.2's price row is the cheapest of 31 endpoints that span
    # $0.82-$3.00 in. Printing it as "est. $X" read as a forecast and set the wrong
    # expectation for how much a round costs; a floor is the honest frame.
    print(f"  payload: ~{in_tok:,} input tokens per reviewer "
          f"(x{len(reviewers)} seats) · ${est:.2f} FLOOR this round "
          f"(billed ~2-3x higher: reasoning tokens)", file=sys.stderr)
    if args.cls == "light":
        # Never let a cheap panel look like the ship gate.
        print("  class=light (default): single anchor seat, one lineage. This is the "
              "ITERATION panel.\n  The SHIP gate is --class heavy.", file=sys.stderr)
    if rounds:
        print(f"  round {rounds + 1} on {os.path.basename(args.artifact)} "
              f"— ${spent:.2f} already spent on this artifact "
              f"(counted across the whole {surface_key(args.artifact, args.surface)} surface, "
              f"so a repoint or rename does not reset it)", file=sys.stderr)
    # ---- Cumulative budget check-in -------------------------------------
    # NOT a per-run cap: measured across 414 invocations, exactly one ever exceeded $3, and on
    # 2026-07-29 ($37.87 across 31 runs) the largest single run was $2.53 — a per-run ceiling
    # would have stopped nothing. This trips on the ACCUMULATION, which is where the money went.
    try:
        or_budget.check("claim_ledger", budget=args.max_spend, about_to_spend=est)
    except or_budget.BudgetExceeded as e:
        print(f"\n{e}\n", file=sys.stderr)
        record_fail_hold("FAIL", args.artifact,
                         "BUDGET CHECK-IN — the gate stopped before dispatching; you set the "
                         "ceiling.", rounds=rounds, spent=spent)
        emit({"verdict": "BLOCKED", "gate": "budget", "artifact": args.artifact,
              "reason": str(e), "cost_usd": 0.0}, args.outdir)
        sys.exit(1)

    if rounds >= 3 and args.cls == "heavy":
        print("  NOTE: 4+ heavy rounds on one artifact. A heavy round re-verifies every "
              "already-TRACEABLE claim at full price. Iterate with --class light and "
              "spend the heavy panel once, at ship.", file=sys.stderr)

    if in_tok > args.max_input_tokens and not args.force_oversize:
        biggest = source_sizes(args.primary_data + args.lineage)[:6]
        result = {"verdict": "BLOCKED", "gate": "payload",
                  "reason": f"payload ~{in_tok:,} input tokens exceeds --max-input-tokens "
                            f"{args.max_input_tokens:,}; est. ${est:.2f} per round across "
                            f"{len(reviewers)} seats. Narrow --primary-data/--lineage to the "
                            f"sources the claims actually trace to, or pass --force-oversize.",
                  "missing": [f"{p}: ~{t:,} tokens" for p, t in biggest],
                  "reviewers": [], "cost_usd": 0.0}
        emit(result, args.outdir)
        print(f"\nVERDICT: BLOCKED (payload gate) — nothing dispatched, $0 spent.",
              file=sys.stderr)
        print(f"  ~{in_tok:,} tokens > ceiling {args.max_input_tokens:,}; "
              f"would have cost ~${est:.2f} this round.", file=sys.stderr)
        print("  largest sources:", file=sys.stderr)
        for p, t in biggest:
            print(f"    ~{t:>9,} tok  {p}", file=sys.stderr)
        print("  A directory passed to --primary-data/--lineage expands to EVERY file "
              "under it.\n  Pass the specific files the claims trace to, or "
              "--force-oversize to accept the cost.", file=sys.stderr)
        sys.exit(1)

    # Key is loaded only once the payload has cleared: being told the payload is too
    # big must not require credentials.
    key = or_peer.load_key()
    results = []
    # Reviewers think for a long time — a reasoning model working through a 40-claim ledger
    # routinely runs into the minutes, and a slow provider day can push one dispatch past
    # five. Say so before going quiet, or the first-time user reads a working gate as a hang.
    print(f"  dispatching {len(reviewers)} reviewer(s) — this typically takes 1-5 minutes "
          f"per seat, in parallel. Nothing further prints until a seat returns.",
          file=sys.stderr, flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(reviewers)) as ex:
        futs = {ex.submit(dispatch_one, m, REVIEWER_SYSTEM, user,
                          args.max_tokens, args.reasoning_effort, key,
                          label=f"{args.cls}:{os.path.basename(args.artifact)}"): m
                for m in reviewers}
        for fut in concurrent.futures.as_completed(futs):
            r = fut.result()
            print(f"  ← {r['model']} returned in {r['dt']:.0f}s "
                  f"({r['verdict']}, ${r['cost']:.4f})", file=sys.stderr, flush=True)
            results.append(r)
    results.sort(key=lambda r: reviewers.index(r["model"]))

    # ---- OR-of-FAILs aggregation ----------------------------------------
    any_error = any(r["verdict"] == "ERROR" for r in results)
    any_fail = any(r["verdict"] not in ("PASS", "ERROR") for r in results)
    # Both block (fail-closed). They are reported differently because they mean
    # different things: FAIL = a claim did not trace; ERROR = nothing was checked.
    verdict = "FAIL" if any_fail else ("ERROR" if any_error else "PASS")
    total_cost = sum(r["cost"] for r in results)

    agg = {
        "verdict": verdict,
        "aggregation": "OR-of-FAILs (unchaired; any reviewer FAIL fails the artifact)",
        "class": args.cls,
        "artifact": args.artifact,
        "reviewers": [
            {"model": r["model"], "verdict": r["verdict"], "reason": r["reason"],
             "cost_usd": round(r["cost"], 4), "seconds": round(r["dt"], 1),
             "failing_claims": [c for c in (r["bad"] or [])],
             "uncited_traceables": [c for c in (r["uncited"] or [])],
             "ledger": r["ledger"]}
            for r in results
        ],
        "cost_usd": round(total_cost, 4),
        "input_tokens_est": in_tok,
        "round": rounds + 1,
        "artifact_cost_usd": round(spent + total_cost, 4),
    }
    emit(agg, args.outdir)
    record_spend(args.artifact, args.cls, reviewers, in_tok, total_cost, verdict,
                 surface=args.surface)

    # ---- Human summary to stderr ----------------------------------------
    print("\n" + "=" * 70, file=sys.stderr)
    print(f"FACT-CHECK GATE VERDICT: {verdict}   (${total_cost:.4f}, {len(reviewers)} reviewers"
          f", round {rounds + 1}, ${spent + total_cost:.2f} on this artifact)", file=sys.stderr)
    print("=" * 70, file=sys.stderr)
    for r in results:
        mark = {"PASS": "PASS", "ERROR": "ERROR"}.get(r["verdict"], "FAIL")
        print(f"  [{mark}] {r['model']}: {r['reason']}", file=sys.stderr)
        for c in (r["bad"] or [])[:6]:
            print(f"         - {c.get('classification','?')}: {c.get('claim','')[:100]}",
                  file=sys.stderr)
    if verdict == "ERROR":
        print("\n  GATE ERROR — the artifact was NOT evaluated. This is a transport/dispatch "
              "failure (see the reason above), not a finding about the claims. It still blocks "
              "(exit 1) because fail-closed is the charter, but do NOT record it as a QA failure "
              "and do NOT 'fix' claims in response to it — re-run the gate. A $0.0000 verdict is "
              "never a content verdict.\n", file=sys.stderr)
    if verdict == "FAIL":
        print("\n  QA FAILED — this run COMPLETES and reports FAIL (exit 1); the per-claim ledger "
              "above is the note. The process is not halted or looped. A QA-FAILED artifact must "
              "not go to an investor/customer as-is (an operator gate); disposition: fix the failing "
              "claims + re-run, or override with this failure on record. Never surface it silently.\n"
              "  Fix EVERY claim in the per-claim ledger above before re-running — the 'reason' line "
              "names only the FIRST blocking claim, and re-running once per claim pays a full panel "
              "to re-verify everything that already passed. Iterate with --class light; spend the "
              "heavy panel once, at ship.", file=sys.stderr)
        # The disposition of a FAIL is the operator's, so it is recorded as a hold HERE rather
        # than left to the agent — which is what previously turned one FAIL into nine rounds.
        first_fail = next((r for r in results if r["verdict"] != "PASS"), None)
        record_fail_hold(verdict, args.artifact,
                         (first_fail or {}).get("reason", "see the per-claim ledger"),
                         rounds=rounds, spent=spent + total_cost)
    sys.exit(0 if verdict == "PASS" else 1)


def emit(result, outdir):
    if outdir:
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "ledger.json"), "w", encoding="utf-8") as fh:
            json.dump(result, fh, indent=2, ensure_ascii=False)
        with open(os.path.join(outdir, "ledger.md"), "w", encoding="utf-8") as fh:
            fh.write(render_md(result))
    # Always print machine-readable JSON to stdout for programmatic callers.
    print(json.dumps({"verdict": result["verdict"], "cost_usd": result.get("cost_usd", 0.0),
                      "outdir": outdir}))


def render_md(result):
    lines = [f"# Fact-Check Gate ledger — verdict: **{result['verdict']}**", ""]
    if result["verdict"] == "BLOCKED":
        lines += [f"_{result.get('reason','')}_", "", "## Missing (intake gate)"]
        lines += [f"- {m}" for m in result.get("missing", [])]
        return "\n".join(lines) + "\n"
    lines += [f"- Artifact: `{result.get('artifact','')}`",
              f"- Class: {result.get('class','')}  ·  Aggregation: {result.get('aggregation','')}",
              f"- Cost: ${result.get('cost_usd',0.0)}", ""]
    for rv in result.get("reviewers", []):
        lines += [f"## {rv['model']} — **{rv['verdict']}**", f"_{rv.get('reason','')}_", ""]
        ledger = rv.get("ledger") or {}
        claims = ledger.get("claims") or []
        if claims:
            lines += ["| Claim | Class | Cited source | Note |", "|---|---|---|---|"]
            for c in claims:
                claim = str(c.get("claim", "")).replace("|", "\\|")[:160]
                cls = c.get("classification", "")
                src = str(c.get("cited_source", "")).replace("|", "\\|")[:80]
                note = str(c.get("note", "")).replace("|", "\\|")[:120]
                lines.append(f"| {claim} | {cls} | {src} | {note} |")
        else:
            lines.append("_(no ledger returned — treated as FAIL)_")
        lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
