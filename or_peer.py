#!/usr/bin/env python3
"""or_peer.py — minimal, stdlib-only OpenRouter dispatch.

Reads OPENROUTER_API_KEY from ./.env (never prints it). POSTs a system+user pair to
OpenRouter's chat/completions and reports the completion, token usage, and computed cost.
Carries the retry/backoff, truncation detection, quantization-aware provider pinning, and
the spend ledger that claim_ledger.py depends on.

Usage:
  python3 or_peer.py \
      --model deepseek/deepseek-v4-pro \
      --system-file system.txt \
      --input-file  input.md \
      --out run.json
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# OpenRouter list price per 1M tokens (input, output).
#
# RECONCILED AGAINST LIVE https://openrouter.ai/api/v1/models ON 2026-07-17. Five entries were
# STALE and every one of them under-reported, so every board cost this table ever printed was an
# UNDER-estimate — including the $0.35-0.81/run figure the $0.75 auto-convene cap was set against.
# The 2026-07-17 reconcile genuinely corrected 5 stale entries (deepseek-v4-flash, qwen3.7-max,
# kimi-k2.6, tencent/hy3, nemotron — all under-reporting). BUT the same pass ALSO corrupted
# z-ai/glm-5.2, which was correct, by misreading a different z-ai row (0.42/1.32 -> 0.9464,
# 2.3x too high) — fixed 2026-07-18. Lesson: a table that AGREES WITH ITSELF is not a table
# that is RIGHT; the parity test only catches cross-file drift. Before editing any price, run
#   curl -s https://openrouter.ai/api/v1/models | jq -r '.data[]|select(.id=="<slug>")|.pricing'
# which reads the LIVE OpenRouter API. Values are full precision — do not
# round them 'tidy' (that pass also wrongly rounded deepseek-v4-pro 0.435 -> 0.43). No blogs;
# a blog reported kimi-k2.6 at 0.66/3.41 when OpenRouter's own API said 0.95/4.00. Re-check with:
#   curl -s https://openrouter.ai/api/v1/models | jq -r '.data[]|select(.id=="<slug>")|.pricing'
PRICES = {
    # A FLOATING SLUG IS NOT A FIXED PRICE (2026-08-15). This row sat at 0.435/0.87 from the
    # day the anchor was seated; on 2026-08-15 the live catalog said 1.168/2.336 — the vendor
    # repriced the floating alias 2.7x under a table nobody re-checked. Nothing failed: the
    # gate kept printing its old floor while OpenRouter billed the new rate. The DATED slug
    # below still serves the old price, which is why the anchor moved to it. Re-check any
    # undated vendor alias with check_prices.py before trusting a cost argument built on it.
    "deepseek/deepseek-v4-pro":   (0.4138, 0.8275),  # live-refreshed 2026-08-22 (was 1.168/2.336 on
                                                   # 08-15). The floating alias came back DOWN 2.8x —
                                                   # third distinct rate in eight days. Read this row as
                                                   # a snapshot with a shelf life, never as a constant.
    # A DATED SLUG IS NOT A FIXED PRICE EITHER (2026-08-16). The comment that stood here claimed
    # "a dated slug cannot be repriced out from under the roster the way the alias just was."
    # That was falsified 24 hours after it was written. At 16:00 UTC on 2026-08-16 DeepSeek moved
    # V4-Pro to peak/off-peak billing and the DATED slug moved with it: 0.435/0.870 -> 0.660/1.980
    # off-peak, 1.320/3.960 peak, with cache reads going 0.003625 -> 0.022 (6x). The dated snapshot
    # pins the WEIGHTS, not the rate card. Nothing in a slug's name binds a vendor's pricing.
    # Peak windows: 01:00-04:00 and 06:00-10:00 UTC. This row records the OFF-PEAK rate, which is
    # what the live API reports outside those windows — so a refresh run during a peak window
    # will disagree with this row by exactly 2x, and that is not drift.
    "deepseek/deepseek-v4-pro-0813": (1.1880, 3.5640),  # live-refreshed 2026-08-22 (was 0.66/1.98).
                                                   # The DATED slug is now 2.9x DEARER than the floating
                                                   # alias above — the reason the anchor moved here on
                                                   # 08-15 has inverted. Prefer the alias on cost today.
    "deepseek/deepseek-v4-flash": (0.0790, 0.1579),  # live-refreshed 2026-08-30 (was 0.0601/0.1201)
    "z-ai/glm-5.2":               (0.9660, 3.0360),  # live-refreshed 2026-08-22: 3.1x UP from 0.308/0.968
                                              # (2026-08-16). This seat is no longer a cheap seat.
                                              # Prior note, still true: (was 0.462/1.452,
                                              # itself live on 2026-07-18). MULTI-PROVIDER: 31
                                              # endpoints span $0.82-$3.00 in / $2.59-$10.25 out,
                                              # and this row is only the CHEAPEST of the moment —
                                              # which is why cost() now prefers the response's
                                              # usage["cost"] and this number is an ESTIMATE for
                                              # pre-flight budgeting only. Historic trap, still
                                              # true: a 2026-07-17 edit "corrected" this UP to
                                              # 0.9464/2.9744 by misreading a DIFFERENT z-ai row
                                              # (2.3x too high, caught in review), so
                                              # always match the exact slug. See check_prices.py.
    "openai/gpt-5.6-sol":         (2.00, 10.00),   # live-refreshed 2026-08-22 (was 5.00/30.00 — a 2.5x
                                                   # vendor price CUT the table never saw)
    "google/gemini-3.1-pro-preview": (2.00, 12.00),
    "x-ai/grok-4.5":              (2.00, 6.00),
    # 2026-08-15 seat-refresh candidates. VERIFIED live against openrouter.ai/api/v1/models
    # the same day. All hold NO seat until the eval says otherwise.
    #
    # TIERED PRICING WARNING — grok-4.6 and qwen3.7-plus BOTH carry a long-prompt override
    # this flat two-number table cannot express: grok-4.6 doubles to 4.00/12.00 above 200K
    # prompt tokens, qwen3.7-plus triples to 0.96/3.84 above 256K. The gate's own
    # --max-input-tokens ceiling is 150K, so every gate round prices correctly here; a
    # research or board dispatch that feeds one of them a 300K payload does not. cost()
    # prefers the billed usage["cost"], so the LEDGER stays honest either way — it is the
    # pre-flight estimate that would under-report.
    "x-ai/grok-4.6":              (2.00, 6.00),
    "z-ai/glm-5":                 (0.60, 1.92),
    "z-ai/glm-4.7":               (0.40, 1.75),
    "qwen/qwen3.7-plus":          (0.32, 1.28),
    "qwen/qwen3.7-max":           (1.475, 4.425),  # live-corrected 2026-07-17 (was 1.25/3.75)
    "qwen/qwen3.8-max":           (2.00, 6.00),    # added 2026-08-03 for the k3-vs-3.8 head-to-head.
                                                   # VERIFIED live against openrouter.ai/api/v1/models
                                                   # the same day (2e-6/6e-6 per token, 1M ctx).
                                                   # Eval candidate — holds NO seat; the heavy panel
                                                   # still seats qwen3.7-max.
    "moonshotai/kimi-k2.6":       (0.5415, 2.2800),  # live-refreshed 2026-08-15 (was 0.589/2.48);
                                                   # multi-provider, so an estimate — see glm note
    "moonshotai/kimi-k3":         (3.00, 15.00),   # added 2026-07-17 — was MISSING, so every k3
                                                   # dispatch printed COST $0.0000 while OpenRouter
                                                   # billed $0.158. See SEAT_ROUND_BUDGET_USD below.
    "mistralai/mistral-medium-3-5": (1.50, 7.50),
    "meta/muse-spark-1.1":        (1.25, 4.25),   # added 2026-07-21 for the Muse Spark
                                                   # audition. VERIFIED live against
                                                   # openrouter.ai/api/v1/models the same day
                                                   # (1.25e-6/4.25e-6 per token; cache read
                                                   # 0.15e-6). Audition-only — holds no seat
                                                   # on the default roster.
    # 2026-07-12 audition candidates (bench + cost A/Bs)
    "openai/gpt-5.6-luna":        (0.2000, 1.2000),  # live-refreshed 2026-08-22 (was 0.10/0.60)
    "openai/gpt-5.6-luna-pro":    (0.2000, 1.2000),  # added 2026-08-22 for the cost re-seat audition;
                                                   # VERIFIED live the same day
    "x-ai/grok-4.3":              (1.25, 2.50),     # added 2026-08-22, cost-re-seat candidate (verified live)
    "moonshotai/kimi-k2.5":       (0.45, 2.25),     # added 2026-08-22, cost-re-seat candidate (verified live)
    "google/gemini-3.7-flash":    (0.375, 1.875),   # added 2026-08-22, cost-re-seat candidate (verified live)
    "google/gemini-3.5-flash":    (1.50, 9.00),
    "tencent/hy3":                (0.1320, 0.5280),    # live-refreshed 2026-08-03 (was 0.14/0.58)
    "minimax/minimax-m3":         (0.30, 1.20),
    "nvidia/nemotron-3-ultra-550b-a55b": (0.60, 3.60),  # live-corrected 2026-07-17 (was 0.50/2.20)
    # RF-T4's --brain opus dispatches this via OpenRouter's Anthropic routing
    # harness. Without
    # a price entry here, a dispatcher's fail-closed unknown-
    # model check raises UnknownModelError on the very first real dispatch.
    #
    # SETTLED 2026-08-22 by a live test dispatch, closing the question flagged
    # here on 2026-07-25. The hyphenated slug is a working ALIAS: OpenRouter
    # accepted it and the response came back with `"model":
    # "anthropic/claude-opus-4.8"` and billed 19 prompt / 4 completion tokens at
    # $0.000095 / $0.000100 — exactly $5.00/$25.00 per 1M, the dotted row's rate,
    # NOT the $15/$75 this row carried. So the old entry overstated every
    # table-priced opus-4-8 estimate by 3x. It never overstated the LEDGER
    # (cost() prefers the billed usage["cost"]); it did overstate any pre-flight
    # budget or ceiling derived from this table, so the correction is recorded
    # here with its evidence.
    "anthropic/claude-opus-4-8":  (5.00, 25.00),
    # Confirmed LIVE via https://openrouter.ai/api/v1/models, 2026-07-25 (both
    # correctly dot-separated, real catalog entries — not the hyphenated slug
    # above). Added to price a chair-dispatch bump to Opus 5.
    "anthropic/claude-opus-4.8":  (5.00, 25.00),
    "anthropic/claude-opus-5":    (5.00, 25.00),
}


def resolve_env_path(env_path=".env"):
    """Find the env file, worktree-safe. Returns an existing path or None.

    Secrets like .env are gitignored, so a LINKED git worktree never contains
    them — a dispatch whose cwd is a worktree (agent harnesses often build in
    per-task worktrees) would otherwise see no .env and fail. So: use the cwd
    path if it exists; else resolve to the git MAIN worktree's env file (the one
    real checkout that does carry the gitignored secret). Existing callers that
    already have a local .env hit the first branch unchanged.
    """
    if os.path.exists(env_path):
        return env_path
    try:
        common = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, encoding="utf-8", timeout=5,
        )
        if common.returncode == 0 and common.stdout.strip():
            # <main-worktree>/.git -> its parent is the main worktree root
            main_root = os.path.dirname(common.stdout.strip())
            cand = os.path.join(main_root, os.path.basename(env_path))
            if os.path.exists(cand):
                return cand
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def load_key(env_path=".env", var=None):
    """Load the OpenRouter API key. The ENVIRONMENT wins, then an env file.

    Two supported ways to supply it, in this order:
      1. The process environment — OPENROUTER_API_KEY=sk-or-... python3 claim_ledger.py ...
         This is what CI secret stores inject, so it has to work without a file on disk.
      2. A .env file beside this script (or in the git main worktree, so a run from inside
         a linked worktree still finds the checkout's file). Format: KEY=value per line.

    OPENROUTER_ASSISTANT_API_KEY is honored first in both, for setups that keep a
    separate key for automated callers. Pass an explicit `var` to force one name.

    The key is never printed, never logged, and never written to the spend ledger.
    """
    candidates = [var] if var else ["OPENROUTER_ASSISTANT_API_KEY", "OPENROUTER_API_KEY"]

    for name in candidates:
        if name and os.environ.get(name, "").strip():
            return os.environ[name].strip()

    resolved = resolve_env_path(env_path)
    if resolved:
        found = {}
        with open(resolved, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                for name in candidates:
                    if name and line.startswith(name + "="):
                        found[name] = line.partition("=")[2].strip().strip('"').strip("'")
        for name in candidates:
            if name and found.get(name):
                return found[name]

    sys.exit(
        f"or_peer: no OpenRouter API key found.\n"
        f"  Set one in the environment:   export {candidates[-1]}=sk-or-...\n"
        f"  or put it in {env_path}:      {candidates[-1]}=sk-or-...\n"
        f"  Get a key at https://openrouter.ai/keys")


def read_file(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class UnknownPriceError(ValueError):
    """A model was costed with no entry in PRICES.

    Raised rather than returning 0.0. The old `.get(model, (0.0, 0.0))` default meant an
    unpriced model reported COST $0.0000 forever: kimi-k3 printed $0.0000 across a whole
    audition while OpenRouter billed $0.53. A seat that appears free is worse than a seat
    that errors — it silently defeats every spend cap built on top of this number. Mirrors
    an unknown-model error, which already fail-closes on this same table.
    """


def cost(model, usage):
    """Cost this usage in USD — the ACTUAL billed amount when OpenRouter reports one.

    ORDER OF TRUTH (set 2026-07-21):
      1. ``usage["cost"]`` — what OpenRouter actually billed for this exact request. It is in
         every response payload and it is provider-aware.
      2. ``PRICES[model]`` — a snapshot estimate, used only when the payload carries no cost.

    WHY THE FLIP. PRICES stores ONE number per model, but many OpenRouter models are served by
    MANY providers at different rates and the published top-level price is merely the cheapest
    endpoint of the moment. z-ai/glm-5.2 — a SEATED Executive Board member — has 31 endpoints
    spanning $0.82-$3.00 in and $2.59-$10.25 out. Measured across every board dispatch stored on
    disk, the table under-reported glm-5.2 by 2.69x (12 calls routed across 6 providers:
    $0.0942 computed vs $0.2532 actually billed) and deepseek-v4-pro by 1.71x, while every
    SINGLE-provider model (kimi-k3, gemini, muse-spark, qwen, gpt-5.6-sol) matched to the penny.
    No amount of table maintenance fixes that: the correct number depends on where the request
    was routed, which is only knowable after the fact — and it was sitting unused in the
    response the whole time.

    This is the kimi-k3 $0.0000 bug in a different disguise, and the same doctrine applies: a
    seat that appears cheap silently defeats every spend cap computed from that number. So a
    reported cost of exactly 0.0 on a request that actually consumed tokens is treated as
    MISSING, not as free, and falls back to the table rather than reporting a free dispatch.

    PRICES remains the pre-flight estimate — `assert_priced()` and `max_tokens_for_budget()`
    must still work BEFORE a request exists, so an unpriced model still fails fast and free.
    """
    reported = usage.get("cost")
    pt = usage.get("prompt_tokens", 0)
    ct = usage.get("completion_tokens", 0)
    if isinstance(reported, (int, float)) and not isinstance(reported, bool):
        if reported > 0:
            return float(reported)
        # cost 0 with tokens consumed = do not believe it; fall through to the table.
        if pt == 0 and ct == 0:
            return 0.0
    if model not in PRICES:
        raise UnknownPriceError(
            f"or_peer.cost: model {model!r} has no entry in PRICES and the response carried no "
            f"usable usage['cost'] — its cost would silently report as $0.00. Add its LIVE price "
            f"(check https://openrouter.ai/api/v1/models, not a blog) to or_peer.PRICES."
        )
    pin, pout = PRICES[model]
    return (pt / 1e6) * pin + (ct / 1e6) * pout


# ── the durable spend ledger ───────────────────────────────────────────────────────────────
#
# WHY (audit 2026-08-03). An OpenRouter account had burned $206.83 of $240 and ~96% of it left
# NO trace on disk: the only ledger held 20 rows and $3.53, while 547 observed paid dispatches
# ran through dispatch_chat from six different callers. Answering "where did the money go"
# meant scraping cost lines out of session transcripts, and that recovered only $135 of the
# $207. The number was never missing — `cost()` above computes the TRUE billed amount at
# dispatch time, and it was simply thrown away.
#
# dispatch_chat is the ONE shared POST path, so a single write point here is total coverage:
# no caller can spend unmetered, and no caller has to remember to meter itself. That is the
# machine-blocking rung of the ladder rather than the human-remembered one.
def _resolve_spend_log():
    """ONE ledger for the whole repo, never one per CWD.

    Anchored the way claim_ledger._resolve_spend_log() is, and for the same reason it had to
    be fixed on 2026-07-30: a CWD-relative ledger cannot hold in a repo that uses git
    worktrees — the isolation is the thing that breaks it. `git rev-parse --git-common-dir` resolves to the MAIN checkout's .git even
    from inside a linked worktree, and it is run from THIS FILE's directory so the answer
    cannot depend on the caller.
    """
    override = os.environ.get("OR_SPEND_LOG")
    if override:
        return override
    root = None
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
            cwd=os.path.dirname(os.path.abspath(__file__)))
        if out.returncode == 0 and out.stdout.strip():
            root = os.path.dirname(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    if not root:  # not a git checkout at all — fall back to this file's repo layout
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "output", "openrouter_spend.jsonl")


SPEND_LOG = _resolve_spend_log()


def spend_log_path():
    """Re-read the override each call so tests can redirect the ledger without reimport."""
    return os.environ.get("OR_SPEND_LOG") or SPEND_LOG


def resolve_caller(explicit=None):
    """Who spent this money. Explicit arg > env (for shell wrappers) > argv0.

    Some callers reach this module as a SUBPROCESS, so they cannot pass a Python
    argument; they pass --caller (which arrives here as `explicit`). OR_DISPATCH_CALLER is the
    escape hatch for any wrapper that cannot add a flag. argv0 is the last resort and is still
    better than "unknown" — it at least names the entry point.
    """
    if explicit:
        return explicit
    env = os.environ.get("OR_DISPATCH_CALLER")
    if env:
        return env
    return os.path.basename(sys.argv[0] or "") or "unknown"


# PER-CALLER REASONING EFFORT (2026-08-16). Reasoning tokens are 82% of every output token this
# repo buys (3,127,525 of 3,799,481 over the 13-day ledger), and output dominates the bill. No
# routing or vendor change touches that; effort is the only lever on it.
#
# MEASURED BEFORE SET, on one identical prompt per model, high vs low:
#
#   model                       reasoning@high  @low     delta
#   x-ai/grok-4.6                     964        403     -58%
#   x-ai/grok-4.5                     946        470     -50%
#   deepseek/deepseek-v4-flash        656        538     -18%   (and served by two DIFFERENT
#                                                                providers across the pair, so
#                                                                even this is confounded)
#
# Two things that measurement settles, neither of which was safe to assume:
#
# 1. THE KNOB IS NOT UNIFORMLY LIVE. It moves grok hard and barely moves deepseek-v4-flash. A
#    caller-blind global default would have been half wasted and half a silent quality change.
# 2. EFFORT SCALES TOTAL OUTPUT, NOT THE REASONING FRACTION. The reasoning/output RATIO held at
#    0.60-0.63 across every arm. An early read of this experiment used that ratio and concluded
#    the knob was inert; the ratio is the wrong statistic and absolute reasoning tokens is the
#    right one. Anyone re-running this must compare absolute counts on an IDENTICAL prompt.
#
# WHY claim_ledger IS DELIBERATELY ABSENT. It is the adjudicating seat — the one caller whose
# missed defect is expensive, and the only one no human reads before it acts. The planted-defect
# harness that would license lowering it was measured SATURATED (every candidate caught every
# defect), and a saturated instrument has no discriminating power left: "low still catches 8/8"
# cannot distinguish a safe reduction from an undetectable one. It can only detect a collapse.
# So the gate keeps its current effort until a harness exists that can actually fail.
# Every caller listed below is human-reviewed or non-adjudicating.
CALLER_EFFORT = {
    # claim_ledger: intentionally unset — see above. An unlisted caller omits the key entirely
    # and takes the vendor default. Add your own non-adjudicating callers here if you reuse
    # this module; the reasoning above is why the gate itself must not be one of them.
}


# QUANTIZATION-AWARE ROUTING, FOR EVERY CALLER (lifted here 2026-08-16).
#
# This map lived in the gate and applied to exactly one caller. Everything else dispatching
# through this module routed blind, and OpenRouter's default routing chases price, which means it chases quantized
# endpoints. Caught live: a review round convened on 2026-08-16 to decide this very question had its
# deepseek-v4-pro seat served by StreamLake/fp8 — the exact configuration this repo measured at
# 7.3 clean-base false flags against 0.33 non-quantized. The panel deliberated on degraded weights
# while ratifying a rule against doing that.
#
# WHY PER-MODEL AND NOT A BLANKET fp16/bf16 ALLOWLIST. A global "no quantization" filter is the
# obvious design and it contradicts this repo's own measurements. fp8 was measured CLEAN for
# glm-5.2 ([0,1,0] via Baidu) and minimax-m3 ([0,0,0]), whose non-quantized alternatives are
# +46% and nonexistent respectively. It was measured RUINOUS for deepseek-v4-pro. Quantization
# sensitivity is a property of the model, not of the number, so the map records a per-model
# judgement with its evidence rather than a rule that is wrong in both directions.
#
# allow_fallbacks stays True everywhere on purpose. The Fact-Check Gate is fail-closed on
# VERDICTS; it must never become fail-closed on AVAILABILITY because one preferred endpoint has a
# bad hour. `order` is a preference, not an exclusion.
PROVIDER_PREFS = {
    # Non-quantized FIRST, deliberately forfeiting the prompt cache. Measured on the real prompt:
    # digitalocean (not quantized) $0.00148 flat, no cache hits; streamlake/fp8 $0.00140 -> $0.00030
    # with 99% cache hits. Under a cent a round at production size, against a demonstrated quality
    # risk. The 36x caching win is real but scales with PRICE and PAYLOAD; on a sub-cent seat it is
    # noise and quality wins.
    "deepseek/deepseek-v4-flash": {
        "order": ["digitalocean", "streamlake/fp8", "baidu/fp8"], "allow_fallbacks": True},
    # CORRECTED IN THE LIFT (2026-08-16). An earlier copy of this entry listed fp8 endpoints
    # first. That was harmless there — v4-pro stopped being a seated reviewer on 2026-08-15 — but
    # another caller DOES seat this model, so lifting the entry unchanged would have made the fp8
    # degradation repo-wide instead of retiring it. This is the model the 0.33-vs-7.3 measurement
    # was taken ON; it gets non-quantized first.
    "deepseek/deepseek-v4-pro": {
        "order": ["deepseek", "digitalocean"], "allow_fallbacks": True},
    "deepseek/deepseek-v4-pro-0813": {
        "order": ["deepseek", "digitalocean"], "allow_fallbacks": True},
    # These two stay on fp8, and that is a judgement with a stated basis rather than a default:
    # both measured CLEAN at fp8 in the 2026-08-15 eval, and their non-quantized alternatives are
    # expensive (digitalocean is +46% for glm-5.2) or absent (minimax-m3 has none at all).
    # Revisit if either starts flagging a clean base.
    "z-ai/glm-5.2": {
        "order": ["baidu/fp8", "novita/fp8"], "allow_fallbacks": True},
    "minimax/minimax-m3": {
        "order": ["deepinfra/fp8", "gmicloud/fp8"], "allow_fallbacks": True},
}

_NO_PIN_ENV = ("OR_PEER_NO_PROVIDER_PIN",)


def provider_prefs(model):
    """Routing preference for a model, or None to leave OpenRouter's default routing alone.

    Setting OR_PEER_NO_PROVIDER_PIN=1 disables
    pinning process-wide. That exists so the pin can be A/B'd against default routing on the SAME
    prompt: quantization is a quality variable, not just a price one, and without a way to turn
    the pin off a routing-induced quality regression is indistinguishable from a model- or
    prompt-induced one.
    """
    if any(os.environ.get(v) for v in _NO_PIN_ENV):
        return None
    return PROVIDER_PREFS.get(model)


def resolve_effort(explicit=None, caller=None):
    """Explicit argument > per-caller default > omit the key (vendor default).

    ``explicit`` wins unconditionally so a caller that has thought about it is never overridden
    by this table. The sentinel for "caller did not specify" is None, NOT "none" — "none" is a
    real OpenRouter tier meaning reasoning OFF, and conflating the two would silently disable
    reasoning on every caller that never passed the argument.
    """
    if explicit is not None:
        return explicit
    return CALLER_EFFORT.get(resolve_caller(caller))


def _finite(value):
    """None unless `value` is a real, finite number.

    spent_usd deliberately becomes float("inf") when an unpriced model is dispatched under a
    dollar bound (that is what makes _escalation_headroom refuse to fund another attempt), and
    json.dumps would happily write `Infinity` — which is not valid JSON and would poison every
    later reader of this ledger. An unmeasurable cost is recorded as null and FLAGGED, never as
    Infinity and never as a silent 0.0 (the kimi-k3 $0.0000 bug, in ledger form).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != value or value in (float("inf"), float("-inf")):
        return None
    return float(value)


def record_dispatch(model, usage, cost_usd, caller, label=None, attempts=1,
                    truncated=False, cost_source="reported", path=None, provider=None):
    """Append ONE line per logical dispatch. NEVER raises, NEVER fails a dispatch.

    Same precedent as the gate's ledger: a ledger-write failure is a warning on stderr. Money
    is already spent by the time we get here — refusing to return the answer we paid for would
    turn an accounting problem into a lost-work problem.
    """
    path = path or spend_log_path()
    details = usage.get("completion_tokens_details") or {}
    # Cache reads are the cheapest input tokens available (deepseek-v4-pro-0813 bills them at
    # $0.003625/M against $0.435/M cold — 120x) and they are INVISIBLE in every number this
    # ledger recorded before 2026-08-15: prompt_tokens counts cached and cold tokens alike, and
    # usage["cost"] is already net of the discount, so a prefix that stopped caching would show
    # up as "the gate got more expensive" with nothing to point at. Recording the split is what
    # makes the caching claim falsifiable — 0 cached tokens on a repeat round means the stable
    # prefix broke, and that is a bug, not a price rise.
    prompt_details = usage.get("prompt_tokens_details") or {}
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "caller": caller,
        "label": label,
        "model": model,
        # WHICH ENDPOINT SERVED IT. On a multi-provider slug this explains the bill better than
        # the model id does: deepseek/deepseek-v4-pro has 18 endpoints spanning 5.5x in input
        # price and 91x in cache-read price, so "the same model" can cost wildly different
        # amounts run to run. Without this field a routing change is indistinguishable from a
        # vendor reprice, which is exactly how 2026-08-15 was misread on first look.
        "provider": provider,
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "cached_prompt_tokens": prompt_details.get("cached_tokens"),
        "completion_tokens": usage.get("completion_tokens", 0),
        "reasoning_tokens": details.get("reasoning_tokens"),
        "cost_usd": _finite(cost_usd),
        "cost_source": cost_source,
        "attempts": attempts,
        "truncated": bool(truncated),
        # Scopes the cumulative budget (or_budget.py) to ONE session. Without it the gate could
        # only ever be all-time or per-run, and per-run was measured useless: on 2026-07-29 the
        # largest single run was $2.53 against a $37.87 day.
        "session": (os.environ.get("CLAUDE_CODE_SESSION_ID")
                    or os.environ.get("CLAUDE_SESSION_ID") or None),
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except (OSError, IOError, TypeError, ValueError) as e:
        print(f"or_peer: could not append to spend ledger {path}: {e}", file=sys.stderr)


def assert_priced(models):
    """Fail fast, before spending, if any model in `models` is unpriced."""
    missing = [m for m in models if m not in PRICES]
    if missing:
        raise UnknownPriceError(
            f"or_peer: unpriced model(s) {missing} — refusing to dispatch, because their cost "
            f"would report as $0.00 and defeat any spend ceiling. Add LIVE prices to "
            f"or_peer.PRICES first."
        )


def max_tokens_for_budget(model, budget_usd, prompt_tokens):
    """Largest max_tokens that keeps ONE dispatch at or under `budget_usd`.

    Derives a real dollar bound from the seat's own price instead of guessing a token number,
    so a per-seat ceiling stays correct when a price changes. Output tokens carry reasoning
    tokens too (they bill inside completion_tokens), so this bounds the reasoning blowup that
    has truncated boards before.
    """
    pin, pout = PRICES[model] if model in PRICES else (_ for _ in ()).throw(
        UnknownPriceError(f"or_peer.max_tokens_for_budget: {model!r} is unpriced.")
    )
    if pout <= 0:
        raise UnknownPriceError(f"or_peer.max_tokens_for_budget: {model!r} has no output price.")
    room = budget_usd - (prompt_tokens / 1e6) * pin
    if room <= 0:
        raise UnknownPriceError(
            f"or_peer.max_tokens_for_budget: {model!r} input alone ({prompt_tokens} tokens) "
            f"exceeds the ${budget_usd:.2f} ceiling."
        )
    return int(room / (pout / 1e6))


# OpenRouter reasoning effort tiers (OpenAI-compatible). "none" == reasoning off.
REASONING_EFFORTS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")


def build_request_body(model, system, user, max_tokens, temperature,
                       reasoning_effort="none", provider=None):
    """Assemble the OpenRouter chat/completions payload.

    When ``reasoning_effort`` is a real tier (not "none"), attach OpenRouter's
    ``reasoning`` control so the model DELIBERATELY engages its thinking pass
    instead of leaving it to emerge (or not) by chance — the R3 audit found the
    tooling never asked for reasoning, so it fired on only a third of verify
    runs. Caveat baked into the verify path: on DeepSeek V4 reasoning tokens are
    billed inside completion_tokens and draw down ``max_tokens``, so turning
    reasoning on without raising max_tokens truncates the final answer.

    ``provider`` is OpenRouter's routing-preference block, and on a multi-provider
    slug it matters MORE than the slug (measured 2026-08-15). One model id,
    ``deepseek/deepseek-v4-pro``, is served by 18 endpoints spanning $0.348-$1.910
    per 1M input — 5.5x — and cache reads spanning $0.0036-$0.33, which is 91x.
    Unpinned, two identical requests can land on different backends at different
    prices, and neither can reuse the other's cached prefix because a prompt cache
    is per-provider. That is not a hypothetical: the gate was being routed to a
    reseller at ~$1.24/M while DeepSeek's own endpoint served the same model at
    $0.435/M, and the "price rise" looked exactly like a vendor reprice.

    Pass ``{"order": ["DeepSeek"], "max_price": {...}}`` to prefer a named endpoint
    while still allowing fallback. Do NOT set ``allow_fallbacks: False`` on the
    fact-check path: the gate is fail-closed, so a single unavailable endpoint would
    convert into a FAIL on an artifact nobody reviewed. Prefer-plus-price-cap keeps
    the cheap route without making availability a correctness problem.
    """
    body = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if reasoning_effort and reasoning_effort != "none":
        body["reasoning"] = {"effort": reasoning_effort}
    if provider:
        body["provider"] = provider
    return body


def was_truncated(choice):
    """True when the model hit the token ceiling mid-answer (finish_reason=length).

    The silent-truncation guard: a reasoning-heavy verify can spend its whole
    budget thinking and return an empty/cut-off verdict. We surface that loudly
    rather than let a truncated PASS/FAIL be mistaken for a real one.
    """
    return (choice or {}).get("finish_reason") == "length"


def truncation_warning(choice, max_tokens, reasoning_tokens=None):
    """The loud cut-off message when the response was truncated, else None.

    Split out from the print path so the surface behaviour is unit-testable
    (a bare bool wasn't enough — the warning wording + the numbers matter).
    """
    if not was_truncated(choice):
        return None
    spent = f" ({reasoning_tokens} of it spent on reasoning)" if reasoning_tokens else ""
    return (f"or_peer: WARNING — response hit the token ceiling "
            f"(finish_reason=length, max_tokens={max_tokens}). The answer is CUT OFF{spent}. "
            f"Raise --max-tokens and re-run before trusting this output.")


def is_empty_truncation(data):
    """True when a response burned its whole budget and wrote NO usable answer.

    The pathological reasoning-model failure: finish_reason=length AND a
    whitespace-only completion — the model spent every one of its max_tokens
    thinking and emitted zero content. This is STRICTLY narrower than
    was_truncated(), which also fires on a partial answer cut off mid-sentence
    (finish_reason=length WITH content). An empty truncation is the one a caller
    must NEVER treat as a substantive vote: it is silence, not a verdict. The
    board used to feed this seat's "" straight into the next round as its
    position, so downstream read the silence as a non-agreeing vote — a phantom
    disagreement that triggered a wasted round + re-fix loop.

    Accepts the full parsed OpenRouter response dict.
    """
    choice = (data.get("choices") or [{}])[0]
    content = ((choice.get("message") or {}).get("content") or "").strip()
    return was_truncated(choice) and not content


# --- cut-off-output policy ---------------------------------------------------------
#
# THE ONE HOME for truncation resilience. Before this, three callers each carried their own
# partial implementation (an empty-only escalation, a doubling loop, a fail-closed check) and
# the caller with none filed a review cut off mid-word as a finished position.
#
# 64000 is a mechanical BACKSTOP, not a target. Where a caller declares max_spend_usd, the
# dollar bound is the real ceiling and this only stops a runaway.
TRUNCATION_CEILING_TOKENS = 64000

# Distinct from 1 (argparse/usage) and 2 (a dispatch failure) so a caller can
# tell "the answer is cut off" from "the request died".
EXIT_TRUNCATED = 3


def truncation_state(data):
    """Read the truncation block off a response dict. Safe on any dict, including one
    revived from JSON — this is how the signal crosses a subprocess boundary."""
    blk = (data or {}).get("or_peer") or {}
    return {
        "truncated": bool(blk.get("truncated")),
        "attempts": int(blk.get("attempts") or 0),
        "final_max_tokens": blk.get("final_max_tokens"),
    }


def _escalation_headroom(model, max_spend_usd, spent_usd, prompt_tokens):
    """Tokens the remaining dollar budget can still fund, counting SUNK cost.

    Sunk cost is the whole point: the failed attempt is already billed and not refundable.
    Sizing the retry against the FULL budget instead would walk straight through the cap that
    the per-seat derivation exists to enforce.

    An unpriced model yields 0 — if the spend cannot be bounded, it is not escalated. Same
    doctrine as assert_priced(): a cost that cannot be measured must not be spent blind.
    """
    remaining = max_spend_usd - spent_usd
    if remaining <= 0:
        return 0
    try:
        return max_tokens_for_budget(model, remaining, prompt_tokens)
    except UnknownPriceError:
        return 0


class OrPeerRequestError(RuntimeError):
    """Raised by dispatch_chat on an unrecoverable OpenRouter request failure."""


def _post_with_retry(body, key, referer, title, retries, timeout):
    """POST one chat/completions body to OpenRouter with backoff. Returns parsed JSON.

    The transport seam: exactly one retry/backoff/error-handling implementation.
    Split out of dispatch_chat so the empty-truncation escalation can re-POST an
    adjusted body through the same path, and so tests can monkeypatch a single
    function to simulate a truncated-then-good exchange with no network.
    """
    req = urllib.request.Request(ENDPOINT, data=json.dumps(body).encode("utf-8"), method="POST")
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("HTTP-Referer", referer)
    req.add_header("X-Title", title)

    # Resilience: OpenRouter maintenance/degradation surfaces as timeouts, resets,
    # or 429/5xx. Retry those with exponential backoff so a blip doesn't kill a run.
    RETRYABLE_HTTP = {408, 409, 425, 429, 500, 502, 503, 504}
    last_err = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            if e.code in RETRYABLE_HTTP and attempt < retries:
                last_err = f"HTTP {e.code}: {detail}"
            else:
                raise OrPeerRequestError(f"or_peer: HTTP {e.code}: {detail}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            last_err = f"network error: {e}"
            if attempt >= retries:
                raise OrPeerRequestError(
                    f"or_peer: {last_err} after {attempt + 1} tries "
                    f"(OpenRouter maintenance window is the likely cause)") from e
        wait = 4 * (2 ** attempt)
        print(f"or_peer: attempt {attempt + 1} failed ({last_err}); retrying in {wait}s...",
              file=sys.stderr)
        time.sleep(wait)
    raise OrPeerRequestError(f"or_peer: no response after {retries + 1} tries: {last_err}")


def dispatch_chat(model, system=None, user=None, max_tokens=6000, temperature=0.3,
                   reasoning_effort=None, key=None, retries=3, timeout=180,
                   referer="https://github.com/greghaidev/claim-ledger",
                   title="claim-ledger", messages=None,
                   truncation_retry_max_tokens=None,
                   truncation_retries=0, max_spend_usd=None,
                   truncation_ceiling_tokens=TRUNCATION_CEILING_TOKENS,
                   caller=None, label=None, provider=None):
    """POST one chat/completions request to OpenRouter, with retry/backoff.

    THE shared OpenRouter POST path — or_peer.py's own CLI (main(), below) and
    claim_ledger.py both call this, so there is exactly one retry/backoff/
    error-handling implementation for talking to OpenRouter, not two drifting copies.

    Pass either (system, user) — the two-string shape build_request_body expects —
    or a fully-formed OpenAI-style ``messages`` list. ``messages``, when given, wins.

    ``model`` is always the caller's explicit choice — this function never falls
    back to a default/ambient/session model.

    CUT-OFF OUTPUT. Two separate things, deliberately split
    because one is free and the other costs money:

    DETECTION is ALWAYS ON and costs nothing. Every returned dict carries an ``or_peer``
    block (read it with ``truncation_state``) reporting whether the FINAL response was cut
    off. The predicate is ``was_truncated`` — ANY ``finish_reason == "length"``, with or
    without content. It used to be ``is_empty_truncation``, which by its own docstring left
    "a partial answer cut off mid-sentence" alone; that gap is exactly how a 13,676-character
    review ending mid-word was filed as a finished position.

    ESCALATION IS OPT-IN, because output tokens are billed. A caller that declares no budget
    makes exactly one request — it is not silently double-charged. Opting out of escalation
    is safe precisely because detection is not optional: the worst case is a loud abstain,
    never a cut-off answer reported as complete. Opt in with either:

      * ``truncation_retries`` (+ optional ``max_spend_usd``) — re-POST with a DOUBLED budget,
        because the cause is a ceiling too low for THIS input, so retrying at the same budget
        would only reproduce the cut-off. Bounded by ``max_spend_usd`` when given (counting
        sunk cost) and by ``truncation_ceiling_tokens`` always.
      * ``truncation_retry_max_tokens`` (legacy) — ONE retry at exactly that ceiling.

    Why this is not another ceiling raise: the ceiling has gone 6000 -> 9000 -> 12000 and the
    class recurred after each raise. A scalar constant compared against an unbounded input is
    not a fix. Here the OBSERVED finish_reason drives the next budget, and exhaustion is
    machine-blocking (``truncated: True``; the CLI exits EXIT_TRUNCATED) rather than silent.

    Returns the parsed JSON response dict on success. Raises OrPeerRequestError
    on an unrecoverable failure (non-retryable HTTP error, or retries exhausted).
    """
    if key is None:
        key = load_key()
    # Resolve BEFORE the body is built, so both the `messages` and the system/user path get the
    # same answer. Default is None ("caller did not specify") rather than "none" ("reasoning
    # OFF") — those are different states and this module previously conflated them in its own
    # default value.
    reasoning_effort = resolve_effort(reasoning_effort, caller)
    # Default routing chases price, and the cheapest endpoints are quantized. A caller that has
    # chosen its own routing keeps it; a caller that has not gets the measured per-model
    # preference instead of whatever is cheapest this minute.
    if provider is None:
        provider = provider_prefs(model)
    if messages is not None:
        body = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if reasoning_effort and reasoning_effort != "none":
            body["reasoning"] = {"effort": reasoning_effort}
        if provider:
            body["provider"] = provider
    else:
        body = build_request_body(model, system, user, max_tokens, temperature,
                                  reasoning_effort, provider)

    # A legacy caller passing only truncation_retry_max_tokens gets exactly one escalated
    # retry, at exactly that ceiling — the seat path still relies on that shape.
    allowed = truncation_retries
    if truncation_retry_max_tokens and truncation_retry_max_tokens > max_tokens:
        allowed = max(allowed, 1)

    budget = max_tokens
    attempts = 0
    spent_usd = 0.0
    # Ledger accounting runs alongside the escalation budget but never shares its sentinel:
    # spent_usd is allowed to go infinite (that is what stops escalation), the ledger figure
    # is not (see _finite).
    ledger_cost = 0.0
    cost_source = "reported"
    while True:
        body = {**body, "max_tokens": budget}
        data = _post_with_retry(body, key, referer, title, retries, timeout)
        attempts += 1
        usage = data.get("usage") or {}
        try:
            attempt_cost = cost(model, usage)
            reported = usage.get("cost")
            if not (isinstance(reported, (int, float)) and not isinstance(reported, bool)
                    and reported > 0):
                cost_source = "table"   # cost() fell back to the PRICES snapshot
            if ledger_cost is not None:
                ledger_cost += attempt_cost
            spent_usd += attempt_cost
        except UnknownPriceError:
            # Unmeasurable spend: keep going, but _escalation_headroom will refuse to fund
            # any further attempt when a dollar bound was requested.
            cost_source = "unknown"
            ledger_cost = None
            spent_usd = float("inf") if max_spend_usd is not None else spent_usd

        choice = (data.get("choices") or [{}])[0]
        if not was_truncated(choice) or attempts > allowed:
            break

        # Doubling by default; the legacy ceiling wins on the first retry when supplied.
        nxt = (truncation_retry_max_tokens
               if attempts == 1 and truncation_retry_max_tokens
               else budget * 2)
        nxt = min(nxt, truncation_ceiling_tokens)
        if max_spend_usd is not None:
            nxt = min(nxt, _escalation_headroom(
                model, max_spend_usd, spent_usd, usage.get("prompt_tokens", 0)))
        if nxt <= budget:
            break  # no headroom: re-POSTing here would just buy the same cut-off again
        print(f"or_peer: response cut off at max_tokens={budget} "
              f"(finish_reason=length); retrying at max_tokens={nxt}...", file=sys.stderr)
        budget = nxt

    truncated = was_truncated((data.get("choices") or [{}])[0])
    # One line per LOGICAL dispatch (a truncation escalation is one dispatch that cost more,
    # carried in `attempts` + the summed cost), written for every caller without exception.
    record_dispatch(model, data.get("usage") or {}, ledger_cost, resolve_caller(caller),
                    label=label, attempts=attempts, truncated=truncated,
                    cost_source=cost_source, provider=data.get("provider"))

    data["or_peer"] = {
        "truncated": truncated,
        "attempts": attempts,
        "final_max_tokens": budget,
        "cost_usd": _finite(ledger_cost),
        "cost_source": cost_source,
    }
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="deepseek/deepseek-v4-pro")
    ap.add_argument("--system-file", required=True)
    ap.add_argument("--input-file", required=True)
    ap.add_argument("--out", default=None, help="save raw response JSON here")
    ap.add_argument("--label", default="run")
    ap.add_argument("--caller", default=None,
                    help="who is spending this money, for the spend ledger "
                         "(e.g. claim_ledger). Falls back to $OR_DISPATCH_CALLER, then argv0.")
    ap.add_argument("--max-tokens", type=int, default=6000)
    ap.add_argument("--temperature", type=float, default=0.3)
    ap.add_argument("--reasoning-effort", default="none", choices=REASONING_EFFORTS,
                    help="engage OpenRouter reasoning at this effort tier (default: none/off). "
                         "DeepSeek V4 bills reasoning inside completion_tokens, so raise "
                         "--max-tokens alongside it or the answer truncates.")
    ap.add_argument("--retries", type=int, default=3, help="retries on timeout/reset/429/5xx")
    ap.add_argument("--timeout", type=int, default=180, help="per-attempt seconds")
    ap.add_argument("--truncation-retry-max-tokens", type=int, default=0,
                    help="legacy: re-dispatch ONCE at exactly this higher ceiling when the "
                         "response is cut off (0=off). Prefer --truncation-retries.")
    ap.add_argument("--truncation-retries", type=int, default=0,
                    help="re-dispatch up to N times with a DOUBLED token budget when the "
                         "response is cut off (finish_reason=length). 0 (default) spends "
                         "nothing extra; the cut-off is still reported and still exits "
                         f"{EXIT_TRUNCATED}.")
    ap.add_argument("--truncation-max-spend-usd", type=float, default=None,
                    help="bound the escalation in DOLLARS (counting the spend already "
                         "sunk in the failed attempts) rather than in tokens.")
    ap.add_argument("--allow-truncated", action="store_true",
                    help=f"exit 0 even when the final answer is cut off (default: exit "
                         f"{EXIT_TRUNCATED}). For interactive use. The truncation flag is "
                         "still written to --out either way — this hides the exit code, "
                         "never the fact.")
    args = ap.parse_args()

    key = load_key()
    system = read_file(args.system_file)
    user = read_file(args.input_file)

    t0 = time.time()
    try:
        data = dispatch_chat(
            args.model, system=system, user=user, max_tokens=args.max_tokens,
            temperature=args.temperature, reasoning_effort=args.reasoning_effort,
            key=key, retries=args.retries, timeout=args.timeout,
            truncation_retry_max_tokens=(args.truncation_retry_max_tokens or None),
            truncation_retries=args.truncation_retries,
            max_spend_usd=args.truncation_max_spend_usd,
            caller=args.caller, label=args.label,
        )
    except OrPeerRequestError as e:
        sys.exit(str(e))
    dt = time.time() - t0

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)

    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message", {}) or {}
    content = msg.get("content") or ""
    reasoning = msg.get("reasoning") or ""
    usage = data.get("usage", {}) or {}
    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")

    print("=" * 78)
    print(f"MODEL: {data.get('model', args.model)}   LABEL: {args.label}   {dt:.1f}s")
    print("=" * 78)
    if reasoning:
        print("\n----- REASONING (truncated to 1500 chars) -----")
        print(reasoning[:1500])
    print("\n----- COMPLETION -----\n")
    print(content)
    print("\n" + "=" * 78)
    rtok = f" reasoning={reasoning_tokens}" if reasoning_tokens else ""
    print(f"USAGE: prompt={usage.get('prompt_tokens')} "
          f"completion={usage.get('completion_tokens')}{rtok} "
          f"total={usage.get('total_tokens')}")
    print(f"COST:  ${cost(args.model, usage):.4f}")
    print("=" * 78)
    # Silent-truncation guard (R3): if the model hit the ceiling, the verdict is
    # cut off. Shout it on BOTH streams so a truncated PASS/FAIL is never trusted.
    state = truncation_state(data)
    warn = truncation_warning(choice, state["final_max_tokens"] or args.max_tokens,
                              reasoning_tokens)
    if warn:
        print("\n" + warn)
        print(warn, file=sys.stderr)
    # Exit non-zero so a cut-off answer cannot be read as a completed one. Printing a
    # warning and exiting 0 is what let a caller report `ok` for a review that stopped
    # mid-word. If you wrap this CLI, map a non-zero exit to a blocker.
    if state["truncated"] and not args.allow_truncated:
        sys.exit(EXIT_TRUNCATED)


if __name__ == "__main__":
    # Windows writes the ANSI code page to a pipe or console by default; a printed arrow or
    # em dash in a claim would otherwise crash the run.
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8", errors="replace")
    main()
