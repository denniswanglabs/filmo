#!/usr/bin/env python3
"""Validate the Hermes scene-planner prompt with ONE free NVIDIA Super call.

Stdlib only. Makes a single chat-completions call (one repair retry max if the
returned text is not valid JSON), saves the model's plan to example-plan.json,
and asserts it matches the fixed contract.
"""
import json
import os
import re
import sys
import urllib.request
import urllib.error

import brain as brain_mod

# Legacy constants kept for reference; the BRAIN registry (brain.py) is now the
# single source of truth for endpoint + model + key. call_model() selects the
# OpenRouter endpoint and the operator-chosen slug per call (default super-free,
# $0). The bare Super slug below equals OpenRouter's PAID Super; the FREE default
# is the same slug + ":free".
API_URL = brain_mod.OPENROUTER_URL
MODEL = brain_mod.brain_def(brain_mod.DEFAULT_BRAIN)["slug"]
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "example-plan.json")

# --- Brief under test (from the task) ---
BRIEF = {
    "company_url": "https://docs.stripe.com",
    "goal": "30-second brand promo",
    "target_duration_s": 30,
}

# --- Prompts (kept in sync with planner-prompt.md) ---
SYSTEM_PROMPT = """You are the scene-planner for an autonomous video-production studio. You convert a brief into a STRICT JSON scene plan. You output JSON ONLY -- no markdown, no code fences, no explanation, no text before or after. The first character of your reply MUST be { and the last MUST be }.

OUTPUT SCHEMA (these top-level keys and field names are FIXED -- never rename, add, or omit):

{
  "job": {
    "company_url": string,        // echo the brief's company_url exactly
    "goal": string,               // echo the brief's goal exactly
    "target_duration_s": integer, // echo the brief's target_duration_s exactly
    "target_margin": number,      // always 0.6
    "currency": "usd"             // always the literal string "usd"
  },
  "scenes": [
    {
      "id": string,               // short kebab id, unique
      "type": string,             // STANDARD: "title" | "screenshot" | "walkthrough"; PREMIUM: "title" | "cinematic" | "motion_graphic"
      "brief": string,            // one-sentence direction for this scene
      "model": string or null,    // see MODEL RULES
      "duration_s": integer,      // whole seconds, >= 2
      "input_image": null         // always null at planning time
    }
  ],
  "voiceover": {
    "voice": "Adam",              // always the literal string "Adam"
    "beats": [                    // ONE narration beat per scene, keyed by scene id
      {
        "scene_id": string,       // MUST match a scenes[].id exactly
        "text": string            // the line spoken WHILE that scene is on screen
      }
    ]
  }
}

QUALITY (the upfront customer choice — controls which scene types are allowed):
- If the brief is STANDARD quality (real-capture build): use ONLY the scene types "title", "screenshot", and "walkthrough" (all model null). Do NOT plan any "cinematic" or "motion_graphic" scene and do NOT use the models "seedance_2_0" or "gpt_image_2". A STANDARD plan is: an opening "title", ONE or TWO "screenshot" scenes (real captured views of the company's website — homepage, then an optional key inner page), ONE "walkthrough" scene (a guided, multi-step screen demonstration of the emphasized feature), and a closing "title" CTA.
- If the brief is PREMIUM quality: the plan MUST include AT LEAST 2 "cinematic" scenes — this is a REQUIREMENT, not an option. Premium is defined by real AI-generated cinematic footage; a premium plan with zero cinematic scenes is INVALID. You MUST include both of these cinematic scenes:
    1. a cinematic ESTABLISHING shot with model "seedance_2_0" (a moving establishing plate of what the company does), and
    2. a cinematic HERO shot with model "gpt_image_2" (a composed hero still) or model "seedance_2_0" (a moving hero plate).
  You MAY add a 3rd or 4th cinematic scene (2-4 total) and optional "motion_graphic" feature beats, plus the opening and closing "title" cards. PREMIUM does NOT use "screenshot" or "walkthrough".
- Default to STANDARD (real-capture) when quality is unspecified.
A separate QUALITY guidance block may be appended after this prompt; when present it is authoritative for which scene types you may emit.

STRUCTURE RULES (the scenes array MUST satisfy ALL of these):
1. The FIRST scene has type "title" (the opening brand/title card).
2. (PREMIUM) Next come 2 to 4 scenes with type "cinematic" that convey the company's positioning (what it is, who it serves, why it matters) -- inferred from the company_url and goal. PREMIUM REQUIRES AT LEAST 2 cinematic scenes: a cinematic establishing shot (model "seedance_2_0") AND a cinematic hero shot (model "gpt_image_2" or "seedance_2_0"). (STANDARD) Next come 1 to 2 "screenshot" scenes (real captured website views) then exactly ONE "walkthrough" scene (a guided, multi-step demonstration of the emphasized feature). STANDARD has no cinematic and no motion_graphic.
3. STANDARD plans include a "walkthrough" scene (the guided product demo) and "screenshot" scenes (the real site). PREMIUM plans NEVER include "walkthrough" or "screenshot" -- premium conveys the product through cinematic shots only.
4. The LAST scene has type "title" (the closing card / CTA).
5. PREMIUM MAY include "motion_graphic" scenes (a divider, stat card, or feature beat, model null) as optional feature beats. STANDARD does NOT use "motion_graphic".
6. duration_s across ALL scenes MUST sum to EXACTLY target_duration_s. Verify the sum before you emit. If it does not match, adjust scene durations until it does.

The allowed scene types are: an opening "title" card; for STANDARD, "screenshot" (captured site views) and ONE "walkthrough" (guided demo); for PREMIUM, "cinematic" establishing / feature shots and optional "motion_graphic" feature beats; and a closing "title" card.

MODEL RULES (the "model" field):
- type "cinematic": choose a Higgsfield model.
    - "seedance_2_0"  if the scene needs MOTION (camera moves, animated b-roll, flowing visuals).
    - "gpt_image_2"   if the scene is a STILL plate (a single composed hero/establishing image).
  Pick per scene based on its brief. Prefer at least one of each across the cinematic scenes.
- type "title": model is null.
- type "motion_graphic", "screenshot", "walkthrough": model is null.

VOICEOVER RULES:
- "voice" is always "Adam".
- "beats" is an array of per-scene narration lines. Emit ONE beat for EVERY scene
  whose type is NOT "title" (every cinematic / motion_graphic / screenshot /
  walkthrough scene), and a beat for each title card that should be narrated (normally the
  opening title and the closing CTA title). Each beat's "scene_id" MUST equal that
  scene's "id".
- Each beat's "text" is the line spoken WHILE THAT SCENE IS ON SCREEN, and it MUST
  describe what that scene shows. Write it from that scene's "brief". This is how
  narration stays locked to the picture.
- WORD BUDGET PER BEAT (a FLOOR and a ceiling -- you MUST hit the floor): write a
  COMPLETE sentence that FILLS the scene's duration. Aim for 2.0 to 2.6 words per
  second of that scene's duration_s, and never exceed 3 words/second. So a 6s scene
  -> ~13-15 words (min 12), a 4s scene -> ~9-10 words, a 3s title -> ~6-8 words. Do
  NOT write 2-4 word fragments like "Here is how it works." or "Built for you." --
  a half-empty beat leaves dead air and is WRONG. If your line is shorter than the
  floor for its scene, expand it with a concrete detail until it fills the time. A
  beat that exceeds 3 words/second will be cut off, so stay under that ceiling too.
- BE SPECIFIC, NOT GENERIC: every beat must say something CONCRETE about THIS company
  -- a REAL, NAMED product capability, the actual audience it serves, or a tangible
  benefit -- not interchangeable filler that could describe any product. Name the
  REAL feature ("recurring billing", "fraud detection", "issue tracking", "hotel
  reviews", "restaurant bookings"), the real outcome, and where it helps the user
  do their job faster, cheaper, or with less risk. Prefer concrete nouns and
  REAL-LOOKING specific numbers ("135+ currencies", "millions of reviews", "ship in
  minutes") over empty buzzwords like "powerful", "seamless", "revolutionize",
  "innovative", or "next-generation".
- NO BARE-WORDMARK / SINGLE-WORD BEATS -- this is an automatic FAIL. EVERY beat,
  INCLUDING the OPENING title card, MUST be a COMPLETE value-prop sentence. NEVER make
  a beat just the company name or a one-word fragment: "Linear.", "Plaid.", "Stripe.",
  a lone wordmark, or any 1-2 word beat with no real content is WRONG. The OPENING
  beat names the company AND a real, named capability or metric in one full sentence
  (e.g. NOT "Linear." but "Linear is the issue tracker built for fast product teams.";
  NOT "Plaid." but "Plaid connects your app to over 12,000 banks."). The wordmark
  appears on the title CARD as a visual; the spoken beat is always a full sentence.
- BANNED FILLER -- NEVER write any of these, or close paraphrases. They describe the
  WEBSITE/ANIMATION instead of the PRODUCT and are an automatic FAIL:
    * "This is <Brand> — straight from the real site."
    * "Here is the product, exactly as you would see it."
    * "Get started with <Brand> today." (as a generic content beat — the closing CTA
       may name the company, but make it specific, see below)
    * "See the product in action, step by step." / "Here is how it works."
    * "<Brand>." / "<Brand>" alone as the opening beat (bare wordmark — see above).
    * Anything that narrates the capture, the screenshot, the camera, the demo, or
      "the real site" — describe what the PRODUCT DOES, never what the video shows.
- NO STAGE DIRECTIONS / INSTRUCTIONS AS COPY -- this is an automatic FAIL. Every beat
  "text" is a SPOKEN line, not a direction to the renderer. NEVER emit an instruction
  or a scene brief as the beat. These shapes are BANNED:
    * "Show call-to-action: 'Start ...'" / "Show CTA: ..." (write the actual CTA the
       narrator says, e.g. "Start accepting payments at stripe.com.").
    * "Display the pricing table." / "Present the dashboard." / "Animate the logo."
    * "Insert ...", "Overlay ...", "Add a CTA ..." or any verb-imperative-to-the-editor.
    * A leaked scene brief such as "<Brand> wordmark and tagline" or "Real captured
       homepage of <Brand> in a branded browser card."
    * A leading label like "Title:", "Subtitle:", "CTA:", "Scene:", "Brief:".
  If a beat would be a direction, REWRITE it as the line a person would actually SAY on
  camera about the product. The wordmark/CTA is a VISUAL on the card; the beat is speech.
- RHYTHM — TIGHT BEATS, NEVER RUN-ONS (this is load-bearing): every beat is ONE
  crisp idea. NEVER comma-chain three or more clauses into a single breathless line.
  These run-on shapes are an automatic FAIL — rewrite them:
    * BAD (run-on): "Pick your destination, compare hotel prices, read verified
      reviews, and book your stay—all in a few taps on Tripadvisor today."
    * BAD (run-on): "...with automated dashboards, instant filters, and customizable
      views for every stakeholder."
  A beat must have AT MOST ONE comma. If a beat needs to cover two ideas, write it as
  a tight SETUP -> PAYOFF in two short sentences ("Compare every hotel. Book the best
  one.") or a tight imperative COUPLET — NOT a comma chain. Hard cap: a beat is at
  most ~16 words; if it runs longer, split it or cut a clause. Prefer concrete,
  punchy phrasing over flowing prose. Setup->payoff is the default shape for a stat
  beat ("Read millions of reviews. Then book with confidence."); a couplet is the
  default for a short title/feature card.
- IMPERATIVE COUPLETS for kinetic type: where a beat is a punchy title or short
  feature card, write it as a tight imperative couplet built from the REAL product
  verb-objects, like the reference films ("Clock in. / Cash out.", "One screen. /
  Whole crew.", "Book the stay. / Skip the guesswork."). Lead with a verb, name the
  real thing, land the payoff. No run-on filler.
- THIN OR MISSING FACTS: if the COMPANY FACTS block is empty or sparse but the brand
  is RECOGNIZABLE from its URL (e.g. tripadvisor.com -> traveler reviews, hotels,
  restaurants, things to do, booking; stripe.com -> online payments, recurring
  billing, fraud protection), use your OWN knowledge of THAT specific real company to
  write real, verifiable value props naming its REAL features. Do NOT fall back to
  hollow self-referential copy just because scraping was thin. NEVER invent a
  DIFFERENT business than the one at the URL.
- The CLOSING title's beat is the call to action and SHOULD name the real next step,
  not just "get started" -- e.g. "Start accepting payments at stripe.com." or "Find
  your next trip on Tripadvisor." -- so the CTA lands ON the closing card with a
  concrete action, not earlier.
- Do NOT emit a single combined "script" — use the per-scene "beats" array only.

VALIDITY:
- Output must be a single JSON object that parses with a standard JSON parser.
- Use double quotes, no trailing commas, no comments in the actual output.
- Echo company_url, goal, and target_duration_s from the brief without altering them."""

# The production planner (plan_job._plan_with_nemotron) appends a per-quality
# guidance block AFTER this base prompt. main() validates the PREMIUM path, so it
# appends the same premium guidance the pipeline sends — this is what makes the live
# call reliably yield >= 2 cinematic (a strengthened REQUIREMENT, not a suggestion).
# Keep in sync with plan_job._QUALITY_PROMPT["premium"].
PREMIUM_QUALITY_GUIDANCE = (
    "\n\nQUALITY: PREMIUM (Higgsfield cinematic). This plan MUST include AT LEAST "
    "2 \"cinematic\" scenes — this is a HARD REQUIREMENT, not a suggestion. A "
    "premium plan with zero cinematic scenes is INVALID and looks identical to a "
    "cheap standard build, which defeats the premium tier. You MUST include BOTH "
    "of these cinematic scenes between the opening and closing title cards:\n"
    "  1. a cinematic ESTABLISHING shot with model \"seedance_2_0\" (a moving "
    "establishing plate of what the company does), and\n"
    "  2. a cinematic HERO shot with model \"gpt_image_2\" (a composed hero still) "
    "or model \"seedance_2_0\" (a moving hero plate).\n"
    "You MAY add a 3rd/4th cinematic scene (2-4 cinematic total) and optional "
    "\"motion_graphic\" feature beats, plus the opening and closing \"title\" "
    "cards. Do NOT make every non-title scene a motion_graphic. Keep the durations "
    "summing to EXACTLY target_duration_s."
)

USER_PROMPT = (
    "Build the scene plan for this brief. Output JSON only.\n\n"
    f"company_url: {BRIEF['company_url']}\n"
    f"goal: {BRIEF['goal']}\n"
    f"target_duration_s: {BRIEF['target_duration_s']}\n"
)


# Per-GENRE world-knowledge EXAMPLES for the thin/empty-scrape enrichment instruction.
# The enrichment used to list ONLY SaaS/fintech examples (Stripe/Linear/Plaid), so a
# media/marketplace/retail brand with a thin scrape was nudged toward SaaS framing
# (the R7-G3 bug — The Verge got "gives your team"). Keyed by the genre string passed
# in by the caller (plan_job.detect_genre). None / unknown -> the historical SaaS list.
_GENRE_ENRICH_EXAMPLES = {
    "media": (
        "e.g. The Verge: technology, science and culture coverage, gadget reviews, "
        "breaking news; a publication speaks to its READERS, never \"your team\""
    ),
    "marketplace": (
        "e.g. Airbnb: stays, Hosts, listings, Experiences; Tripadvisor: traveler "
        "reviews, hotels, things to do — speak to GUESTS and HOSTS, not \"your team\""
    ),
    "ecommerce": (
        "e.g. Allbirds: wool runners, tree sneakers, natural materials; Huckberry: "
        "field-tested outdoor gear, exclusive brands — speak to SHOPPERS about the "
        "PRODUCTS, never \"your team\""
    ),
    "fintech": (
        "e.g. Stripe: Billing, Connect, Radar, 135+ currencies; Plaid: Link, Auth, "
        "Balance, Signal, 12,000+ banks"
    ),
    "social": (
        "e.g. a social network: feeds, profiles, communities, sharing — speak to the "
        "PEOPLE who use it, not \"your team\""
    ),
    "services": (
        "e.g. a services brand: bookings, appointments, the result delivered — speak "
        "to CLIENTS, not \"your team\""
    ),
    "dev-tool": (
        "e.g. Stripe: Billing, Connect, Radar, 135+ currencies; Linear: Cycles, "
        "Projects, Triage, keyboard-first; Plaid: Link, Auth, Balance, Signal, "
        "12,000+ banks"
    ),
}


def company_facts_block(facts, company_url=None, genre=None):
    """Format a 'COMPANY FACTS' block to APPEND to the planner USER prompt.

    `facts` is the normalized dict from build_runner._brand_facts:
        {"wordmark": str, "tagline": str, "features": [str, ...]}
    These are the REAL brand facts (curated fixture, else honest brand_extract) so
    the planner writes the voiceover + every scene brief about the ACTUAL product
    instead of inventing a different one (the VO-vs-visual incoherence bug:
    Orinovate, a 3D-print/CNC manufacturer, was getting an "AI insight platform /
    data streams" voiceover while the visual cards correctly showed manufacturing).

    `company_url` is used to name the brand when scraped facts are THIN/EMPTY
    (bot-blocked sites like tripadvisor.com.tw): rather than returning "" and
    leaving the planner to write hollow self-referential filler, we instruct the
    planner to ground on its OWN world-knowledge of that RECOGNIZABLE brand — while
    keeping the hard "never invent a DIFFERENT business" guard. Always returns a
    non-empty block when either facts OR a usable company_url are present.

    `genre` (one of plan_job's genre strings — media/marketplace/ecommerce/fintech/
    social/services/dev-tool) selects GENRE-APPROPRIATE world-knowledge EXAMPLES for
    the thin-scrape enrichment so a non-SaaS brand is not nudged toward SaaS framing.
    None -> the historical SaaS/fintech example list (behavior unchanged for SaaS).
    Stdlib only; never raises.
    """
    if not isinstance(facts, dict):
        facts = {}
    wordmark = (facts.get("wordmark") or "").strip()
    tagline = (facts.get("tagline") or "").strip()
    features = [str(f).strip() for f in (facts.get("features") or []) if str(f).strip()]
    # A truncated meta-description (brand_extract caps at 80 chars and may cut
    # mid-word) is NOT a real tagline — don't feed a mangled fragment to the brain.
    if tagline and tagline.endswith(("…", "...")):
        tagline = ""
    brand_name = wordmark or _brand_from_url(company_url)

    if not (wordmark or tagline or features) and not brand_name:
        return ""  # truly nothing to ground on — graceful fallback unchanged

    lines = ["", "COMPANY FACTS (the REAL product — these are verified, not inferred):"]
    if wordmark:
        lines.append("- Company / wordmark: %s" % wordmark)
    elif brand_name:
        lines.append("- Company / wordmark: %s" % brand_name)
    if tagline:
        lines.append("- Tagline / positioning: %s" % tagline)
    if features:
        lines.append("- Real product features / capabilities:")
        for f in features:
            lines.append("    * %s" % f)

    # THIN-SCRAPE detection. World-knowledge enrichment used to fire ONLY on an EMPTY
    # scrape, so brands with a few low-signal scraped features (Linear, Plaid) skipped
    # it and the planner emitted bare/generic copy (the R2 D3=2 finding). A scrape is
    # THIN when there are <3 features OR the features are all short low-signal tokens
    # (avg < ~3 words) — in that case we ALSO append the world-knowledge instruction
    # on top of whatever facts we do have, so the planner names real features/metrics.
    def _is_thin(feats):
        if len(feats) < 3:
            return True
        avg_words = sum(len(f.split()) for f in feats) / max(1, len(feats))
        return avg_words < 3.0

    thin_scrape = _is_thin(features)

    if features:
        lines.append(
            "Base the voiceover and EVERY scene's brief on THESE real facts. Each "
            "feature beat must highlight ONE of the real features listed above. The "
            "opening title's beat is a FULL value-prop sentence naming a real feature "
            "or metric (NEVER just the bare company name), and the closing CTA names a "
            "concrete next step at the company."
        )

    # Append the world-knowledge instruction on an EMPTY scrape OR a THIN one (few /
    # low-signal facts). For a recognizable brand this is what lifts D3 above 2 — it
    # supplies named features + real-looking numbers the thin scrape lacked.
    if (not features) or thin_scrape:
        who = brand_name or "this company"
        if features:
            preface = (
                "The scraped facts above are THIN — too few or too generic to carry "
                "the whole script. "
            )
        else:
            preface = "Scraping returned few or no facts, but "
        examples = _GENRE_ENRICH_EXAMPLES.get(genre) or _GENRE_ENRICH_EXAMPLES["dev-tool"]
        lines.append(
            "%s%s is a RECOGNIZABLE real company at %s. Use your OWN knowledge of THAT "
            "specific real company to ENRICH the voiceover and scene briefs: name its "
            "REAL products and REAL feature names (%s), the REAL audience it serves, "
            "and real-looking specific numbers. Speak to THAT brand's actual audience "
            "and value — do NOT default to B2B-SaaS \"gives your team\" framing unless "
            "the brand really is a software tool for teams. Write concrete "
            "benefit-driven lines, NOT hollow self-referential filler."
            % (preface, who, (company_url or "its website"), examples)
        )
    lines.append(
        "EVERY voiceover beat — including the OPENING title — MUST be a COMPLETE "
        "value-prop sentence. NEVER emit a single-word or bare-wordmark beat (a beat "
        "that is just \"%s\" or the company name). The opening beat names the company "
        "AND a real capability or metric in one full sentence." % (brand_name or "Brand")
    )
    lines.append(
        "Do NOT invent a DIFFERENT product, market, audience, or business than the "
        "one actually at this URL — that guard is absolute. NEVER describe the "
        "video, the screenshot, the capture, or 'the real site'; describe what the "
        "PRODUCT does for the user."
    )
    return "\n".join(lines) + "\n"


def _brand_from_url(url):
    """Best-effort brand display name from a URL host (public-suffix-naive but good
    enough to name a recognizable brand for the world-knowledge prompt). Returns ""
    when no host is parseable."""
    u = (url or "").lower().replace("https://", "").replace("http://", "").replace("www.", "")
    host = u.split("/")[0].split(".")
    host = [h for h in host if h]
    if not host:
        return ""
    # strip common cc/second-level TLD tails so "tripadvisor.com.tw" -> "tripadvisor"
    tails = {"com", "co", "org", "net", "io", "app", "ai", "tw", "uk", "jp", "de", "fr", "cn"}
    core = [h for h in host if h not in tails]
    name = core[-1] if core else host[0]
    return name.capitalize()


# Output budget for the planner call. A full STANDARD/PREMIUM plan JSON is well
# under ~2.5k tokens, but the Nemotron models (esp. the free 120B Super) emit
# HIDDEN reasoning tokens that ALSO count against this completion budget while
# NEVER appearing in `content`. At the old 8000 cap the 120B's reasoning (observed
# ~8151 tokens) consumed the whole budget -> finish_reason=length -> the JSON was
# truncated mid-object -> parse/repair failed -> the build silently fell back to the
# deterministic template ~2 of 3 times. We now (a) turn reasoning OFF for this
# structured-JSON call (reasoning.effort="none" stops generation and frees the
# budget; exclude=true belt-and-suspenders strips any leaked reasoning from
# `content`), AND (b) raise the cap so even if a model ignores the reasoning hint a
# full plan is never truncated. The two together are what make Super plan reliably.
PLANNER_MAX_TOKENS = 16000


def call_model(messages, brain=None, meta=None):
    """Call the operator-selected planner BRAIN via OpenRouter (OpenAI-compatible).

    `brain` is one of brain.VALID_BRAINS (ultra-paid | super-free | super-paid);
    None / unknown defaults to super-free ($0) so existing callers that pass no
    brain keep today's free behavior. Endpoint + model slug + key all come from the
    brain registry — the call body/response shape are unchanged from the legacy
    build.nvidia.com path.

    `meta`: optional dict the caller passes in; when given it is populated with the
    OpenRouter `finish_reason` and `usage` (prompt/completion/reasoning tokens) so
    the planner can record WHY a build did or did not get an LLM plan and surface
    real token costs in the ledger. The return value (the message content string)
    is unchanged, so existing callers that don't pass `meta` are unaffected.
    """
    bdef = brain_mod.brain_def(brain)
    key = brain_mod.brain_key()
    if not key:
        sys.exit("OPENROUTER_API_KEY not set in environment "
                 "(source ~/.zshrc, or set it in ~/.hermes/.env)")
    payload = {
        "model": bdef["slug"],
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": PLANNER_MAX_TOKENS,
        # Turn reasoning OFF for the structured-JSON planner call. effort="none"
        # tells OpenRouter to stop the model GENERATING reasoning tokens (freeing
        # the completion budget — the root-cause fix for the 120B truncation);
        # exclude=true additionally strips any reasoning the model still emits from
        # `content` so it can't corrupt the JSON we parse. OpenRouter filters
        # unsupported reasoning fields per-model, so this is safe across all 3
        # brains. (See OpenRouter "Reasoning Tokens" guide.)
        "reasoning": {"effort": "none", "exclude": True},
        # Ask OpenRouter to include token accounting in the response so we can log
        # the real prompt/completion/reasoning token counts and dollar cost.
        "usage": {"include": True},
    }
    req = urllib.request.Request(
        brain_mod.brain_endpoint(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            # OpenRouter ranking/attribution headers (optional, harmless).
            "HTTP-Referer": "https://walk.studio",
            "X-Title": "Walk Studio",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    choice = body["choices"][0]
    fr = choice.get("finish_reason")
    usage = body.get("usage")
    if isinstance(meta, dict):
        meta["finish_reason"] = fr
        meta["usage"] = usage
    if fr and fr != "stop":
        print(f"[finish_reason={fr} usage={usage}]", file=sys.stderr)
    return choice["message"]["content"]


def extract_json(text):
    """Strip fences, take first { to last }, return parsed obj or raise."""
    t = text.strip()
    # drop a leading ```json / ``` fence and trailing ```
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    start, end = t.find("{"), t.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in model output")
    return json.loads(t[start : end + 1])


def schema_check(plan, target_duration_s, quality="premium"):
    """Assert the plan matches the fixed contract for the given quality.

    quality="standard": the plan MUST be Remotion-only — ZERO cinematic and ZERO
    walkthrough scenes (only title + motion_graphic). quality="premium": cinematic
    scenes ARE allowed (2-4 required, the historical contract). Default is
    "premium" so the existing live validation run (PREMIUM-equivalent) is unchanged.
    """
    quality = "standard" if str(quality).strip().lower() == "standard" else "premium"
    problems = []
    if set(plan.keys()) != {"job", "scenes", "voiceover"}:
        problems.append(f"top-level keys are {sorted(plan.keys())}, expected job/scenes/voiceover")

    job = plan.get("job", {})
    # Required job keys are fixed; the optional "emphasis" hint (the feature to
    # demonstrate in the STANDARD walkthrough) is tolerated as an extra key.
    if set(job.keys()) - {"emphasis"} != {"company_url", "goal", "target_duration_s", "target_margin", "currency"}:
        problems.append(f"job keys are {sorted(job.keys())}")
    if job.get("currency") != "usd":
        problems.append(f"job.currency={job.get('currency')!r}, expected 'usd'")
    if job.get("target_duration_s") != target_duration_s:
        problems.append(f"job.target_duration_s={job.get('target_duration_s')}, expected {target_duration_s}")

    scenes = plan.get("scenes", [])
    # STANDARD is the real-capture stack (title + screenshot + walkthrough); PREMIUM
    # is the cinematic stack (title + cinematic + motion_graphic). Gate the allowed
    # types on quality so each path only emits the scene types its stack renders.
    if quality == "standard":
        allowed_types = {"title", "screenshot", "walkthrough"}
    else:
        allowed_types = {"title", "cinematic", "motion_graphic"}
    if not scenes:
        problems.append("scenes is empty")
    else:
        for i, s in enumerate(scenes):
            if set(s.keys()) != {"id", "type", "brief", "model", "duration_s", "input_image"}:
                problems.append(f"scene[{i}] keys are {sorted(s.keys())}")
            if s.get("type") not in allowed_types:
                problems.append(f"scene[{i}].type={s.get('type')!r} not allowed")
            if s.get("input_image") is not None:
                problems.append(f"scene[{i}].input_image should be null")
        if scenes[0].get("type") != "title":
            problems.append("first scene is not title")
        if scenes[-1].get("type") != "title":
            problems.append("last scene is not title")
        n_walk = sum(1 for s in scenes if s.get("type") == "walkthrough")
        n_shot = sum(1 for s in scenes if s.get("type") == "screenshot")
        n_cine = sum(1 for s in scenes if s.get("type") == "cinematic")
        if quality == "standard":
            # STANDARD is the real-capture stack: title -> 1-2 screenshot ->
            # walkthrough -> title. NO cinematic / motion_graphic; EXACTLY one
            # walkthrough and at least one screenshot.
            if n_cine != 0:
                problems.append(f"cinematic count={n_cine}, expected 0 for STANDARD (real-capture: title + screenshot + walkthrough)")
            if n_shot < 1:
                problems.append(f"screenshot count={n_shot}, expected >=1 for STANDARD (the captured site views)")
            if n_walk != 1:
                problems.append(f"walkthrough count={n_walk}, expected exactly 1 for STANDARD (the guided demo)")
        else:
            # PREMIUM is cinematic-only and RETIRES the walkthrough/screenshot types.
            if n_walk != 0:
                problems.append(f"walkthrough count={n_walk}, expected 0 for PREMIUM (cinematic stack only)")
            if n_shot != 0:
                problems.append(f"screenshot count={n_shot}, expected 0 for PREMIUM (cinematic stack only)")
            # PREMIUM REQUIRES >= 2 cinematic (a seedance establishing shot + a
            # gpt/seedance hero shot); 4 is the historical upper bound on cinematic
            # scenes. Zero cinematic means premium is indistinguishable from standard.
            if n_cine < 2:
                problems.append(f"cinematic count={n_cine}, expected >=2 for PREMIUM (cinematic establishing + hero shots required)")
            elif n_cine > 4:
                problems.append(f"cinematic count={n_cine}, expected <=4")
        for s in scenes:
            if s.get("type") == "cinematic" and s.get("model") not in {"seedance_2_0", "gpt_image_2"}:
                problems.append(f"cinematic scene {s.get('id')!r} model={s.get('model')!r} invalid")
            if s.get("type") in {"title", "motion_graphic", "screenshot", "walkthrough"} and s.get("model") is not None:
                problems.append(f"{s.get('type')} scene {s.get('id')!r} model should be null")
        total = sum(int(s.get("duration_s", 0)) for s in scenes)
        if total != target_duration_s:
            problems.append(f"durations sum to {total}, expected {target_duration_s}")

    vo = plan.get("voiceover", {})
    if vo.get("voice") != "Adam":
        problems.append(f"voiceover.voice={vo.get('voice')!r}, expected 'Adam'")
    # Scene-aligned schema: voiceover.beats = one {scene_id, text} per scene.
    beats = vo.get("beats")
    extra_keys = set(vo.keys()) - {"beats", "voice", "script"}
    if extra_keys:
        problems.append(f"voiceover has unexpected keys {sorted(extra_keys)}")
    if not isinstance(beats, list) or not beats:
        problems.append("voiceover.beats must be a non-empty array of {scene_id, text}")
    else:
        scene_ids = {s.get("id") for s in scenes}
        non_title_ids = {s.get("id") for s in scenes if s.get("type") != "title"} or scene_ids
        beat_scene_ids = []
        for j, b in enumerate(beats):
            if set(b.keys()) != {"scene_id", "text"}:
                problems.append(f"voiceover.beats[{j}] keys are {sorted(b.keys())}, expected scene_id/text")
            if b.get("scene_id") not in scene_ids:
                problems.append(f"voiceover.beats[{j}].scene_id={b.get('scene_id')!r} is not a scene id")
            if not (b.get("text") or "").strip():
                problems.append(f"voiceover.beats[{j}].text is empty")
            beat_scene_ids.append(b.get("scene_id"))
        # Every content (non-title) scene should be narrated; title cards may be
        # silent, but a beat per content scene is the contract that fixes drift.
        missing = non_title_ids - set(beat_scene_ids)
        if missing:
            problems.append(f"voiceover.beats missing a beat for scenes {sorted(missing)}")
    return problems


def main():
    # main() validates the PREMIUM path (schema_check defaults to premium), so send
    # the same base + premium guidance the production pipeline sends.
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT + PREMIUM_QUALITY_GUIDANCE},
        {"role": "user", "content": USER_PROMPT},
    ]
    raw = call_model(messages)
    first_try_ok = True
    try:
        plan = extract_json(raw)
    except (ValueError, json.JSONDecodeError) as e:
        first_try_ok = False
        print(f"[first attempt did not parse: {e}] -> one repair retry", file=sys.stderr)
        repair = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "Your previous output did not parse as JSON. Return ONLY the corrected JSON object, nothing else."},
        ]
        raw2 = call_model(repair)
        plan = extract_json(raw2)  # let it raise if still bad

    with open(OUT, "w") as f:
        json.dump(plan, f, indent=2)

    problems = schema_check(plan, BRIEF["target_duration_s"])

    print(f"FIRST_TRY_VALID_JSON={first_try_ok}")
    print(f"SCHEMA_OK={not problems}")
    if problems:
        print("SCHEMA_PROBLEMS:")
        for p in problems:
            print(f"  - {p}")
    print("---SCENE SUMMARY---")
    for s in plan["scenes"]:
        print(f"  {s['id']:<26} {s['type']:<14} {s['duration_s']:>2}s  model={s['model']}")
    total = sum(int(s["duration_s"]) for s in plan["scenes"])
    print(f"  TOTAL = {total}s (target {BRIEF['target_duration_s']}s)")
    # Scene-aligned schema: voiceover carries per-scene "beats", not a single "script".
    vo = plan.get("voiceover", {})
    beats = vo.get("beats") or []
    wc = sum(len((b.get("text") or "").split()) for b in beats)
    print(f"  voiceover: {len(beats)} beats, {wc} words, voice={vo.get('voice')!r}")
    print(f"  saved -> {OUT}")
    sys.exit(0 if (first_try_ok and not problems) or not problems else 2)


if __name__ == "__main__":
    main()
