#!/usr/bin/env python3
"""Skill-routing eval — can the SMALLER Nemotron model drive Hermes's skills?

Hermes triggers a skill by matching a request against each skill's `description:`.
On a small open model that matching is the weak link. This harness reads the LIVE
descriptions from ~/.hermes/skills/<skill>/SKILL.md, asks the free Nemotron brain to
pick the right skill for a battery of realistic requests (with distractors), and
scores it. When a skill mis-routes, sharpen its `description:` and re-run — the eval
reads from disk, so edits show up immediately. This is the "import skills → test on
the small model → fix the skill → re-evaluate until satisfied" loop, $0.

Model = FREE Nemotron Super via OpenRouter (super-free, $0). Needs OPENROUTER_API_KEY
(source ~/.zshrc).
Run:  source ~/.zshrc 2>/dev/null && python3 hermes_skill_eval.py
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error

import brain as brain_mod

# Route through the shared BRAIN registry, defaulting to the free Super (super-free,
# $0) — the historical "free Nemotron" intent for this dev eval.
API_URL = brain_mod.OPENROUTER_URL
MODEL = brain_mod.brain_def("super-free")["slug"]
SKILLS_DIR = os.path.expanduser("~/.hermes/skills")
HERE = os.path.dirname(os.path.abspath(__file__))

# The candidate skills the router chooses among: our video-studio skills, the
# official Stripe Skills for Hermes, plus real distractors. "none" is allowed.
CANDIDATES = [
    "producer-brain", "walk-agent", "higgsfield-scene", "motion-graphics", "video-stitch",
    "stripe-link-cli", "stripe-projects", "mpp-agent",
    "dogfood", "yuanbao",
]

# request -> the skill that SHOULD fire (golden). "none" = no skill should trigger.
CASES = [
    ("Produce a complete 30-second promo plus an app walkthrough for acme.com, price it for a 60% margin and give me the P&L", "producer-brain"),
    ("Run the whole studio end to end on stripe.com: plan it, price it, make it under budget", "producer-brain"),
    ("Make a tutorial video showing how to start a focus session on beside.app", "walk-agent"),
    ("Record a screen walkthrough of finding the API keys in the Stripe dashboard", "walk-agent"),
    ("Generate a cinematic hero shot of a refinery at dawn with drifting steam", "higgsfield-scene"),
    ("Animate this still image into a 12-second clip", "higgsfield-scene"),
    ("Render a title card that says 'Welcome to Operon' with a lime accent", "motion-graphics"),
    ("Make a lower-third name bar for the speaker", "motion-graphics"),
    ("Stitch these three clips and the voiceover track into one finished mp4", "video-stitch"),
    ("Buy 5000 Higgsfield credits for me / complete this checkout", "stripe-link-cli"),
    ("Pay for this purchase with a one-time virtual card", "stripe-link-cli"),
    ("Provision a Postgres database and a Twilio number for this project", "stripe-projects"),
    ("Set up Neon and sync the credentials into my .env", "stripe-projects"),
    ("This merchant API returned HTTP 402 Payment Required — pay it per request", "mpp-agent"),
    ("Set up an agent wallet so I can pay per-request APIs", "mpp-agent"),
    ("Do exploratory QA on my web app, find bugs and write a report with evidence", "dogfood"),
    ("In the Yuanbao group, @mention everyone and ask who is free Friday", "yuanbao"),
    ("What's the weather in Taipei tomorrow?", "none"),
    ("Tell me a joke about refineries", "none"),
]


def load_descriptions():
    out = {}
    for name in CANDIDATES:
        path = os.path.join(SKILLS_DIR, name, "SKILL.md")
        out[name] = _read_description(path)
    return out


def _read_description(path):
    if not os.path.exists(path):
        return "(skill not installed)"
    try:
        with open(path) as f:
            text = f.read()
    except OSError:
        return "(unreadable)"
    # frontmatter description: may be quoted and/or wrap to the next indented lines
    m = re.search(r"(?m)^description:\s*(.+)$", text)
    if not m:
        return "(no description)"
    desc = m.group(1).strip().strip('"').strip("'")
    return desc[:400]


def catalog_block(desc):
    lines = ["Available skills (choose AT MOST ONE):"]
    for name in CANDIDATES:
        lines.append("- %s: %s" % (name, desc[name]))
    lines.append('- none: no skill fits this request')
    return "\n".join(lines)


SYSTEM = ("You are the skill router for the Hermes agent. Given a user request and a list of "
          "skills with their descriptions, choose the SINGLE best skill to handle it, or 'none' "
          "if no skill fits. Judge purely on the descriptions. Reply with JSON only: "
          '{"skill": "<exact skill name or none>"}. First char {, last char }.')


def call_model(messages):
    key = brain_mod.brain_key()
    if not key:
        sys.exit("OPENROUTER_API_KEY not set — run: source ~/.zshrc 2>/dev/null && python3 hermes_skill_eval.py")
    payload = {"model": MODEL, "messages": messages, "temperature": 0.0, "max_tokens": 6000}
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                                          "HTTP-Referer": "https://walk.studio", "X-Title": "Walk Studio"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode())["choices"][0]["message"]["content"]


def extract(text):
    t = re.sub(r"^```(?:json)?\s*", "", text.strip()); t = re.sub(r"\s*```$", "", t)
    a, b = t.find("{"), t.rfind("}")
    return json.loads(t[a:b + 1])


def main():
    desc = load_descriptions()
    missing = [n for n in CANDIDATES if desc[n].startswith("(no description") or desc[n].startswith("(skill")]
    if missing:
        print("WARN — weak/missing descriptions (fix these to improve routing): " + ", ".join(missing) + "\n")
    cat = catalog_block(desc)

    results = []
    for req, want in CASES:
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": cat + "\n\nRequest: " + req + "\n\nJSON only."}]
        try:
            got = (extract(call_model(msgs)).get("skill") or "").strip()
        except (urllib.error.URLError, ValueError, KeyError) as e:
            got = "ERROR:" + str(e)
        ok = got == want
        results.append({"request": req, "want": want, "got": got, "ok": ok})
        print("  %-9s want=%-16s got=%-16s %s" % ("PASS" if ok else "FAIL", want, got, "" if ok else "  <-- mis-route"))

    passed = sum(1 for r in results if r["ok"])
    by_skill = {}
    for r in results:
        by_skill.setdefault(r["want"], [0, 0])
        by_skill[r["want"]][0] += 1 if r["ok"] else 0
        by_skill[r["want"]][1] += 1
    print("\nPer-skill recall:")
    for s, (p, n) in by_skill.items():
        flag = "" if p == n else "   *** needs a sharper description ***"
        print("  %-16s %d/%d%s" % (s, p, n, flag))
    print("\nNemotron skill-routing accuracy: %d/%d (%.0f%%)  model=%s"
          % (passed, len(results), 100.0 * passed / len(results), MODEL))
    out = os.path.join(HERE, "runs", "skill-eval.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump({"model": MODEL, "passed": passed, "total": len(results), "results": results}, f, indent=2)
    print("saved -> %s" % out)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    main()
