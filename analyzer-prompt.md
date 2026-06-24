# Hermes Conversion-Read Prompt

This file documents the exact prompt the ANALYZE step (`analyze.py`) sends to Nemotron.
It turns a page's real copy into a **strict Conversion Read JSON** that is (a) shown to
the user as a first-class diagnosis and (b) seeds the video plan. The string source of
truth is `analyze.SYSTEM_PROMPT`; this doc restates it for humans and freezes the contract.

## Output contract (FIXED — consumers read these exact names)

```json
{
  "url": "str",
  "verdict": "str",
  "dimensions": [
    {"key": "promise|outcome|proof|show|specificity|cta",
     "score": 0, "finding": "str", "evidence": "str", "fix": "str"}
  ],
  "priority_fixes": [{"rank": 1, "fix": "str", "maps_to": "str"}],
  "headline_fix": "str"
}
```

## The 6 dimensions (score 0 worst — 5 best)

| key | question | 0 | 5 |
|---|---|---|---|
| `promise` | first 5s say what it is + who it's for? | makes you work | instantly clear |
| `outcome` | sells the buyer's result vs features? | feature list | outcome-led |
| `proof` | credible evidence (numbers/demo/logos)? | none | strong, specific |
| `show` | shows the product working vs abstract talk? | all tell | real demo |
| `specificity` | concrete vs vague? | "powerful" | "10x faster" |
| `cta` | one clear next step? | none/many | single obvious |

`proof` and `show` are the highest-leverage dimensions (Ploy: "zero social proof is the
biggest lever"); `priority_fixes` weights toward them.

## Rules (numbered, as sent)

1. Ground every finding/evidence in the page's actual words (quote them).
2. proof + show are highest-leverage; weight `priority_fixes` toward them.
3. `priority_fixes` = top 1-3 fixes, rank 1 first; `maps_to` is a short scene hint.
4. `headline_fix` = one outcome-led sentence (never a feature, never the bare brand name).
5. Never invent a different product than the one in the copy.
6. Self-check before emitting: 6 keys present once, int scores 0-5, JSON parses, `{`…`}`.
7. EACH field value (especially `evidence`, `finding`, `fix`) is **one** JSON string —
   never split it into multiple comma-separated quoted pieces. No trailing commas, no
   smart/curly quotes (use straight `"`).

```text
CORRECT:    "evidence": "Financial infrastructure; Millions of companies of all sizes"
MALFORMED:  "evidence": "Financial infrastructure", "and", "Millions of companies"
```

## Failure handling

`analyze.analyze_read` does up to **4 attempts**. Each attempt first tries the planner's
strict `vp.extract_json`, then an **analyze-local `repair_json`** that fixes the common
super-free Nemotron slips before any reprompt:

- collapses multiple comma-separated quoted fragments inside one value into a single
  string (the `"a", "b", "c"` evidence bug that degraded ~2/3 of runs),
- normalizes smart/curly quotes to straight quotes,
- drops trailing commas before `}`/`]`.

`repair_json` is ANALYZE-path only — it never touches the shared `vp.extract_json`/planner.
On no-key, network error, output still unparseable after repair across all attempts, or a
Read that fails `validate_read`, it returns `analyze.minimal_read(url, body_text)`
(deterministic, valid, `degraded=true`). The pipeline is NEVER blocked by the analyzer.
