#!/usr/bin/env python3
"""URL + goal -> a validated scene plan. The "agent decides the storyboard" step.

Calls the free Nemotron planner (reusing validate_planner's prompt) to decompose a
brief into a scene plan, validates it against the schema, and returns it. Falls back
to a deterministic template plan if Nemotron is unavailable, so the live console can
always proceed. Stdlib only.
"""

import json
import os
import re
import sys

import validate_planner as vp
import brain as brain_mod
from plan_schema import validate_plan

# --- Style differentiation -------------------------------------------------
# The three user-facing styles control the OUTPUT (scene count / hold durations /
# cut rhythm), NOT just console pacing. `standard` is the historical default and
# MUST leave the planner prompt and the plan untouched so today's exact output is
# reproduced. `snappy` and `cinematic` add real variation.
VALID_STYLES = ("snappy", "standard", "cinematic")

# Extra guidance appended to the planner SYSTEM_PROMPT per style. `target_duration_s`
# stays constant (total ~30s) — only the number of scenes and the per-scene holds
# change. standard injects nothing (None).
_STYLE_PROMPT = {
    "snappy": (
        "\n\nSTYLE: SNAPPY. Cut fast and keep energy high. Favour MORE scenes with "
        "SHORTER holds: aim for 6-8 scenes total, most non-title holds around 2-4 "
        "seconds. Include the optional motion_graphic scene (a quick divider or stat "
        "card) to add a cut. The durations must "
        "still sum to EXACTLY target_duration_s."
    ),
    "cinematic": (
        "\n\nSTYLE: CINEMATIC. Let shots breathe. Favour FEWER scenes with LONGER "
        "holds: aim for 4-5 scenes total, non-title holds around 6-9 seconds. Skip "
        "the optional motion_graphic. For the cinematic scenes prefer the "
        "\"seedance_2_0\" model (motion plates) over still \"gpt_image_2\" so the "
        "footage moves. The durations must still sum to EXACTLY target_duration_s."
    ),
    "standard": None,
}

# --- Quality differentiation -----------------------------------------------
# QUALITY ("standard" | "premium") is the upfront cost-plus choice. It is
# ORTHOGONAL to STYLE (which only sets pacing/scene-count/holds) and it gates the
# ALLOWED SCENE TYPES at PLAN time, so the storyboard the customer sees matches the
# stack that will actually produce it:
#   - STANDARD => Remotion-renderable scenes ONLY: "title" + "motion_graphic".
#                 NO cinematic (no seedance_2_0 / gpt_image_2), NO walkthrough.
#   - PREMIUM  => cinematic establishing/hero shots allowed (today's behavior).
# This fixes the bug where a Standard shot list still listed Seedance / GPT-image
# cinematic scenes that the Standard produce stack would never render.
VALID_QUALITIES = ("standard", "premium")

# Appended to the planner SYSTEM_PROMPT per quality, AFTER the style guidance.
# premium REQUIRES cinematic (>=2) so the plan actually uses Higgsfield footage and
# is visibly different from standard; standard forbids cinematic (Remotion-only).
_QUALITY_PROMPT = {
    "standard": (
        "\n\nQUALITY: STANDARD (Remotion + real site capture). For THIS plan you may "
        "use the scene types \"title\", \"screenshot\", \"walkthrough\", and "
        "\"motion_graphic\" (kinetic animated text/stat/figure cards, rendered by "
        "Remotion at $0). USE at least one \"motion_graphic\" scene for fancy animated "
        "visual energy. Do "
        "NOT plan any \"cinematic\" scene and do NOT use the models \"seedance_2_0\" "
        "or \"gpt_image_2\" — there is NO Higgsfield/AI-footage stage in a standard "
        "build. OVERRIDE structure rule 2 and the no-walkthrough rule. A STANDARD plan "
        "has EXACTLY this shape, in order:\n"
        "  1. an opening \"title\" card (the brand lockup),\n"
        "  2. ONE or TWO \"screenshot\" scenes (model null) — each is a real captured "
        "view of the company's website shown in a branded browser card; the first is "
        "the homepage, an optional second is a key inner page,\n"
        "  3. ONE \"walkthrough\" scene (model null) — a guided, multi-step screen "
        "demonstration of the emphasized feature (a recorded product tour),\n"
        "  4. a closing \"title\" CTA.\n"
        "Every scene's model is null. Keep the durations summing to EXACTLY "
        "target_duration_s. \"motion_graphic\" scenes ARE allowed and encouraged "
        "(Remotion, $0) for animated energy; do NOT emit \"cinematic\" scenes (no "
        "Higgsfield in a standard build).\n"
        "COPY (this is the load-bearing part): every voiceover beat must be GROUNDED "
        "and CONCRETE about the REAL product — name a REAL feature, the REAL audience, "
        "or a real benefit with a real-looking specific number. NEVER write hollow, "
        "self-referential filler that describes the website or the video instead of "
        "the product. These exact lines (and close paraphrases) are BANNED: \"This is "
        "<Brand> — straight from the real site.\", \"Here is the product, exactly as "
        "you would see it.\", \"See the product in action, step by step.\", \"See how "
        "to use the …\". Write the screenshot/walkthrough beats as benefit-driven "
        "lines naming the REAL capability on screen (e.g. \"Accept payments in 135+ "
        "currencies.\", \"Read millions of real traveler reviews before you book.\"). "
        "Use tight IMPERATIVE couplets where the line is short, like the reference "
        "films (\"Clock in. / Cash out.\"). RHYTHM: keep every beat TIGHT — one crisp "
        "idea, AT MOST one comma, never a comma-chained run-on of three or more "
        "clauses (e.g. NOT \"Pick your destination, compare hotel prices, read "
        "verified reviews, and book your stay—all in a few taps…\"). When a beat "
        "needs two ideas, split it into a SETUP -> PAYOFF of two short sentences "
        "(\"Compare every hotel. Book the best one.\") — never one breathless line. "
        "Hard cap ~16 words per beat; if longer, split or cut a clause. If the "
        "COMPANY FACTS are thin but the "
        "brand is recognizable, use your own knowledge of that REAL company — never go "
        "hollow. THE OPENING BEAT IS LOAD-BEARING: the first scene's voiceover beat "
        "MUST be a COMPLETE value-prop sentence that names the company AND a real, "
        "named feature or a real-looking metric (e.g. \"Linear is the issue tracker "
        "built for fast product teams.\", \"Plaid connects your app to over 12,000 "
        "banks.\"). NEVER make the opening beat a bare wordmark or single word "
        "(\"Linear.\", \"Plaid.\") — a one- or two-word opening beat is an automatic "
        "FAIL. Every beat is a full sentence; the wordmark lives on the title card as "
        "a visual, not as the spoken line."
    ),
    "premium": (
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
    ),
}

# --- House style (Luceo Studio signature) ----------------------------------
# Distilled from Dennis's published Luceo Studio films (research/CURATED-DESIGN-
# LIBRARY.md): the kinetic-light flagship arc + pacing budgets + imperative-couplet
# VO rhythm. Injected into the planner SYSTEM_PROMPT so EVERY plan is biased toward
# the studio's signature instead of a generic SaaS template. Craft = the studio's;
# palette = always the customer's own brand. Toggle off with HERMES_HOUSE_STYLE=0.
_HOUSE_STYLE = (
    "\n\nHOUSE STYLE (Luceo Studio signature — bias every plan toward this):\n"
    "This studio has a recognizable signature distilled from its published films "
    "(Orinovate, iKala, Webduino, Kuli, TapPay). Shape the plan to match it:\n"
    "- ARC: cold-open brand title -> 3 to 4 punchy feature beats (ONE hero statement + "
    "ONE concrete product element per beat) -> a closing CTA title naming the real next "
    "step. Exactly ONE big idea per scene — never two.\n"
    "- PACING: no scene longer than 9s; 4 to 7 content beats; every beat earns its hold. "
    "Kinetic and readable — fast but never rushed.\n"
    "- VO RHYTHM (kinetic typography): prefer tight IMPERATIVE COUPLETS built from the "
    "product's REAL verb-objects, like the studio's films (\"Clock in. / Cash out.\", "
    "\"One screen. / Whole crew.\", \"Book the stay. / Skip the guesswork.\"). Lead with "
    "a verb, name the real thing, land the payoff. When a beat needs two ideas, split it "
    "SETUP -> PAYOFF across two short sentences — never one breathless run-on.\n"
    "- DISPLAY TEXT: hero titles are short and bold; accent the single punch word or "
    "number; NO trailing period on the on-screen title text itself.\n"
    "- SUBSTANCE: one real, NAMED feature per beat; concrete nouns and real-looking "
    "specific numbers over buzzwords (\"powerful\", \"seamless\", \"next-generation\")."
)

# --- House templates (per-genre look selection) -----------------------------
# Maps the target company's detected genre -> the Luceo named template whose arc best
# fits it (research/CURATED-DESIGN-LIBRARY.md §2). The look is RENDERED by style_fill;
# only `orinovate-kinetic-light` has a wired render theme today, so selection is CLAMPED
# to _WIRED_TEMPLATES to avoid a plan/render mismatch (don't tell the model to plan a
# dark aurora-glass arc the renderer can't produce). To activate a new template: wire its
# theme in style_fill.py, add it to _WIRED_TEMPLATES, and it auto-selects for its genres.
_HOUSE_TEMPLATES = {
    "dev-tool":    "orinovate-kinetic-light",
    "services":    "orinovate-kinetic-light",
    "media":       "orinovate-kinetic-light",
    "marketplace": "orinovate-kinetic-light",
    "ecommerce":   "apple-style",      # product-as-hero (render theme not wired yet)
    "fintech":     "zelios-aurora",    # premium aurora+glass (render theme not wired yet)
    "social":      "zelios-aurora",    # consumer-facing, cinematic (not wired yet)
}
_DEFAULT_TEMPLATE = "orinovate-kinetic-light"
# Only templates whose style_fill render theme exists may actually be selected.
_WIRED_TEMPLATES = {"orinovate-kinetic-light"}


def pick_house_style(genre):
    """Pick the Luceo named template for a company's genre, clamped to wired themes.

    Returns a template name from _HOUSE_TEMPLATES, but only if its render theme is
    wired in style_fill (else falls back to the wired default) so the plan never
    describes a look the renderer can't produce. Returns the default for None/unknown."""
    want = _HOUSE_TEMPLATES.get((genre or "").strip().lower(), _DEFAULT_TEMPLATE)
    return want if want in _WIRED_TEMPLATES else _DEFAULT_TEMPLATE


def _fewshot_block(quality):
    """One of Dennis's curated plans as a few-shot DEMONSTRATION, so the small model
    learns scene-count, imperative-couplet beat rhythm, and CTA phrasing by example.

    Standard-shape exemplar only (a premium plan looks different, so it would mislead a
    premium build). Returns "" if disabled or the file is missing. Toggle: HERMES_FEWSHOT=0."""
    if os.environ.get("HERMES_FEWSHOT", "1") == "0":
        return ""
    if _normalize_quality(quality) != "standard":
        return ""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "exemplars", "orinovate-kinetic.plan.json")
    try:
        with open(path) as f:
            ex = f.read().strip()
    except OSError:
        return ""
    return (
        "\n\nEXAMPLE — a Luceo Studio plan in the studio's signature. Match its shape: the "
        "scene count and arc (title -> screenshots -> walkthrough -> motion_graphic -> CTA "
        "title), the tight imperative-couplet beats, and the CTA that names the real next "
        "step. Do NOT copy its company, its features, or its wording — produce the SAME "
        "CRAFT for the brief's REAL company and its REAL features:\n" + ex)


def _normalize_quality(quality):
    q = str(quality or "").strip().lower()
    return q if q in VALID_QUALITIES else "standard"


def plan_job(company_url, goal, target_duration_s=30, target_margin=0.6,
             currency="usd", style="standard", quality="standard",
             brain="super-free", company_facts=None, emphasis=None,
             conversion_read=None):
    style = style if style in VALID_STYLES else "standard"
    quality = _normalize_quality(quality)
    # BRAIN: the operator-chosen planner LLM (all via OpenRouter). Defaults to
    # super-free ($0) so nothing bills unless the operator deliberately picks a paid
    # brain. Orthogonal to style/quality; only changes WHICH LLM plans the storyboard.
    brain = brain_mod.normalize_brain(brain)
    # COMPANY FACTS: the REAL brand facts (wordmark/tagline/features) resolved by the
    # caller (build_runner) from the curated fixture or brand_extract. Threaded into
    # the planner USER prompt so the voiceover + scene briefs describe the ACTUAL
    # product instead of an invented one (the VO-vs-visual incoherence fix). None /
    # empty => the prompt block is omitted and planning is unchanged.
    # BRAND NAME: prefer the already-resolved brand name from company_facts (which is
    # public-suffix-aware via brand_extract) over re-parsing the URL. This fixes ccTLD
    # sites (e.g. tripadvisor.com.tw) where _brand_name(url) returns "Com" instead of
    # "Tripadvisor". Fall back to _brand_name() when company_facts is absent.
    _wm = (company_facts or {}).get("wordmark", "").strip() if company_facts else ""
    _resolved_brand = _wm if _wm and _wm.lower() != "the product" else _brand_name(company_url)
    emphasis = (emphasis or "").strip()
    # Planner-call telemetry. _plan_with_nemotron populates this with finish_reason,
    # token usage, and a `reason` string. We use it to (a) stamp plan_source on the
    # plan so EVERY build plainly shows whether the real LLM planned it or it fell
    # back to the deterministic template, and (b) emit a clear log line on fallback
    # so a template build is NEVER silent. This is what lets Dennis trust that
    # "testing on Super" actually exercised the 120B and not a canned template.
    planner_meta = {}
    plan = _plan_with_nemotron(company_url, goal, target_duration_s, style, quality,
                               brain, company_facts, meta=planner_meta,
                               conversion_read=conversion_read)
    plan_source = "llm"
    if plan is None:
        plan_source = "template"
        reason = planner_meta.get("reason") or "error"
        fr = planner_meta.get("finish_reason")
        print(
            "[planner] brain=%s LLM plan UNAVAILABLE (reason=%s finish_reason=%s) "
            "-> FALLING BACK to deterministic template plan. This build was NOT "
            "planned by the LLM." % (brain, reason, fr),
            file=sys.stderr,
        )
        plan = _template_plan(company_url, goal, target_duration_s, style, quality,
                              brand=_resolved_brand, emphasis=emphasis,
                              company_facts=company_facts)
    else:
        print("[planner] brain=%s LLM plan OK (finish_reason=%s usage=%s)"
              % (brain, planner_meta.get("finish_reason"), planner_meta.get("usage")),
              file=sys.stderr)
    # force the brief fields so the rest of the pipeline is consistent. emphasis +
    # the resolved wordmark are stamped onto job BEFORE _enforce_quality so the
    # STANDARD structure backstop can name the emphasized feature in the walkthrough
    # goal and use the real brand name. emphasis is NOT a frozen-schema job key (it's
    # an internal hint), so the schema validators ignore it.
    plan.setdefault("job", {})
    plan["job"].update({"company_url": company_url, "goal": goal,
                        "target_duration_s": target_duration_s,
                        "target_margin": target_margin, "currency": currency,
                        "emphasis": emphasis, "_wordmark": _resolved_brand})
    # Deterministic quality guard. STANDARD: force the real-capture structure (title
    # -> 1-2 screenshot -> walkthrough -> title). PREMIUM: guarantee >= 2 cinematic by
    # upgrading feature beats if the live model under-delivered. Runs even when the
    # model ignored the prompt.
    plan = _enforce_quality(plan, quality)
    # If PREMIUM still lacks >= 2 cinematic (too few non-title scenes to upgrade),
    # fall back to the deterministic premium template, which always has cinematic.
    if quality == "premium":
        n_cine = sum(1 for s in (plan.get("scenes") or [])
                     if isinstance(s, dict) and s.get("type") == "cinematic")
        if n_cine < 2:
            if plan_source == "llm":
                plan_source = "template"
                print("[planner] brain=%s PREMIUM LLM plan had <2 cinematic scenes "
                      "-> FALLING BACK to deterministic premium template." % brain,
                      file=sys.stderr)
            plan = _template_plan(company_url, goal, target_duration_s, style, quality,
                                  brand=_resolved_brand)
            plan["job"].update({"company_url": company_url, "goal": goal,
                                "target_duration_s": target_duration_s,
                                "target_margin": target_margin, "currency": currency})
    # Deterministic backstop: redistribute the FIXED duration per style so the
    # rhythm differs even when the LLM ignores the prompt guidance. No-op for
    # standard (and for any plan that already matches the target shape closely).
    plan = _restyle_durations(plan, style, target_duration_s)
    # Deterministic stage-direction backstop (runs for BOTH the LLM and template
    # paths): rewrite any VO beat that is an INSTRUCTION / STAGE DIRECTION rather than
    # spoken copy. Small planners leak the scene BRIEF or a prompt fragment into the
    # beat text — e.g. notion's "Show call-to-action: 'Start" rendered as a VO line.
    # A stage direction is NEVER something a narrator says; replace it with a grounded
    # value-prop / CTA line for THIS brand. Runs BEFORE the bare-wordmark pass so a
    # rewrite that still reads thin is caught there too.
    plan = _degut_stage_direction_beats(plan, _resolved_brand, company_url,
                                        company_facts, emphasis)
    # Deterministic grounding backstop (runs for BOTH the LLM and template paths):
    # rewrite any VO beat that is just the brand name or a fragment into a full
    # value-prop sentence. Small planners (and the legacy template) emit a bare
    # "Linear." / "Plaid." opening beat — the D3=2 thin-grounding bug — even when the
    # body beats are grounded. Use _resolved_brand + company_facts so the rewrite
    # names a real feature/metric (world-knowledge first, then scraped features).
    plan = _degut_bare_wordmark_beats(plan, _resolved_brand, company_url,
                                      company_facts, emphasis)
    # CONVERSION READ seeding backstop: guarantee the diagnosed top fixes appear as
    # beats and the headline_fix opens the video, even if the LLM/template dropped
    # them. No-op when conversion_read is None (flag off) -> behavior unchanged.
    plan = seed_plan_with_read(plan, conversion_read)
    # Drop the internal-only `_wordmark` hint before validation/return — `emphasis`
    # stays (a recognized optional job key), but `_wordmark` is a private plumbing
    # field that must not leak into the persisted plan or the strict planner schema.
    (plan.get("job") or {}).pop("_wordmark", None)
    problems = validate_plan(plan)
    if problems:
        if plan_source == "llm":
            plan_source = "template"
            print("[planner] brain=%s LLM plan FAILED final validation (%s) "
                  "-> FALLING BACK to deterministic template." % (brain, "; ".join(problems)),
                  file=sys.stderr)
        # one more chance on the deterministic template before giving up
        plan = _template_plan(company_url, goal, target_duration_s, style, quality,
                              brand=_resolved_brand, emphasis=emphasis,
                              company_facts=company_facts)
        plan["job"].update({"target_margin": target_margin, "currency": currency,
                            "emphasis": emphasis})
        problems = validate_plan(plan)
        if problems:
            raise ValueError("planner produced an invalid plan: " + "; ".join(problems))
    # Stamp planner provenance on the plan so the ledger/console can show EVERY build
    # plainly as LLM-planned or template-fallback (with finish_reason + token usage).
    # build_runner reads plan["_planner"] into ledger selection. Not a frozen-schema
    # key on `job`/`scenes`/`voiceover`, so the strict planner schema is unaffected;
    # build_runner persists it under plan["selection"] for the dashboard.
    plan["_planner"] = {
        "plan_source": plan_source,
        "brain": brain,
        "finish_reason": planner_meta.get("finish_reason"),
        "reason": planner_meta.get("reason") or ("ok" if plan_source == "llm" else "fallback"),
        "usage": planner_meta.get("usage"),
    }
    return plan


def _enforce_quality(plan, quality):
    """Deterministically make the plan match its quality tier (defense-in-depth).

    The SYSTEM_PROMPT + _QUALITY_PROMPT already steer the model, but small models
    drift, so this guarantees the contract no matter what the LLM returns:

    - STANDARD: GUARANTEE the Standard structure (the same defense-in-depth idea as
      the premium upgrade backstop) — opening title -> 1-2 screenshot scenes -> one
      walkthrough scene -> closing title. Stray cinematic/motion_graphic content
      scenes are RE-TYPED into that shape (the first becomes a screenshot, the next a
      walkthrough); a plan that already has screenshot/walkthrough scenes is left
      alone. If the model produced no usable content scenes, deterministic ones are
      synthesized so a Standard plan ALWAYS carries the real-capture pillars.
    - PREMIUM: GUARANTEE at least 2 cinematic scenes. If the model under-delivers
      (returns < 2 cinematic — the live-Nemotron bug), upgrade enough non-title
      feature beats (preferring motion_graphic, then any non-title) to cinematic so
      premium always has its establishing + hero shots. The first upgraded scene gets
      "seedance_2_0" (establishing/motion), the second "gpt_image_2" (hero still).
      Walkthrough scenes (which should never appear) are upgraded/normalized to
      cinematic here rather than dropped.

    Scene ids, order, durations, briefs, and voiceover beats are always preserved;
    only `type` and `model` are rewritten.
    """
    q = _normalize_quality(quality)
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    if q == "standard":
        return _enforce_standard_structure(plan, scenes)

    # PREMIUM: ensure >= 2 cinematic scenes with valid Higgsfield models.
    # First, normalize any stray walkthrough to cinematic (walkthrough is retired).
    for s in scenes:
        if s.get("type") == "walkthrough":
            s["type"] = "cinematic"
    # Fix any cinematic scene missing a valid model before counting.
    for s in scenes:
        if s.get("type") == "cinematic" and s.get("model") not in ("seedance_2_0", "gpt_image_2"):
            s["model"] = "seedance_2_0"

    cine = [s for s in scenes if s.get("type") == "cinematic"]
    if len(cine) >= 2:
        return plan

    # Under-delivered: upgrade feature beats to cinematic. Prefer motion_graphic
    # scenes (the model's "feature beats"); fall back to any non-title scene. Never
    # touch the opening/closing title cards. Preserve id, brief, duration; set type +
    # model. Assign seedance_2_0 (establishing/motion) then gpt_image_2 (hero still).
    need = 2 - len(cine)
    upgrade_models = ["seedance_2_0", "gpt_image_2"][len(cine):2]
    candidates = [s for s in scenes if s.get("type") == "motion_graphic"]
    if len(candidates) < need:
        candidates += [s for s in scenes if s.get("type") not in ("title", "cinematic", "motion_graphic")]
    for s, model in zip(candidates[:need], upgrade_models):
        s["type"] = "cinematic"
        s["model"] = model
    return plan


def _walkthrough_brief_for_emphasis(brand, emphasis):
    """A SPECIFIC, multi-step walkthrough goal from the emphasis input.

    A vague goal makes walk-agent loop on one nav link (the P2 failure: 13x "Click
    Pricing"). Naming the feature AND demanding 2-3 distinct steps gives the agent a
    concrete target to reach. When no emphasis is supplied, fall back to a generic
    but still multi-step product tour so the goal is never a one-link loop.
    """
    emphasis = (emphasis or "").strip()
    if emphasis:
        # Use the emphasis phrase verbatim (it may already read "the pricing page" /
        # "instant quoting") — don't wrap it in "the ... feature of {brand}", which
        # produced ungrammatical "the the pricing page feature" double-articles.
        return ("From the homepage, navigate to and demonstrate %s, showing 2-3 "
                "distinct steps." % emphasis)
    return ("From the homepage, take a short guided tour of %s, showing 2-3 distinct "
            "steps through its core product flow." % brand)


def seed_plan_with_read(plan, conversion_read):
    """Deterministic backstop that GUARANTEES the Conversion Read's top prescriptions
    appear in the plan, even when the LLM silently dropped them:
      - headline_fix -> the OPENING title scene's voiceover beat text (the outcome-led
        hero line the Read prescribes).
      - the top priority_fixes -> directed into the content scenes' briefs (and a
        marker in the matching beat) so each diagnosed fix maps to a beat the producer
        will shoot. Mapping is by `maps_to`: a 'proof'/'show' fix targets the
        screenshot/walkthrough beats (the real-capture pillars that BEAT AI-film
        rivals); a 'cta' fix targets the CLOSING title.

    Mutates + returns `plan`. No-op when conversion_read is falsy. Never raises."""
    if not isinstance(conversion_read, dict):
        return plan
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    vo = plan.get("voiceover") or {}
    beats = vo.get("beats")
    if not isinstance(beats, list):
        beats = []
        vo["beats"] = beats
        plan["voiceover"] = vo
    beat_by_id = {b.get("scene_id"): b for b in beats if isinstance(b, dict)}

    titles = [s for s in scenes if s.get("type") == "title"]
    opening = titles[0] if titles else (scenes[0] if scenes else None)
    closing = titles[-1] if len(titles) >= 2 else None
    content = [s for s in scenes if s.get("type") in ("screenshot", "walkthrough")]

    # 1) headline_fix -> opening title beat text (the diagnosis's outcome-led open).
    hf = (conversion_read.get("headline_fix") or "").strip()
    if hf and opening is not None:
        sid = opening.get("id")
        b = beat_by_id.get(sid)
        if b is None:
            b = {"scene_id": sid, "text": hf}
            beats.insert(0, b)
            beat_by_id[sid] = b
        else:
            b["text"] = hf

    # 2) priority_fixes -> directed beats. Append the fix to the target scene's brief
    # and mark its beat so the prescription is shot. Targeting by maps_to keyword.
    def _target_for(maps_to):
        mt = (maps_to or "").lower()
        if "cta" in mt and closing is not None:
            return closing
        if ("proof" in mt or "show" in mt) and content:
            # prefer the walkthrough (the strongest 'show' surface), else a screenshot
            walk = [s for s in content if s.get("type") == "walkthrough"]
            return (walk or content)[0]
        return content[0] if content else (opening if opening is not None else None)

    for f in (conversion_read.get("priority_fixes") or []):
        if not isinstance(f, dict):
            continue
        fix = (f.get("fix") or "").strip()
        if not fix:
            continue
        tgt = _target_for(f.get("maps_to"))
        if tgt is None:
            continue
        prior = (tgt.get("brief") or "").strip()
        tgt["brief"] = (prior + " " if prior else "") + ("CONVERSION FIX: %s" % fix)
        # NOTE: the raw `fix` is an EDITORIAL meta-instruction (e.g.
        # "CONVERSION FIX: Replace dual hero CTAs with one 'Start free' button.")
        # — it belongs ONLY in the producer-facing scene BRIEF above, NEVER in the
        # spoken voiceover. Injecting it into the beat text made the narrator read
        # imperative stage directions aloud. The grounded OUTCOME/proof reaches the
        # VO through headline_fix (opening beat) + the producer's grounded VO pass,
        # so we deliberately do NOT push `fix` into any spoken beat here.
    return plan


def _enforce_standard_structure(plan, scenes):
    """Deterministically force the Standard shape: title -> 1-2 screenshot ->
    walkthrough -> title (model null everywhere). Defense-in-depth so a STANDARD
    plan ALWAYS carries the real-capture pillars regardless of what the LLM returned.

    Strategy (preserve ids/durations/order where possible):
      - Title scenes keep type "title" / model null.
      - Existing screenshot/walkthrough content scenes are kept as-is (model null).
      - Stray content scenes (cinematic / motion_graphic / other) are RE-TYPED to
        fill any missing pillar: the first available becomes a "screenshot", the next
        a "walkthrough"; any remaining stray content scenes also become screenshots
        (so nothing is left as an unrenderable cinematic/motion_graphic).
      - If the plan has NO content scene at all to host a walkthrough, one is
        synthesized between the title cards (rare; only when the LLM emitted a
        title-only plan).
    The walkthrough scene's brief is rewritten to the emphasis-specific multi-step
    goal so capture has a concrete target.
    """
    job = plan.get("job") or {}
    brand = _brand_name(job.get("company_url"))
    _wm = (job.get("_wordmark") or "").strip()
    if _wm and _wm.lower() != "the product":
        brand = _wm
    emphasis = job.get("emphasis")

    content = [s for s in scenes if s.get("type") != "title"]
    has_walk = any(s.get("type") == "walkthrough" for s in content)
    has_shot = any(s.get("type") == "screenshot" for s in content)

    # Re-type stray content scenes (cinematic / motion_graphic / unknown) into the
    # missing pillars, in scene order.
    stray = [s for s in content if s.get("type") not in ("screenshot", "walkthrough")]
    if not has_shot and stray:
        s = stray.pop(0)
        s["type"] = "screenshot"
        s["model"] = None
        has_shot = True
    if not has_walk and stray:
        s = stray.pop(0)
        s["type"] = "walkthrough"
        s["model"] = None
        has_walk = True
    # Anything still stray becomes an extra screenshot (never leave a cinematic/
    # motion_graphic in a Standard plan).
    for s in stray:
        s["type"] = "screenshot"
        s["model"] = None
    # Normalize models on the kept pillars.
    for s in content:
        if s.get("type") in ("screenshot", "walkthrough"):
            s["model"] = None

    # If no walkthrough could be sourced from existing scenes, synthesize one and
    # insert it just before the closing title (or at the end if no closing title).
    if not has_walk:
        wt = {"id": "walkthrough", "type": "walkthrough",
              "brief": "", "model": None,
              "duration_s": 8, "input_image": None}
        all_scenes = plan.get("scenes") or []
        insert_at = len(all_scenes)
        for i in range(len(all_scenes) - 1, -1, -1):
            if isinstance(all_scenes[i], dict) and all_scenes[i].get("type") == "title":
                insert_at = i
                break
        all_scenes.insert(insert_at, wt)
        plan["scenes"] = all_scenes
        content.append(wt)
        # rebalance: steal a couple seconds from the longest non-title scene so the
        # total still sums to target (the duration backstop also re-checks below).
        donors = sorted((s for s in all_scenes if isinstance(s, dict)
                         and s.get("type") == "title" or s.get("type") == "screenshot"),
                        key=lambda s: int(s.get("duration_s", 2)), reverse=True)
        steal = wt["duration_s"]
        for d in donors:
            if steal <= 0:
                break
            give = min(steal, max(0, int(d.get("duration_s", 2)) - 2))
            d["duration_s"] = int(d.get("duration_s", 2)) - give
            steal -= give

    # Rewrite the walkthrough brief to the emphasis-specific multi-step goal.
    for s in content:
        if s.get("type") == "walkthrough":
            s["brief"] = _walkthrough_brief_for_emphasis(brand, emphasis)
    return plan


def _restyle_durations(plan, style, target_duration_s):
    """Deterministic re-timer: redistribute the fixed total across scenes per style.

    Keeps the scene LIST as the planner decided it (count, types, order, models,
    voiceover) and only rewrites `duration_s` so the total still equals
    target_duration_s while the per-scene holds reflect the style:
      - snappy   : compress non-title holds toward a SHORT floor (punchier cuts)
      - cinematic: expand non-title holds toward a LONG target (slower, breathing)
      - standard : identity — return the plan untouched (safety invariant)

    Title scenes keep their planner durations (the open/close cards are framing,
    not the content that should stretch/compress). All durations stay >= 2s
    integers and the sum is corrected to exactly target_duration_s.
    """
    if style == "standard":
        return plan
    scenes = plan.get("scenes") or []
    if not scenes:
        return plan
    titles = [s for s in scenes if s.get("type") == "title"]
    content = [s for s in scenes if s.get("type") != "title"]
    if not content:
        return plan

    # Title policy per style. The plan keeps 2-4 cinematic content scenes (no
    # walkthrough), so cinematic can't drop BELOW ~2 content scenes — the lever that
    # separates cinematic from standard is therefore HOLD LENGTH. Compress the framing title
    # cards to a tight floor for cinematic so that freed budget flows into long
    # content holds (clearly longer than a default-paced standard plan). Snappy
    # leaves titles as planned (its win is the higher cut count from the prompt).
    if style == "cinematic":
        for s in titles:
            s["duration_s"] = 2  # schema floor; frees max budget for long holds
    title_total = sum(max(2, int(s.get("duration_s", 3))) for s in titles)
    content_budget = target_duration_s - title_total
    if content_budget < 2 * len(content):
        # not enough room to re-time without starving scenes — leave as planned
        return plan

    # Per-style target hold for content scenes; we bias toward it but always
    # spend exactly `content_budget` across the content scenes. Cinematic aims
    # HIGH (10s) so even a 3-content-scene plan reads slower than standard's
    # natural ~6-8s holds; snappy aims short (3s) for punchy cuts.
    target_hold = 3 if style == "snappy" else 10  # snappy short, cinematic long
    n = len(content)
    base = max(2, min(target_hold, content_budget // n))
    durs = [base] * n
    # distribute the remainder so the sum hits content_budget exactly
    remainder = content_budget - base * n
    i = 0
    # snappy spreads leftover thinly (keeps holds short); cinematic piles leftover
    # onto the earlier (usually cinematic) scenes so a few shots run long.
    order = range(n) if style == "snappy" else range(n)
    idxs = list(order)
    if style == "cinematic":
        idxs = sorted(idxs, key=lambda k: 0 if content[k].get("type") == "cinematic" else 1)
    while remainder > 0:
        durs[idxs[i % n]] += 1
        remainder -= 1
        i += 1
    while remainder < 0:  # over budget (base floor too high) — trim round-robin
        k = idxs[i % n]
        if durs[k] > 2:
            durs[k] -= 1
            remainder += 1
        i += 1
    for s, d in zip(content, durs):
        s["duration_s"] = int(d)
    return plan


def _plan_with_nemotron(company_url, goal, target_duration_s, style="standard",
                        quality="standard", brain="super-free", company_facts=None,
                        meta=None, conversion_read=None):
    # `meta`: optional dict the caller threads in to learn WHY the LLM path did or
    # did not produce a plan. Populated with finish_reason / usage (token costs) and
    # a short `reason` string ("ok", "no-key", "refusal", "truncated", "parse-fail",
    # "error") so plan_job can stamp plan_source + finish_reason on the plan and log
    # a NON-SILENT template fallback. Never raises on account of meta.
    if meta is None:
        meta = {}
    meta.setdefault("finish_reason", None)
    meta.setdefault("usage", None)
    # Gate on the OpenRouter key now that the planner brain routes through OpenRouter
    # (all 3 brains). When it's unset, return None so plan_job falls back to the
    # deterministic template plan (the live console always proceeds at $0).
    if not brain_mod.brain_key():
        meta["reason"] = "no-key"
        return None
    brain = brain_mod.normalize_brain(brain)
    # GENRE HINT: detect the brand's business model (media/marketplace/ecommerce/
    # fintech/social/services/dev-tool) so the LLM speaks to the RIGHT audience and
    # value — not the SaaS "gives your team" default for every brand (the R7-G3 bug
    # that made The Verge, a media publication, get B2B-SaaS framing). Empty string for
    # the dev-tool default so the historical SaaS prompt is byte-unchanged for SaaS.
    genre = detect_genre(company_url, company_facts)
    genre_hint = genre_hint_text(genre)
    # HOUSE STYLE: bias the plan toward Dennis's Luceo Studio signature (kinetic-light
    # arc + imperative-couplet VO), and pick the named template that best fits this
    # company's genre (clamped to wired render themes). Recorded in meta for the
    # render side. Toggle the whole bias off with HERMES_HOUSE_STYLE=0.
    house_block = "" if os.environ.get("HERMES_HOUSE_STYLE", "1") == "0" else _HOUSE_STYLE
    house_template = pick_house_style(genre)
    meta["house_template"] = house_template
    meta["house_style"] = bool(house_block)
    # Order: SYSTEM contract -> house-style craft -> pacing style -> genre audience hint
    # -> quality scene-type rule (LAST so it overrides any cinematic mention) -> few-shot
    # example (a demonstration of the house style, appended after the rules).
    system = (vp.SYSTEM_PROMPT + house_block + (_STYLE_PROMPT.get(style) or "") + genre_hint
              + (_QUALITY_PROMPT.get(_normalize_quality(quality)) or "")
              + _fewshot_block(quality))
    # Ground the brain in the REAL brand facts so the VO + briefs describe the actual
    # product, not an invented one. The block is appended to the USER prompt (after
    # the brief) and is "" when no facts were resolved — in which case the user prompt
    # is byte-identical to the historical one (graceful, behavior unchanged).
    # Pass company_url too: when the scrape is thin/empty (bot-blocked brands), the
    # facts block uses world-knowledge of the recognizable brand instead of going
    # hollow. Call unconditionally so even a None/empty facts dict still grounds on
    # the URL's brand.
    facts_block = vp.company_facts_block(company_facts or {}, company_url=company_url,
                                         genre=genre, conversion_read=conversion_read)
    user = ("Build the scene plan for this brief. Output JSON only.\n\n"
            "company_url: %s\ngoal: %s\ntarget_duration_s: %d\n"
            % (company_url, goal, target_duration_s))
    if facts_block:
        user = user + facts_block
    # Anti-REFUSAL guard. The free 120B Super sometimes answers a perfectly complete
    # brief with "I need the brief details…" instead of JSON, which produced no plan
    # and silently dropped to the template. Make it explicit that the brief above is
    # COMPLETE and that the ONLY acceptable response is the JSON object — never a
    # question, apology, or request for more information.
    user = user + (
        "\nThe brief above is COMPLETE. Do NOT ask for more information, do NOT "
        "apologize, and do NOT explain. Respond with ONLY the JSON scene-plan "
        "object and nothing else.\n")
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": user}]

    def _looks_like_refusal(text):
        # A refusal / clarifying-question reply has no JSON object and reads like
        # prose ("I need the brief details", "Could you provide…"). If extract_json
        # can't find a `{...}` AND the text is short, treat it as a refusal so the
        # retry uses a firmer nudge rather than the generic repair.
        t = (text or "").strip()
        if "{" in t and "}" in t:
            return False
        return True

    def _normalize_llm_plan(plan):
        # The 120B reliably emits id/type/brief/model/duration_s but OMITS
        # input_image (which is ALWAYS null for these scene types — every template
        # scene sets it None). Without this, a perfectly good LLM plan failed the
        # strict per-scene key check and was SILENTLY discarded to the template even
        # though finish_reason=stop and the JSON parsed (observed on the real Stripe
        # super-free call). Default the always-null structural field so a valid LLM
        # plan is KEPT instead of thrown away. Only fills a MISSING key — never
        # overwrites a value the model provided.
        if isinstance(plan, dict):
            for s in (plan.get("scenes") or []):
                if isinstance(s, dict):
                    s.setdefault("input_image", None)
        return plan

    # Try up to 2 fresh attempts. A transient refusal or truncation on the first
    # call should NOT immediately drop to the template — one clean retry recovers
    # most of them. Each attempt also gets a single JSON-repair sub-retry.
    last_reason = "error"
    for attempt in range(2):
        try:
            raw = vp.call_model(messages, brain=brain, meta=meta)
        except Exception:
            last_reason = "error"  # network/HTTP failure — try once more, then template
            continue
        fr = meta.get("finish_reason")
        if fr == "length":
            # Output budget exhausted (should be rare now that reasoning is off and
            # the cap is raised). Record it and retry once fresh.
            last_reason = "truncated"
            continue
        try:
            plan = _normalize_llm_plan(vp.extract_json(raw))
            meta["reason"] = "ok"
            return plan
        except (ValueError, json.JSONDecodeError):
            pass
        # No parseable JSON. If it reads like a refusal, nudge firmly and retry the
        # WHOLE call; otherwise do the in-context JSON repair.
        if _looks_like_refusal(raw):
            last_reason = "refusal"
            messages = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Do not ask for details — the brief is "
                 "complete. Output ONLY the JSON scene-plan object now."}]
            continue
        last_reason = "parse-fail"
        try:
            repair = messages + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": "Your previous output did not parse. Return ONLY the corrected JSON object."}]
            plan = _normalize_llm_plan(vp.extract_json(vp.call_model(repair, brain=brain, meta=meta)))
            meta["reason"] = "ok"
            return plan
        except Exception:
            continue  # fresh attempt on the next loop iteration
    meta["reason"] = last_reason
    return None  # all attempts failed -> fall back to the template (now logged by caller)


# --- GENRE-aware grounding -------------------------------------------------
# The 12-brand generality test exposed a SaaS-ONLY assumption: The Verge (a media
# publication) got a B2B-SaaS voiceover ("Theverge gives your team the latest quick
# posts"). The grounding had no genre awareness beyond dev-tool/SaaS, so a news site,
# a marketplace, and a retail store all got "gives your team" tool-framing and the
# wrong audience.
#
# A GENRE classifies the brand's BUSINESS MODEL so the VO speaks to the RIGHT audience
# and the RIGHT value. Genres (broad, by audience/value, not by industry):
#   - "dev-tool"      developer / engineering tools + B2B SaaS (Linear, Vercel,
#                      Notion, Webflow) -> teams ship/build/work faster.
#   - "fintech"       payments / banking APIs (Stripe, Plaid) -> businesses move money.
#   - "marketplace"   two-sided platforms (Airbnb, Tripadvisor) -> hosts/guests,
#                      listings, booking.
#   - "ecommerce"     DTC retail / online stores (Allbirds, Huckberry, Shopify-stores)
#                      -> products, materials, shop, collection.
#   - "media"         publications / news / journalism (The Verge) -> coverage,
#                      reporting, readers/audience. NEVER "gives your team".
#   - "social"        social networks / communities -> people, posts, connection.
#   - "services"      professional / local services -> clients, bookings, results.
# Each genre carries (a) an AUDIENCE word, (b) a VALUE verb-frame, and (c) a generic
# (brand-agnostic) fallback 5-tuple used when the brand isn't in the world-knowledge
# map AND the scrape is thin — so a NEW media/retail/marketplace brand still gets
# genre-appropriate copy instead of the SaaS "gives your team" template.
GENRE_DEFAULT = "dev-tool"

# Keyword signals -> genre. Matched against the URL host + the scraped tagline +
# feature text (lowercased). Order matters: the FIRST genre whose keywords match wins,
# so more specific genres (media, marketplace, ecommerce) are checked before the broad
# dev-tool/SaaS catch-all. Host-name hints are the strongest single signal.
_GENRE_HOST_HINTS = {
    "theverge.com": "media",
    "airbnb.com": "marketplace",
    "tripadvisor": "marketplace",
    "allbirds.com": "ecommerce",
    "huckberry.com": "ecommerce",
    "shopify.com": "ecommerce",
    "vercel.com": "dev-tool",
    "notion.so": "dev-tool",
    "webflow.com": "dev-tool",
    "linear.app": "dev-tool",
    "stripe.com": "fintech",
    "plaid.com": "fintech",
}

# Keyword buckets for genre inference from tagline/feature text when the host isn't a
# known hint. Checked in this order (specific -> broad).
_GENRE_KEYWORDS = [
    ("media", (
        "news", "journalism", "magazine", "publication", "editorial", "reporting",
        "reviews and news", "tech news", "coverage", "headlines", "articles",
        "podcast", "newsroom", "reporters", "stories", "the verge", "blog",
    )),
    ("marketplace", (
        "marketplace", "book a", "booking", "hosts", "guests", "listings",
        "travelers", "rentals", "stays", "vacation rental", "find a place",
        "two-sided", "buyers and sellers", "trips",
    )),
    ("ecommerce", (
        "shop", "store", "cart", "checkout", "free shipping", "collection",
        "new arrivals", "add to bag", "add to cart", "products", "wool", "footwear",
        "apparel", "outfit", "gear", "sale", "buy now", "shoes", "merch",
    )),
    ("fintech", (
        "payments", "banking", "transactions", "money", "fraud", "payouts",
        "invoices", "billing", "financial", "fintech", "ach", "cards", "wallet",
    )),
    ("social", (
        "social network", "friends", "followers", "community", "feed", "posts",
        "share photos", "connect with people", "messaging",
    )),
    ("services", (
        "consulting", "agency", "appointments", "schedule a call", "clients",
        "salon", "clinic", "law firm", "book an appointment",
    )),
    ("dev-tool", (
        "developer", "developers", "api", "sdk", "deploy", "build", "ship",
        "issue tracker", "workflow", "productivity", "no-code", "platform",
        "dashboard", "integrations", "your team", "engineering", "software",
        "saas", "automate", "collaborate",
    )),
]

# Per-genre framing used by the deterministic template (and exposed to the LLM as a
# GENRE HINT). Each entry:
#   audience    -> who the value is FOR (the spoken "audience" of the VO)
#   value_verb  -> the core value framing the VO should lead with
#   open_fmt    -> generic opening value-prop when no world-knowledge + thin scrape;
#                  "%(brand)s" is filled in. Genre-appropriate, NEVER SaaS for media.
#   home_fmt / inner_fmt / walk_phrase / cta_fmt -> the rest of the generic 5-tuple.
_GENRE_FRAMING = {
    "dev-tool": {
        "audience": "teams who build software",
        "value_verb": "helps your team ship faster",
        "open_fmt": "%(brand)s helps product teams build and ship faster.",
        "home_fmt": "Everything your team needs in one workspace.",
        "inner_fmt": "Built to help your team move faster every day.",
        "walk_phrase": "the core workflow",
        "cta_fmt": "Get started with %(brand)s.",
    },
    "fintech": {
        "audience": "businesses that move money",
        "value_verb": "powers payments and financial data",
        "open_fmt": "%(brand)s powers payments and financial data for businesses.",
        "home_fmt": "Move money and connect accounts in one place.",
        "inner_fmt": "Built-in fraud protection and instant payouts.",
        "walk_phrase": "the payment flow",
        "cta_fmt": "Start building with %(brand)s.",
    },
    "marketplace": {
        "audience": "hosts and guests",
        "value_verb": "connects hosts and guests",
        "open_fmt": "%(brand)s connects hosts and guests around the world.",
        "home_fmt": "Browse unique listings and book in a few taps.",
        "inner_fmt": "Compare places, read real reviews, then book with confidence.",
        "walk_phrase": "finding and booking a listing",
        "cta_fmt": "Find your next stay on %(brand)s.",
    },
    "ecommerce": {
        "audience": "shoppers",
        "value_verb": "sells products you actually want",
        "open_fmt": "%(brand)s makes products built to last, shipped to your door.",
        "home_fmt": "Shop the collection and find your fit.",
        "inner_fmt": "Premium materials, honest pricing, free returns.",
        "walk_phrase": "browsing the collection and checking out",
        "cta_fmt": "Shop the collection at %(brand)s.",
    },
    "media": {
        "audience": "readers",
        "value_verb": "covers the stories that matter",
        "open_fmt": "%(brand)s covers technology, science, and culture for millions of readers.",
        "home_fmt": "The latest reporting, reviews, and analysis every day.",
        "inner_fmt": "In-depth features, breaking news, and expert reviews.",
        "walk_phrase": "reading the latest coverage",
        "cta_fmt": "Read the latest at %(brand)s.",
    },
    "social": {
        "audience": "people and communities",
        "value_verb": "connects people",
        "open_fmt": "%(brand)s connects people and communities around the things they love.",
        "home_fmt": "Share, follow, and discover what people are talking about.",
        "inner_fmt": "Find your people and join the conversation.",
        "walk_phrase": "sharing your first post",
        "cta_fmt": "Join the community on %(brand)s.",
    },
    "services": {
        "audience": "clients",
        "value_verb": "delivers results for clients",
        "open_fmt": "%(brand)s delivers results for the clients who count on it.",
        "home_fmt": "Everything you need, handled by people who care.",
        "inner_fmt": "Book in minutes and get real results.",
        "walk_phrase": "booking an appointment",
        "cta_fmt": "Book with %(brand)s today.",
    },
}


def detect_genre(company_url, company_facts=None):
    """Classify a brand's GENRE (business model) from the URL host + scraped facts.

    Returns one of _GENRE_FRAMING's keys. Priority:
      1. A known HOST hint (theverge.com -> media, airbnb.com -> marketplace, …) —
         the strongest, most reliable single signal.
      2. Keyword inference from the tagline + feature text (specific genres first).
      3. GENRE_DEFAULT ("dev-tool"/SaaS) as the historical catch-all.

    Genre-awareness is the R7-G3 fix: before this, EVERY brand was grounded as a B2B
    SaaS tool, so a media publication (The Verge) got "gives your team" tool-framing.
    Stdlib only; never raises.
    """
    host = (company_url or "").lower()
    host = host.replace("https://", "").replace("http://", "").replace("www.", "")
    host = host.split("/")[0]
    for hint, genre in _GENRE_HOST_HINTS.items():
        if hint in host:
            return genre

    facts = company_facts if isinstance(company_facts, dict) else {}
    tagline = str(facts.get("tagline") or "")
    feats = facts.get("features") or []
    feat_text = []
    for f in feats:
        if isinstance(f, dict):
            f = f.get("label") or f.get("title") or ""
        feat_text.append(str(f))
    hay = " ".join([host, tagline] + feat_text).lower()

    for genre, keywords in _GENRE_KEYWORDS:
        for kw in keywords:
            if kw in hay:
                return genre
    return GENRE_DEFAULT


def genre_hint_text(genre):
    """A one-paragraph GENRE HINT appended to the planner prompt so the LLM speaks to
    the RIGHT audience and value for this brand's business model — NOT the SaaS
    "gives your team" default for every brand. Returns "" for the dev-tool default so
    the historical SaaS prompt is byte-unchanged for SaaS brands."""
    g = genre if genre in _GENRE_FRAMING else GENRE_DEFAULT
    if g == "dev-tool":
        return ""  # historical default — leave the SaaS-tuned prompt unchanged
    fr = _GENRE_FRAMING[g]
    label = {
        "fintech": "FINTECH / payments",
        "marketplace": "MARKETPLACE (two-sided platform)",
        "ecommerce": "E-COMMERCE / retail store",
        "media": "MEDIA / publication",
        "social": "SOCIAL network / community",
        "services": "professional / local SERVICES",
    }.get(g, g.upper())
    extra = ""
    if g == "media":
        extra = (
            " This is a PUBLICATION, not a B2B tool — NEVER write \"gives your team\", "
            "\"for your team\", \"your workspace\", \"productivity\", or any SaaS-tool "
            "framing. The audience is READERS, not customers buying software. Speak "
            "about COVERAGE, reporting, reviews, and the stories the publication "
            "delivers to its readers."
        )
    elif g == "marketplace":
        extra = (
            " The audience is HOSTS and GUESTS (or buyers and sellers) — speak about "
            "listings, booking, and trips, NOT a SaaS tool \"for your team\"."
        )
    elif g == "ecommerce":
        extra = (
            " The audience is SHOPPERS — speak about the PRODUCTS, materials, the "
            "collection, and the shopping experience, NOT a SaaS tool \"for your team\"."
        )
    return (
        "\n\nGENRE HINT: This brand is a %s. Its audience is %s, and its core value is "
        "that it %s. Write the voiceover for THAT audience and value — do NOT default "
        "to generic B2B-SaaS \"gives your team\" / \"for your workspace\" framing unless "
        "this brand is actually a software tool for teams.%s"
        % (label, fr["audience"], fr["value_verb"], extra)
    )


# World-knowledge value props for RECOGNIZABLE brands. Used by the deterministic
# template fallback (LLM unavailable) AND as the OPENING-beat backstop so even the
# offline path — and any plan whose opening beat the LLM emitted as a bare wordmark —
# writes grounded, concrete, imperative copy instead of hollow filler. Keyed by a
# host substring. Each entry is a 5-tuple:
#   (open_line, screenshot-home line, screenshot-inner line, walkthrough verb-phrase,
#    closing CTA)
# `open_line` is a FULL value-prop sentence naming a real feature/metric — it
# REPLACES the bare "Linear." / "Plaid." wordmark beat (the D3=2 root cause). These
# describe the REAL product and never the website/animation; never invents a
# DIFFERENT business. The new (non-SaaS) brands are GENRE-grounded: theverge speaks to
# readers/coverage (NOT "gives your team"), airbnb to hosts/guests, allbirds/huckberry
# to products/materials.
_BRAND_WORLD_KNOWLEDGE = {
    "stripe": (
        "Stripe powers online payments for millions of businesses worldwide.",
        "Accept payments online in over 135 currencies.",
        "Recurring billing, fraud protection, and instant payouts.",
        "set up a payment in minutes",
        "Start accepting payments at stripe.com.",
    ),
    "tripadvisor": (
        "Tripadvisor guides over a billion trips with real traveler reviews.",
        "Read millions of real traveler reviews before you book.",
        "Compare hotels, restaurants, and things to do worldwide.",
        "find and book your next trip",
        "Plan your next trip on Tripadvisor.",
    ),
    "shopify": (
        "Shopify powers millions of online stores selling in every market.",
        "Launch an online store and start selling today.",
        "Run payments, shipping, and inventory from one dashboard.",
        "set up your store and add a product",
        "Start your store at shopify.com.",
    ),
    "linear": (
        "Linear is the issue tracker built for high-performance product teams.",
        "Plan with Cycles and Projects, then ship faster as a team.",
        "Triage bugs and move issues in sub-second, keyboard-first flow.",
        "create an issue and move it through the board",
        "Build your product roadmap on Linear.",
    ),
    "plaid": (
        "Plaid connects your app to over 12,000 banks and financial institutions.",
        "Use Link to connect a bank account in seconds.",
        "Verify balances and identity with Auth, Balance, and Signal.",
        "link an account through the Plaid Link flow",
        "Connect financial data with Plaid.",
    ),
    # --- R7-G3 new (non-SaaS) brands, GENRE-grounded ---
    # MEDIA: readers/coverage, NEVER "gives your team".
    "theverge": (
        "The Verge covers technology, science, and culture for millions of readers.",
        "Breaking tech news, in-depth reviews, and sharp analysis every day.",
        "From gadget reviews to policy reporting, all in one feed.",
        "reading the latest coverage",
        "Read the latest at theverge.com.",
    ),
    # MARKETPLACE: hosts/guests, listings, booking.
    "airbnb": (
        "Airbnb connects travelers with unique homes and experiences worldwide.",
        "Book stays from millions of homes hosted by real people.",
        "Become a host and earn by sharing your space.",
        "finding and booking a stay",
        "Find your next stay on Airbnb.",
    ),
    # E-COMMERCE: products, materials, shop.
    "allbirds": (
        "Allbirds makes comfortable shoes from natural, sustainable materials.",
        "Shop wool runners and tree sneakers made to last.",
        "Made with merino wool and eucalyptus, designed to lower carbon.",
        "browsing the collection and checking out",
        "Shop the collection at allbirds.com.",
    ),
    # E-COMMERCE: men's outdoor / adventure gear.
    "huckberry": (
        "Huckberry curates rugged gear and apparel for the modern adventurer.",
        "Shop field-tested clothing, boots, and outdoor essentials.",
        "Handpicked brands and exclusives you won't find anywhere else.",
        "browsing the shop and checking out",
        "Gear up at huckberry.com.",
    ),
    # DEV-TOOL / frontend deploy.
    "vercel": (
        "Vercel is the platform for frontend developers to deploy and ship fast.",
        "Push to git and get a live preview deployment in seconds.",
        "Edge network, instant rollbacks, and zero-config builds.",
        "deploying a project and opening a preview",
        "Deploy your frontend on Vercel.",
    ),
    # DEV-TOOL / docs + wiki + projects.
    "notion": (
        "Notion is the connected workspace for docs, wikis, and projects.",
        "Write docs, build wikis, and track projects in one place.",
        "Databases, templates, and AI built into every page.",
        "creating a page and turning it into a database",
        "Build your workspace on Notion.",
    ),
    # DEV-TOOL / visual web design, no-code.
    "webflow": (
        "Webflow lets you design and ship responsive websites without code.",
        "Build pixel-perfect sites visually, then publish in one click.",
        "A built-in CMS, hosting, and clean production-ready code.",
        "designing a page and publishing it",
        "Build your site on Webflow.",
    ),
}


def _world_knowledge_for(brand, company_url):
    """Return the (home, inner, walk_phrase, cta) tuple for a recognizable brand, or
    None. Matches on the URL host first (most reliable), then the brand name."""
    hay = ("%s %s" % (company_url or "", brand or "")).lower()
    for key, props in _BRAND_WORLD_KNOWLEDGE.items():
        if key in hay:
            return props
    return None


def _genre_open_frame(brand, feature_phrase, genre):
    """The OPENING value-prop sentence for the scraped-features path, framed for the
    brand's GENRE. The old code hardcoded "%s gives your team %s." (SaaS-tool framing)
    for EVERY brand — that is exactly the bug that made The Verge (media) say
    "Theverge gives your team the latest quick posts". Each genre gets a verb-frame
    that fits its audience: media COVERS, marketplace CONNECTS, ecommerce MAKES, etc.
    `feature_phrase` is the real scraped top capability (already lowercased, no period).
    """
    g = genre if genre in _GENRE_FRAMING else GENRE_DEFAULT
    fp = (feature_phrase or "").strip()
    if g == "media":
        return "%s brings you %s." % (brand, fp)
    if g == "marketplace":
        return "%s connects you with %s." % (brand, fp)
    if g == "ecommerce":
        return "%s brings you %s." % (brand, fp)
    if g == "fintech":
        return "%s powers %s for your business." % (brand, fp)
    if g == "social":
        return "%s connects people through %s." % (brand, fp)
    if g == "services":
        return "%s delivers %s for its clients." % (brand, fp)
    # dev-tool / default — historical SaaS framing (unchanged for SaaS brands).
    return "%s gives your team %s." % (brand, fp)


def _grounded_template_beats(brand, company_url, emphasis, features, company_facts=None):
    """Build grounded, concrete, imperative open/screenshot/walkthrough/CTA copy for
    the deterministic STANDARD fallback. Priority:
      1. RECOGNIZABLE brand -> world-knowledge value props (real feature names).
      2. Real scraped `features` -> name the actual capabilities (GENRE-framed open).
      3. Genre-appropriate generic benefit lines (last resort) — still NOT the banned
         hollow filler ("straight from the real site", "exactly as you would see it"),
         and NOT SaaS "gives your team" framing for a media/marketplace/retail brand.
    The OPENING beat is a FULL value-prop sentence naming a real feature/metric —
    NEVER a bare wordmark ("Linear." / "Plaid.") which is the D3=2 root cause. Also
    fixes the grammar bug: the walkthrough beat is an IMPERATIVE ("Watch <verb
    phrase>") with no "use the <noun>" stitch.

    `company_facts` (with `company_url`) drives GENRE detection so a non-SaaS brand
    speaks to the RIGHT audience even when it isn't in the world-knowledge map.

    Returns (open_line, home_line, inner_line, walk_line, cta_line).
    """
    emphasis = (emphasis or "").strip()
    # Strip a leading article so "the pricing page" reads cleanly in an imperative.
    emph_label = re.sub(r"^(the|a|an)\s+", "", emphasis, flags=re.IGNORECASE).strip()
    feats = [str(f).strip() for f in (features or []) if str(f).strip()]
    genre = detect_genre(company_url, company_facts)
    fr = _GENRE_FRAMING.get(genre, _GENRE_FRAMING[GENRE_DEFAULT])

    wk = _world_knowledge_for(brand, company_url)
    if wk:
        open_line, home_line, inner_line, walk_phrase, cta_line = wk
        # If the customer emphasized a specific feature, let the walkthrough follow it.
        if emph_label:
            walk_phrase = emph_label
        walk_line = "Watch %s, step by step." % walk_phrase
        return open_line, home_line, inner_line, walk_line, cta_line

    if feats:
        f0 = feats[0]
        f1 = feats[1] if len(feats) > 1 else None
        # Sentence-case + end with a period (real feature names rarely carry one).
        home_core = (f0[:1].upper() + f0[1:]).strip()
        home_line = home_core if home_core.endswith((".", "!", "?")) else home_core + "."
        # second line: name the next real feature as a concrete benefit.
        if f1:
            f1_core = (f1[:1].lower() + f1[1:]).strip().rstrip(".!?")
            inner_line = "Plus %s — built right into the product." % f1_core
        else:
            inner_line = fr["inner_fmt"]
        walk_phrase = emph_label or f0.lower().rstrip(".!?")
        walk_line = "Watch %s, step by step." % walk_phrase
        cta_line = fr["cta_fmt"] % {"brand": brand}
        # Opening value-prop names the brand AND its top real feature, framed for the
        # brand's GENRE (NOT a hardcoded SaaS "gives your team" for every brand).
        f0_core = f0.lower().rstrip(".!?")
        open_line = _genre_open_frame(brand, f0_core, genre)
        return open_line, home_line, inner_line, walk_line, cta_line

    # Last resort: honest, benefit-driven, NOT hollow/self-referential, and framed for
    # the brand's GENRE so a media/marketplace/retail brand never gets SaaS framing.
    open_line = fr["open_fmt"] % {"brand": brand}
    home_line = fr["home_fmt"]
    inner_line = fr["inner_fmt"]
    walk_phrase = emph_label or fr["walk_phrase"]
    walk_line = "Watch %s, step by step." % walk_phrase
    cta_line = fr["cta_fmt"] % {"brand": brand}
    return open_line, home_line, inner_line, walk_line, cta_line


def _is_bare_wordmark_beat(text, brand):
    """True if a VO beat is a single-word / bare-wordmark fragment rather than a full
    value-prop sentence. Catches "Linear.", "Plaid", "Stripe!", a lone brand token,
    or any beat that is just one or two words with no real content. These are the
    D3=2 thin-grounding failure: a beat must always be a complete value-prop sentence.
    """
    t = (text or "").strip()
    if not t:
        return True
    # Strip surrounding punctuation/whitespace for the word count + brand compare.
    core = t.strip(" .!?,:;—-").strip()
    if not core:
        return True
    words = core.split()
    # 1 or 2 words is never a value-prop sentence (e.g. "Linear.", "Plaid.",
    # "Get started.") — treat as bare. The reference films use SHORT imperative
    # COUPLETS, but those carry a verb+object (>=2 content words) and live in feature
    # cards, not the grounded opening beat we backstop here.
    if len(words) <= 1:
        return True
    # Exactly the brand name (case-insensitive), optionally with trailing punctuation.
    if core.lower() == (brand or "").strip().lower():
        return True
    return False


# Stage-direction / instruction prefixes that must NEVER appear as spoken VO copy.
# These are directions to the renderer, not lines a narrator says. Mirrors (and is
# kept in sync with) style_fill._is_prompt_artifact, but applied at the BEAT level so
# the artifact is killed at the PLANNER source — before it reaches alignment/TTS or a
# title — not only at the display layer. The notion artifact ("Show call-to-action:
# 'Start") is the canonical case.
_STAGE_DIRECTION_PREFIXES = (
    "show call-to-action",
    "show cta",
    "show a call",
    "show the call",
    "display the ",
    "display a ",
    "display an ",
    "present the ",
    "present a ",
    "animate ",
    "animated ",
    "insert ",
    "place a ",
    "place the ",
    "add a cta",
    "add cta",
    "add a call",
    "overlay ",
    "scene:",
    "title:",
    "subtitle:",
    "cta:",
    "headline:",
    "caption:",
    "brief:",
    "voiceover:",
    "narration:",
    "call-to-action:",
    "call to action:",
)

# Stage-direction substrings that are a dead giveaway anywhere in the beat (a beat
# should describe the PRODUCT, never the call-to-action mechanic or the card itself).
_STAGE_DIRECTION_SUBSTRINGS = (
    "call-to-action:",
    "call to action:",
    "wordmark and tagline",
    "in a branded browser card",
)

# Fancy unicode hyphens/minus that small planners (and copy-pasted META descriptions)
# emit instead of an ASCII '-'. Normalizing them to '-' is what lets the
# "call-to-action" substring match "call‑to‑action" (the notion-rebuild leak: the
# fancy hyphen U+2011 in "Closing call‑to‑action card urging users" defeated the plain
# ASCII substring test, so the meta-description phrasing slipped past the planner).
_FANCY_HYPHENS = "‐‑‒–—―−"
_HYPHEN_TRANS = {ord(c): "-" for c in _FANCY_HYPHENS}


def _norm_hyphens(s):
    """Lowercase + map every fancy unicode hyphen/minus (U+2010–U+2015, U+2212) to an
    ASCII '-' so hyphenated stage-direction phrasing matches regardless of which dash
    glyph the planner emitted. Stdlib only; never raises."""
    return (s or "").lower().translate(_HYPHEN_TRANS)


# META-DESCRIPTION phrasing class: a beat that DESCRIBES the card/scene/CTA mechanic
# ("Closing call-to-action card urging users …", "Call-to-action card using the brand
# color", "card urging users to …") instead of speaking TO the user. This is the
# notion-rebuild leak — it is NOT caught by a stage-direction PREFIX (the beat opens
# with "Closing"/"Call-to-action", not "Show"/"Display") and the existing
# "call-to-action:" substring requires a trailing colon, so "call-to-action card" slips
# through. Matched anywhere in the HYPHEN-NORMALIZED beat. Each entry is meta-talk that
# only appears when copy is describing the artifact, never in real spoken product copy.
_META_DESCRIPTION_SUBSTRINGS = (
    "call-to-action",
    "call to action",
    "closing card",
    "closing call",
    "urging users",
    "card urging",
    "cta card",
    "the cta",
    "using the brand",
    "brand color",
    "the wordmark",
    "stage direction",
)

# Stage-OPENER verbs: a beat that STARTS with one of these and then describes a
# card/scene/title (rather than speaking to the user) is a stage direction, e.g.
# "Closing call-to-action card …", "Show the title card", "Present the closing scene".
# The opener alone is NOT enough (real copy starts with "Show your work to the world");
# it must ALSO mention a scene/card noun to qualify, so legit imperative copy is kept.
_STAGE_OPENER_VERBS = ("closing", "show", "display", "animate", "present")

# Scene/card nouns that, when a beat OPENS with a stage-opener verb, mark the beat as
# describing the artifact (the card/scene), not addressing the viewer.
_STAGE_SCENE_NOUNS = (
    "card", "scene", "title card", "cta", "call-to-action", "call to action",
    "lockup", "wordmark", "browser card", "screen", "closing title", "opening title",
)


def _is_meta_description_text(norm):
    """True when the (hyphen-normalized, lowercased) beat is META-DESCRIPTION phrasing —
    it describes the CTA/card/scene mechanic instead of being spoken product copy.

    Two signals:
      1. a dead-giveaway META substring anywhere (_META_DESCRIPTION_SUBSTRINGS), OR
      2. a STAGE-OPENER shape: the beat STARTS with Closing/Show/Display/Animate/Present
         AND mentions a card/scene/cta noun (so it is describing the artifact, not
         addressing the user). The noun requirement is what preserves legit copy that
         merely opens with one of those verbs ("Show your work to the world",
         "Closing time") — those carry no scene/card noun, so they are NOT flagged.
    """
    if not norm:
        return False
    for sub in _META_DESCRIPTION_SUBSTRINGS:
        if sub in norm:
            return True
    first = norm.split()[0] if norm.split() else ""
    if first in _STAGE_OPENER_VERBS:
        for noun in _STAGE_SCENE_NOUNS:
            if noun in norm:
                return True
    return False


def _is_stage_direction_text(text):
    """True when a VO beat is an INSTRUCTION / STAGE DIRECTION rather than spoken copy.

    A stage direction tells the renderer what to do ("Show call-to-action: 'Start",
    "Display the pricing table", "Animated feature beat …", or a leaked scene brief
    like "<Brand> wordmark and tagline"). It also covers META-DESCRIPTION phrasing that
    describes the CARD/SCENE mechanic instead of being spoken copy ("Closing
    call-to-action card urging users …") — this is the notion-rebuild leak that opens
    with "Closing"/"Call-to-action" rather than a known prefix. It is NEVER a line a
    narrator speaks, so it must never become a VO beat or a title. Conservative: only
    flags strings whose WHOLE shape is an instruction (a known prefix), that carry a
    dead-giveaway stage-direction / meta-description substring, or that open with a
    stage-opener verb AND name a card/scene noun — not strings that merely contain a
    verb like "show".
    """
    t = (text or "").strip()
    if not t:
        return False
    lower = t.lower()
    for prefix in _STAGE_DIRECTION_PREFIXES:
        if lower.startswith(prefix):
            return True
    for sub in _STAGE_DIRECTION_SUBSTRINGS:
        if sub in lower:
            return True
    # META-DESCRIPTION / stage-opener phrasing — normalize fancy hyphens first so
    # "call‑to‑action card" (fancy U+2011) matches "call-to-action".
    if _is_meta_description_text(_norm_hyphens(t)):
        return True
    return False


def _degut_stage_direction_beats(plan, brand, company_url, company_facts, emphasis):
    """Rewrite any VO beat that is an instruction / stage direction into real spoken
    copy for THIS brand. Defense-in-depth: runs on the FINAL plan no matter whether the
    beats came from the LLM or the template, because small planners leak the scene
    BRIEF (or a prompt fragment) into the beat text — e.g. notion's
    "Show call-to-action: 'Start" rendered as a spoken VO line.

    Replacement, genre-grounded for THIS brand (never invents a different business):
      - a CLOSING title beat / any beat that reads like a CTA -> the grounded CTA line;
      - any other stage-direction beat -> the grounded opening value-prop line.
    No-op when no beat is a stage direction (the common case).
    """
    vo = (plan or {}).get("voiceover") or {}
    beats = vo.get("beats")
    if not isinstance(beats, list) or not beats:
        return plan
    scenes = {s.get("id"): s for s in (plan.get("scenes") or []) if isinstance(s, dict)}

    # Normalize scraped features to capability strings (same shape the template uses)
    # so the rewrite names a real feature.
    raw_feats = (company_facts or {}).get("features") or []
    feats = []
    for f in raw_feats:
        if isinstance(f, dict):
            f = f.get("label") or f.get("title") or ""
        if str(f).strip():
            feats.append(str(f).strip())

    open_line, home_line, _inner, _walk, cta_line = _grounded_template_beats(
        brand, company_url, emphasis, feats, company_facts=company_facts)

    # Identify the closing (last) title scene id so a CTA-shaped artifact -> CTA copy.
    title_scene_ids = [s.get("id") for s in (plan.get("scenes") or [])
                       if isinstance(s, dict) and s.get("type") == "title"]
    last_title_id = title_scene_ids[-1] if title_scene_ids else None

    for b in beats:
        if not isinstance(b, dict):
            continue
        if not _is_stage_direction_text(b.get("text")):
            continue
        sid = b.get("scene_id")
        scene = scenes.get(sid) or {}
        artifact = (b.get("text") or "").lower()
        is_cta = (
            sid == last_title_id
            or "call-to-action" in artifact or "call to action" in artifact
            or artifact.startswith(("show cta", "add cta", "add a cta"))
        )
        if is_cta:
            b["text"] = cta_line
        elif scene.get("type") == "title":
            b["text"] = open_line
        else:
            b["text"] = home_line or open_line
    return plan


def _degut_bare_wordmark_beats(plan, brand, company_url, company_facts, emphasis):
    """Rewrite any bare-wordmark / single-word VO beat into a full value-prop sentence.

    Defense-in-depth: runs on the FINAL plan no matter whether the beats came from the
    LLM or the deterministic template, because small planners still emit a single-word
    opening beat ("Linear." / "Plaid.") even when the body is grounded. The replacement
    is a real value-prop naming a feature/metric:
      - for the OPENING title beat: prefer the world-knowledge opening line (names a
        real feature/metric), else the brand's first scraped feature, else an honest
        full sentence;
      - for any other bare beat: a grounded benefit line.
    Never invents a different business — pulls only from world-knowledge or scraped
    facts for THIS brand. No-op when every beat is already a full sentence.
    """
    vo = (plan or {}).get("voiceover") or {}
    beats = vo.get("beats")
    if not isinstance(beats, list) or not beats:
        return plan
    scenes = {s.get("id"): s for s in (plan.get("scenes") or []) if isinstance(s, dict)}

    # Normalize scraped features to a list of capability strings (same shape as the
    # template path uses) so the rewrite can name a real feature.
    raw_feats = (company_facts or {}).get("features") or []
    feats = []
    for f in raw_feats:
        if isinstance(f, dict):
            f = f.get("label") or f.get("title") or ""
        if str(f).strip():
            feats.append(str(f).strip())

    open_line, home_line, inner_line, _walk_line, _cta_line = _grounded_template_beats(
        brand, company_url, emphasis, feats, company_facts=company_facts)

    # Find the first/opening title scene id so we can give it the strongest open line.
    first_title_id = None
    for s in (plan.get("scenes") or []):
        if isinstance(s, dict) and s.get("type") == "title":
            first_title_id = s.get("id")
            break

    for b in beats:
        if not isinstance(b, dict):
            continue
        if not _is_bare_wordmark_beat(b.get("text"), brand):
            continue
        sid = b.get("scene_id")
        scene = scenes.get(sid) or {}
        # The opening title gets the value-prop open line; any other bare beat gets a
        # grounded benefit line (home line, else the honest open line as a fallback).
        if sid == first_title_id or scene.get("type") == "title":
            b["text"] = open_line
        else:
            b["text"] = home_line or open_line
    return plan


def _standard_template_plan(brand, company_url, goal, target_duration_s, style,
                            emphasis=None, company_facts=None):
    """Standard deterministic plan: title -> 2 screenshot -> walkthrough -> title.

    The real-capture pillars (model null everywhere): the opening title, two captured
    website views, one guided walkthrough of the emphasized feature, the closing CTA.
    No cinematic / motion_graphic — a standard build renders the titles in Remotion
    and fills the screenshot/walkthrough scenes with real captured assets. Durations
    sum to EXACTLY target_duration_s here (and stay summed after _restyle_durations).

    Beats are GROUNDED and IMPERATIVE (no hollow "straight from the real site"
    filler, no "use the <noun>" grammar bug) — see _grounded_template_beats.
    """
    open_d, close_d = 3, 5
    body = max(6, target_duration_s - open_d - close_d)
    # Split the body across two screenshots + one (longer) walkthrough; the
    # walkthrough gets the larger share so the demo can breathe.
    walk_d = max(6, body // 2)
    shot_rem = max(4, body - walk_d)
    shot1 = max(2, shot_rem // 2)
    shot2 = max(2, shot_rem - shot1)
    # Correct any rounding so the four content+title scenes sum to target exactly.
    total = open_d + shot1 + shot2 + walk_d + close_d
    walk_d += (target_duration_s - total)
    if walk_d < 2:  # pathological tiny target — clamp and re-derive
        walk_d = 2

    scenes = [
        {"id": "title-open", "type": "title", "brief": "%s wordmark and tagline" % brand,
         "model": None, "duration_s": open_d, "input_image": None},
        {"id": "screenshot-home", "type": "screenshot",
         "brief": "Real captured homepage of %s in a branded browser card" % brand,
         "model": None, "duration_s": shot1, "input_image": None},
        {"id": "screenshot-inner", "type": "screenshot",
         "brief": "Real captured key page of %s showing the product" % brand,
         "model": None, "duration_s": shot2, "input_image": None},
        {"id": "walkthrough", "type": "walkthrough",
         "brief": _walkthrough_brief_for_emphasis(brand, emphasis),
         "model": None, "duration_s": walk_d, "input_image": None},
        {"id": "title-close", "type": "title", "brief": "Call to action: get started with %s" % brand,
         "model": None, "duration_s": close_d, "input_image": None},
    ]
    # Normalize scraped features (may be strings or {label}/{title} dicts) to a list
    # of real capability strings for grounding.
    raw_feats = (company_facts or {}).get("features") or []
    feats = []
    for f in raw_feats:
        if isinstance(f, dict):
            f = f.get("label") or f.get("title") or ""
        if str(f).strip():
            feats.append(str(f).strip())
    open_line, home_line, inner_line, walk_line, cta_line = _grounded_template_beats(
        brand, company_url, emphasis, feats, company_facts=company_facts)
    beats = [
        # OPENING beat is a full value-prop sentence (a real feature/metric), NOT the
        # bare "%s." wordmark — bare wordmark beats are the D3=2 thin-grounding bug.
        {"scene_id": "title-open", "text": open_line},
        {"scene_id": "screenshot-home", "text": home_line},
        {"scene_id": "screenshot-inner", "text": inner_line},
        {"scene_id": "walkthrough", "text": walk_line},
        {"scene_id": "title-close", "text": cta_line},
    ]
    return {
        "job": {"company_url": company_url, "goal": goal,
                "target_duration_s": target_duration_s, "target_margin": 0.6, "currency": "usd"},
        "scenes": scenes,
        "voiceover": {"voice": "Adam", "beats": beats},
    }


def _template_plan(company_url, goal, target_duration_s, style="standard",
                   quality="standard", brand=None, emphasis=None, company_facts=None):
    brand = brand or _brand_name(company_url)
    quality = _normalize_quality(quality)

    # STANDARD: deterministic real-capture fallback. An opening title, two captured
    # website screenshots, one guided walkthrough of the emphasized feature, a closing
    # title CTA. This is the path the OPENROUTER-key-unset console uses, so it must
    # satisfy the standard structure contract on its own. (PREMIUM keeps the cinematic
    # template below.) _restyle_durations is a no-op for standard (it returns the plan
    # untouched for style="standard"); for snappy/cinematic style it only re-times the
    # holds while keeping the scene TYPES intact.
    if quality == "standard":
        plan = _standard_template_plan(brand, company_url, goal, target_duration_s,
                                       style, emphasis=emphasis,
                                       company_facts=company_facts)
        return _restyle_durations(plan, style, target_duration_s)

    # durations sum to target (3 + 6 + feat + 6 + close). `feat` is the middle
    # cinematic feature beat that replaced the retired walkthrough scene.
    feat = max(6, target_duration_s - 3 - 6 - 6 - 5)

    if style == "snappy":
        # MORE scenes, SHORTER holds: add a motion_graphic divider + a 3rd cinematic
        # so the cut count is higher than the default 5-scene template.
        scenes = [
            {"id": "title-open", "type": "title", "brief": "%s wordmark and tagline" % brand,
             "model": None, "duration_s": 3, "input_image": None},
            {"id": "cine-establish", "type": "cinematic",
             "brief": "Cinematic establishing shot of what %s does" % brand,
             "model": "seedance_2_0", "duration_s": 4, "input_image": None},
            {"id": "motion-divider", "type": "motion_graphic",
             "brief": "Quick divider card with the text 'Built for teams'",
             "model": None, "duration_s": 3, "input_image": None},
            {"id": "cine-feature", "type": "cinematic",
             "brief": "Fast b-roll montage of %s features" % brand,
             "model": "seedance_2_0", "duration_s": 4, "input_image": None},
            {"id": "feature-beat", "type": "motion_graphic",
             "brief": "Animated feature beat highlighting what %s does best" % brand,
             "model": None, "duration_s": 5, "input_image": None},
            {"id": "cine-hero", "type": "cinematic",
             "brief": "Clean hero plate of the %s product UI" % brand,
             "model": "gpt_image_2", "duration_s": 4, "input_image": None},
            {"id": "title-close", "type": "title", "brief": "Call to action: get started with %s" % brand,
             "model": None, "duration_s": 4, "input_image": None},
        ]
        beats = [
            {"scene_id": "title-open", "text": "%s." % brand},
            {"scene_id": "cine-establish", "text": "%s helps you do more with less." % brand},
            {"scene_id": "motion-divider", "text": "Built for teams."},
            {"scene_id": "cine-feature", "text": "Powerful features, fast."},
            {"scene_id": "feature-beat", "text": "Here is what makes it work."},
            {"scene_id": "cine-hero", "text": "Built for the way you work."},
            {"scene_id": "title-close", "text": "Get started with %s today." % brand},
        ]
    elif style == "cinematic":
        # FEWER scenes, LONGER holds: drop the second cinematic + lean on seedance
        # motion plates so the few shots breathe.
        scenes = [
            {"id": "title-open", "type": "title", "brief": "%s wordmark and tagline" % brand,
             "model": None, "duration_s": 4, "input_image": None},
            {"id": "cine-establish", "type": "cinematic",
             "brief": "Slow cinematic establishing shot of what %s does" % brand,
             "model": "seedance_2_0", "duration_s": 9, "input_image": None},
            {"id": "cine-feature", "type": "cinematic",
             "brief": "Slow cinematic feature montage of %s in action" % brand,
             "model": "seedance_2_0", "duration_s": 8, "input_image": None},
            {"id": "title-close", "type": "title", "brief": "Call to action: get started with %s" % brand,
             "model": None, "duration_s": 9, "input_image": None},
        ]
        beats = [
            {"scene_id": "title-open", "text": "%s." % brand},
            {"scene_id": "cine-establish", "text": "%s helps you do more with less." % brand},
            {"scene_id": "cine-feature", "text": "See it in action, end to end."},
            {"scene_id": "title-close", "text": "Get started with %s today." % brand},
        ]
    else:  # standard — UNCHANGED from the historical default (safety invariant)
        scenes = [
            {"id": "title-open", "type": "title", "brief": "%s wordmark and tagline" % brand,
             "model": None, "duration_s": 3, "input_image": None},
            {"id": "cine-establish", "type": "cinematic",
             "brief": "Cinematic establishing shot of what %s does" % brand,
             "model": "seedance_2_0", "duration_s": 6, "input_image": None},
            {"id": "cine-feature", "type": "cinematic",
             "brief": "Cinematic feature montage of %s in action" % brand,
             "model": "seedance_2_0", "duration_s": feat, "input_image": None},
            {"id": "cine-hero", "type": "cinematic",
             "brief": "Clean hero plate of the %s product UI" % brand,
             "model": "gpt_image_2", "duration_s": 6, "input_image": None},
            {"id": "title-close", "type": "title", "brief": "Call to action: get started with %s" % brand,
             "model": None, "duration_s": 5, "input_image": None},
        ]
        beats = [
            {"scene_id": "title-open", "text": "%s." % brand},
            {"scene_id": "cine-establish", "text": "%s helps you do more with less." % brand},
            {"scene_id": "cine-feature", "text": "See it in action, end to end."},
            {"scene_id": "cine-hero", "text": "Built for the way you work."},
            {"scene_id": "title-close", "text": "Get started with %s today." % brand},
        ]

    plan = {
        "job": {"company_url": company_url, "goal": goal,
                "target_duration_s": target_duration_s, "target_margin": 0.6, "currency": "usd"},
        # Scene-aligned beats: one narration line per scene, keyed by scene id,
        # each sized to its scene's duration so it lands on the matching picture.
        "scenes": scenes,
        "voiceover": {"voice": "Adam", "beats": beats},
    }
    # Re-time the deterministic fallback per style too, so the durations always sum
    # to target_duration_s and the holds match the style (standard = identity).
    return _restyle_durations(plan, style, target_duration_s)


def _brand_name(url):
    u = (url or "").lower().replace("https://", "").replace("http://", "").replace("www.", "")
    host = u.split("/")[0].split(".")
    name = host[-2] if len(host) >= 2 else (host[0] if host else "the product")
    return name.capitalize()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--goal", default="")
    ap.add_argument("--emphasis", default="",
                    help="the feature/area to emphasize; becomes the STANDARD "
                         "walkthrough's specific multi-step goal")
    ap.add_argument("--duration", type=int, default=30)
    ap.add_argument("--style", choices=list(VALID_STYLES), default="standard")
    ap.add_argument("--quality", choices=list(VALID_QUALITIES), default="standard",
                    help="standard => real-capture (title + screenshot + walkthrough); "
                         "premium => cinematic shots allowed")
    ap.add_argument("--brain", choices=list(brain_mod.VALID_BRAINS), default=brain_mod.DEFAULT_BRAIN,
                    help="planner LLM (operator, via OpenRouter): "
                         "ultra-paid | super-free (default, $0) | super-paid")
    a = ap.parse_args()
    p = plan_job(a.url, a.goal or ("%d-second promo" % a.duration), a.duration,
                 style=a.style, quality=a.quality, brain=a.brain, emphasis=a.emphasis)
    json.dump(p, sys.stdout, indent=2)
    print()
