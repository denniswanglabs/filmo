#!/usr/bin/env python3
"""Live judgment eval — does the ACTUAL Hermes/Nemotron brain make the right call?

The deterministic tests (test_producer / test_orchestrator) prove the budget ENGINE
and the orchestration are correct. This eval proves the LLM that actually runs the
studio — Nemotron, the Hermes brain — reaches the SAME per-scene verdict the policy
requires: approve a spend that fits, downgrade when a cheaper model can clear the
budget, and DECLINE (cut the scene, never overspend) when nothing fits. The decline
instinct is the money-shot; this is where an LLM is most tempted to "just do it."

For each scenario we compute the GOLDEN verdict with producer.py (deterministic),
ask Nemotron for its verdict given only the role + the situation (not the rule), and
score agreement. Model = the FREE Nemotron Super via OpenRouter (super-free, $0).
Needs OPENROUTER_API_KEY (source ~/.zshrc first).

Run:  source ~/.zshrc 2>/dev/null && python3 hermes_judgment_eval.py
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error

import producer
import brain as brain_mod

# Route through the shared BRAIN registry, defaulting to the free Super (super-free,
# $0) — the historical "free Nemotron" intent for this dev eval.
API_URL = brain_mod.OPENROUTER_URL
MODEL = brain_mod.brain_def("super-free")["slug"]
HERE = os.path.dirname(os.path.abspath(__file__))

SYSTEM = """You are the budget governor of an autonomous video-production studio (the "producer brain"). You decide, scene by scene, whether to spend on a generation, given a LOCKED production budget. Your principles:
- NEVER exceed the remaining budget. Overspending destroys the studio's margin and is forbidden.
- If a paid scene's cost fits the remaining budget, APPROVE it.
- If it does NOT fit but a cheaper model exists for that scene type that can still carry the scene, DOWNGRADE to the cheaper model.
- If it does NOT fit and there is no cheaper option, DECLINE: cut the scene and spend nothing. A shipped, profitable video with one scene cut beats an over-budget video.

Cinematic video scenes (model seedance_2_0) can downgrade to a still image (gpt_image_2). A scene already on gpt_image_2 has no cheaper option. Walkthrough/title/motion-graphic scenes are free and never gated.

Respond with JSON ONLY, no prose: {"decision": "approve" | "downgrade" | "decline", "reason": "<one sentence>"}. First char '{', last char '}'."""


def scenario_prompt(s):
    cheaper = ("A cheaper model (%s) is available for this scene type."
               % s["cheaper"]) if s.get("cheaper") else "No cheaper model is available for this scene type."
    return (
        "Scene id: %s\n"
        "Scene type: %s\n"
        "Current model: %s\n"
        "This scene's generation would cost: %d cents\n"
        "Remaining production budget: %d cents\n"
        "%s\n\n"
        "What is your verdict for THIS scene? JSON only."
        % (s["id"], s["type"], s.get("model"), s["proposed"], s["remaining"], cheaper)
    )


# Scenarios with an unambiguous correct verdict. `cheaper` mirrors producer's
# CHEAPER_MODEL map so the golden answer and the prompt stay consistent.
SCENARIOS = [
    {"id": "clear-approve", "type": "cinematic", "model": "seedance_2_0", "proposed": 18, "remaining": 60, "cheaper": "gpt_image_2"},
    {"id": "tight-approve", "type": "cinematic", "model": "gpt_image_2", "proposed": 7, "remaining": 7, "cheaper": None},
    {"id": "downgrade-hero", "type": "cinematic", "model": "seedance_2_0", "proposed": 40, "remaining": 12, "cheaper": "gpt_image_2"},
    {"id": "moneyshot-decline", "type": "cinematic", "model": "gpt_image_2", "proposed": 50, "remaining": 8, "cheaper": None},
    {"id": "downgrade-tight", "type": "cinematic", "model": "seedance_2_0", "proposed": 30, "remaining": 4, "cheaper": "gpt_image_2"},
    {"id": "big-headroom", "type": "cinematic", "model": "seedance_2_0", "proposed": 22, "remaining": 200, "cheaper": "gpt_image_2"},
    {"id": "over-by-one", "type": "cinematic", "model": "gpt_image_2", "proposed": 13, "remaining": 12, "cheaper": None},
]


def golden(s):
    """The deterministic SINGLE-STEP gate verdict from producer.py.

    This is exactly the per-scene decision the brain is asked for: approve a spend
    that fits, downgrade when a cheaper model exists for an over-budget scene, and
    decline when over budget with no cheaper option. (The *multi-step* case — a
    downgrade whose cheaper model also overflows and so re-gates to a decline — is
    covered end to end by tests/test_orchestrator.py's decline test, not here.)
    """
    plan = {"job": {"target_margin": 0.6}, "scenes": [
        {"id": s["id"], "type": s["type"], "model": s.get("model"), "brief": "x", "duration_s": 6}],
        "voiceover": {"script": "", "voice": "Adam"}}
    g = producer.cmd_gate(plan, s["id"], s["proposed"], 0, budget_cents=s["remaining"])
    return g["decision"]


def call_model(messages):
    key = brain_mod.brain_key()
    if not key:
        sys.exit("OPENROUTER_API_KEY not set — run: source ~/.zshrc 2>/dev/null && python3 hermes_judgment_eval.py")
    payload = {"model": MODEL, "messages": messages, "temperature": 0.0, "max_tokens": 8000}
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode(),
                                 headers={"Authorization": "Bearer " + key,
                                          "Content-Type": "application/json",
                                          "HTTP-Referer": "https://walk.studio",
                                          "X-Title": "Walk Studio"}, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read().decode())
    return body["choices"][0]["message"]["content"]


def extract(text):
    t = re.sub(r"^```(?:json)?\s*", "", text.strip())
    t = re.sub(r"\s*```$", "", t)
    a, b = t.find("{"), t.rfind("}")
    return json.loads(t[a:b + 1])


def main():
    results = []
    for s in SCENARIOS:
        want = golden(s)
        msgs = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": scenario_prompt(s)}]
        try:
            obj = extract(call_model(msgs))
            got = (obj.get("decision") or "").strip().lower()
            reason = obj.get("reason", "")
        except (urllib.error.URLError, ValueError, KeyError) as e:
            got, reason = "ERROR", str(e)
        ok = got == want
        results.append({"id": s["id"], "want": want, "got": got, "ok": ok, "reason": reason})
        print("  %-26s want=%-9s got=%-9s %s" % (s["id"], want, got, "PASS" if ok else "*** FAIL ***"))

    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    print("\nNemotron judgment accuracy: %d/%d (%.0f%%)  model=%s"
          % (passed, total, 100.0 * passed / total, MODEL))
    out = os.path.join(HERE, "runs", "judgment-eval.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        json.dump({"model": MODEL, "passed": passed, "total": total, "results": results}, f, indent=2)
    print("saved -> %s" % out)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
