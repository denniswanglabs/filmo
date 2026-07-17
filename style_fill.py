#!/usr/bin/env python3
"""style_fill.py -- Phase 2 keystone of the VO-driven style engine.

Fills one of Dennis's CURATED style templates with a customer's brand + scene
copy, then drives the FULL VO-driven render end to end. This is exactly Dennis's
manual re-skin workflow, automated (see docs/2026-06-21-vo-driven-style-engine-design.md).

Pipeline (all $0 on the free tier):
    plan.json + brand_theme.json
       |  align_vo.py     (edge-tts synth + whisper-cli word timing)  -> vo_alignment.json
       |  build_timeline.py (word spans -> in/out frames, cues -> at_frame) -> timeline.json
       |  style_fill (THIS) merge: timeline + plan copy + brand theme + STYLE -> props.json
       |  remotion render Timeline --props props.json
       v  montage.png (proof the scenes are VO-anchored and reveals land on words)

THE STYLE REGISTRY (extensible -- adding a style = ONE entry):
    A Style maps each plan scene's `role`/`type` -> a Timeline `archetype`
    ("hero-title" | "card-ui") and a `shape_data(scene, brand) -> SceneData` fn
    that builds the archetype's `data` block from plan copy + brand features.
    To add a style later: append a Style(...) to STYLES with its own role->archetype
    map and data shapers. No other code changes.

props.json contract (EXACT shape the <Timeline> composition consumes, one props
object -- studio/src/timeline/types.ts):
    {
      "fps": int, "total_frames": int, "audio_path": str, "lang": str,
      "theme": { bg, bgCard, bgCardRaised, navy, navyBright, accent, ok, text,
                 textMuted, textDim, border, fontPrimary, fontMono, fontDisplay,
                 wordmark },
      "scenes": [ { id, archetype, in_frame, out_frame,
                    cues:[{label, word, at_frame}],   # ABSOLUTE frames (Timeline rebases)
                    data:{...SceneData per archetype} } ]
    }

CLI:
    python3 style_fill.py --plan <plan.json> --brand <brand_theme.json> \
        --style orinovate-kinetic-light --out runs/<id>/ [--fps 30] \
        [--render] [--no-align] [--tier free]
"""
from __future__ import annotations

import argparse
import html as _html_mod
import json
import os
import re
import subprocess
import sys
from typing import Any, Callable, Dict, List, Optional

import align_vo
import build_timeline
# plan_job owns the HONEST card-treatment/entity/stat logic. We reuse its miners
# (`_mine_named_entities`, `_stat_is_real`, `_feature_entities_from_facts`) in a
# POST-FILL pass below so treatment selection runs on the REAL filled card copy
# (title/subtitle) instead of the empty titles plan_job saw at plan time. Safe
# import: plan_job depends only on validate_planner/brain/plan_schema (no cycle).
import plan_job

# ---------------------------------------------------------------------------
# HTML-ENTITY DECODE  (R5 fix — must be the LAST pass on every user-facing string)
# Handles numeric (&#x27; &#39; &#38; &#34; &#60; &#62; &#160;) AND named
# (&amp; &quot; &lt; &gt; &nbsp; &apos;) entities so raw HTML entities never
# reach the renderer. Applied via _decode() at prop-finalization time.
# ---------------------------------------------------------------------------
def _decode(s: object) -> str:
    """html.unescape() wrapper — safe on None/non-str inputs, returns str."""
    if not s:
        return "" if s is None or s == "" else str(s)
    return _html_mod.unescape(str(s))


# --- Timeline archetype ids (must match studio/src/timeline/types.ts Archetype) ---
ARCH_HERO = "hero-title"
ARCH_CARD = "card-ui"
# The never-blank designed card for a cinematic/walkthrough/demo beat that gets no
# real footage on a $0/standard run (the blank-scenes fix). Shows the narrated
# point as kinetic motion-graphics instead of a flat solid color.
ARCH_EXPLAINER = "explainer-card"
# Card-treatment vocabulary (SHARED DATA CONTRACT with the Remotion ExplainerCard
# archetype). plan_job picks + honesty-guards these on scene["data"]; _shape_explainer
# only carries the surviving fields into the rendered props. The last three are
# DORMANT — the ExplainerCard renders them, but no selection logic emits them yet.
_CARD_TREATMENTS = {
    "icon-stat", "split-mosaic", "split-stat", "icon-headline",
    # DORMANT — render + validate only; no selection logic emits these yet.
    "big-number", "logo-wall", "feature-list",
}
# A produced walkthrough MP4 (Walk Agent capture) played INSIDE the branded studio
# composition, so the clip inherits Walk Studio overlays + per-scene VO. Used for a
# `walkthrough` role ONLY when a real clip exists; otherwise the role falls back to
# ARCH_EXPLAINER (the never-blank designed card) so a clip-less run is never blank.
ARCH_WALKTHROUGH = "walkthrough-player"
# A REAL captured website screenshot shown inside a brand-tinted browser card (the
# "here is the actual site" proof beat). Used for a `screenshot` role; the captured
# PNG is wired into data.imageSrc from runs/<id>/screenshots/. Falls back to the
# explainer card only if no image staged (the archetype itself has a never-blank floor).
ARCH_SCREENSHOT = "apple-screenshot"

# Plan-scene keys that may carry the produced walkthrough clip path (the producer
# writes `output_path`; some plans pre-stage it as `videoSrc`/`media_path`).
_WALKTHROUGH_CLIP_KEYS = ("videoSrc", "video_path", "output_path", "media_path", "clip_path")

# Number of brand feature cards the CardUi 2x2 grid renders.
CARD_COUNT = 4
# Max capability bullets the ExplainerCard renders.
EXPLAINER_BULLET_COUNT = 4


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _plan_scenes(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    return plan["scenes"] if isinstance(plan, dict) else plan


# ---------------------------------------------------------------------------
# ROBUSTNESS — copy-length guards for planner-output VARIABILITY (Super↔Ultra)
# ---------------------------------------------------------------------------
# The timeline is VO-driven: each scene's window is the span of the words spoken
# over it (build_timeline). A DENSER planner (Ultra/550B writes 14-18 word beats)
# therefore produces a LONGER film (the A/B Stripe run hit 33.1s on a 30s target),
# while a SPARSER planner (Super/120B, 8-13 word beats) under-fills it (23.6s).
# The planner-prompt's "2.0-2.6 words/sec, never exceed 3" rule is ADVISORY — the
# model does not reliably honor it. These guards ENFORCE it downstream so EITHER
# brain's plan renders as a clean ~target-second film with no VO clipping.
#
# Words-per-second the TTS ACTUALLY reads. Measured from real edge-tts alignments
# (runs/ab-stripe-*: 2.05-2.10 w/s incl. inter-word/sentence pauses) — markedly
# slower than the planner-prompt's 2.6 "speaking" target, because synthesis adds
# silence the prompt's rule ignores. Budget against the REAL rate so a condensed
# beat lands in the time it is actually given. A hair above the measured mean so we
# trim only genuinely over-long beats, never a beat already close to pace.
_VO_WORDS_PER_SEC = 2.15
# An absolute per-beat word ceiling: even a long scene must not narrate a wall of
# text (keeps any single beat readable / on-pace regardless of its duration_s). At
# ~2.15 w/s, 30 words ≈ 14s. D (Dennis 2026-07-02): raised 22 -> 30 so a read-heavy
# beat (a full testimonial pull-quote given a 13s read-time hold) can SPEAK to a clean
# stop instead of being clamped mid-sentence. The per-scene cap (duration_s * rate)
# still governs every SHORT beat, and the whole-film GLOBAL squeeze still caps the
# total VO — so only a genuinely long-read-time scene ever uses the extra room.
_VO_BEAT_MAX_WORDS = 30
# A per-beat FLOOR so condensing never strips a beat below a speakable line.
_VO_BEAT_MIN_WORDS = 6
# Hard ceiling for the split-layout SUPPORTING line (the muted secondary sentence in
# the left column, 28px, maxWidth ≈ leftColW-30 ≈ 630px ≈ ~2 lines). Both the derived
# (_supporting_line) and an explicit plan-authored supporting line are clamped here so
# a DENSE planner can't author a full sentence that overflows the box.
_SUPPORTING_MAX_CHARS = 84
# Tolerance on the GLOBAL VO word budget. The summed narration may reach
# target * words_per_sec * tol before the proportional squeeze bites. < 1.0 so the
# WHOLE-FILM VO holds a little UNDER the target's worth of words — the remaining
# time is the holds (titles/cards read past their VO) and pacing breath. This is the
# lever that pulls a DENSE Ultra plan (67 words ≈ 32.6s VO) back toward ~30s while
# leaving a SPARSE Super plan (39 words ≈ 18.6s VO) entirely untouched.
_VO_GLOBAL_TOL = 0.96


def _word_count(text: str) -> int:
    return len((text or "").split())


def _word_slice_clean(text: str, max_words: int) -> str:
    """Hard word-boundary slice to <= max_words, with the dangling-function-word /
    orphan-connector tail cleanup so it never ends mid-clause on a dangling
    connector. Uses (close to) the FULL budget — the complement to the clause clip,
    which can undershoot far. Drops a trailing comma so we never end on ", ...".
    """
    sliced = " ".join((text or "").split()[:max_words]).rstrip(",;:").strip()
    cleaned = _strip_dangling_tail(sliced)
    if _ends_on_orphan_connector(cleaned, was_cut=True):
        cleaned = _drop_orphan_connector_phrase(cleaned)
    return _strip_dangling_tail(cleaned) or sliced


def _condense_to_words(text: str, max_words: int) -> str:
    """Trim `text` to <= max_words, never mid-word, keeping CLOSE to the budget.

    Two candidates, take the one that USES THE BUDGET BEST (the longest that fits):
      1. A clause-boundary clip (_clip_to_clause) — cleanest, but can undershoot the
         word budget badly when the first clause is short (a 6-word clause for a
         13-word budget would WASTE more than half the scene's narration time).
      2. A hard word-slice to the budget with the dangling/orphan tail cleanup — uses
         (almost) the full budget so the beat still fills its scene.
    Prefer the clause clip ONLY when it keeps at least ~70% of the budget's words
    (a clean boundary worth the few dropped words); otherwise prefer the fuller
    word-slice so a dense beat is shortened to fit WITHOUT starving its scene.
    Never fabricates — only trims real narration."""
    t = (text or "").strip()
    if max_words <= 0 or _word_count(t) <= max_words:
        return t
    # ~6.2 chars/word (incl. spaces) over-estimates so _clip_to_clause has room.
    char_budget = int(max_words * 6.2)
    clause = _clip_to_clause(t, char_budget)
    clause_ok = bool(clause) and 2 <= _word_count(clause) <= max_words
    sliced = _word_slice_clean(t, max_words)
    sliced_ok = bool(sliced) and _word_count(sliced) >= 2

    # Keep the clause clip when it is BOTH valid AND not a heavy undershoot.
    if clause_ok and _word_count(clause) >= max(2, int(round(max_words * 0.7))):
        return clause
    if sliced_ok:
        return sliced
    if clause_ok:
        return clause
    return t


def _condense_vo_beats(plan: Dict[str, Any], fps: int = 30) -> List[Dict[str, Any]]:
    """Return the plan's VO beats with each spoken line capped to fit its scene's
    pacing budget AND the whole film's target duration. The core copy-length guard
    that makes the framework robust to a DENSE (Ultra) vs SPARSE (Super) planner.

    Two budgets, the tighter wins per beat:
      1. PER-SCENE: words <= duration_s * _VO_WORDS_PER_SEC (clamped to a min/max).
         A beat with no duration_s gets the absolute max ceiling.
      2. GLOBAL: if the summed words would overrun target_duration_s * w/s (× a small
         tolerance), scale every beat's budget down proportionally so the TOTAL VO
         fits ~target. This is what reins a dense 5-scene Ultra plan back to ~30s.

    A SPARSE plan (Super) is left ENTIRELY UNCHANGED — its beats are already under
    budget, so condensing is a no-op and the duration-fill side (build_timeline) does
    the work of reaching target. Mutates beat dicts in place (and returns the list)
    so the caller's `plan` carries the condensed beats into align_vo/cost/console.
    """
    vo = plan.get("voiceover") or {}
    beats = vo.get("beats") or []
    if not beats:
        return beats
    scenes_by_id = {s.get("id"): s for s in _plan_scenes(plan)}
    target_s = float((plan.get("job") or {}).get("target_duration_s") or 0.0)

    # Per-scene word budget = the words that fit in the scene's EVENTUAL rendered
    # window, NOT its (possibly undersized) plan duration_s. A sparse planner (Super)
    # routinely sets tiny duration_s (3,4,5,3 = 15s on a 30s target); build_timeline
    # STRETCHES those scenes to fill the target, so budgeting off the raw duration_s
    # would over-condense a beat that will actually be given far more screen time.
    # Use max(duration_s, fair share of target) as each scene's effective time so the
    # cap only trims a beat that is dense RELATIVE TO THE TIME IT WILL GET. The GLOBAL
    # squeeze below is the real lever that pulls a dense plan down to target.
    n = max(1, len(beats))
    fair_share_s = (target_s / n) if target_s > 0 else 0.0
    per_budgets: List[int] = []
    protected = set()
    for i, b in enumerate(beats):
        sc = scenes_by_id.get(b.get("scene_id")) or {}
        # PULL-QUOTE / testimonial: SPEAK THE FULL QUOTE. The card renders the whole quote
        # (data.quote), so the VO must too — never trim a testimonial to the word cap or the
        # voice ends mid-thought while the card still shows the rest (Dennis 2026-07-02). The
        # read-time hold already sizes the scene to fit it, and ElevenLabs speaks faster than
        # the condense's conservative estimate, so a real testimonial lands inside its hold.
        if str((sc.get("data") or {}).get("quote") or "").strip():
            per_budgets.append(_word_count(b.get("text", "")))
            protected.add(i)
            continue
        try:
            dur = float(sc.get("duration_s") or 0.0)
        except (TypeError, ValueError):
            dur = 0.0
        eff_s = max(dur, fair_share_s)
        if eff_s > 0:
            budget = int(round(eff_s * _VO_WORDS_PER_SEC))
            budget = max(_VO_BEAT_MIN_WORDS, min(_VO_BEAT_MAX_WORDS, budget))
        else:
            budget = _VO_BEAT_MAX_WORDS
        per_budgets.append(budget)

    # GLOBAL squeeze: the words that fit the WHOLE film at the real TTS rate. If the
    # narration would overrun target * w/s * tol, scale every per-beat budget down by
    # the SAME factor so the total VO fits ~target (the picture's holds + pacing fill
    # the rest). Only bites on a genuinely DENSE plan (Ultra). A sparse plan (Super)
    # already sits under this budget, so the squeeze is a no-op and every beat keeps
    # its full, already-short narration. Distribute the squeeze on EXCESS over the
    # min floor so a long beat gives up more words than a short one.
    if target_s > 0:
        global_word_budget = target_s * _VO_WORDS_PER_SEC * _VO_GLOBAL_TOL
        # What we would actually narrate per beat under the per-scene cap.
        planned = [min(per_budgets[i], _word_count(b.get("text", "")))
                   for i, b in enumerate(beats)]
        planned_total = sum(planned)
        if planned_total > global_word_budget and planned_total > 0:
            floor_total = _VO_BEAT_MIN_WORDS * n
            excess_budget = max(0.0, global_word_budget - floor_total)
            excess_total = max(1, planned_total - floor_total)
            scale = excess_budget / excess_total
            per_budgets = [
                max(_VO_BEAT_MIN_WORDS,
                    _VO_BEAT_MIN_WORDS + int(round((p - _VO_BEAT_MIN_WORDS) * scale)))
                for p in planned
            ]
            # A protected testimonial keeps its FULL quote even under the global squeeze —
            # the other beats absorb the compression rather than clipping the quote.
            for i in protected:
                per_budgets[i] = _word_count(beats[i].get("text", ""))

    for b, budget in zip(beats, per_budgets):
        text = str(b.get("text") or "").strip()
        if not text:
            continue
        if _word_count(text) > budget:
            condensed = _condense_to_words(text, budget)
            if condensed and _word_count(condensed) >= 2:
                b["text"] = condensed
    return beats


# ---------------------------------------------------------------------------
# VO<->VISUAL GROUNDING — align a screenshot scene's SPOKEN beat to the page it shows
# ---------------------------------------------------------------------------
# The planner writes each screenshot scene's VO from the run EMPHASIS (PRE-capture),
# while the screenshot + its distilled headline come from whatever page the capture
# step actually reached (POST-capture). When those disagree, the on-screen headline
# (already surface-aligned by _shape_screenshot's R5 pass) and the spoken VO contradict
# each other on the SAME scene — e.g. the headline reads "Pricing & Fees" (the /pricing
# page that got captured) while the voice says "...recurring billing, fraud protection,
# and instant payouts" (the feature the planner emphasized). The audio is synthesized
# in align_vo BEFORE the captured surface is known, so the headline got fixed but the
# voice did not. This pass closes that gap: AFTER capture (the manifest is on disk) and
# BEFORE align_vo synthesizes the audio, it re-grounds each screenshot scene's beat to
# describe the surface actually shown, so narration and visual tell ONE coherent story.
#
# Surface-grounded VO sentence templates, keyed by the captured surface NOUN
# (_surface_aligned_headline distills the manifest <title>/label down to this same
# noun, so the spoken line and the on-screen headline name the SAME thing). The brand
# wordmark is folded in at compose time. Kept natural — a real value-prop line about
# that page, never "here is the pricing page" capture-narration.
_SURFACE_VO_TEMPLATES = {
    "pricing": "See {brand}'s clear, transparent pricing built for teams of every size.",
    "the dashboard": "Get a clear, real-time view of everything that matters from the {brand} dashboard.",
    "dashboard": "Get a clear, real-time view of everything that matters from the {brand} dashboard.",
    "the app": "Manage everything from one place inside the {brand} app.",
    "payments": "Accept payments from customers worldwide with {brand}.",
    "checkout": "Give customers a fast, secure checkout built and hosted by {brand}.",
    "billing": "Run subscriptions, invoicing, and recurring billing with {brand} Billing.",
    "the docs": "Get up and running fast with {brand}'s clear, developer-first documentation.",
    "developers": "Build on {brand}'s developer-first APIs in just a few lines of code.",
    "the api": "Integrate {brand}'s powerful API with just a few lines of code.",
    "integrations": "Connect the tools you already use with {brand}'s integrations.",
    "analytics": "Understand your business with built-in analytics and reporting from {brand}.",
    "calendar": "Plan your day and keep every event in sync with {brand} Calendar.",
    "templates": "Start fast with ready-made templates built into {brand}.",
    "security": "Keep your data safe with enterprise-grade security from {brand}.",
}

# Tokens that KEEP their capitalization when a Title-Case page phrase is folded into a
# lower-case sentence position (acronyms / proper-noun-ish all-caps). Everything else
# is lowercased so "Financial Infrastructure" -> "financial infrastructure" reads as
# running prose, not a mid-sentence Title Case wall.
_KEEP_CASE_RE = re.compile(r"^[A-Z0-9]{2,}$|^[A-Z][a-z]*[A-Z]")  # API, SDK, CRM, PayPal


def _phrase_to_sentence_case(phrase: str) -> str:
    """Lowercase a Title-Case page phrase for use INSIDE a sentence, preserving
    acronyms / camel-cased proper tokens ("Pricing & Fees" -> "pricing & fees";
    "API Reference" -> "API reference"). Empty in -> empty out."""
    p = (phrase or "").strip()
    if not p:
        return ""
    out = [w if _KEEP_CASE_RE.match(w) else w.lower() for w in p.split()]
    return " ".join(out)


# Surface keywords (substring-matched in the captured page <title> phrase) -> the
# normalized surface NOUN key into _SURFACE_VO_TEMPLATES. Lets a generically-labelled
# capture ("route") still resolve the right template from its page title ("Pricing &
# Fees" -> "pricing"). Order matters: more specific keys first.
_SURFACE_PHRASE_KEYWORDS = (
    ("pricing", "pricing"), ("price", "pricing"), ("plans", "pricing"),
    ("dashboard", "the dashboard"), ("checkout", "checkout"),
    ("billing", "billing"), ("invoic", "billing"), ("subscription", "billing"),
    ("payment", "payments"), ("docs", "the docs"), ("documentation", "the docs"),
    ("developer", "developers"), ("api", "the api"),
    ("integration", "integrations"), ("analytic", "analytics"),
    ("report", "analytics"), ("calendar", "calendar"),
    ("template", "templates"), ("security", "security"),
)


def _surface_noun_from_phrase(phrase: str) -> str:
    """Detect a known surface NOUN inside a captured page-title phrase, or "".

    A capture often labels an emphasized page generically (e.g. label "route") while
    its <title> carries the real surface name ("Pricing & Fees"). This maps such a
    phrase to the surface key the VO templates use, so the spoken line names the page
    even when the capture-target label was generic. "" when no known surface matches."""
    p = (phrase or "").lower()
    if not p:
        return ""
    for kw, noun in _SURFACE_PHRASE_KEYWORDS:
        if kw in p:
            return noun
    return ""


def _surface_grounded_vo(surface_noun: str, surface_phrase: str,
                         brand: Dict[str, Any]) -> str:
    """A natural VO sentence that DESCRIBES the captured surface, or "".

    `surface_noun` is the normalized surface key (e.g. "pricing", "the dashboard");
    `surface_phrase` is the display headline _surface_aligned_headline produced for the
    SAME shot (e.g. "Pricing & Fees", "Dashboard"). We keep the spoken line about the
    same subject as the on-screen headline so voice and picture agree.

    Source priority (honest — only real brand/surface text, never invented features):
      1. A template keyed by the surface noun, with the brand wordmark folded in.
      2. A generic, surface-named line built from the display phrase when the noun is
         unmapped but the page is still specifically named ("See {brand}'s {phrase}.").
    Returns "" for a generic/home surface (the caller then keeps the planner's beat)."""
    brand_name = (brand.get("wordmark") or brand.get("brand")
                  or brand.get("name") or "").strip()
    key = (surface_noun or "").strip().lower()
    tmpl = _SURFACE_VO_TEMPLATES.get(key)
    if tmpl:
        # Fold the brand in; if we have no brand name, drop the possessive/brand token
        # gracefully so the line still reads ("See clear, transparent pricing...").
        if brand_name:
            line = tmpl.format(brand=brand_name)
        else:
            line = (tmpl.replace("{brand}'s ", "").replace(" {brand}", "")
                    .replace("{brand} ", "").replace("{brand}", "").strip())
            line = re.sub(r"\s{2,}", " ", line).strip()
            if line and line[0].islower():
                line = line[0].upper() + line[1:]
        return line.strip()
    # Unmapped but specifically-named surface: build a clean generic line from the
    # display phrase so the voice still names what's on screen (no capture-narration).
    phrase = (surface_phrase or "").strip()
    if phrase and brand_name and not _is_ui_nav_label(phrase) \
            and not _is_prompt_artifact(phrase):
        # Lead with a richer, natural frame so the line is a real value-prop sentence
        # (>= 4 words) about the page on screen, never bare page-narration. Sentence-case
        # the phrase so a Title-Case page name folds into the sentence ("...Notion's
        # api reference...") while acronyms/proper tokens keep their case.
        head = _phrase_to_sentence_case(phrase)
        return f"Take a closer look at {brand_name}'s {head}.".strip()
    return ""


def _homepage_grounded_vo(home_phrase: str, brand: Dict[str, Any]) -> str:
    """A brand-level homepage VO line built from the home page's headline phrase, or "".

    Used only when the planner put a NARROW feature beat on the home shot that drifts
    from the homepage headline. Keeps the spoken line agreeing with the on-screen
    home headline (both derive from the same captured <title>/tagline). Honest — it
    only reuses the real home headline phrase + the brand wordmark, never invents.

    Two shapes, chosen by the phrase:
      - a SHORT noun phrase ("Financial Infrastructure") -> "Stripe is the financial
        infrastructure that powers businesses of all sizes." (frame supplies the verb);
      - a phrase that ALREADY reads like a value-prop clause ("The AI workspace that
        works for you") -> "Notion is the AI workspace that works for you." (use it
        directly — wrapping it would double the article and ramble).
    A leading article on the phrase is stripped so we never produce "is the the …".
    Returns "" when there is no usable phrase."""
    brand_name = (brand.get("wordmark") or brand.get("brand")
                  or brand.get("name") or "").strip()
    phrase = (home_phrase or "").strip()
    if not phrase or _is_ui_nav_label(phrase) or _is_prompt_artifact(phrase):
        return ""
    head = _phrase_to_sentence_case(phrase)
    # Strip a leading article so the "{brand} is the {head}" frame never doubles it.
    head_noart = re.sub(r"^(the|a|an)\s+", "", head, flags=re.IGNORECASE).strip()
    if not head_noart:
        return ""
    subj = brand_name or "It"
    # A multi-word phrase that already carries a verb / relative clause is a full
    # value-prop — use it directly ("{brand} is the {phrase}.") rather than wrapping it
    # in the "...that powers businesses..." frame (which would ramble + risk a condense
    # clip). _looks_like_headline detects the verb/clause shape.
    if _word_count(head_noart) >= 4 and _looks_like_headline(head_noart):
        return f"{subj} is the {head_noart}.".strip()
    # Short noun phrase: supply the value-prop frame so the line stands on its own.
    return f"{subj} is the {head_noart} that powers businesses of all sizes.".strip()


def _beat_references_surface(beat_text: str, surface_noun: str,
                             surface_phrase: str) -> bool:
    """True when the VO beat ALREADY talks about the captured surface, so we leave it
    alone (no regression on a coherent plan whose VO matches the page). Word-overlap
    test against the surface noun + the display phrase's content words."""
    bt = {w for w in re.findall(r"[a-z]+", (beat_text or "").lower()) if len(w) > 2}
    if not bt:
        return False
    surf_words = set()
    for src in (surface_noun, surface_phrase):
        surf_words |= {w for w in re.findall(r"[a-z]+", (src or "").lower())
                       if len(w) > 2 and w not in _PUNCH_STOPWORDS}
    if not surf_words:
        return False
    return bool(bt & surf_words)


def _ground_screenshot_vo_beats(plan: Dict[str, Any], out_dir: str,
                                brand: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Re-ground each screenshot scene's VO beat to the SURFACE actually captured, so
    the spoken line and the (surface-aligned) on-screen headline agree.

    Runs AFTER capture (the screenshots manifest exists on disk) and BEFORE align_vo
    synthesizes the audio, inside run_pipeline. For each `screenshot` scene (mapped in
    order to the Nth captured shot):
      - derive the captured SURFACE NOUN + display phrase from the shot's <title>/label
        (the SAME machinery _shape_screenshot uses for the headline);
      - if the surface is GENERIC (home / unnamed inner page) -> leave the beat (the VO
        already speaks to the brand/homepage);
      - if the beat ALREADY references that surface -> leave it (coherent already);
      - otherwise REPLACE the beat text with a natural surface-grounded value-prop line
        so the narration describes what's on screen.

    Honest + additive: only the screenshot beats can change; bookend (title) and
    walkthrough beats are NEVER touched. A surface with no grounded line, or any
    failure, leaves the original beat intact. Mutates beats in place (and returns the
    list) so align_vo/cost/console all see the grounded copy."""
    vo = plan.get("voiceover") or {}
    beats = vo.get("beats") or []
    if not beats or not out_dir:
        return beats
    try:
        shots = _load_screenshot_manifest(out_dir)
    except Exception:
        return beats
    if not shots:
        return beats

    scenes = _plan_scenes(plan)
    # Map each screenshot scene (in plan order) -> its captured shot (Nth shot).
    screenshot_ids: List[str] = []
    for s in scenes:
        if str(s.get("type") or s.get("role") or "").strip().lower() == "screenshot":
            screenshot_ids.append(s.get("id"))
    if not screenshot_ids:
        return beats
    shot_for_id = {sid: shots[i] for i, sid in enumerate(screenshot_ids)
                   if i < len(shots)}

    wordmark = (brand.get("wordmark") or brand.get("brand")
                or brand.get("name") or "").strip()
    for b in beats:
        sid = b.get("scene_id")
        shot = shot_for_id.get(sid)
        if not shot:
            continue
        shot_title = str(shot.get("title") or "").strip()
        shot_label = str(shot.get("label") or "").strip()
        lbl = re.sub(r"^mock-", "", shot_label.lower()).strip()
        # HOME / homepage scene: the home page IS the brand, so a BRAND-LEVEL beat is
        # right here (the value-prop / "global commerce" line). We DON'T impose a
        # surface noun — but if the planner put a NARROW feature line on the home shot
        # that drifts from the home headline (e.g. "...enables any billing model" over
        # the homepage whose headline reads "Financial Infrastructure"), re-ground it to
        # the brand-level homepage line the headline is built from, so voice + picture
        # agree on the first screenshot too. A beat that already speaks to the homepage
        # headline is left untouched.
        if lbl in ("home", "homepage", ""):
            home_phrase = _surface_aligned_headline(shot_title, shot_label, brand,
                                                    avoid=wordmark, limit=38)
            home_line = _homepage_grounded_vo(home_phrase, brand)
            text = str(b.get("text") or "").strip()
            if (home_line and _word_count(home_line) >= 4 and home_phrase
                    and not _beat_references_surface(text, home_phrase, home_phrase)):
                b["text"] = home_line
            continue
        # The display phrase the headline will show for this shot (home/generic -> "").
        surface_phrase = _surface_aligned_headline(shot_title, shot_label, brand,
                                                   avoid=wordmark, limit=38)
        if not surface_phrase:
            continue  # generic/unnamed inner page: keep the planner's beat (no regression)
        # The normalized surface NOUN (pricing / the dashboard / ...) for the template.
        # Resolve from BOTH the capture-target label AND the captured page <title>
        # phrase: capture often labels an emphasized page generically ("route") while
        # its <title> names the surface ("Pricing & Fees"), so the phrase carries the
        # real noun. Prefer a mapped label noun; else detect a known surface keyword
        # inside the phrase; else fall back to the phrase itself.
        surface_noun = (_SURFACE_LABEL_WORDS.get(lbl, "")
                        or _surface_noun_from_phrase(surface_phrase)
                        or surface_phrase.lower())
        text = str(b.get("text") or "").strip()
        # Already coherent? (VO names the surface) -> leave it untouched.
        if _beat_references_surface(text, surface_noun, surface_phrase):
            continue
        grounded = _surface_grounded_vo(surface_noun, surface_phrase, brand)
        if grounded and _word_count(grounded) >= 4:
            b["text"] = grounded
    return beats


def _wants_kinetic_open(vibe_label: str, vibe_motion: str, tie_break: int) -> bool:
    """Per-brand OPENING style (Design-Fit variety): a bold/energetic brand opens with
    the animated kinetic-statement (word-rise + accent emphasis); an enterprise/calm
    brand keeps the clean wordmark lockup; an unknown vibe falls to the hash tie-break
    so different unknown brands still vary."""
    if vibe_label in ("startup-bold", "consumer-playful") or vibe_motion == "energetic":
        return True
    if vibe_label in ("enterprise", "technical-precise") or vibe_motion == "calm":
        return False
    # Unknown/unclassifiable vibe -> the SAFE, established clean wordmark opening
    # (no signal is not a "tie"). The hash tie-break (`tie_break`) is reserved for
    # genuine content-fit ties in Phase 2 routing.
    return False


def _open_variant_for(brand: Dict[str, Any]) -> int:
    """Deterministic per-brand tie-break for the opening style. Uses hashlib (NOT
    hash(), which is salted per-process and would differ between the worker's runs)."""
    import hashlib
    seed = str((brand or {}).get("host") or (brand or {}).get("name")
               or (brand or {}).get("wordmark") or "brand").lower()
    return int(hashlib.sha1((seed + "|open").encode()).hexdigest(), 16) % 2


def _scene_role(scene: Dict[str, Any]) -> str:
    """The classifier key for the registry: explicit `role`, else `type`."""
    return str(scene.get("role") or scene.get("type") or "").strip().lower()


def _scene_by_id(scenes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    return {s.get("id"): s for s in scenes}


# ---------------------------------------------------------------------------
# STYLE REGISTRY  (data shapers per archetype, then the Style entries)
# ---------------------------------------------------------------------------
# Shapers receive (plan_scene, brand_theme) and return a SceneData dict for the
# archetype. They prefer explicit copy in scene["data"], falling back to brand.
# A tagline sourced from a raw <meta name="description"> is hard-cut at 80 chars by
# brand_extract and routinely ends MID-WORD ("Try Shopify free… Get more than ecomme",
# "easy, safe and re"). Such a fragment must NEVER be used as a title/headline. We
# detect it and prefer a clean, COMPLETE source instead.
def _is_truncated_meta(text: str) -> bool:
    """True when `text` looks like a truncated meta-description fragment unsuitable
    as a headline: an explicit ellipsis, OR a long-ish string whose final token is
    cut mid-word (no terminal punctuation and the tail isn't a clean word ending).
    Conservative — short, complete phrases (real taglines) are NOT flagged."""
    t = (text or "").strip()
    if not t:
        return False
    if t.endswith(("…", "...")) or "…" in t:
        return True
    # brand_extract caps at 80 chars; a fragment at/near that length with no terminal
    # punctuation is almost certainly a mid-word cut of a sentence-y meta description.
    if len(t) >= 70 and not t.rstrip().endswith((".", "!", "?", '"', "'")):
        # also true mid-word giveaways: ends on a lone 1-2 char tail like "re"/"ecomme"
        # after a longer sentence. Treat any 70+ char unpunctuated meta as truncated.
        return True
    # Mid-WORD chop guard: works even on shorter strings where the last "word" looks
    # like a word fragment (a partial token produced by slicing mid-word).
    # Heuristic: last token is all-alphabetic, 1-4 chars, NOT a known short complete
    # English word/acronym, AND is preceded by a longer sentence (3+ words before it).
    # This catches "…all in Webf" where "Webf" is a 4-char partial brand name.
    if _ends_mid_word(t):
        return True
    return False


# Short complete English words/acronyms that are valid final tokens (do NOT flag
# as mid-word fragments). Extend as needed, but keep it conservative.
_KNOWN_SHORT_WORDS = frozenset((
    "ai", "ml", "ui", "ux", "api", "sdk", "saas", "b2b", "b2c", "erp", "crm",
    "on", "in", "at", "by", "up", "to", "do", "go", "no", "so", "is", "it",
    "all", "any", "app", "can", "you", "for", "now", "pay", "buy", "new",
    "top", "get", "run", "try", "use", "see", "set", "add", "let", "cut",
    "put", "out", "off", "one", "two", "the", "and", "but", "not", "yet",
    "an", "a",
))


def _ends_mid_word(text: str) -> bool:
    """True when `text` appears to end mid-word — the last token looks like a
    partial prefix, not a complete English word.

    Conservative heuristic: last alphabetic-only token is 1-4 chars, NOT in the
    known-short-words allowlist, AND the string has at least 3 words before it
    (so a genuine 1-word brand name like "Webf" is not flagged when it IS the
    brand rather than a mid-word cut).
    """
    if not text:
        return False
    # Only applies when the string ends on a plain letter (no punctuation tail).
    if not text[-1].isalpha():
        return False
    words = text.split()
    if len(words) < 2:
        return False  # single-word strings: can't distinguish brand from fragment
    last = words[-1].lower()
    # If it's a known short complete word, it's fine.
    if last in _KNOWN_SHORT_WORDS:
        return False
    # Flag short (1-4 char) all-alpha tokens that aren't in our allowlist when
    # there are at least 2 words before them (i.e., sentence context exists).
    if len(last) <= 4 and last.isalpha() and len(words) >= 3:
        return True
    return False


def _is_ui_nav_label(text: str) -> bool:
    """True when `text` is a UI/nav-label string scraped from interactive chrome,
    NOT a real brand headline or tagline.

    Detects two patterns:
      (a) Explicit known UI-chrome phrases: "Added to Cart", "New Arrivals",
          "Become a host", "Homes on", "What's happening", "Sign in", "Log in",
          "Sign up", "New Arrivals", "Shop Now", etc.
      (b) Two nav-tab items joined by " · " (e.g. "Homes on Airbnb · Become a host",
          "What's happening · Enable any billing model") — a dot-bullet join is a
          dead giveaway this is a tab-bar or breadcrumb, never a real headline.

    Conservative: doesn't flag genuine taglines that happen to share a word.
    """
    t = (text or "").strip()
    if not t:
        return False
    # (b) Nav-tab join: 2+ segments separated by a rail separator — middot/bullet/
    # pipe (with optional spaces) or a spaced en/em-dash. A brand tagline never uses
    # these to join clauses; it's a UI navigation pattern. Reject the WHOLE string
    # when it splits into a multi-segment join (regardless of segment content), AND
    # reject when ANY segment is itself a nav label.
    parts = [p.strip() for p in re.split(r"\s*[·•|]\s*|\s+[–—]\s+", t) if p.strip()]
    if len(parts) >= 2:
        return True

    # (a) Single-segment nav/section label (no separator): gendered store category,
    # support rail, leading nav-action token, or a known UI-chrome phrase.
    return _is_nav_label_segment(t)


# Nav SECTION / category labels (single segment) that are navigation destinations,
# not headlines: gendered store categories, support/account rails, "find a …"
# actions. Mirrors brand_extract._NAV_SECTION_EXACT so a feature label scraped as a
# nav item ("Men's Shoes", "Help Center", "Find a co-host") is rejected at render.
_NAV_SECTION_EXACT = frozenset((
    "men's shoes", "mens shoes", "women's shoes", "womens shoes",
    "men's clothing", "women's clothing", "kids' shoes", "kids shoes",
    "apparel & accessories", "apparel and accessories", "accessories",
    "customer favorites", "customer favourites", "fan favorites",
    "help center", "help centre", "support center", "contact support",
    "find a co-host", "find a cohost", "find a store", "find a host",
    "all products", "all collections", "shop by category", "browse all",
    "gift guide", "gift guides", "size guide", "size chart",
    "latest news", "latest posts", "latest stories",
    "popular", "featured", "collections", "categories",
))

_NAV_LEADING_TOKENS = (
    "find a ", "find an ", "shop ", "browse ", "explore ", "discover ",
    "view all ", "see all ", "go to ", "visit the ", "back to ",
)

# Known UI-chrome phrases — matched as a substring so "Homes on Airbnb" is caught.
_UI_CHROME_PHRASES = (
    "added to cart", "new arrivals", "become a host", "homes on",
    "what's happening", "sign in", "log in", "sign up", "log out", "sign out",
    "shop now", "learn more", "get started", "view all", "see all", "load more",
    "cookie settings", "privacy policy", "terms of service", "skip to content",
)


def _is_nav_label_segment(text: str) -> bool:
    """True when a SINGLE segment (no rail separator) is a UI/nav-section label
    rather than a real headline: a gendered store category, a support/account rail,
    a leading nav-action token, or a known UI-chrome phrase. Conservative — short
    section labels only; genuine taglines are not flagged."""
    low = (text or "").strip().lower().strip(" .!·•|-—–")
    if not low:
        return False
    if low in _NAV_SECTION_EXACT:
        return True
    if any(low.startswith(tok) for tok in _NAV_LEADING_TOKENS):
        return True
    for phrase in _UI_CHROME_PHRASES:
        if phrase in low:
            return True
    return False


def _is_prompt_artifact(text: str) -> bool:
    """True when `text` contains instruction/stage-direction fragments that leaked
    from the LLM prompt into a rendered string.

    Catches patterns like:
      - "Show call-to-action: ..." (the notion artifact: 'Show call-to-action: 'Start')
      - "Display the ..."
      - "Animated ..."  (when used as a stage direction)
      - "Present the ..."
      - A leading verb-colon like "Scene:", "Title:", "CTA:" etc.
      - Generic instruction openings: "Insert ", "Place ", "Add a "

    Conservative: only flags strings where the WHOLE string looks like an
    instruction, not just strings that contain any of these words.
    """
    t = (text or "").strip()
    if not t:
        return False
    lower = t.lower()

    # Verb-colon prefixes — instruction fragments that escaped into display copy.
    _INSTRUCTION_VERB_COLONS = (
        "show call-to-action:",
        "show cta:",
        "display the ",
        "display a ",
        "present the ",
        "present a ",
        "animate ",
        "animated ",
        "insert ",
        "add a cta",
        "add cta",
        "scene:",
        "title:",
        "subtitle:",
        "cta:",
        "headline:",
        "caption:",
    )
    for prefix in _INSTRUCTION_VERB_COLONS:
        if lower.startswith(prefix):
            return True

    # Also catch mid-string instruction fragments that are a dead giveaway:
    # e.g. "Show call-to-action" anywhere in the string.
    _INSTRUCTION_SUBSTRINGS = (
        "call-to-action:",
        "call to action:",
    )
    for sub in _INSTRUCTION_SUBSTRINGS:
        if sub in lower:
            return True

    return False


# Fancy / non-ASCII hyphen variants that a model (or a meta-description scrape) may
# emit in place of an ASCII "-": non-breaking hyphen U+2011, figure dash U+2012,
# en/em dash U+2013/U+2014, horizontal bar U+2015, minus sign U+2212. Normalizing
# these to "-" lets a single phrase set ("call-to-action") match regardless of which
# hyphen the source used ("call‑to‑action" with U+2011, "call—to—action" with em-dash).
_FANCY_HYPHENS = "‐‑‒–—―−"
_HYPHEN_NORM_RE = re.compile("[" + _FANCY_HYPHENS + "]")


def _normalize_hyphens(text: str) -> str:
    """Fold every fancy-hyphen codepoint to an ASCII '-' so phrase matching is robust
    to the unicode-hyphen variants a model emits ("call‑to‑action" → "call-to-action")."""
    return _HYPHEN_NORM_RE.sub("-", text or "")


# Self-referential META-DESCRIPTION phrases: a string that DESCRIBES the CTA/closing
# card ("a call-to-action card urging users…") instead of BEING the CTA copy addressed
# to the viewer. These leak when the LLM planner's closing beat is a STAGE DIRECTION
# rather than a line of copy. plan_job's `_degut_stage_direction_beats` (R7-G3) caught
# the "Show call-to-action:" verb-colon form but NOT this descriptive phrasing — so
# style_fill is the LAST line of defense on the rendered CTA. Hyphen-normalized + lower.
_CTA_META_DESCRIPTION_PHRASES = (
    "call-to-action",          # "call-to-action card", "closing call-to-action…"
    "call to action",          # spaced form (no hyphen at all)
    "closing card",
    "closing call",            # "Closing call-to-action card…"
    "urging users",            # "…card urging users to sign up"
    "urging the user",
    "urging viewers",
    "card urging",
    "stage direction",
    "using the brand",         # "Call-to-action card using the brand color"
    "brand color",             # "…using the brand color"
    "brand colour",
    "the wordmark",            # "Closing card with the wordmark"
    "cta card",
    "the cta",                 # "Show the CTA"
    "closing scene",
    "closing beat",
    "final card",
    "outro card",
)

# A meta-description often OPENS with a stage-direction verb + a noun that names the
# card itself ("Closing …", "Show …", "Display …", "Animate …"). When a candidate CTA
# starts with one of these AND describes the card (rather than addressing the viewer
# with an imperative product action), it is a stage direction, not real CTA copy.
_CTA_STAGE_OPENERS = (
    "closing", "close ", "show ", "display ", "displays ", "animate ",
    "animated ", "present ", "presents ", "render ", "renders ", "reveal ",
    "fade ", "fades ", "cut to", "end on", "ends on", "end card", "wrap ",
)
# Nouns that, when they follow a stage-opener, confirm the string is describing the
# card/scene rather than telling the viewer to do something ("Closing card…",
# "Show the call-to-action…", "Display the wordmark…").
_CTA_CARD_NOUNS = (
    "card", "call-to-action", "call to action", "cta", "scene", "wordmark",
    "title", "lockup", "screen", "frame", "logo", "tagline", "the brand",
)


def _is_cta_stage_direction(text: str) -> bool:
    """True when `text` is a self-referential STAGE-DIRECTION / meta-description of the
    closing CTA card rather than real CTA copy addressed to the viewer.

    Catches the leaked-planner-beat class that R7-G3's sanitizer missed:
      - "Closing call‑to‑action card urging users"          (U+2011 hyphens)
      - "Call-to-action card using the brand color"
      - "Closing card with the wordmark"
      - "Show the CTA"

    Robust to fancy unicode hyphens (U+2010–U+2015, U+2212) and case. Two signals:
      (1) the string CONTAINS a meta-description phrase that names the card/CTA/scene
          ("call-to-action", "closing card", "urging users", "the wordmark", "cta card",
          "using the brand", "brand color", "stage direction", "the cta", …), OR
      (2) the string OPENS with a stage-direction verb ("Closing"/"Show"/"Display"/
          "Animate"/…) AND a card-noun ("card"/"call-to-action"/"wordmark"/…) appears,
          i.e. it directs the card rather than addressing the viewer.

    Conservative: a REAL imperative CTA addressed to the viewer ("Shop Allbirds",
    "Begin your free trial", "Start your trip on Tripadvisor", "Visit theverge.com",
    "Start accepting payments") contains none of these phrases and does not open with a
    card-directing stage verb, so it is NOT flagged.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    norm = _normalize_hyphens(raw).lower()
    # (1) Contains a meta-description phrase that names the card / CTA / scene.
    for phrase in _CTA_META_DESCRIPTION_PHRASES:
        if phrase in norm:
            return True
    # (2) Opens with a stage-direction verb + a card-noun somewhere in the string.
    for opener in _CTA_STAGE_OPENERS:
        if norm.startswith(opener):
            if any(noun in norm for noun in _CTA_CARD_NOUNS):
                return True
            break
    return False


# Capture / screenshot STAGE-DIRECTION phrases: a string that DESCRIBES the
# screenshot SHOT ("Real captured homepage … in a branded browser card") rather
# than the PRODUCT value-prop. The planner-prompt forbids these in the VO, but a
# screenshot scene's `brief` is itself this kind of camera/capture direction — so it
# must never leak into the on-screen headline. Hyphen-normalized + lowercased.
_CAPTURE_STAGE_PHRASES = (
    "captured homepage", "captured home page", "captured key page",
    "captured view", "captured page", "captured site", "captured website",
    "real captured", "screenshot of", "screen shot of", "browser card",
    "branded browser", "in a browser", "the real site", "the real website",
    "real website of", "real site of", "homepage of", "home page of",
    "key page of", "inner page of", "landing page of",
)
# Stage-opener verbs that, with a capture/shot noun, confirm a screenshot direction.
_CAPTURE_STAGE_OPENERS = (
    "real captured", "captured", "screenshot", "screen shot", "show the real",
    "showing the", "display the", "capture the", "the homepage", "the home page",
    "the inner page", "the landing page", "the key page",
)
_CAPTURE_SHOT_NOUNS = (
    "homepage", "home page", "screenshot", "browser card", "browser", "site",
    "website", "page", "capture", "view",
)


def _is_capture_stage_direction(text: str) -> bool:
    """True when `text` is a screenshot/capture STAGE-DIRECTION describing the SHOT
    ("Real captured homepage of The Verge in a branded browser card") rather than a
    grounded product value-prop. Used to keep a screenshot scene's camera-direction
    `brief` out of the on-screen headline.

    Two signals (hyphen-normalized, lowercased):
      (1) the string CONTAINS a capture/shot meta-phrase ("real captured",
          "browser card", "homepage of", "the real site", …), OR
      (2) it OPENS with a capture verb AND a shot-noun appears somewhere.
    Conservative: a real value-prop ("Breaking tech news, in-depth reviews …")
    contains none of these and is NOT flagged.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    norm = _normalize_hyphens(raw).lower()
    for phrase in _CAPTURE_STAGE_PHRASES:
        if phrase in norm:
            return True
    for opener in _CAPTURE_STAGE_OPENERS:
        if norm.startswith(opener):
            if any(noun in norm for noun in _CAPTURE_SHOT_NOUNS):
                return True
            break
    return False


def _is_fragment_subtitle(text: str) -> bool:
    """True when `text` is an unusable subtitle/tagline fragment that must be DROPPED.

    Rejects strings that are clearly a mid-sentence scrape artifact rather than a
    complete brand tagline:
      (a) Starts with a lowercase letter — a mid-sentence fragment (e.g. "store they
          line up for"). Real taglines are title-cased or sentence-cased.
      (b) Ends on a preposition, article, coordinating conjunction, or relative
          pronoun — an open clause that was truncated (e.g. "store they line up for",
          "brands you can rely on", "the platform built with", "brands for men who").
          The set covers prepositions/articles that are NEVER a natural sentence-final
          word, plus relative pronouns (who/that/which/where) that introduce a
          following clause which was chopped.
      (c) Fewer than 2 words — too thin to be a subtitle (single-word fragments).
      (d) UI/nav-label copy (see _is_ui_nav_label).
      (e) Prompt/instruction artifact (see _is_prompt_artifact).

    Conservative: only rejects clear fragments; short complete taglines like
    "For everyone." (capital F) or "Do more." are NOT rejected.
    """
    t = (text or "").strip()
    if not t:
        return False
    # (d) UI/nav-label copy
    if _is_ui_nav_label(t):
        return True
    # (e) Prompt artifact
    if _is_prompt_artifact(t):
        return True
    # (c) Single-word fragment
    words = t.split()
    if len(words) < 2:
        return True
    # (a) Starts lowercase — mid-sentence fragment
    if t[0].islower():
        return True
    # (b) Ends on a preposition/article/conjunction/relative pronoun — open clause
    _FRAGMENT_TERMINALS = frozenset((
        "for", "to", "the", "a", "an", "with", "of", "on", "in", "at",
        "by", "from", "and", "or", "but", "nor", "so", "yet",
        "up", "out", "over", "into", "onto", "upon", "about",
        # Relative/subordinating words that introduce a following clause (chopped mid-clause)
        "who", "that", "which", "where", "when", "while", "than",
    ))
    last = words[-1].lower().rstrip(".,!?;:")
    if last in _FRAGMENT_TERMINALS:
        return True
    return False


# Secondary on-screen fields that must never repeat across scenes. Hero fields
# (title, headline) are deliberately EXCLUDED — blanking a hero line is worse than
# a rare repeat; the shapers + plan-time validator handle hero dedup upstream.
_DEDUPE_SECONDARY_FIELDS = ("subtitle", "kicker", "eyebrow", "supporting", "punchWord", "caption")


def _norm_phrase(s: str) -> str:
    """Lowercased, whitespace-collapsed, punctuation-trimmed key for dedup."""
    return " ".join((s or "").lower().split()).strip(" .!?·•|-—–")


def _dedupe_cross_scene_secondary(scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic backstop: drop any SECONDARY string or bullet that already
    appeared (normalized) on an earlier scene. Only phrases of >= 2 words are
    treated as dedupable (so shared short tokens like a kicker 'YC' survive).
    Mutates + returns `scenes`."""
    seen: set = set()
    for sc in scenes:
        data = sc.get("data") or {}
        for field in _DEDUPE_SECONDARY_FIELDS:
            val = data.get(field)
            if not isinstance(val, str) or not val.strip():
                continue
            key = _norm_phrase(val)
            if len(key.split()) < 2:
                continue  # never dedup a single short token
            if key in seen:
                data[field] = ""
            else:
                seen.add(key)
        bullets = data.get("bullets")
        if isinstance(bullets, list):
            kept = []
            for b in bullets:
                if not isinstance(b, str) or not b.strip():
                    continue
                key = _norm_phrase(b)
                if key and key in seen:
                    continue
                if len(key.split()) >= 2:
                    seen.add(key)
                kept.append(b)
            data["bullets"] = kept
        sc["data"] = data
    return scenes


def _clean_complete_headline(text: str, limit: int = 72) -> str:
    """Return a clean, COMPLETE headline derived from `text`, or "" if nothing usable.

    NEVER returns a mid-word cut: prefers the first full sentence/clause that fits;
    if even the first clause overflows, truncates on a WORD boundary and drops a
    dangling function word (reusing _title_from_text). Rejects an obviously truncated
    meta-description fragment up front so a mangled `…ecomme` never surfaces.

    Also rejects UI/nav-label strings (e.g. "Added to Cart · New Arrivals") and
    prompt/stage-direction artifacts (e.g. "Show call-to-action: 'Start") — these
    must never reach the rendered title/subtitle/CTA props.
    """
    t = (text or "").strip()
    if not t:
        return ""
    # Reject UI chrome and prompt artifacts before any further processing.
    if _is_ui_nav_label(t) or _is_prompt_artifact(t):
        return ""
    if _is_truncated_meta(t):
        # Salvage a complete leading sentence if one exists before the cut; else "".
        sent = re.split(r"(?<=[.!?])\s+", t, maxsplit=1)[0].strip()
        if sent and not _is_truncated_meta(sent) and len(sent) <= limit:
            return sent
        return ""
    return _title_from_text(t, limit=limit)


def _brand_fallback_title(brand: Dict[str, Any]) -> str:
    """A NEVER-empty on-brand title: CLEAN tagline -> wordmark -> brand name.

    A truncated meta-description tagline (mid-word cut) is rejected here so it can
    never become the headline; we fall through to the wordmark/brand instead.
    A UI/nav-label string or prompt artifact is also rejected so "Added to Cart ·
    New Arrivals" or "Show call-to-action: 'Start" never becomes a display title.
    A fragment subtitle (lowercase-leading or preposition-final/relative-clause scrape
    artifact) is also rejected so "store they line up for" or "brands for men who"
    never becomes a display title."""
    tag = (brand.get("tagline") or "").strip()
    clean_tag = _clean_complete_headline(tag) if tag else ""
    # Also reject a fragment subtitle so it never becomes the display title.
    if clean_tag and _is_fragment_subtitle(clean_tag):
        clean_tag = ""
    return (clean_tag or brand.get("wordmark")
            or brand.get("brand") or brand.get("name") or "").strip()


def _distinct_tagline(brand: Dict[str, Any], avoid: str = "") -> str:
    """A short tagline/subtitle DISTINCT from the wordmark and from `avoid`.

    Priority:
      1. The brand's clean tagline — but only when it is meaningfully different
         from the wordmark (case-insensitive) AND different from `avoid`.
      2. Synthesize a short one from the first two feature labels joined with " · "
         (e.g. "Payment Processing · Billing") — still on-brand, never invented.
      3. Empty string (caller decides the graceful fallback).

    Never returns a string that is the same word (case-insensitive) as `avoid` or
    as the brand wordmark, so eyebrow ≠ display ≠ tagline.
    """
    wordmark = (brand.get("wordmark") or brand.get("brand") or brand.get("name") or "").strip()
    avoid_lower = (avoid or "").strip().lower()
    wordmark_lower = wordmark.lower()

    # 1. Clean tagline that is distinct from both wordmark and avoid.
    tag = _clean_complete_headline(brand.get("tagline") or "")
    # Reject a fragment subtitle (lowercase-leading / preposition/relative-final, UI label, artifact).
    if tag and (_is_fragment_subtitle(tag) or _is_ui_nav_label(tag) or _is_prompt_artifact(tag)):
        tag = ""
    if tag and tag.lower() != wordmark_lower and tag.lower() != avoid_lower:
        return tag

    # 2. Feature-label synthesis: take up to 2 short feature labels. A lone bare
    #    category noun ("Products", "Pricing") is REJECTED here — it reads as a nav
    #    label, never a punchy display headline (the Plaid title='Products' bug).
    #    NAV-LABEL GUARD (R8): a feature scraped as a nav/section item ("Men's Shoes",
    #    "Customer Favorites", "Help Center", "Find a co-host") must NOT seed a synth
    #    — that's the "Men's Shoes · Customer Favorites" hero-title bug. Drop any
    #    candidate that is a nav-label segment, and never RETURN a string that the
    #    UI/nav guard flags (the synth itself is a " · " join → _is_ui_nav_label).
    feats = [f.get("label") or f.get("title") or "" for f in (brand.get("features") or [])]
    feats = [f.strip() for f in feats if f.strip()]
    candidates = [f for f in feats
                  if f.lower() != wordmark_lower and f.lower() != avoid_lower
                  and not _is_weak_headline(f)
                  and not _is_nav_label_segment(f)]
    if candidates:
        short = [f for f in candidates if len(f) <= 26][:2]
        if len(short) >= 2:
            # Only synthesize a " · " pair from TWO real capability labels; a single
            # label paired with nothing is not a join. The synth must not itself read
            # as a nav-tab join (defensive: candidates already passed the nav filter).
            synth = " · ".join(short)
            if synth.lower() != avoid_lower and not _is_ui_nav_label(synth):
                return synth
        # One short label, or no SHORT label but a longer real feature phrase exists:
        # distill a punchy phrase from the first one rather than emit a " · " join or
        # fall through to the bare wordmark.
        punchy = _punchy_headline(candidates[0])
        if (punchy and punchy.lower() != avoid_lower
                and not _is_weak_headline(punchy)
                and not _is_nav_label_segment(punchy)
                and not _is_fragment_subtitle(punchy)):
            return punchy

    return ""


# Title-scene roles / id markers that mean the CLOSING title (a call-to-action),
# as opposed to the OPENING title (the brand lockup). build_timeline derives role
# "close" for a closing-id title; build_props also flags the final scene.
_CLOSING_ROLES = ("close", "cta", "closing", "outro", "end")


def _is_closing_title(scene: Dict[str, Any]) -> bool:
    """True when a title/hero scene is the CLOSING lockup (CTA), not the opening one.

    Signals (any): role/id marks it as a close/cta/outro, OR build_props flagged it
    as the final scene (data._is_closing). The opening title is everything else.
    """
    d = scene.get("data") or {}
    if d.get("_is_closing"):
        return True
    role = _scene_role(scene)
    if role in _CLOSING_ROLES:
        return True
    sid = str(scene.get("id") or "").strip().lower()
    return any(kw in sid for kw in ("clos", "cta", "outro"))


def _brand_name(brand: Dict[str, Any]) -> str:
    """The display brand name for an anchored CTA: wordmark -> brand -> name."""
    return (str(brand.get("wordmark") or brand.get("brand")
                or brand.get("name") or "")).strip()


def _brand_domain(brand: Dict[str, Any]) -> str:
    """A clean visit-able domain from the brand's cta_url/url, WITHOUT scheme/path,
    KEEPING the TLD ('.com') intact (R10 keep-the-.com). '' if none usable."""
    raw = (str(brand.get("cta_url") or brand.get("url") or brand.get("host") or "")).strip()
    if not raw:
        return ""
    # Strip scheme and any path/query so only the host remains: "https://theverge.com/x"
    # -> "theverge.com". A bare "theverge.com" passes through unchanged.
    host = re.sub(r"^[a-z]+://", "", raw, flags=re.IGNORECASE)
    host = host.split("/", 1)[0].split("?", 1)[0].strip().strip(".")
    return host


def _derive_cta(brand: Dict[str, Any], raw_threaded: str = "") -> str:
    """Derive a REAL, brand-anchored CTA when the planned closing copy is unusable
    (a stage-direction / meta-description, a UI label, or a prompt artifact).

    An imperative addressed to the viewer, anchored to the brand. Priority:
      1. The GROUNDED closing copy salvaged from the threaded VO beat — but ONLY when
         it is itself a real imperative CTA (passes the stage-direction / artifact /
         nav-label guards). This preserves a legitimately-narrated close
         ("Start accepting payments") and keeps the R10 keep-the-.com win
         ("Visit theverge.com" stays intact, domain preserved).
      2. "Get started with <Brand>" / "Start with <Brand>" — a brand-anchored imperative
         (R9 imperative CTA win) when a brand name exists.
      3. "Visit <domain>" — KEEPING the '.com' (R10) — when only a domain is known.
      4. The bare wordmark — never empty.
    """
    # 1. Salvage a real imperative from the grounded closing beat.
    grounded = _punchy_headline(raw_threaded or "")
    if (grounded and not _is_cta_stage_direction(grounded)
            and not _is_ui_nav_label(grounded) and not _is_prompt_artifact(grounded)
            and not _is_fragment_subtitle(grounded)):
        return grounded

    name = _brand_name(brand)
    domain = _brand_domain(brand)
    if name:
        return "Get started with %s" % name
    if domain:
        return "Visit %s" % domain  # keep the .com (R10)
    return name or domain or ""


def _is_section_label_subtitle(text: str) -> bool:
    """True when `text` is a bare SECTION/nav label unsuitable as a subtitle.

    The subtitle may legitimately be a short value-prop tagline that is NOT a full
    clause ("On-demand manufacturing", "Payment Processing") — so we do NOT gate the
    subtitle through the full _looks_like_headline test (that would reject a real
    tagline). Instead reject only the e-commerce SECTION-HEADER class: a short (<=3
    word) PURE Title-Case noun phrase (every significant word capitalized) that reads
    like rotating store chrome ("All Sale", "Customer Favorites", "New Arrivals",
    "Popular Picks", "Best Sellers", "Top Rated").

    Distinguishing signal vs a real tagline: a real value-prop tagline is
    sentence-cased — at least one interior content word is lowercase
    ("On-demand manufacturing", "Built for builders"). A section label capitalizes
    EVERY significant word. So: pure Title-Case + short + no verb/clause = chrome.
    """
    t = (text or "").strip()
    if not t:
        return False
    words = t.split()
    if not (1 <= len(words) <= 3):
        return False  # longer phrases are taglines/headlines, not section chrome
    # A real headline/value-prop is never a section label.
    if _looks_like_headline(t):
        return False
    _TITLECASE_FUNCTION = frozenset((
        "a", "an", "the", "of", "and", "or", "in", "on", "to", "for", "with",
        "by", "at", "from", "as", "&",
    ))
    # Pure Title-Case = every significant (non-function) word starts uppercase.
    has_significant = False
    for w in words:
        cw = w.strip(".,!?;:\"'’“”()")
        if not cw:
            continue
        if cw.lower() in _TITLECASE_FUNCTION:
            continue
        has_significant = True
        if not cw[0].isupper():
            return False  # a lowercase significant word → sentence-cased tagline, keep it
    return has_significant


def _grounded_headline(raw_threaded: str, brand: Dict[str, Any],
                       avoid: str = "", limit: int = 56) -> str:
    """Distill the GROUNDED opening value-prop into a punchy hero headline, or "".

    Source priority (R9 — derive the OPENING title from the grounded value-prop, NOT
    scraped feature/section labels):
      1. The planner's OPENING VO BEAT (`raw_threaded`) — a complete grounded sentence
         like "Allbirds makes comfortable shoes from natural, sustainable materials."
         distilled via _punchy_headline (clause-end + numeral guards) into a crisp
         headline ("Allbirds makes comfortable shoes from natural, sustainable
         materials"). This is the world-grounded line the planner produced for THIS
         brand, so it is always on-topic.
      2. The brand's world-knowledge / real tagline — _clean_complete_headline of
         brand.tagline (a hand-verified known-brand tagline, or a clean scraped one).
      3. "" — caller falls to the wordmark.

    Every candidate must pass the POSITIVE _looks_like_headline test (a real
    headline/value-prop, not a section label) AND not be a weak/nav/artifact string
    AND differ from `avoid` (the wordmark). Entity-decoded by the caller's _decode().
    """
    avoid_l = (avoid or "").strip().lower()

    def _ok(cand: str) -> bool:
        if not cand:
            return False
        c = cand.strip()
        if c.lower() == avoid_l:
            return False
        if _is_weak_headline(c) or _is_ui_nav_label(c) or _is_prompt_artifact(c):
            return False
        return _looks_like_headline(c)

    # 1. Distill the grounded opening VO beat.
    cand = _punchy_headline(raw_threaded or "", limit=limit)
    if _ok(cand):
        return cand
    # Some VO beats are short enough that _punchy_headline returns "" (it requires
    # >=2 words AND trims tails); fall back to a plain clause clamp of the same line.
    cand = _title_from_text(raw_threaded or "", limit=72)
    if _ok(cand):
        return cand
    # 2. World-knowledge / real tagline.
    cand = _clean_complete_headline(brand.get("tagline") or "")
    if _ok(cand):
        return cand
    return ""


def _shape_hero(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """HeroTitle data: kicker / title / punchWord / subtitle.

    OPENING title -> brand lockup: wordmark + tagline headline (the spoken line for
    an opening title just narrates the wordmark, so the tagline reads better).
    CLOSING title -> call-to-action: the scene's OWN closing line (from its threaded
    VO beat / brief) becomes the headline, the brand wordmark renders as a smaller
    sub-line (HeroTitle draws theme.wordmark above the title whenever it differs
    from the title), and the brand URL sits under it. NEVER the wordmark twice; the
    kicker is dropped on the close so the wordmark isn't echoed as the eyebrow.
    The title is NEVER empty.

    DISTINCT TAGLINE RULE: eyebrow ≠ display ≠ subtitle. When the would-be title is
    effectively the same word as the wordmark (no meaningful tagline), _distinct_tagline
    synthesizes a short value-prop line from brand features so the hierarchy is never
    redundant ("PLAID" / "Plaid" / "Plaid" -> "PLAID" / tagline / url instead).
    """
    d = scene.get("data") or {}
    wordmark = (brand.get("wordmark") or brand.get("brand") or brand.get("name") or "").strip()
    raw_threaded = d.get("_text") or scene.get("brief") or ""
    threaded = _title_from_text(d.get("_text") or "") or _title_from_text(scene.get("brief") or "")

    if _is_closing_title(scene):
        # CTA headline = the closing line actually narrated, distilled into a PUNCHY
        # phrase ("Start building better financial products") — NOT the raw spoken
        # sentence, which truncates mid-URL ("...with Plaid at plaid"). _punchy_headline
        # strips the trailing CTA tail ("at <domain>", "with <brand>", "today"). Fall
        # back to a tagline/wordmark only if the plan threaded no closing copy.
        punchy_cta = _punchy_headline(d.get("_text") or "") or _punchy_headline(scene.get("brief") or "")
        # Sanitize explicit plan title: reject UI-label, prompt-artifact, OR a
        # self-referential STAGE-DIRECTION / meta-description that DESCRIBES the CTA card
        # instead of addressing the viewer (R11 — "Closing call‑to‑action card urging
        # users", "Call-to-action card using the brand color", "Closing card with the
        # wordmark", "Show the CTA"). R7-G3's planner sanitizer caught only the
        # "Show call-to-action:" verb-colon form; this is the last line of defense.
        explicit_title = d.get("title") or ""
        if explicit_title and (_is_ui_nav_label(explicit_title)
                               or _is_prompt_artifact(explicit_title)
                               or _is_cta_stage_direction(explicit_title)):
            explicit_title = ""
        # The threaded/distilled closing line can ALSO be a stage direction (the leak
        # came in via the planner's closing VO beat → d["_text"]); reject it the same way.
        if punchy_cta and _is_cta_stage_direction(punchy_cta):
            punchy_cta = ""
        if threaded and _is_cta_stage_direction(threaded):
            threaded = ""
        title = (explicit_title or punchy_cta or threaded).strip()
        # R11: the plan THREADED closing copy but EVERY usable source was rejected as a
        # stage-direction / artifact. Don't fall to the bare wordmark — that's not a CTA.
        # DERIVE a real brand-anchored imperative ("Get started with <Brand>" / "Visit
        # <domain>"). Only when NO copy was threaded at all do we keep the tagline/wordmark
        # lockup fallback (an opening-style brand close, which is a legitimate design).
        had_closing_copy = bool((d.get("title") or "").strip()
                                or (d.get("_text") or "").strip()
                                or (scene.get("brief") or "").strip())
        if not title and had_closing_copy:
            title = _derive_cta(brand, d.get("_text") or scene.get("brief") or "")
        if not title:
            title = (_brand_fallback_title(brand) or wordmark or "").strip()
        # FINAL CTA GUARD: if we somehow still hold a stage-direction/meta-description
        # (or nothing usable), DERIVE a real brand-anchored imperative CTA.
        if not title or _is_cta_stage_direction(title) or _is_prompt_artifact(title):
            title = (_derive_cta(brand, d.get("_text") or scene.get("brief") or "")
                     or wordmark)
        # R5 — CLAMP the close-hero headline to ~2 lines (L2-style). Notion's close
        # headline ran "Start using Notion today at notion.com to organize all your
        # work" → a 4-line wall on the centered close card. The CTA headline is a
        # PUNCHY 2-line phrase, not a sentence; clause-clip to <=48 chars (the centered
        # close column is wider than the split column's 38, but a sentence still wraps
        # to 4 lines). _clip_to_clause only trims real text — never a mid-word cut, and
        # the brand-anchored "Get started with <Brand>" derived CTAs already fit. Skip
        # when the title is already short (no needless re-trim of "Visit stripe.com").
        CLOSE_HEADLINE_LIMIT = 48
        if title and len(title) > CLOSE_HEADLINE_LIMIT:
            clamped = _clip_to_clause(title, CLOSE_HEADLINE_LIMIT)
            # Only accept a clamp that keeps a usable multi-word imperative; otherwise
            # derive a clean brand-anchored CTA rather than ship a 1-word stub.
            if clamped and len(clamped.split()) >= 2:
                title = clamped
            else:
                title = _derive_cta(brand, d.get("_text") or scene.get("brief") or "") or title
        subtitle = d.get("subtitle")
        if subtitle is None:
            subtitle = (brand.get("cta_url")
                        or _clean_complete_headline(brand.get("tagline") or "") or "")
        # Ensure subtitle ≠ title (distinct tagline rule for CTA).
        if subtitle and subtitle.strip().lower() == title.strip().lower():
            subtitle = brand.get("cta_url") or ""
        # FRAGMENT GUARD: reject a subtitle that is a scrape fragment (lowercase-leading,
        # preposition-final, or single-word). Fall back to cta_url or drop.
        if _is_fragment_subtitle(subtitle):
            subtitle = brand.get("cta_url") or ""
        # R11 SUBTITLE GUARD: a stage-direction / meta-description must not survive as
        # the closing SUBTITLE either ("Call-to-action card using the brand color"
        # threaded as the subtitle). Fall back to the brand URL, else drop.
        if subtitle and (_is_cta_stage_direction(subtitle) or _is_prompt_artifact(subtitle)):
            subtitle = brand.get("cta_url") or ""
        # R3 — SLOGAN-LANDS-ON-CTA (feedback_slogan_lands_on_cta, spec §3 scene 7):
        # the closing hero must read as a CALL TO ACTION, not a second opening title.
        # HeroTitle.isCtaBeat only renders the accent CTA *pill* when the subtitle
        # carries a CTA signal (an arrow, a URL/domain, or "start"/"get started").
        # A plain tagline ("Build internet businesses") rendered as a muted line made
        # the CTA scene indistinguishable from the open (R2 miss). When the resolved
        # subtitle has NO CTA signal, upgrade it to a real brand-anchored action
        # lockup "Start now → <domain>" (domain from cta_url/url/host) so the pill
        # fires. Honest: only the real brand domain, never fabricated copy. When no
        # domain is known, keep the existing tagline/url subtitle unchanged.
        _CTA_SIGNAL_RE = re.compile(r"→|->|https?://|www\.|\.com|\.io|\.ai|start\b|get started",
                                    re.IGNORECASE)
        if not (subtitle and _CTA_SIGNAL_RE.search(subtitle)):
            _cta_domain = _brand_domain(brand)
            if _cta_domain:
                subtitle = "Start now → %s" % _cta_domain
        out = {
            # No kicker on the close: the wordmark already renders as the sub-line,
            # so a "ORINOVATE" eyebrow would show the wordmark twice.
            "kicker": _decode(d.get("kicker") or ""),
            "title": _decode(title),
            "subtitle": _decode(subtitle or ""),
        }
    else:
        # OPENING title (R9): DERIVE the headline from the GROUNDED value-prop, NOT
        # from scraped feature/section labels. E-commerce homepages surface endless
        # rotating section headers ("Popular Picks", "Customer Favorites", "New
        # Arrivals") that denylisting can never fully enumerate; the POSITIVE
        # _looks_like_headline test rejects the whole class (a Title-Case noun phrase
        # with no verb is chrome, by construction), and the grounded opening VO beat
        # supplies a real value-prop headline for ANY brand.

        # 1. An EXPLICIT plan title is authoritative ONLY when it reads like a real
        #    headline — reject UI-label/prompt-artifact copy AND any scraped phrase
        #    that fails the positive headline test ("Popular Picks", "All Sale").
        explicit_title_open = (d.get("title") or "").strip()
        if explicit_title_open and not (
                _looks_like_headline(explicit_title_open)
                and not _is_ui_nav_label(explicit_title_open)
                and not _is_prompt_artifact(explicit_title_open)):
            explicit_title_open = ""

        if explicit_title_open:
            title = explicit_title_open
        else:
            # 2. No real H1 / explicit headline → DERIVE from the grounded value-prop:
            #    distill the planner's opening VO beat, else the world-knowledge / real
            #    tagline, else the wordmark. NEVER pick or synthesize the opening title
            #    from scraped feature/section labels (no _distinct_tagline here — that
            #    synthesizes from feature labels, the "Popular Picks · All Sale" bug).
            grounded = _grounded_headline(raw_threaded, brand, avoid=wordmark, limit=56)
            title = grounded or wordmark or threaded or ""

        # FINAL HEADLINE GUARD: a weak display title (a bare category noun like
        # "Products", or a lone wordmark) is never a punchy on-card headline. Distill
        # a real grounded phrase from the threaded opening VO line / world tagline
        # before falling back to the wordmark. (Grounded-first; no feature-label synth.)
        if _is_weak_headline(title) or (wordmark and title.lower() == wordmark.lower()):
            grounded = _grounded_headline(raw_threaded, brand, avoid=wordmark, limit=56)
            if grounded:
                title = grounded

        # NAV-LABEL RENDER GUARD (R8, belt-and-suspenders): a UI/nav-label or a
        # separator-joined nav pair ("Men's Shoes · Customer Favorites") must NEVER be
        # the rendered hero title even if some path produced one. Fall to the grounded
        # value-prop headline and finally the wordmark.
        if _is_ui_nav_label(title) or _is_prompt_artifact(title):
            title = _grounded_headline(raw_threaded, brand, avoid=wordmark, limit=56) \
                or wordmark or ""

        # R6 — CLAMP an OVER-LONG OPENING-hero headline to a complete shorter clause.
        # The R5 clamp only touched the CLOSE branch; Notion still OPENED on a multi-line
        # serif wall when an EXPLICIT plan title (which bypasses _grounded_headline's
        # 56-char clause distiller) ran long. We do NOT touch headlines at/under the
        # grounded-headline limit (56) — those are already 2-line display phrases the
        # system intentionally allows complete (e.g. "Allbirds makes comfortable shoes
        # from natural wool", a complete numeric claim like "...800 million trusted
        # reviews"). Only a title LONGER than that grounding ceiling is the 4-line wall;
        # for it, prefer a COMPLETE shorter clause (comma/clause boundary) and accept the
        # clamp ONLY when it ends at a real clause boundary (not a hard mid-clause chop
        # that would drop a compelling tail). Otherwise keep the long headline unchanged
        # (a complete long clause beats a meaning-losing chop). Never clamp the wordmark.
        OPEN_WALL_LIMIT = 56  # == _grounded_headline's opening ceiling; only longer titles wall
        if (title and len(title) > OPEN_WALL_LIMIT
                and title.strip().lower() != wordmark.lower()):
            clamped = _clip_to_clause(title, OPEN_WALL_LIMIT)
            # Accept only a clause-boundary clamp: the clamp must be a PREFIX of the
            # original that ends where a comma/clause-opener split occurred (so we kept a
            # complete sub-clause, not a hard chop mid-thought). A hard word-boundary chop
            # (the Tripadvisor "...access" case) is rejected — keep the full headline.
            if (clamped and len(clamped.split()) >= 3
                    and title.lower().startswith(clamped.lower())
                    and len(title) > len(clamped)
                    and title[len(clamped):len(clamped) + 1] in (",", ";", ":")):
                title = clamped

        subtitle = d.get("subtitle")
        if subtitle is None:
            # Subtitle must be distinct from both title AND wordmark.
            sub_cand = _distinct_tagline(brand, avoid=title)
            subtitle = sub_cand if sub_cand else ""
        # Final guard: never show wordmark in subtitle when it already shows as eyebrow/title.
        if subtitle and subtitle.strip().lower() == wordmark.lower():
            subtitle = ""
        # FRAGMENT GUARD + SALVAGE: a scrape fragment (lowercase-leading, preposition-
        # final, or single-word) must never render. Before blanking it, salvage —
        # (a) a complete leading sentence from the fragment's own text, then (b) the
        # brand's real distinct value-prop / tagline. Empty only if nothing usable and
        # distinct remains ("store they line up for", the Shopify residual: dropped,
        # never rendered verbatim).
        if subtitle and _is_fragment_subtitle(subtitle):
            salvaged = _clean_complete_headline(subtitle)
            if (salvaged and not _is_fragment_subtitle(salvaged)
                    and salvaged.strip().lower() not in (wordmark.lower(),
                                                         title.strip().lower())):
                subtitle = salvaged
            else:
                sub_cand = _distinct_tagline(brand, avoid=title)
                subtitle = sub_cand if (sub_cand and not _is_fragment_subtitle(sub_cand)) else ""
        # NAV-LABEL / SECTION-LABEL GUARD: a UI/nav-label, separator-joined nav pair,
        # OR a bare section label that fails the positive headline test ("All Sale",
        # "Customer Favorites") must not render as the subtitle either (allbirds
        # subtitle was "Men's Shoes" / "All Sale"). A real value-prop subtitle passes
        # _looks_like_headline; a section-chrome label does not. We keep multi-word
        # value-prop taglines that aren't full clauses (e.g. "On-demand manufacturing")
        # by only rejecting strings the nav/label guards positively flag.
        if subtitle and (_is_ui_nav_label(subtitle) or _is_prompt_artifact(subtitle)
                         or _is_section_label_subtitle(subtitle)):
            subtitle = ""
        # Opening eyebrow. An explicit plan kicker wins. Otherwise default to the
        # wordmark uppercased — BUT NOT when the wordmark already renders as the logo
        # lockup right above it (a real captured logo, or the wordmark text the
        # archetype draws when wordmark != title): echoing "STRIPE" under the Stripe
        # logo is redundant chrome (R2 polish miss). In that case drop the eyebrow so
        # the lockup is logo → headline, clean. When there is NO logo AND the title IS
        # the wordmark, keep the wordmark eyebrow (it's the only brand mark).
        has_logo = bool(str(brand.get("logo_src") or brand.get("logoSrc") or "").strip())
        wordmark_shows_above = has_logo or (wordmark and wordmark.lower() != title.strip().lower())
        explicit_kicker = str(d.get("kicker") or "").strip()
        open_kicker = explicit_kicker or ("" if wordmark_shows_above else wordmark.upper())
        out = {
            "kicker": _decode(open_kicker),
            "title": _decode(title),
            "subtitle": _decode(subtitle or ""),
        }
    # punchWord must be a substring of title for the accent split to fire.
    punch = d.get("punchWord")
    decoded_title = out["title"]
    if punch and _decode(punch) in decoded_title:
        out["punchWord"] = _decode(punch)
    return out


def _shape_cards(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """CardUi data: an accent-split heading + the brand's 2x2 feature grid.

    The four cards come from brand["features"]; the heading/accent from plan copy.
    Each card: {label, value?, sub?, accent?}. The first defaults to the accent
    card if none is flagged (so the highlighted-card tail pulse always has a home).
    """
    d = scene.get("data") or {}
    features = list(brand.get("features") or [])[:CARD_COUNT]
    cards: List[Dict[str, Any]] = []
    for f in features:
        # accept {label,value,sub,accent} (fixture) or {title,sub} (brand_extract).
        cards.append({
            "label": f.get("label") or f.get("title") or "",
            "value": f.get("value"),
            "sub": f.get("sub"),
            "accent": bool(f.get("accent")),
        })
    if cards and not any(c["accent"] for c in cards):
        cards[0]["accent"] = True
    # Decode entities in card labels/values/subs.
    decoded_cards = [
        {
            "label": _decode(c.get("label") or ""),
            "value": _decode(c["value"]) if c.get("value") is not None else None,
            "sub": _decode(c["sub"]) if c.get("sub") is not None else None,
            "accent": c["accent"],
        }
        for c in cards
    ]
    return {
        "heading": _decode(d.get("heading") or "Built to ship"),
        "headingAccent": _decode(d.get("headingAccent") or ""),
        "cards": decoded_cards,
    }


_DANGLING_WORDS = frozenset((
    "from", "to", "and", "with", "at", "of", "for", "the", "a", "an",
    "in", "on", "or", "by", "as", "but", "so", "nor", "yet",
    # Determiners / possessives / articles that introduce a following noun — a
    # headline must never end on one (mid-possessive chop, e.g. "that keep your",
    # "powers its", "for their"). "their" is already covered as a bare-quantifier
    # but listing it here keeps the dangling-tail strip self-contained.
    "your", "its", "their", "our", "his", "her", "my", "this", "these", "those",
    # Relative/subordinating words that open a following clause — a headline must
    # never end on these (mid-relative-clause chop, e.g. "brands for men who",
    # "builds apps that", "a platform where", "markets which").
    "who", "that", "which", "where", "when", "while", "than", "whose", "whom",
))

# Trailing present-participle / gerund "helper" words. When a distilled headline ends
# on one of these AFTER a complete clause, the participle opens a following subordinate
# clause that was clipped ("...self-driving, letting", "...runners keeping", "...gear
# making"). A headline must NOT end on a dangling participle-helper. This set is the
# COMMON clause-bridge participles; a content-word -ing ending ("Linear makes shipping
# faster") is NOT in here, so it is preserved.
_DANGLING_PARTICIPLES = frozenset((
    "letting", "keeping", "making", "helping", "giving", "bringing", "turning",
    "allowing", "enabling", "powering", "driving", "creating", "building",
    "delivering", "providing", "offering", "connecting", "growing", "scaling",
    "saving", "earning", "moving", "sending", "putting", "getting", "showing",
    "leaving", "letting", "having", "using", "doing", "being", "going",
    "starting", "ensuring", "guiding", "leading",
))

# Trailing PAST-participle "bridge" words. A headline that ends on one of these is
# almost always a clipped reduced-relative clause whose object lived past the cut
# ("...comfortable shoes made" cut from "...made from natural materials";
# "...software built" from "...built for teams"; "...products designed" from
# "...designed to last"). A headline must NOT end on a bare past participle.
# Because _strip_dangling_tail only ever inspects the LAST token, adding these
# strips them ONLY when they are literally the final word — exactly the dangle
# case. A COMPLETE phrase keeps its object ("shoes made from wool" ends on "wool",
# a content word) and is untouched. R7 gap 3.
_DANGLING_PAST_PARTICIPLES = frozenset((
    "made", "built", "designed", "crafted", "engineered", "powered", "backed",
    "trusted", "based", "founded", "created", "driven", "loved",
))

# Trailing CONNECTOR SYMBOLS. A headline clipped from a page <title> can end on a
# bare ampersand / plus / separator ("Comfortable, Sustainable Shoes &" cut from
# "...Shoes & Apparel"; "...Tools |" / "...Home ·"). These are not words so they
# never appear in _DANGLING_WORDS; strip them as a trailing dangling tail too.
# R7 gap 2.
_DANGLING_SYMBOLS = frozenset(("&", "+", "·", "•", "|", "/", "-", "—", "–", ":", ";"))


# A sentence-terminating "." (or ! or ?) is followed by whitespace or end-of-string.
# A "." glued to a following alnum token is part of a domain/decimal ("theverge.com",
# "12.5") and is NOT a sentence boundary — splitting there drops the TLD ("Visit
# theverge.com" -> "Visit theverge"), the theverge CTA bug. "!" / "?" / newlines are
# always boundaries (they don't appear mid-domain).
_SENTENCE_BOUNDARY_RE = re.compile(r"(?:\.(?=\s|$))|[!?\n]")


def _split_first_sentence(text: str) -> str:
    """First sentence of `text`, treating a "." inside a domain/decimal as NON-terminal
    so a trailing CTA domain (".com") is preserved ("Visit theverge.com" stays whole)."""
    m = _SENTENCE_BOUNDARY_RE.search(text)
    return (text[:m.start()] if m else text).strip()


def _strip_dangling_tail(text: str) -> str:
    """Drop a trailing comma AND any dangling tail word — a function word
    (preposition/conjunction/article/relative-pronoun in _DANGLING_WORDS), a
    determiner/possessive ("your"/"its"), or a clause-bridge participle-helper
    ("letting"/"keeping") — so the phrase ends on a CONTENT word that completes the
    thought, never on a dangling token. Idempotent; strips repeatedly so a
    "..., letting" tail collapses past both the participle AND the trailing comma.
    """
    # Strip a trailing comma AND any trailing connector symbol ("&"/"|"/"·"/"+"/…)
    # before splitting, so a bare-symbol tail collapses whether it is glued
    # ("Apparel&") or space-separated ("Apparel &"). R7 gap 2.
    head = (text or "").strip()
    while head and head[-1] in _DANGLING_SYMBOLS:
        head = head[:-1].strip()
    head = head.rstrip(",").strip()
    words = head.split()
    while words:
        last = words[-1].lower().rstrip(",.")
        # A bare symbol token left as its own word ("Shoes &" -> token "&").
        if words[-1].strip() in _DANGLING_SYMBOLS:
            words.pop()
            continue
        if (last in _DANGLING_WORDS or last in _DANGLING_PARTICIPLES
                or last in _DANGLING_PAST_PARTICIPLES):
            words.pop()
            continue
        # A trailing comma glued to a content word ("wikis,") means the clause was cut
        # mid-list — drop the comma (the word stays; "...docs, wikis" reads complete).
        if words[-1].endswith(","):
            words[-1] = words[-1].rstrip(",")
        # A trailing connector symbol glued to a content word ("Apparel|") — drop the
        # symbol, keep the word.
        elif words[-1] and words[-1][-1] in _DANGLING_SYMBOLS:
            words[-1] = words[-1][:-1].rstrip(",")
        break
    return " ".join(w for w in words if w)


# Clause-boundary punctuation/words at which a long sentence can be cut to a COMPLETE
# leading clause rather than hard-chopped mid-phrase. A comma/semicolon/colon ends a
# clause; a relative/subordinating pronoun OPENS a trailing clause (so we cut BEFORE
# it). We never cut inside a domain (the "." guard lives in _split_first_sentence).
_CLAUSE_CUT_RE = re.compile(r"[,;:]")
_CLAUSE_OPENERS = frozenset((
    "that", "which", "who", "whom", "whose", "where", "when", "while", "so",
    "letting", "keeping", "making", "helping", "giving", "allowing", "enabling",
))


# Connectors (prepositions + clause-bridge participle-helpers + the infinitive "to")
# that introduce an object/clause. When a distilled phrase ends on one of these
# WITH only a short orphaned object after it (the rest of the object got cut at a
# comma/limit), the phrase reads as a mid-clause chop ("...using clear" cut from
# "...using clear, comprehensive documentation"; "...go to Migrate to" cut from
# "...Migrate to Stripe"). _ends_on_orphan_connector detects that shape so the
# clause-clipper can back up past the whole connector phrase to a COMPLETE shorter
# line instead.
_ORPHAN_CONNECTORS = frozenset((
    # prepositions
    "from", "to", "with", "at", "of", "for", "in", "on", "by", "as", "into",
    "onto", "via", "through", "across", "over", "about", "after", "before",
    # clause-bridge participle helpers (a connector that opens a clipped clause)
    "using", "letting", "keeping", "making", "helping", "giving", "bringing",
    "allowing", "enabling", "powering", "creating", "building", "delivering",
    "providing", "offering", "connecting",
))


def _ends_on_orphan_connector(text: str, was_cut: bool, orphan_max: int = 2) -> bool:
    """True when `text` ends on a connector whose object was SEVERED by a cut.

    The orphan shape is: a connector (preposition / participle-helper / "to") near
    the end with only `orphan_max` or fewer words after it, AND we KNOW content was
    removed right after this fragment (`was_cut=True`). That combination means the
    connector's full object lived past the cut ("...using clear" cut at the comma
    before "comprehensive documentation"; "...go to Migrate to" -> trailing "to").

    `was_cut` is REQUIRED and load-bearing: a naturally-complete line that merely
    FITS the limit ("Accept payments online with Stripe", "...for millions of
    internet businesses", "...integrate Payments in minutes") has a complete
    connector phrase and must NOT be back-trimmed. So when `was_cut=False` this
    only flags a connector that is literally the LAST word (a pure dangling tail,
    which _strip_dangling_tail already removes) — i.e. it returns False for any
    fragment with trailing content. The orphan back-up is reserved for true cuts.
    """
    words = [w for w in (text or "").strip().split() if w]
    if len(words) < 2:
        return False
    low = [w.lower().rstrip(",.;:!?") for w in words]
    if not was_cut:
        # No cut happened: the text is the full source. A trailing connector with
        # an object after it is a COMPLETE phrase — never an orphan. (A connector as
        # the final word is handled by _strip_dangling_tail, not here.)
        return False
    # A cut happened right after this fragment. Scan the tail window for a connector
    # whose trailing object is short enough to be a severed-object artifact.
    for off in range(1, orphan_max + 1):
        idx = len(low) - 1 - off
        if idx < 1:  # keep at least one content word before the connector
            break
        if low[idx] in _ORPHAN_CONNECTORS:
            return True
    return False


def _first_complete_clause(text: str, limit: int) -> str:
    """Prefer the FIRST COMPLETE CLAUSE that fits within `limit` over a hard word-count
    chop, so a long VO beat distills to a clean complete phrase instead of a dangling
    mid-clause tail. "Allbirds makes comfortable wool runners that keep your feet warm"
    -> "Allbirds makes comfortable wool runners" (cut before the relative-clause opener)
    rather than "...that keep your". Returns "" when no in-limit clause boundary exists
    (the caller then falls back to the hard-chop-then-strip path).

    ORPHAN-CONNECTOR GUARD: a clause candidate that ends on a connector with a
    severed object ("...in minutes using clear" cut at the comma before
    "comprehensive documentation") is REJECTED in favour of a COMPLETE shorter
    candidate (back up past the connector phrase: "...Payments in minutes"). This
    prevents a comma-cut from preserving the start of an object whose head noun
    lived on the other side of the comma.
    """
    t = (text or "").strip()
    if not t:
        return ""
    # Candidate cut points: each clause-punctuation position, plus the position just
    # BEFORE each clause-opener word. Keep the LONGEST complete clause that still fits.
    cuts = [m.start() for m in _CLAUSE_CUT_RE.finditer(t)]
    words = t.split()
    # Word-start offsets, to locate clause-opener boundaries by character position.
    pos, offsets = 0, []
    for w in words:
        idx = t.find(w, pos)
        offsets.append(idx)
        pos = idx + len(w)
    for i, w in enumerate(words):
        if i > 0 and w.lower().strip(".,!?;:") in _CLAUSE_OPENERS:
            cuts.append(offsets[i] - 1)  # cut just before the opener
    best = ""
    for c in sorted(set(cuts)):
        cand = _strip_dangling_tail(t[:c])
        if not (cand and len(cand) <= limit and len(cand.split()) >= 2):
            continue
        # ORPHAN-CONNECTOR GUARD: every candidate here is a PREFIX cut at a clause
        # boundary, so content followed (was_cut=True). If the candidate ends on a
        # connector whose object was severed by that cut ("...using clear" before the
        # comma), back up past the whole connector phrase to the last complete
        # sub-clause. Keep the backed-up form only if a real phrase remains.
        if _ends_on_orphan_connector(cand, was_cut=True):
            cand = _drop_orphan_connector_phrase(cand)
        if cand and len(cand) <= limit and len(cand.split()) >= 2:
            best = cand  # longest fitting complete clause wins
    return best


def _drop_orphan_connector_phrase(text: str, orphan_max: int = 2) -> str:
    """Back up past a trailing orphaned-connector phrase to a COMPLETE shorter line.

    Given "...Payments in minutes using clear" (connector "using" + the severed
    object "clear"), drop the connector AND its short orphaned object so the result
    ends on the last COMPLETE clause ("...Payments in minutes"). We back up to the
    LAST (right-most) orphaning connector only, then a single _strip_dangling_tail
    cleans any newly-exposed dangling word. We deliberately do NOT re-flag a
    now-complete prepositional tail that the back-up exposed ("in minutes" is a
    complete phrase, not a second orphan) — backing up over a single severed object
    is enough; a pure dangling connector left behind is removed by the strip, never
    by re-running the orphan back-up. Returns the shortened phrase, or the cleaned
    original when nothing can be safely removed.
    """
    words = [w for w in (text or "").strip().split() if w]
    if len(words) < 2:
        return (text or "").strip()
    low = [w.lower().rstrip(",.;:!?") for w in words]
    # Find the RIGHT-MOST orphaning connector in the tail window (closest to the end)
    # so we drop only the final severed-object phrase, not a complete earlier clause.
    cut_at = None
    for off in range(1, orphan_max + 1):
        idx = len(low) - 1 - off
        if idx < 1:
            break
        if low[idx] in _ORPHAN_CONNECTORS:
            cut_at = idx  # keep words[:idx]
            break  # right-most connector wins — single back-up
    if cut_at is None:
        return _strip_dangling_tail((text or "").strip())
    out = _strip_dangling_tail(" ".join(words[:cut_at]))
    # Never reduce to a single word — if back-up over-trimmed, return the cleaned
    # original instead so the caller can fall back to a different candidate.
    if len(out.split()) >= 2:
        return out
    return _strip_dangling_tail((text or "").strip())


def _clip_to_clause(text: str, max_len: int) -> str:
    """Boundary-safe clip of `text` to <= max_len characters.

    The single entry point for trimming a spoken line / emphasis phrase down to a
    headline-length string that is ALWAYS a COMPLETE phrase:
      1. Take the first sentence (domain-safe) and the part before an em-dash.
      2. If it already fits AND does not end on a dangling word or orphaned
         connector phrase, return it verbatim.
      3. Otherwise prefer the FIRST COMPLETE CLAUSE that fits (comma / clause-opener
         boundary), backing up past any orphaned-connector phrase.
      4. Fall back to a hard word-boundary chop, then drop a trailing dangling
         connector AND any orphaned-connector phrase, NEVER ending mid-word or on a
         dangling a/an/the/and/or/to/of/in/using/with/for/your/its...
    Prefers a COMPLETE shorter line over a mid-phrase cut. NEVER fabricates — it
    only trims real text. Returns "" only for empty input.
    """
    t = (text or "").strip()
    if not t:
        return ""
    head = _split_first_sentence(t)
    head = re.split(r"\s+[—–-]\s+", head, maxsplit=1)[0].strip()
    if not head:
        return ""
    # Already complete and in-limit: keep as-is (was_cut=False — nothing removed, so
    # a trailing connector phrase here is a complete phrase, not an orphan).
    if (len(head) <= max_len
            and _strip_dangling_tail(head) == head):
        return head
    # Prefer a complete clause that fits.
    clause = _first_complete_clause(head, max_len)
    if clause:
        return clause
    # Hard word-boundary chop (content was removed -> was_cut=True), then cleanup.
    cut = head[:max_len].rsplit(" ", 1)[0].rstrip(",").strip() or head[:max_len]
    cut = _strip_dangling_tail(cut)
    if _ends_on_orphan_connector(cut, was_cut=True):
        cut = _drop_orphan_connector_phrase(cut)
    return _strip_dangling_tail(cut)


def _title_from_text(text: str, limit: int = 72) -> str:
    """A short, honest title from a scene's brief/VO text: the first clause,
    trimmed. NEVER fabricates marketing copy — it just truncates real text.

    The result reads as a COMPLETE phrase:
      - Trailing commas are stripped.
      - A dangling function word (preposition, conjunction, article, or relative
        pronoun like "who"/"that"/"which"/"where") at the end is ALWAYS dropped,
        whether the string was truncated or not — so "brands for men who" becomes
        "brands for men" (the mid-relative-clause chop guard).
      - Prefer ending at the last full sentence that fits over a hard mid-clause cut.
    """
    if not text:
        return ""
    # First sentence/clause, then a hard length clamp on a word boundary.
    # DOMAIN GUARD: a "." inside a domain ("theverge.com", "stripe.com") is NOT a
    # sentence boundary — it must NOT split "Visit theverge.com" into "Visit theverge"
    # (dropping ".com", the theverge CTA bug). Only split on a "." that is followed by
    # whitespace or end-of-string (a real sentence terminator), never on a "." glued to
    # a following TLD-like token.
    head = _split_first_sentence(str(text).strip())
    head = re.split(r"\s+[—–-]\s+", head, maxsplit=1)[0].strip()
    _was_truncated = len(head) > limit
    _took_hard_chop = False
    if _was_truncated:
        # COMPLETE-CLAUSE-FIRST: prefer the first complete clause that fits (cut at a
        # comma/semicolon/colon or before a relative-clause opener) over a hard
        # mid-clause word chop, so "...runners that keep your feet warm" distills to
        # "...runners", never "...that keep your".
        clause = _first_complete_clause(head, limit)
        if clause:
            head = clause  # already orphan-guarded inside _first_complete_clause
        else:
            cut = head[:limit].rsplit(" ", 1)[0]
            head = cut or head[:limit]
            _took_hard_chop = True
    # Strip a trailing comma + any dangling tail (function word, possessive, or a
    # clause-bridge participle-helper) — applies BOTH when the string was truncated AND
    # when it naturally ends on a dangling token ("brands for men who" -> "brands for
    # men"; "...docs, wikis," -> "...docs, wikis"; "...self-driving, letting" ->
    # "...self-driving").
    out = _strip_dangling_tail(head)
    # ORPHAN-CONNECTOR GUARD for the HARD-CHOP path ONLY. The clause path above is
    # already orphan-guarded inside _first_complete_clause, so re-applying here would
    # double-trim a clean clause ("...Payments in minutes" -> "...Payments"). Only the
    # raw mid-word/limit chop can leave a fresh severed-object connector tail.
    if out and _took_hard_chop and _ends_on_orphan_connector(out, was_cut=True):
        backed = _drop_orphan_connector_phrase(out)
        if len(backed.split()) >= 2:
            out = backed
    return out if out else head


# Bare generic nouns that read as a label, not a punchy headline. A feature scraped
# as just "Products" / "Pricing" must NEVER become the on-card display title (the
# Plaid `title='Products'` failure). A real punchy headline is a verb-led imperative
# or a multi-word benefit phrase, not a lone category noun.
_BARE_NOUN_HEADLINES = frozenset((
    "products", "product", "pricing", "features", "feature", "solutions",
    "solution", "platform", "overview", "company", "about", "home", "docs",
    "developers", "customers", "resources", "enterprise", "use cases", "use case",
))


def _is_weak_headline(text: str) -> bool:
    """True when `text` is too weak to be an on-CARD display headline: empty, a lone
    bare category noun ("Products", "Pricing"), or a 1-word fragment. These read as a
    nav label, not the punchy imperative/benefit phrase the reference films use."""
    t = (text or "").strip().strip(" .!?,:;—-").strip()
    if not t:
        return True
    if t.lower() in _BARE_NOUN_HEADLINES:
        return True
    # A single word (with no real verb-object) is never a headline.
    return len(t.split()) <= 1


# ---------------------------------------------------------------------------
# POSITIVE HEADLINE TEST  (R9 — replaces the negative nav-label denylist for the
# OPENING title). A scraped phrase may be used as the hero title ONLY if it reads
# like a real headline / value-prop: it contains a VERB or is a full clause/sentence,
# NOT a short Title-Case noun phrase. E-commerce homepages surface endless rotating
# section headers ("Popular Picks", "Customer Favorites", "New Arrivals", "Best
# Sellers", "Featured", "Shop All", "Help Center", "Men's Shoes", "Gift Guide",
# "Top Rated") — these are nav/section chrome and must NEVER be eligible as the title.
# Denylisting them is whack-a-mole; the positive test rejects the WHOLE class:
# a Title-Case noun phrase with no verb is chrome, by construction.
# ---------------------------------------------------------------------------

# Common English verbs (base + frequent inflections) that signal a real clause.
# Covers the imperative/3rd-person value-prop verbs the reference films use
# ("Build internet businesses", "Allbirds makes comfortable shoes"). Not exhaustive
# — the morphological -s/-ing/-ed signal below catches the long tail.
_HEADLINE_VERBS = frozenset((
    "build", "builds", "make", "makes", "made", "ship", "ships", "create",
    "creates", "plan", "plans", "design", "designs", "power", "powers",
    "help", "helps", "connect", "connects", "process", "processes", "manage",
    "manages", "track", "tracks", "run", "runs", "grow", "grows", "scale",
    "scales", "sell", "sells", "buy", "buys", "find", "finds", "search",
    "searches", "discover", "discovers", "deliver", "delivers", "launch",
    "launches", "automate", "automates", "is", "are", "lets", "let", "turn",
    "turns", "bring", "brings", "give", "gives", "send", "sends", "move",
    "moves", "pay", "pays", "save", "saves", "earn", "earns", "learn",
    "learns", "work", "works", "do", "does", "get", "gets", "start", "starts",
    "join", "joins", "explore", "explores", "compare", "compares", "book",
    "books", "order", "orders", "trust", "trusts", "love", "loves", "see",
    "sees", "meet", "meets", "use", "uses", "drive", "drives", "fuel",
    "fuels", "unlock", "unlocks", "enable", "enables", "transform",
    "transforms", "accelerate", "accelerates", "simplify", "simplifies",
    "streamline", "streamlines", "empower", "empowers", "support", "supports",
    "lead", "leads", "serve", "serves", "offer", "offers", "provide",
    "provides", "reach", "reaches", "list", "lists", "rent", "rents", "stay",
    "stays", "travel", "travels", "read", "reads", "write", "writes",
))

# Linking/auxiliary words whose presence implies a clause is being formed
# ("X is the platform that…", "we help teams…"). A bare label never contains these.
_CLAUSE_SIGNALS = frozenset((
    "is", "are", "was", "were", "be", "been", "your", "you", "we", "our",
    "they", "their", "it", "its", "every", "everyone", "anything", "everything",
    "that", "which", "who", "where", "when", "how", "why", "into", "from",
    "with", "without", "across", "through", "for", "so", "to",
))


def _looks_like_headline(text: str) -> bool:
    """POSITIVE test: True when `text` reads like a real headline / value-prop and is
    therefore eligible to be used as the OPENING hero title.

    A phrase qualifies when it has the SHAPE of a clause, not a label:
      (1) it contains a recognizable VERB (from _HEADLINE_VERBS or a clear -ing/-ed/
          3rd-person -s/-es inflection on a non-capitalized content word), OR
      (2) it is a FULL clause/sentence: ends with terminal punctuation, OR it carries
          a clause signal (a linking/auxiliary/pronoun word), OR it has a lowercase
          content word (a value-prop is sentence-cased, not Title-Cased).

    DISQUALIFIES the whole class of short Title-Case noun-phrase section labels
    ("Popular Picks", "Customer Favorites", "New Arrivals", "Best Sellers",
    "Featured", "Shop All", "Help Center", "Men's Shoes", "Gift Guide", "Top Rated"):
    every significant word capitalized, no verb, no clause signal → label, not headline.

    Conservative on real headlines: "Build internet businesses", "Plan and build
    products", "Allbirds makes comfortable shoes from natural wool" all PASS.
    """
    t = (text or "").strip()
    if not t:
        return False
    # Hard rejects up front: nav chrome / prompt artifacts are never headlines, and a
    # bare category noun ("Products") is too weak.
    if _is_ui_nav_label(t) or _is_prompt_artifact(t) or _is_weak_headline(t):
        return False
    words = t.split()
    if len(words) < 2:
        return False  # a lone word is a label, never a headline

    # (2a) Ends on terminal sentence punctuation → a full sentence/clause.
    if t.rstrip().endswith((".", "!", "?")):
        return True

    lower_words = [w.lower().strip(".,!?;:\"'’“”()") for w in words]

    # (1) Contains a recognizable verb. Known verbs match regardless of case (an
    # imperative headline often leads with a capitalized verb — "Build …", "Plan …").
    # The MORPHOLOGICAL -ing/-ed signal only counts on a LOWERCASE token, because a
    # Title-Cased "-ed"/"-ing" word is part of a section label ("Top Rated", "Most
    # Loved", "Trending Now"), not a clause verb — a real value-prop verb is
    # sentence-cased ("Allbirds makes …", "powered by …").
    for i, w in enumerate(lower_words):
        if w in _HEADLINE_VERBS:
            return True
        orig = words[i].strip(".,!?;:\"'’“”()")
        if (orig and orig[0].islower() and len(w) >= 5
                and (w.endswith("ing") or w.endswith("ed"))):
            return True

    # (2b) Carries a clause signal (linking/auxiliary/pronoun/subordinator word).
    # Require >=3 words so a 2-word Title-Case about/section label that merely starts
    # with a pronoun ("Our Story", "Your Account") is NOT mistaken for a clause — a
    # real clause-signal value-prop ("We help your team ship", "Built for the way you
    # work") has more than two words.
    if len(lower_words) >= 3 and any(w in _CLAUSE_SIGNALS for w in lower_words):
        return True

    # (2c) A value-prop is sentence-cased: at least one INTERIOR content word is
    # lowercase (not Title-Cased). A pure Title-Case noun phrase ("Popular Picks",
    # "Customer Favorites") capitalizes every significant word → has NO lowercase
    # interior content word → fails here → classified as a label.
    # Skip the first word (often a leading cap regardless) and very short function
    # words (a/an/the/of/and/or/in/on/to/for/with/by — lowercase by convention even
    # in Title Case, so their lowercase-ness is not evidence of a clause).
    _TITLECASE_FUNCTION = frozenset((
        "a", "an", "the", "of", "and", "or", "in", "on", "to", "for", "with",
        "by", "at", "from", "as", "&",
    ))
    for w in words[1:]:
        cw = w.strip(".,!?;:\"'’“”()")
        if not cw:
            continue
        low = cw.lower()
        if low in _TITLECASE_FUNCTION:
            continue
        # An interior content word that is all-lowercase → sentence-cased → headline.
        if cw[0].islower() and cw.isalpha():
            return True
    return False


# A standalone trailing temporal CTA marker ("... today", "... right now").
_CTA_TEMPORAL_RE = re.compile(
    r"\s*(?:[—–-]\s*)?\b(?:today|now|right\s+now|right\s+away)\b\.?\s*$",
    re.IGNORECASE,
)
# A trailing prepositional CTA tail that points at a SITE/BRAND, e.g. "at stripe.com",
# "with Plaid at plaid.com", "on Tripadvisor". We strip it ONLY when the tail names a
# domain (contains a dot) — that is what makes it a CTA address, not mid-sentence
# content. A descriptive "with over 800 million reviews" has no domain, so it stays.
_CTA_DOMAIN_TAIL_RE = re.compile(
    r"\s*\b(?:at|on|with|via|using|through)\b\s+[^.,;:!?]*\b\w+\.\w{2,}\b.*$",
    re.IGNORECASE,
)


def _punchy_headline(text: str, limit: int = 48) -> str:
    """Distill a SHORT, punchy headline phrase from a longer spoken line.

    Strips a trailing CTA tail that points at the site/brand ("at stripe.com",
    "with Plaid at plaid.com") plus a trailing temporal marker ("today", "right
    now"), and any leftover dangling function word — so a long closing-CTA beat
    becomes a crisp imperative phrase ("Start building better financial products")
    instead of a mid-URL truncation. It is CONSERVATIVE: a descriptive prepositional
    phrase with no domain ("with over 800 million reviews") is NOT a CTA tail and is
    preserved, so an OPENING line stays a complete clause. NEVER fabricates — it only
    trims the real text. Returns "" if nothing usable remains.
    """
    t = (text or "").strip()
    if not t:
        return ""
    # Peel the CTA tails on the RAW text FIRST — before any sentence clamp — because a
    # naive sentence split breaks "stripe.com" at its dot and would hide the domain
    # from the domain-tail matcher. Strip the temporal marker, then a trailing
    # sentence period, then the domain-pointing prepositional tail, repeatedly (handles
    # "... with Plaid at plaid.com today.").
    head = t
    prev = None
    while head and head != prev:
        prev = head
        head = head.rstrip().rstrip(".").strip()
        head = _CTA_TEMPORAL_RE.sub("", head).strip()
        head = _CTA_DOMAIN_TAIL_RE.sub("", head).strip()
    # Now take the first remaining sentence/clause and clamp to length.
    head = _title_from_text(head, limit=max(limit, 72))
    # Strip a trailing comma + any dangling tail word (function word, possessive, OR a
    # clause-bridge participle-helper like "letting"/"keeping") so the phrase never ends
    # on a dangling token ("...self-driving, letting" -> "...self-driving").
    head = _strip_dangling_tail(head)
    # The COMPLETE clause (<=72 chars), captured BEFORE the soft-limit truncation
    # below. A number followed by a unit + noun must keep its noun: when a dangling
    # number tail below is merely a truncation artifact, we restore from this clause.
    full_clause = head
    # Final length clamp to a word boundary (keep the lead verb-object, not the tail).
    # COMPLETE-CLAUSE GUARD: if truncation (or the raw text itself) ends mid-clause,
    # back up past the dangling prepositional/conjunction bridge so the headline ends
    # on a COMPLETE phrase, not a dangling tail like "to millions", "access to",
    # "of reviews". Applies BOTH when the text exceeds limit (truncation case) AND
    # when it fits within limit but the last two words form an incomplete prep phrase
    # (e.g. VO beat ends mid-sentence: "...gives travelers access to millions").
    _was_truncated = len(head) > limit
    if _was_truncated:
        # COMPLETE-CLAUSE-FIRST: prefer the first complete clause that fits the limit
        # (cut at a comma/semicolon/colon or BEFORE a relative-clause / participle
        # opener) over a hard mid-clause word chop. "...wool runners that keep your
        # feet warm" -> "...wool runners" (never "...that keep your"); "...workspace
        # for docs, wikis, and projects" -> "...workspace for docs" (never "wikis,").
        clause = _first_complete_clause(head, limit)
        if clause:
            truncated = clause
        else:
            truncated = head[:limit].rsplit(" ", 1)[0].rstrip(",").strip()
            truncated = _strip_dangling_tail(truncated)
        head = truncated
        # DANGLING-PREP-PHRASE guard (only when truncation actually cut the source):
        # a tail of "PREP + one short object" ("from natural", "with sharp", "for
        # businesses") is an INCOMPLETE prepositional phrase whose object was clipped.
        # Back up past the whole prep phrase to the last complete clause so the
        # grounded headline ends cleanly ("Allbirds makes comfortable shoes from
        # natural" -> "Allbirds makes comfortable shoes"). Only fires on truncation,
        # so a naturally-complete tail ("made from wool", "built for builders") is
        # preserved (that text fit within the limit and never entered this branch).
        _PREP_BRIDGES = frozenset((
            "from", "with", "for", "of", "in", "on", "at", "to", "into", "onto",
            "by", "as", "about", "over", "across", "through",
        ))
        w2 = head.split()
        if (len(w2) >= 3
                and w2[-2].lower().rstrip(",.") in _PREP_BRIDGES):
            # Drop the prep + its clipped object, then any newly-dangling tail word.
            w2 = w2[:-2]
            while w2 and w2[-1].lower().rstrip(",.") in _DANGLING_WORDS:
                w2.pop()
            if len(w2) >= 2:  # keep only if a real clause remains
                head = " ".join(w2)

    # Mid-clause chop guard (applies after truncation AND on raw sub-limit text):
    # Cases that produce a semantically incomplete tail:
    #   1. The last word itself is a function word ("access to", "hotels and") — already
    #      handled by the dangling-word strip above (the while loop).
    #   2. The last word is a vague quantifier (e.g. "millions", "thousands") that reads
    #      as incomplete without a following noun phrase — especially when preceded by
    #      "to"/"of"/"for" etc. (e.g. "access to millions", "see of hundreds").
    #   3. The last word is a NUMERAL or MAGNITUDE WORD (e.g. "800", "12,000", "million",
    #      "billion") — these always need a following noun to be complete. A headline must
    #      NEVER end on a bare number or magnitude word like "over 800 million" (the
    #      TripAdvisor residual: "…access to over 800 million" dropped "trusted reviews").
    #      Detection: last token matches a numeral pattern OR is a magnitude-scale word;
    #      if preceded by a function/quantifier word OR another numeral, back up past the
    #      entire dangling number phrase to the nearest content word.
    _BARE_QUANTIFIERS = frozenset((
        "millions", "thousands", "hundreds", "billions", "dozens",
        "many", "some", "few", "several", "various", "multiple",
        "all", "both", "each", "every", "those", "these", "their",
        # singular magnitude scale words (case 3)
        "million", "billion", "trillion", "thousand", "hundred",
    ))
    # A token is a bare numeral when it consists of digits, commas, dots, and optional
    # trailing scale suffix (k/m/b). Examples: "800", "12,000", "1.3m", "4b".
    _NUMERAL_RE = re.compile(r"^\d[\d,.]*(k|m|b)?$", re.IGNORECASE)

    def _is_dangling_number_tail(words: list) -> bool:
        """True when the word list ends on an incomplete number/quantifier phrase."""
        if not words:
            return False
        last = words[-1].lower().rstrip(",.")
        # Case 2: bare vague quantifier (e.g. "millions")
        if last in _BARE_QUANTIFIERS:
            # Only flag it when preceded by a function word or another number token
            # (avoids flagging "Stripe serves millions" where "millions" is complete).
            if len(words) >= 2:
                prev = words[-2].lower().rstrip(",.")
                if prev in _DANGLING_WORDS or _NUMERAL_RE.match(prev) or prev in _BARE_QUANTIFIERS:
                    return True
            return False
        # Case 3: bare numeral token (e.g. "800", "12,000", "1.3m")
        if _NUMERAL_RE.match(last):
            return True
        return False

    # Quantifier-modifier words that precede numbers/magnitudes (e.g. "over 800",
    # "about 12,000", "more than 5 million") — strip these alongside the numeral so
    # "access to over 800" becomes "access" (not "access to over").
    _QUANTIFIER_MODIFIERS = frozenset((
        "over", "about", "approximately", "around", "nearly", "roughly",
        "more", "less", "than", "almost", "exactly", "just", "only",
    ))

    w2 = head.split()
    if _is_dangling_number_tail(w2):
        # KEEP-THE-NOUN guard: the dangling number tail is usually a TRUNCATION
        # ARTIFACT — the complete clause continues with the unit/noun that completes
        # the numeric claim (e.g. "...over 800 million" was clipped from "...over 800
        # million trusted reviews"). When the complete clause does NOT itself end on a
        # bare number, restore it whole so the stat keeps its noun, rather than dropping
        # the most compelling part of the headline. A number+unit+noun must keep the noun.
        if full_clause != head and not _is_dangling_number_tail(full_clause.split()):
            head = full_clause
        else:
            # The SOURCE genuinely ends on a bare number (no completing noun). Strip
            # back past the entire dangling number phrase (may be multiple tokens, e.g.
            # "over 800 million" needs stripping of "over", "800", "million"; "access to
            # over 800" -> strip "800", then "over", then "to" -> "access").
            while w2 and (
                w2[-1].lower().rstrip(",.") in _DANGLING_WORDS
                or w2[-1].lower().rstrip(",.") in _BARE_QUANTIFIERS
                or w2[-1].lower().rstrip(",.") in _QUANTIFIER_MODIFIERS
                or _NUMERAL_RE.match(w2[-1].lower().rstrip(",."))
            ):
                w2.pop()
            head = " ".join(w2)
    elif len(w2) >= 2 and w2[-2].lower() in _DANGLING_WORDS and w2[-1].lower() in _BARE_QUANTIFIERS:
        # Original guard: "PREP QUANTIFIER" tail (kept as belt-and-suspenders).
        w2 = w2[:-2]
        while w2 and w2[-1].lower() in _DANGLING_WORDS:
            w2.pop()
        head = " ".join(w2)

    # FINAL ORPHAN-CONNECTOR GUARD: catch a connector whose object was severed
    # ("...in minutes using clear" cut at the comma before "comprehensive
    # documentation"). _first_complete_clause already backs these up when it fires;
    # this re-check covers any path that produced an orphan shape. `was_cut` is true
    # when the distilled head is shorter than the complete clause captured before the
    # soft-limit truncation (i.e. content was removed) — so a naturally-complete tail
    # ("built for builders", "for businesses") that was never cut is preserved.
    _head_was_cut = (head != full_clause) or _was_truncated
    if head and _ends_on_orphan_connector(head, was_cut=_head_was_cut):
        backed = _drop_orphan_connector_phrase(head)
        if len(backed.split()) >= 2:
            head = backed

    return head if len(head.split()) >= 2 else ""


# Tokens too generic to identify a feature (avoid a spurious "best match").
_FEATURE_STOPWORDS = frozenset((
    "the", "and", "or", "a", "an", "of", "to", "for", "with", "your", "our",
    "machine", "machining", "part", "parts", "metal", "service", "services",
    "manufacturing", "instant", "quote", "quotes", "get", "file", "fast", "today",
))


def _feature_tokens(text: str) -> set:
    """Lowercase content tokens (>=2 chars, not stopwords) for overlap matching."""
    return {t for t in re.findall(r"[a-z0-9]+", str(text).lower())
            if len(t) >= 2 and t not in _FEATURE_STOPWORDS}


def _match_feature(features: List[str], scene_text: str) -> Optional[int]:
    """Index of the feature whose distinctive label words best overlap scene_text,
    or None when nothing meaningfully matches (so the caller falls back to a
    positional rotation). Only REAL features are considered — no fabrication."""
    want = _feature_tokens(scene_text)
    if not want:
        return None
    best_i, best_score = None, 0
    for i, label in enumerate(features):
        score = len(_feature_tokens(label) & want)
        if score > best_score:
            best_i, best_score = i, score
    return best_i


# Magnitude-bearing stat token: currency, big-number suffix (B/M/K/billion...), %,
# x, or a trailing "+" — i.e. an IMPRESSIVE number, not a bare "10 minutes".
_TITLE_STAT_RE = re.compile(
    r"\$\s?\d[\d,\.]*\s?(?:[BMKT]|bn|billion|million|thousand|trillion)?\+?(?![A-Za-z])"
    r"|\d[\d,\.]*\s?(?:[BMKT]|bn|billion|million|thousand|trillion)\+?(?![A-Za-z])"
    r"|\d[\d,\.]*\s?[%x](?![A-Za-z])"
    r"|\d[\d,\.]*\+",
    re.I)


def _mine_stat_from_title(title):
    """If the filled title carries an IMPRESSIVE number (currency / % / x / big-suffix
    / trailing +), split it into {value, label}. Honest: the number is taken verbatim
    from the real filled title. Returns None for bare/small numbers (e.g. "10 minutes")."""
    if not title:
        return None
    # Normalize honest word-forms so site numbers like "50-plus" / "92 percent" mine
    # like their symbolic forms "50+" / "92%". The DIGITS stay verbatim — no invention.
    norm = re.sub(r"(?<![A-Za-z0-9])(\d[\d,\.]*)\s*[- ]?\s*plus\b", r"\1+", title, flags=re.I)
    norm = re.sub(r"(?<![A-Za-z0-9])(\d[\d,\.]*)\s+percent\b", r"\1%", norm, flags=re.I)
    m = _TITLE_STAT_RE.search(norm)
    if not m:
        return None
    value = m.group(0).strip()
    label = (norm[:m.start()] + " " + norm[m.end():])
    label = re.sub(r"\s{2,}", " ", label).strip(" —-·,:").strip()
    # Keep the label a TIGHT phrase for a hero stat: cut at the first clause break
    # and cap at ~5 words ("The standard deal: for 7% with uncapped..." -> "The
    # standard deal").
    label = re.split(r"[:—;(]| - ", label)[0].strip()
    label = " ".join(label.split()[:5])
    return {"value": value, "label": label}


def _split_statement_lines(title: str) -> List[str]:
    """Split a real title into <=2 BALANCED lines for the kinetic-statement hook.
    VERBATIM words only -- never invents or drops copy. Prefers an existing sentence
    boundary ("Paste a URL. Get a launch video." -> two lines); else balances the word
    count across two lines. A short title (<=4 words) stays a single line."""
    t = " ".join((title or "").split()).strip()
    if not t:
        return []
    # 1) Honor an explicit sentence boundary near the middle (keeps the punctuation).
    parts = re.split(r"(?<=[.!?])\s+", t)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) == 2:
        return parts
    if len(parts) > 2:
        # Re-balance >2 sentences into two lines by word count.
        words_all = t.split()
    else:
        words_all = t.split()
    if len(words_all) <= 4:
        return [t]
    # 2) Balance by word count -- break at the word boundary nearest the midpoint.
    mid = len(words_all) // 2
    return [" ".join(words_all[:mid]).strip(), " ".join(words_all[mid:]).strip()]


def _assign_treatment_from_filled_copy(
    out: Dict[str, Any], scene: Dict[str, Any], brand: Dict[str, Any]
) -> None:
    """AUTHORITATIVE card-treatment pass that runs on the FILLED card copy.

    THE BUG THIS FIXES: plan_job's `_assign_card_treatments` runs at PLAN time —
    BEFORE this function (style_fill) writes the card title/subtitle. So plan_job's
    entity miner + `_stat_is_real` saw EMPTY titles and every feature card collapsed
    to "icon-headline", even for entity-rich scenes like "Airbnb, Stripe, Dropbox
    founders share raw stories" whose title is filled HERE, afterward.

    This pass re-derives the treatment from the REAL filled copy (`out["title"]` +
    `out["subtitle"]`, plus any LLM-emitted stat/treatment that survived plan time)
    and OVERRIDES whatever plan_job picked. It reuses plan_job's HONEST miners so the
    rules stay in one place:
      1. Mine featureEntities from the filled title+subtitle (>= 3 proper nouns ->
         keep; exclude the brand wordmark). Real-text only — never invents.
      2. Keep an LLM-emitted `stat` only if `plan_job._stat_is_real` passes against
         a scene whose data carries the FILLED copy (so the stat's number must appear
         in real brand text).
      3. (Re)assign treatment: real stat -> "split-stat" (or "icon-stat" when the
         scene already has a curated icon + a punchy headline); >= 3 real entities ->
         "split-mosaic"; else "icon-headline" (the honest floor).
    Writes treatment / icon / stat / featureEntities onto `out` (the dict the render
    reads). Honesty FIRST — never fabricate a stat or an entity.

    `brand` is style_fill's resolved brand-facts dict (wordmark/tagline/features) and
    serves directly as plan_job's `company_facts` (same field names).
    """
    d = scene.get("data") or {}
    company_facts = brand if isinstance(brand, dict) else {}
    real_entities = plan_job._feature_entities_from_facts(company_facts)

    title = str(out.get("title") or "")
    subtitle = str(out.get("subtitle") or "")
    filled_copy = (title + " " + subtitle).strip()

    # 3y) kinetic-statement (HARVESTED from cluely-promo / Luceo Studio): a big editorial
    #      HOOK that assembles word-by-word (rise-blur), one keyword tinted in accent +
    #      glow halo, an optional highlighter sweep under one word. OPT-IN ONLY +
    #      NON-REGRESSIVE: select only when the scene flags itself a hook
    #      (`kind == "hook"` OR the planner pre-emitted treatment="kinetic-statement")
    #      AND there is real title/lines text AND there is NO competing data (no stat,
    #      featureEntities, metrics, imageSrc, compare, or quote). A generic no-data
    #      scene still degrades to icon-headline, never into this. Words read VERBATIM
    #      from the real copy -- emphasis/underline words are kept only when they appear
    #      verbatim in the joined lines (else rendered plain). Never fabricated.
    opts_in_kinetic = (
        str(d.get("kind") or "").strip().lower() == "hook"
        or str(d.get("treatment") or "").strip() == "kinetic-statement"
    )
    raw_lines = [str(x).strip() for x in (d.get("lines") or [])
                 if isinstance(x, (str, int, float)) and str(x).strip()]
    has_statement_text = bool(raw_lines) or bool(title.strip())
    has_competing_data = bool(
        (d.get("stat") or {}).get("value") if isinstance(d.get("stat"), dict) else d.get("stat")
    ) or bool(
        [e for e in (d.get("featureEntities") or []) if str(e or "").strip()]
    ) or bool(
        [m for m in (d.get("metrics") or []) if isinstance(m, dict) and str(m.get("value") or "").strip()]
    ) or bool(str(d.get("imageSrc") or "").strip()) or bool(d.get("compare")) or bool(
        str(d.get("quote") or "").strip()
    )
    # A competing NUMBER mined from the title means this is a stat beat, not a pure
    # statement beat -- defer to the stat treatments (honesty / non-regression).
    has_competing_number = bool(_mine_stat_from_title(title))
    if opts_in_kinetic and has_statement_text and not has_competing_data and not has_competing_number:
        # Lines: prefer explicit real lines; else derive <=2 balanced lines from the
        # title (verbatim words only -- _split_statement_lines never invents text).
        lines = raw_lines[:2] if raw_lines else _split_statement_lines(title)
        out["treatment"] = "kinetic-statement"
        out["lines"] = [_decode(x) for x in lines]
        joined = " ".join(out["lines"]).lower()
        # Pass through eyebrow / emphasis / underline. Each emphasis/underline word is
        # KEPT only when it appears verbatim (case-insensitive) in the joined lines.
        eyebrow = str(d.get("eyebrow") or "").strip()
        if eyebrow:
            out["eyebrow"] = _decode(eyebrow)
        else:
            out.pop("eyebrow", None)
        for key in ("emphasisWord", "underlineWord"):
            word = str(d.get(key) or "").strip()
            if word and re.search(r"\b" + re.escape(word.lower()) + r"\b", joined):
                out[key] = _decode(word)
            else:
                out.pop(key, None)
        # Brand-badge opening (Design-Fit vibe variety): keep the badge flag, and if no
        # explicit emphasis word, accent the longest content word so the opening pops.
        if d.get("brandBadge"):
            out["brandBadge"] = True
            if not out.get("emphasisWord"):
                _w = max((w.strip(".,!?:;\"'") for w in " ".join(out["lines"]).split()),
                         key=len, default="")
                if len(_w) >= 5:
                    out["emphasisWord"] = _decode(_w)
        out.pop("icon", None)
        out.pop("stat", None)
        out.pop("featureEntities", None)
        out.pop("metrics", None)
        out.pop("compare", None)
        out.pop("imageSrc", None)
        out["patternReason"] = "kinetic-statement: animated hook statement"
        return

    # Build a synthetic scene whose `data` carries the FILLED copy so plan_job's
    # honesty corpus (which reads data.title / data.subtitle / brief) sees the REAL
    # rendered text rather than the empty plan-time data.
    probe = {
        "brief": scene.get("brief") or "",
        "data": {
            "title": title,
            "subtitle": subtitle,
            "_text": d.get("_text") or "",
        },
    }

    # 1) Entities: prefer LLM-emitted featureEntities that are corroborated by the
    #    filled copy / real features; else mine proper nouns from the filled copy.
    entities: List[str] = []
    raw_ents = d.get("featureEntities")
    if isinstance(raw_ents, list):
        ent_corpus = " ".join([filled_copy, " ".join(real_entities),
                               str(company_facts.get("tagline") or "")]).lower()
        entities = [str(e).strip() for e in raw_ents
                    if str(e or "").strip() and str(e).strip().lower() in ent_corpus]
    if len(entities) < 3:
        mined = plan_job._mine_named_entities(
            filled_copy,
            exclude=(company_facts.get("wordmark"), company_facts.get("brand"),
                     company_facts.get("name"),
                     (real_entities[0] if real_entities else None)),
        )
        if len(mined) >= 3:
            entities = mined[:6]
    has_mosaic = len(entities) >= 3

    # 2) Stat: keep an LLM stat if real; else MINE an impressive stat from the title
    #    ("$600B+ combined valuation", "3,000+ alumni"). Honest -- the number is taken
    #    verbatim from the real filled title.
    stat = d.get("stat")
    has_real_stat = plan_job._stat_is_real(stat, probe, company_facts)
    mined_stat = None
    if not has_real_stat:
        mined_stat = _mine_stat_from_title(title)

    # 3) (Re)assign treatment. DENNIS'S LAYOUT PREFERENCE: text LEFT + a fancy VISUAL
    #    RIGHT (number+bars / tile grid) -> the SPLIT treatments dominate. Real OR
    #    mined stat -> split-stat (headline left, number + rising bars right). >=3
    #    entities -> split-mosaic (headline left, tile grid right). Centered
    #    big-number ONLY when the title is JUST a number (nothing for the left).
    #    icon-headline is the honest floor (no stat/entities). Never fabricate.
    icon = str(d.get("icon") or "").strip()

    # 3z) device-frame: text-left / a REAL captured product screenshot wrapped in a
    #     clean browser frame on the RIGHT. HONESTY GUARD: select ONLY when the scene
    #     carries a real captured screenshot (`imageSrc` non-empty) AND it is a product
    #     beat (`kind == "product"` or the planner pre-emitted treatment="device-frame").
    #     Never select without a real screenshot -- without one there is nothing honest
    #     to show in the frame, so we fall through to the stat/entity/floor logic.
    image_src = str(d.get("imageSrc") or "").strip()
    is_product_beat = (
        str(d.get("kind") or "").strip().lower() == "product"
        or str(d.get("treatment") or "").strip() == "device-frame"
    )
    if image_src and is_product_beat:
        out["treatment"] = "device-frame"
        out["imageSrc"] = image_src
        out.pop("icon", None)
        out.pop("stat", None)
        out.pop("featureEntities", None)
        out.pop("metrics", None)
        out["patternReason"] = "device-frame: real product screenshot"
        return

    # 3a) metric-row: a strip of 3-4 REAL small stats (value + label). Selected
    #     BEFORE the single-stat treatments. HONESTY GUARD: keep only metrics whose
    #     `value` carries a real number (same miner as the title stat); drop the rest.
    #     If fewer than 3 survive, do NOT select metric-row -- fall through to the
    #     stat/entity/floor logic below (never a half-empty strip).
    raw_metrics = d.get("metrics")
    valid_metrics: List[Dict[str, Any]] = []
    if isinstance(raw_metrics, list):
        for m in raw_metrics:
            if not isinstance(m, dict):
                continue
            value = str(m.get("value") or "").strip()
            if value and _TITLE_STAT_RE.search(value):
                valid_metrics.append({
                    "value": _decode(value),
                    "label": _decode(str(m.get("label") or "").strip()),
                })
    if len(valid_metrics) >= 3:
        out["treatment"] = "metric-row"
        out.pop("icon", None)
        out.pop("stat", None)
        out.pop("featureEntities", None)
        out["metrics"] = valid_metrics[:4]
        out["patternReason"] = "metric-row: %d real metrics" % len(out["metrics"])
        return

    # 3pp) process-pipeline: a horizontal "how it works" flow of numbered step cards
    #      (harvested from smartbase). HONESTY: select only when REAL steps exist
    #      (>=2 each with a title). Content-fit -- driven by the Design Brief's
    #      story_shape.process_steps seeded onto data.steps.
    raw_steps = d.get("steps")
    valid_steps: List[Dict[str, Any]] = []
    if isinstance(raw_steps, list):
        for st in raw_steps:
            if not isinstance(st, dict):
                continue
            stitle = str(st.get("title") or "").strip()
            if stitle:
                valid_steps.append({
                    "badge": _decode(str(st.get("badge") or ("0%d" % (len(valid_steps) + 1)))),
                    "title": _decode(stitle),
                    "body": _decode(str(st.get("body") or "").strip()),
                })
    if len(valid_steps) >= 2:
        out["treatment"] = "process-pipeline"
        out.pop("icon", None)
        out.pop("stat", None)
        out.pop("featureEntities", None)
        out.pop("metrics", None)
        out["steps"] = valid_steps[:4]
        out["patternReason"] = "process-pipeline: %d real steps" % len(out["steps"])
        return

    # 3c) comparison-columns: a two-column contrast (the muted "old way" LEFT vs the
    #     accented "with Filmo" way RIGHT). HONESTY GUARD: select ONLY when the planner
    #     extracted a REAL contrast -- `compare` is a dict whose leftItems and rightItems
    #     are each lists with >=2 non-empty strings AND both side titles are non-empty.
    #     NEVER invent a contrast; if `compare` is absent or a side is short, fall through
    #     to the stat/entity/floor logic below (never a lopsided / half-empty comparison).
    raw_compare = d.get("compare")
    if isinstance(raw_compare, dict):
        left_items = [str(x).strip() for x in (raw_compare.get("leftItems") or [])
                      if isinstance(x, (str, int, float)) and str(x).strip()]
        right_items = [str(x).strip() for x in (raw_compare.get("rightItems") or [])
                       if isinstance(x, (str, int, float)) and str(x).strip()]
        left_title = str(raw_compare.get("leftTitle") or "").strip()
        right_title = str(raw_compare.get("rightTitle") or "").strip()
        if len(left_items) >= 2 and len(right_items) >= 2 and left_title and right_title:
            out["treatment"] = "comparison-columns"
            out.pop("icon", None)
            out.pop("stat", None)
            out.pop("featureEntities", None)
            out.pop("metrics", None)
            out["compare"] = {
                "leftTitle": _decode(left_title),
                "leftItems": [_decode(x) for x in left_items],
                "rightTitle": _decode(right_title),
                "rightItems": [_decode(x) for x in right_items],
            }
            out["patternReason"] = "comparison-columns: %dv%d items" % (
                len(left_items), len(right_items))
            return

    # 3d) pull-quote: a large editorial testimonial. HONESTY GUARD (the most
    #     important guard in this function): select ONLY when `quote` is a REAL,
    #     non-empty string of >= 6 words AND `quoteAttribution` is non-empty. A
    #     fabricated, padded, or unattributed testimonial is the worst possible
    #     output for an anti-slop product -- so an absent / too-short quote OR a
    #     missing attribution falls through to the stat/entity/floor logic below.
    #     NEVER invent a quote or an attribution.
    quote_text = str(d.get("quote") or "").strip()
    attribution = str(d.get("quoteAttribution") or "").strip()
    if quote_text and attribution and len(quote_text.split()) >= 6:
        out["treatment"] = "pull-quote"
        out["quote"] = _decode(quote_text)
        out["quoteAttribution"] = _decode(attribution)
        out.pop("icon", None)
        out.pop("stat", None)
        out.pop("featureEntities", None)
        out.pop("metrics", None)
        out.pop("compare", None)
        out.pop("imageSrc", None)
        out["patternReason"] = "pull-quote: real testimonial"
        return

    use_stat = stat if (has_real_stat and isinstance(stat, dict)) else (mined_stat or None)
    mined_only = bool(mined_stat) and not has_real_stat
    mined_label = (mined_stat.get("label") or "").strip() if mined_stat else ""
    if use_stat:
        treatment = "big-number" if (mined_only and not mined_label) else "split-stat"
    elif has_mosaic:
        treatment = "split-mosaic"
    else:
        treatment = "icon-headline"

    # 4) Emit onto the rendered props (SHARED DATA CONTRACT field names exact).
    #    Also record patternReason -- a human-readable trace of WHY this treatment was
    #    chosen, citing the REAL data that earned it (stat value / entity count) or the
    #    honest floor. PURELY ADDITIVE legibility: it never alters the choice above.
    out["treatment"] = treatment
    out.pop("icon", None)
    out.pop("stat", None)
    out.pop("featureEntities", None)
    if treatment == "icon-headline":
        out["icon"] = _decode(icon) if icon else plan_job._DEFAULT_ICON
        out["patternReason"] = "icon-headline: no real stat/entities (honest floor)"
    if treatment == "split-stat":
        stat_value = _decode(str(use_stat.get("value") or ""))
        if mined_only:
            # the title WAS the number -> descriptor becomes the LEFT headline,
            # number goes to the RIGHT panel.
            out["title"] = mined_label or str(out.get("title") or "")
            out["stat"] = {"value": stat_value, "label": ""}
        else:
            # has_real_stat: the LLM stat goes on the RIGHT; strip any COMPETING number
            # from the LEFT headline so it doesn't fight the stat panel ("Merchants see
            # revenue lift, 99.9%" + stat 12% -> headline "Merchants see revenue lift").
            ct = _TITLE_STAT_RE.sub("", str(out.get("title") or ""))
            ct = re.sub(r"\s{2,}", " ", ct).strip(" ,—-·:").strip()
            if ct:
                out["title"] = ct
            out["stat"] = {
                "value": stat_value,
                "label": _decode(str(use_stat.get("label") or "")),
            }
        out["patternReason"] = "split-stat: real stat %s" % stat_value
    if treatment == "big-number" and isinstance(use_stat, dict):
        stat_value = _decode(str(use_stat.get("value") or ""))
        out["title"] = ""   # the number is the whole message
        out["stat"] = {"value": stat_value,
                       "label": _decode(str(use_stat.get("label") or ""))}
        out["patternReason"] = "big-number: %s" % stat_value
    if treatment == "split-mosaic":
        out["featureEntities"] = [_decode(str(e)) for e in entities if str(e or "").strip()]
        out["patternReason"] = "split-mosaic: %d real entities" % len(out["featureEntities"])


def _shape_explainer(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """ExplainerCard data: kicker / title / subtitle / bullets.

    A cinematic/walkthrough/demo beat that gets no real footage still SHOWS the
    narrated point. Prefers explicit copy in scene["data"]; falls back to the
    scene's own brief / VO beat text and the brand's real features — never
    invented marketing copy (honesty rule, brand_extract.py).
    """
    d = scene.get("data") or {}
    brief = scene.get("brief") or ""
    # Title source priority: explicit plan copy -> threaded VO beat / brief text
    # -> the scene's own brief -> brand fallback. NEVER empty (blank-scenes fix):
    # an empty input falls through to the brand tagline/wordmark, never "".
    title = (d.get("title")
             or _title_from_text(d.get("_text") or "")
             or _title_from_text(brief)
             or _brand_fallback_title(brand)
             or brand.get("wordmark") or "").strip()
    # Subtitle = ONE distinct DETAIL drawn from THIS scene's own VO beat (the second
    # sentence the title didn't use), deduped across scenes via the shared used list —
    # NOT the shared brand tagline (which produced the repeated-subtitle bug). Empty is
    # fine: a card with just the key phrase reads clean ("reinforce" model).
    used_supporting = d.get("_used_supporting")
    used_supporting = used_supporting if isinstance(used_supporting, list) else None
    subtitle = d.get("subtitle")
    if subtitle is None:
        subtitle = _supporting_line(title, d.get("_text") or "", brief, brand,
                                    used=used_supporting)
    if _is_fragment_subtitle(subtitle):
        subtitle = ""

    # Reinforce model: feature cards show the key phrase + one detail, NO bullets.
    bullets: List[str] = []

    out: Dict[str, Any] = {
        "kicker": _decode(d.get("kicker") or ""),
        "title": _decode(title),
        "subtitle": _decode(subtitle or ""),
        "bullets": bullets,
    }

    # CARD TREATMENT (SHARED DATA CONTRACT with the Remotion ExplainerCard archetype).
    # AUTHORITATIVE post-fill pass: plan_job's plan-time `_assign_card_treatments` saw
    # EMPTY titles (this function fills them AFTER plan time), so it collapsed every
    # feature card to "icon-headline" even when the filled copy is entity/stat-rich.
    # Re-derive the treatment HERE, on the REAL filled title/subtitle, reusing
    # plan_job's HONEST miners. This OVERRIDES plan_job's stale pick.
    #   treatment        "icon-stat" | "split-mosaic" | "split-stat" | "icon-headline"
    #   icon             curated icon name (icon-stat / icon-headline)
    #   stat             {"value": str, "label": str} (stat treatments)
    #   featureEntities  list[str] of REAL named entities (split-mosaic)
    _assign_treatment_from_filled_copy(out, scene, brand)
    return out


def _walkthrough_clip_path(scene: Dict[str, Any]) -> str:
    """The produced walkthrough clip path for a scene, or "" when none exists.

    Looks in scene["data"] AND the scene root (the producer may attach the clip as
    `output_path` on the scene, or a plan may pre-stage it as data.videoSrc). The
    presence of a real clip is what routes a `walkthrough` role to the player
    archetype; absence falls back to the never-blank explainer card.
    """
    d = scene.get("data") or {}
    for key in _WALKTHROUGH_CLIP_KEYS:
        val = d.get(key) or scene.get(key)
        if val and str(val).strip():
            return str(val).strip()
    return ""


def _has_walkthrough_clip(scene: Dict[str, Any]) -> bool:
    return bool(_walkthrough_clip_path(scene))


def _emphasis_phrase(emphasis: str, limit: int = 48) -> str:
    """A clean overlay-title phrase from the run's raw emphasis input.

    The emphasis is user text (e.g. "the pricing page", "instant quoting") that
    feeds the walkthrough goal. For a title bar we want a tidy noun phrase:
      - strip a leading article ("the "/"a "/"an ") so "Stripe — pricing page",
      - capitalize the first letter (leave the rest as-typed to preserve casing
        like "API"),
      - clamp to a word boundary under `limit`.
    Never fabricates — it only trims/cleans the real emphasis string.
    """
    e = (emphasis or "").strip()
    if not e:
        return ""
    e = re.sub(r"^(the|a|an)\s+", "", e, flags=re.IGNORECASE).strip()
    if not e:
        return ""
    # Boundary-safe clip: NEVER end on a dangling connector / mid-word. A plain
    # rsplit chop produced the "Stripe — ... Migrate to" bug (trailing "to"); route
    # through _clip_to_clause so the overlay title is always a COMPLETE phrase.
    e = _clip_to_clause(e, limit) or e
    if not e:
        return ""
    return e[0].upper() + e[1:]


def _shape_walkthrough(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """WalkthroughPlayer data: videoSrc / overlayTitle / muteClip (+ optional caption).

    The produced walkthrough MP4 plays INSIDE the branded frame; the scene VO owns
    the audio, so muteClip defaults True. The overlay title is the brand wordmark
    plus the run's EMPHASIS (the user-supplied feature/area, e.g. "the pricing
    page") — the one thing the title bar must stay on-topic with. The emphasis is
    threaded as `data._emphasis` by build_props; if absent we fall back to the
    scene's brief/VO text trimmed to a phrase. NEVER fabricates copy — it trims
    real emphasis/brand/VO text (honesty rule).

    Only reached when a real clip exists (build_props routes a clip-less walkthrough
    role to the explainer card instead), but it still floors every field so a
    mis-route degrades gracefully rather than crashing.
    """
    d = scene.get("data") or {}
    clip = _walkthrough_clip_path(scene)

    # Overlay title: explicit copy -> brand wordmark + emphasis -> wordmark alone.
    # Prefer the run's real emphasis (data._emphasis, threaded by build_props) over
    # the planner's free-text VO, which often narrates a DIFFERENT flow than the
    # emphasized feature (e.g. emphasis="the pricing page" but VO="create a payment
    # link...") and would otherwise leak into the title bar.
    wordmark = (brand.get("wordmark") or brand.get("brand") or brand.get("name") or "").strip()
    emphasis = (_emphasis_phrase(d.get("_emphasis") or "")
                or _title_from_text(d.get("_text") or "")
                or _title_from_text(scene.get("brief") or "")).strip()
    if d.get("overlayTitle"):
        overlay_title = str(d["overlayTitle"]).strip()
    elif wordmark and emphasis and emphasis.lower() != wordmark.lower():
        # "Brand — emphasis" (en-dash join), e.g. "Stripe — Dashboard walkthrough".
        overlay_title = f"{wordmark} — {emphasis}"
    else:
        overlay_title = wordmark or emphasis or _brand_fallback_title(brand)

    out: Dict[str, Any] = {
        "videoSrc": clip,
        "overlayTitle": _decode(overlay_title),
        # VO owns the audio (per-scene <Audio> placed at the scene's in_frame).
        "muteClip": True,
        # contain so a UI walkthrough never crops its chrome; cover only on request.
        "videoFit": d.get("videoFit") or "contain",
    }
    if d.get("caption"):
        out["caption"] = _decode(str(d["caption"]).strip())
    return out


# Generic "filler" words that should NEVER be the accent-popped punch noun (they read
# as glue, not the salient concept the headline is about). Lowercased comparison.
_PUNCH_STOPWORDS = frozenset((
    "the", "a", "an", "and", "or", "but", "for", "to", "of", "in", "on", "at",
    "by", "with", "from", "into", "onto", "your", "our", "their", "its", "his",
    "her", "this", "that", "these", "those", "is", "are", "be", "been", "was",
    "were", "you", "we", "they", "it", "all", "any", "every", "more", "most",
    "one", "single", "just", "only", "very", "so", "as", "up", "out", "over",
    "makes", "make", "build", "built", "get", "gets", "use", "uses",
))


# Known acronyms / proper-cased tokens that must KEEP their casing in an eyebrow
# label (so "AI" never title-cases to "Ai"). Matched case-insensitively against the
# token; the canonical form here is emitted. A token already mixed-case or all-caps
# (e.g. "PayPal", "SaaS", "iOS") is also preserved by _eyebrow_case below.
_EYEBROW_ACRONYMS = {
    "ai": "AI", "ml": "ML", "ui": "UI", "ux": "UX", "api": "API", "sdk": "SDK",
    "saas": "SaaS", "b2b": "B2B", "b2c": "B2C", "erp": "ERP", "crm": "CRM",
    "ios": "iOS", "id": "ID", "url": "URL", "cli": "CLI", "kpi": "KPI",
    "seo": "SEO", "pdf": "PDF", "qr": "QR", "faq": "FAQ", "ceo": "CEO",
}

# Bare connectors / conjunctions / symbols that may NEVER stand as (or lead) an
# eyebrow label — they are glue, not the topic. A leading one is dropped; a label
# made only of these collapses to the remaining content noun.
_EYEBROW_CONNECTORS = frozenset((
    "&", "+", "/", "and", "or", "but", "the", "a", "an", "of", "for", "to",
    "with", "in", "on", "at", "by", "from", "is", "are", "be", "your", "our",
))

# Leading IMPERATIVE / action verbs to drop so an eyebrow leads with the NOUN topic
# ("Accept payments" -> "Payments", "Run subscriptions" -> "Subscriptions", "Take a
# closer look" -> the trailing noun). Only stripped when a content noun follows. A
# gerund ("Accepting") is caught separately by the "ing" heuristic; a real noun ending
# in "ing" (Pricing/Billing/Marketing) is NOT a verb and is kept.
_EYEBROW_LEAD_VERBS = frozenset((
    "accept", "run", "take", "manage", "track", "build", "get", "see", "view",
    "use", "make", "give", "send", "start", "create", "explore", "discover",
    "connect", "integrate", "understand", "keep", "plan", "show", "find",
    "accepts", "runs", "takes", "manages", "tracks", "builds", "gets",
    "do", "go", "add", "set", "put", "let", "try", "join",
))

# Words ending in "ing" that are real NOUNS (a topic/feature), not gerund verbs — so
# the leading-verb stripper never mistakes them for an action. Lowercased.
_EYEBROW_NOUN_INGS = frozenset((
    "pricing", "billing", "marketing", "training", "onboarding", "reporting",
    "accounting", "shipping", "booking", "listing", "messaging", "meeting",
    "engineering", "advertising", "branding", "banking", "lending", "trading",
))


def _eyebrow_case(word: str) -> str:
    """Casing for ONE eyebrow token: keep a known acronym ("AI", "API"), keep an
    already mixed/all-caps proper token ("PayPal", "iOS", "SaaS"), else Title-case a
    plain lowercase word ("pricing" -> "Pricing"). Never lowercases an acronym."""
    w = (word or "").strip()
    if not w:
        return ""
    low = w.lower()
    if low in _EYEBROW_ACRONYMS:
        return _EYEBROW_ACRONYMS[low]
    # Already carries internal/uppercase signal (acronym or camel/proper token) — keep.
    if w[1:] and any(c.isupper() for c in w[1:]):
        return w  # "PayPal", "iOS", "GitHub"
    if w.isupper() and len(w) >= 2:
        return w  # "SDK", "CRM" not in the table
    return w[:1].upper() + w[1:].lower()


# Connector tokens that SPLIT a page phrase into clauses. We keep only the HEAD
# clause (before the first such connector) so an eyebrow names ONE feature, never a
# multi-clause tail ("Pricing & Fees" -> "Pricing", "Terms of Service" -> "Terms").
_EYEBROW_SPLIT_CONNECTORS = frozenset((
    "&", "+", "/", "and", "or", "of", "plus", "vs",
))


def _short_eyebrow(label: str, max_words: int = 2, avoid: str = "") -> str:
    """Trim a phrase to a SHORT, CLEAN eyebrow label (default <= 2 words) that names
    the FEATURE / key topic, NEVER a dangling fragment, a leading conjunction, or
    mangled casing:
        "Pricing & Fees"                  -> "Pricing"               (not "& Fees")
        "Notion is the AI workspace"      -> "AI Workspace"          (not "Notion Ai")
        "Stripe is the financial …"       -> "Financial Infrastructure"
        "Accepting card payments"         -> "Card Payments"
        "Terms of Service"                -> "Terms"
        "API Reference"                   -> "API Reference"
    Keeps it honest — only selects/normalizes words that are really in the label. ""
    for empty input.

    Pipeline:
      1. Tokenize, stripping surrounding punctuation; strip possessive "'s".
      2. COPULA: for "<subject> is/are the <feature>" keep the PREDICATE feature, not
         the subject ("Notion is the AI workspace" -> "AI workspace") so the eyebrow
         names what the page is, not the brand. Also drop the brand wordmark (`avoid`).
      3. Drop a leading article and a leading imperative / action verb or GERUND so we
         lead with the noun — but NEVER a real noun that merely ends in "ing" (Pricing).
      4. SPLIT on the first clause-connector ("&", "and", "of", "+", "/") and keep only
         the HEAD clause, so the eyebrow is one feature, never a connector tail.
      5. Take the first <= max_words tokens of that head clause and acronym-safe case.
    """
    t = (label or "").strip()
    if not t:
        return ""
    avoid_l = (avoid or "").strip().lower()
    # Tokenize; surrounding punctuation stripped, but a lone "&"/"+"/"/" survives as its
    # own token so it acts as a clause split (rather than gluing onto a noun).
    raw = [w.strip(" .,!?;:—–-\"'’“”()") for w in t.split()]
    tokens = [re.sub(r"['’]s$", "", w) for w in raw if w]
    if not tokens:
        return ""

    # (2) COPULA — "<subject> is/are [the/a/an] <feature>": keep the predicate feature.
    # Scan for a copula verb and, if a noun-bearing predicate follows, drop everything up
    # to and including the copula (+ a trailing article). Names the feature, not the
    # subject brand, even when no `avoid` wordmark was supplied.
    for i, w in enumerate(tokens):
        if w.lower() in ("is", "are", "was", "were"):
            pred = tokens[i + 1:]
            # Drop a leading article on the predicate ("the AI workspace" -> "AI ...").
            if pred and pred[0].lower() in ("the", "a", "an"):
                pred = pred[1:]
            if pred:  # only collapse to the predicate when one actually exists
                tokens = pred
            break

    # Drop the brand wordmark token so the eyebrow names the feature, not the brand.
    if avoid_l:
        tokens = [w for w in tokens if w.lower() != avoid_l] or tokens

    # (3) Drop a leading article, then a leading imperative / action verb or gerund so
    # the label leads with the topic noun. A real noun ending in "ing" (Pricing/Billing)
    # is in _EYEBROW_NOUN_INGS and is kept. Loop to shed stacked leading glue.
    while len(tokens) > 1 and (
            tokens[0].lower() in ("the", "a", "an")
            or tokens[0].lower() in _PUNCH_STOPWORDS
            or tokens[0].lower() in _EYEBROW_LEAD_VERBS
            or (len(tokens[0]) >= 5 and tokens[0].lower().endswith("ing")
                and tokens[0].lower() not in _EYEBROW_NOUN_INGS)):
        tokens = tokens[1:]

    # (4) SPLIT on the first clause-connector — keep only the HEAD clause so the eyebrow
    # is ONE feature ("Pricing & Fees" -> "Pricing", "Terms of Service" -> "Terms").
    head: List[str] = []
    for w in tokens:
        if w.lower() in _EYEBROW_SPLIT_CONNECTORS:
            break
        head.append(w)
    head = head or tokens  # connector led (shouldn't, after the strip) -> keep tokens

    # Drop any residual non-splitting connector/stopword glue (articles, "in", "on"…)
    # so we keep content tokens only; fall back to the head if that empties it.
    content = [w for w in head if w.lower() not in _EYEBROW_CONNECTORS] or head
    # Trim a trailing glue/verb token so the label never ends on a dangling word.
    while len(content) > 1 and content[-1].lower() in _PUNCH_STOPWORDS:
        content = content[:-1]

    # (5) Lead with the topical noun phrase: the FIRST up-to-max_words content tokens.
    chosen = content[:max_words] if max_words > 0 else content
    out = " ".join(_eyebrow_case(w) for w in chosen).strip(" .,!?;:—–-")
    return out


def _pick_punch_word(headline: str, brand: Dict[str, Any], emphasis: str = "") -> str:
    """Pick ONE salient noun from `headline` to accent-pop, or "".

    Hard contract (AppleScreenshot.splitPunch): the returned word must be a
    contiguous SUBSTRING of `headline` exactly as it appears (case included), so the
    accent split fires on the rendered line. We therefore choose from the headline's
    OWN tokens — never fabricate a word.

    Priority among headline tokens (first match wins):
      1. A token that matches a word in the run's emphasis (the feature the video is
         about, e.g. emphasis "accept payments" -> punch "payments"). This is what ties
         the accent to the on-screen highlight.
      2. The brand wordmark if it appears in the headline (rare for a screenshot line).
      3. The LAST content word >= 4 chars that is not a stopword (the noun a value-prop
         line usually ends on, e.g. "...in a single integration" -> "integration").
    Returns the original-cased token (trailing punctuation stripped) so it is a clean
    substring of the headline. "" when nothing suitable (the archetype then renders the
    headline with no accent split — graceful)."""
    h = (headline or "").strip()
    if not h:
        return ""
    # Tokenize preserving order + original case; strip surrounding punctuation for
    # the comparison but KEEP a cleaned form that is still a substring of the headline.
    raw_tokens = h.split()
    cleaned: List[tuple] = []  # (original_substr, lower_alnum)
    for tok in raw_tokens:
        core = tok.strip(".,!?;:\"'’“”()[]—–-")
        if not core:
            continue
        # `core` is a substring of `tok`; `tok` is a substring of the headline (split on
        # whitespace), so `core` is a substring of the headline. Safe for splitPunch.
        cleaned.append((core, core.lower()))
    if not cleaned:
        return ""

    emph_words = {w.strip(".,!?;:").lower()
                  for w in re.findall(r"[A-Za-z][A-Za-z0-9'’-]+", emphasis or "")
                  if len(w) >= 3 and w.lower() not in _PUNCH_STOPWORDS}
    wordmark = (brand.get("wordmark") or brand.get("brand") or brand.get("name") or "").strip().lower()

    # 1. Emphasis match (the feature the highlight points at). Prefer the LAST such
    #    token in the headline — the emphasis noun ("payments", "integration") usually
    #    follows the leading imperative verb ("Accept"), and the noun reads as the
    #    stronger accent than the verb. Scan right-to-left so the noun wins over the verb.
    for core, low in reversed(cleaned):
        if low in emph_words and low not in _PUNCH_STOPWORDS and len(core) >= 3:
            return core
    # 2. Brand wordmark appearing in the headline.
    if wordmark:
        for core, low in cleaned:
            if low == wordmark and len(core) >= 3:
                return core
    # 3. Last content noun-ish token >= 4 chars, not a stopword.
    for core, low in reversed(cleaned):
        if len(core) >= 4 and low not in _PUNCH_STOPWORDS:
            return core
    return ""


def _supporting_line(headline: str, raw_threaded: str, brief_seed: str,
                     brand: Dict[str, Any], limit: int = _SUPPORTING_MAX_CHARS,
                     used: Optional[List[str]] = None) -> str:
    """A short muted SECONDARY sentence for the split layout's left column, DISTINCT
    from the headline. Never fabricated — trims real narrated/brief/brand text.

    Source priority:
      1. The SECOND sentence of the threaded VO beat (the headline already used the
         first), distilled to a clean clause.
      2. A distinct BRAND FEATURE value-prop (rotated by `used` so each screenshot
         scene gets a DIFFERENT feature — not the same tagline repeated).
      3. The brand's clean tagline (when it differs from the headline + is unused).
      4. A non-stage-direction brief clause distinct from the headline.
      5. "" — the archetype renders no supporting line (graceful).
    Always clause-clipped (never a mid-word/dangling cut), never an echo of the
    headline/URL, and — when `used` is provided — never a REPEAT of a supporting line
    already shown on an earlier scene (the R1 "Build internet businesses" x3 bug)."""
    hl = (headline or "").strip().lower()
    used_lower = {u.strip().lower() for u in (used or [])}

    def _distinct(cand: str) -> str:
        c = (cand or "").strip()
        if not c:
            return ""
        c = _clip_to_clause(c, limit)
        if not c:
            return ""
        cl = c.strip().lower()
        if cl == hl or cl in used_lower:
            return ""
        # reject scrape/stage/nav junk so the secondary line stays clean.
        if (_is_fragment_subtitle(c) or _is_ui_nav_label(c)
                or _is_prompt_artifact(c) or _is_capture_stage_direction(c)):
            return ""
        # R7 gap 1 — drop a bare SECTION/nav label ("Popular Picks", "All Sale",
        # "Shop All"): a short Title-Case noun phrase with no verb reads as store
        # chrome, not a value-prop. This is the SAME positive-headline gate
        # _shape_hero applies to the opening subtitle. An empty supporting line is
        # cleaner than a section label, so when the candidate is one we drop it
        # (the caller falls to the next feature / tagline / brief, else "").
        if _is_section_label_subtitle(c):
            return ""
        return c

    def _commit(c: str) -> str:
        if c and used is not None:
            used.append(c)
        return c

    # 1. Second sentence of the narrated beat (headline took the first).
    beat = (raw_threaded or "").strip()
    if beat:
        parts = re.split(r"(?<=[.!?])\s+", beat)
        if len(parts) >= 2:
            second = _distinct(" ".join(parts[1:]).strip())
            if second:
                return _commit(second)
    # 2. A distinct brand FEATURE, GROUNDED to the headline's subject (R5 fix).
    #    The R1/Shopify-g1 bug: this loop pulled the FIRST usable feature[] blindly, so
    #    the supporting line was an unrelated scraped marketing fragment ("Meet your
    #    secret weapon, Sidekick", "Your brand has entered the chat") with no relation
    #    to the eyebrow/headline — the single biggest coherence drag. Fix: build the
    #    headline's content-word set and RANK each candidate feature by keyword overlap
    #    (mirroring _focus_for_headline's ring re-targeting). Prefer the feature whose
    #    text best matches what the headline NAMES; only when NOTHING overlaps do we
    #    fall through to the first distinct feature (degrades to the old behavior, never
    #    worse). Each feature is still a real scraped/known capability — naming one keeps
    #    the line grounded; ranking keeps it RELEVANT.
    def _content_words(text: str) -> set:
        return {w for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]+", (text or "").lower())
                if len(w) >= 4 and w not in _PUNCH_STOPWORDS}

    def _stem(w: str) -> str:
        # Crude stem so "payments"/"payment", "shipping"/"ship" overlap. Strip a few
        # common suffixes; floor at 3 chars so we don't over-merge short words.
        for suf in ("ing", "ments", "ment", "ions", "ion", "ers", "er", "ies",
                    "es", "ed", "s"):
            if len(w) - len(suf) >= 3 and w.endswith(suf):
                stem = w[: -len(suf)]
                # Undo a doubled final consonant from "-ing"/"-ed" ("shipp" -> "ship",
                # "runn" -> "run") so the stem matches the base form.
                if (suf in ("ing", "ed") and len(stem) >= 4
                        and stem[-1] == stem[-2] and stem[-1] not in "aeiou"):
                    stem = stem[:-1]
                return stem
        return w

    def _overlap(a_words: set, b_words: set) -> int:
        # Count matches by stem so near-forms ("payments" vs "payment processing",
        # "shipping" vs "ship orders") still score as RELATED.
        a_stems = {_stem(w) for w in a_words}
        b_stems = {_stem(w) for w in b_words}
        return len(a_stems & b_stems)

    hl_words = _content_words(headline)
    feat_cands: List[tuple] = []  # (score, ordinal, cand_text)
    for ordinal, f in enumerate(brand.get("features") or []):
        if isinstance(f, dict):
            label = (f.get("label") or f.get("title") or "").strip()
            sub = (f.get("sub") or "").strip()
            cand = ("%s — %s" % (label, sub)) if (label and sub) else (label or sub)
        else:
            cand = str(f or "").strip()
        if not cand or _is_nav_label_segment(cand) or _is_weak_headline(cand):
            continue
        score = _overlap(_content_words(cand), hl_words) if hl_words else 0
        feat_cands.append((score, ordinal, cand))
    # Highest overlap first; ties keep the original (planner) order so distinct scenes
    # still rotate through different features rather than all converging on one.
    for _score, _ord, cand in sorted(feat_cands, key=lambda t: (-t[0], t[1])):
        feat = _distinct(cand)
        if feat:
            return _commit(feat)
    # 3. Brand tagline / distinct value-prop (when not echoing the headline + unused).
    tag = _distinct(_distinct_tagline(brand, avoid=headline))
    if tag:
        return _commit(tag)
    # 4. A distinct clause from the (non-stage-direction) brief.
    bs = _distinct(brief_seed)
    if bs:
        return _commit(bs)
    return ""


def _focus_for_headline(default_focus: Any, candidates: Any, headline: str,
                        punch: str, emphasis: str) -> Optional[Dict[str, Any]]:
    """Pick the focus rect whose LABEL best matches what the headline NAMES.

    The R1 bug: the captured `focus` was the single most-prominent CTA ("Sign up
    with Google") with no relation to the headline ("...billing model") — so the
    highlight pointed at the wrong element. Here we re-rank the captured candidate
    rects by keyword overlap with the headline's content words (weighted toward the
    accent `punch` word and the run `emphasis`, which ARE the headline's subject) and
    return the best match. Falls back to `default_focus` when nothing scores — so a
    miss is never WORSE than the old behavior, just degrades to the prominent CTA.

    All rects are card-local % dicts {x,y,w,h,label?}. Returns one such dict (with the
    internal _candidates key stripped) or None."""
    def _clean(rect):
        if not isinstance(rect, dict):
            return None
        out = {k: rect[k] for k in ("x", "y", "w", "h") if k in rect}
        if len(out) != 4:
            return None
        if rect.get("label"):
            out["label"] = rect["label"]
        return out

    cands: List[Dict[str, Any]] = []
    if isinstance(candidates, list):
        cands = [c for c in (_clean(c) for c in candidates) if c]
    # The captured primary is itself a candidate to match against.
    primary = _clean(default_focus)
    if primary and primary not in cands:
        cands = [primary] + cands
    if not cands:
        return primary  # nothing to choose from

    # Build the headline keyword set (content words >= 4 chars, minus stopwords),
    # with the punch word + emphasis nouns weighted higher (they ARE the subject).
    def _words(text):
        return {w for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]+", (text or "").lower())
                if len(w) >= 4 and w not in _PUNCH_STOPWORDS}

    hl_words = _words(headline)
    strong = _words(punch) | _words(emphasis)
    if not hl_words and not strong:
        return primary

    best, best_score = None, 0.0
    for c in cands:
        lbl_words = _words(c.get("label", ""))
        if not lbl_words:
            continue
        score = len(lbl_words & hl_words) + 2.0 * len(lbl_words & strong)
        if score > best_score:
            best, best_score = c, score
    # Require a real match (a single shared content word, or any strong/emphasis hit).
    if best is not None and best_score >= 1.0:
        return best
    return primary


# Capture-target labels (capture_screenshots target names) → a clean noun phrase that
# names the SURFACE. Maps the internal target id to display words so the headline can
# say what the shot shows. Anything not mapped falls back to the page <title>.
_SURFACE_LABEL_WORDS = {
    "home": "", "mock-home": "", "homepage": "",  # the home page is the brand itself; no surface noun
    "pricing": "pricing", "mock-pricing": "pricing", "price": "pricing",
    "dashboard": "the dashboard", "app": "the app", "product": "the product",
    "payments": "payments", "checkout": "checkout", "billing": "billing",
    "list": "", "mock-list": "", "inner": "", "feature": "",  # generic inner page: no specific noun
    "docs": "the docs", "developers": "developers", "api": "the API",
    "integrations": "integrations", "analytics": "analytics",
}


def _surface_aligned_headline(shot_title: str, shot_label: str, brand: Dict[str, Any],
                              avoid: str = "", limit: int = 38) -> str:
    """Best-effort headline that NAMES the captured surface (R5 — Shopify bug #2:
    "Run payments, shipping" rendered over a product-collection list, because the
    headline came from the planner emphasis, NOT the page shown). When the captured
    shot carries a meaningful page <title> or a specific capture-target label, distill
    a short grounded phrase from it so the headline matches the surface on screen.

    Honest: only uses the REAL captured page <title> / target label — never invents.
    Returns "" when the title/label is empty, generic (home/inner page), or yields a
    weak/nav-label phrase (the caller then keeps its VO/brand-derived headline)."""
    wordmark = (brand.get("wordmark") or brand.get("brand") or brand.get("name") or "").strip()
    avoid_l = (avoid or "").strip().lower()

    # 1. A specific capture-target label (pricing/dashboard/payments/…) → its noun.
    lbl = (shot_label or "").strip().lower()
    surface_noun = _SURFACE_LABEL_WORDS.get(lbl, None)
    # Unmapped label that is itself a short content word → use it as the surface noun.
    if surface_noun is None and lbl and lbl not in ("home", "list", "inner"):
        clean = re.sub(r"^mock-", "", lbl).replace("-", " ").strip()
        if clean and clean not in _PUNCH_STOPWORDS and not _is_weak_headline(clean):
            surface_noun = clean

    # 2. The captured page <title> — strip the brand/site suffix ("Pricing | Stripe"
    #    → "Pricing"; "Stripe Dashboard" → "Dashboard"), then distill.
    title_phrase = ""
    t = (shot_title or "").strip()
    if t:
        # Split on common title separators and drop a segment that is just the brand.
        segs = [s.strip() for s in re.split(r"\s*[|–—\-:·•]\s*", t) if s.strip()]
        segs = [s for s in segs if s.lower() != wordmark.lower()] or segs
        # Prefer the most specific (shortest non-brand) segment as the surface name.
        title_phrase = min(segs, key=len) if segs else ""
        # Remove a leading/trailing brand token ("Stripe Dashboard" → "Dashboard").
        if wordmark and title_phrase.lower().startswith(wordmark.lower() + " "):
            title_phrase = title_phrase[len(wordmark):].strip()
        if wordmark and title_phrase.lower().endswith(" " + wordmark.lower()):
            title_phrase = title_phrase[:-len(wordmark)].strip()

    # Compose: prefer the explicit target noun; else the page-title phrase.
    cand = surface_noun or title_phrase
    cand = (cand or "").strip()
    if not cand:
        return ""
    cand = _clip_to_clause(cand, limit)
    # NOTE: do NOT apply _is_weak_headline / _is_section_label_subtitle here — those
    # reject a bare noun like "Pricing"/"Dashboard", which is EXACTLY the surface name
    # we want as a screenshot headline (rendered WITH an eyebrow + accent + supporting
    # line, not alone — a bare surface noun is on-point, not chrome, for a shot that
    # literally shows that page). We only reject empty / wordmark-echo / UI-nav-label /
    # prompt-artifact strings.
    if (not cand or cand.lower() == avoid_l or cand.lower() == wordmark.lower()
            or _is_ui_nav_label(cand) or _is_prompt_artifact(cand)):
        return ""
    # Title-case a bare surface noun so it reads as a display headline ("pricing" →
    # "Pricing"); leave multi-word title-phrases as captured.
    return cand if " " in cand else cand[:1].upper() + cand[1:]


def _shape_screenshot(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    """AppleScreenshot data: imageSrc / frame / caption / headline.

    The captured PNG is wired onto scene.data.imageSrc by build_props (mapping the
    Nth screenshot scene -> shot-NN.png from the run's screenshots/ dir). This shaper
    carries that imageSrc through, derives the browser address-bar `caption` (the
    captured page URL, else the brand cta_url, else the company URL), AND a meaningful
    `headline` — a short grounded value-prop about what the screenshot shows, rendered
    as on-screen TEXT beside the card so the proof beat communicates, not just an image.

    headline source priority (reuses the shared headline-quality machinery — rejects
    nav-labels, section names, prompt artifacts, weak fragments, and the bare URL):
      1. The scene's THREADED VO beat (`data._text`, set by build_props from the line
         actually narrated over this screenshot, e.g. "Breaking tech news, in-depth
         reviews, and sharp analysis every day.") distilled via _grounded_headline.
      2. The scene's `brief` IF it is a real value-prop and NOT a capture/stage
         direction ("Real captured homepage ... in a branded browser card").
      3. The brand's world-knowledge tagline.
      4. "" — the archetype renders cleanly with no headline (backward-compatible).
    The headline is NEVER the URL and NEVER the address-bar caption (no duplication).

    NEVER fabricates a screenshot — a clip-less scene shows the archetype's
    caption/wordmark placeholder. Honesty rule: caption + headline are real
    captured/narrated/brand text only.
    """
    d = scene.get("data") or {}
    img = (d.get("imageSrc") or "").strip()
    # Caption = the captured page URL (set by build_props), else a brand URL. This
    # feeds the browser address bar; it is NOT the on-screen headline.
    caption = (str(d.get("caption") or "").strip()
               or str(d.get("shotUrl") or "").strip()
               or str(brand.get("cta_url") or "").strip()
               or str(brand.get("url") or "").strip())

    # headline = a grounded value-prop line ABOUT what the screenshot shows. Source the
    # narrated VO beat first; fall back to a non-stage-direction brief; then the brand
    # tagline. _grounded_headline applies the full quality gate (nav-label / weak /
    # artifact rejection + positive _looks_like_headline test), so a section label or a
    # bare capture-direction never becomes the headline.
    raw_threaded = str(d.get("_text") or "").strip()
    # Safety net: the planner-prompt forbids narrating the capture/screenshot, but if a
    # capture stage-direction leaked into the VO beat, do not let it become the headline.
    if raw_threaded and _is_capture_stage_direction(raw_threaded):
        raw_threaded = ""
    brief = str(scene.get("brief") or "").strip()
    # Only feed the brief into the distiller when it is NOT a capture/stage direction
    # (those describe the SHOT — "Real captured homepage ... in a branded browser
    # card" — not the product). _is_capture_stage_direction catches the screenshot
    # camera-direction class; _is_cta_stage_direction the closing-card meta forms;
    # _is_prompt_artifact scaffold leakage.
    brief_seed = "" if (brief and (_is_capture_stage_direction(brief)
                                    or _is_cta_stage_direction(brief)
                                    or _is_prompt_artifact(brief))) else brief
    wordmark = (brand.get("wordmark") or brand.get("brand") or brand.get("name") or "").strip()
    # Split-layout headlines live in a ~660px left column at 76px — a kinetic 2-line
    # display headline, NOT a full sentence. A 64-char limit produced 4-line walls
    # ("Enable any billing model with Stripe's flexible subscriptions"). Distill to a
    # PUNCHY <=38-char clause so it lands in 2 lines and reads like Orinovate/TapPay.
    # _grounded_headline already clause-trims (no mid-word cut); the tighter limit just
    # makes the kept clause shorter. Falls back through the same source priority.
    SCREENSHOT_HEADLINE_LIMIT = 38
    headline = (_grounded_headline(raw_threaded, brand, avoid=wordmark, limit=SCREENSHOT_HEADLINE_LIMIT)
                or _grounded_headline(brief_seed, brand, avoid=wordmark, limit=SCREENSHOT_HEADLINE_LIMIT))
    # R5 — ALIGN the headline to the CAPTURED SURFACE (Shopify bug #2). The VO-derived
    # headline comes from the planner emphasis and can NAME a feature the captured page
    # does NOT show ("Run payments, shipping" over a product-collection list). When the
    # shot carries a SPECIFIC page <title> / capture-target label (pricing, dashboard,
    # payments, …), prefer a short headline that names THAT surface so the headline and
    # the on-screen UI agree. Only overrides when the surface noun is meaningful AND the
    # current headline doesn't already reference it; a generic home/inner page yields ""
    # so the VO/brand headline is kept (no regression on real product captures whose VO
    # already matches the surface).
    shot_title = str(d.get("_shot_title") or "").strip()
    shot_label = str(d.get("_shot_label") or "").strip()
    surface_hl = _surface_aligned_headline(shot_title, shot_label, brand,
                                           avoid=wordmark, limit=SCREENSHOT_HEADLINE_LIMIT)
    if surface_hl:
        hl_words = {w for w in re.findall(r"[A-Za-z]+", (headline or "").lower())}
        sf_words = {w for w in re.findall(r"[A-Za-z]+", surface_hl.lower())
                    if w not in _PUNCH_STOPWORDS}
        # If the current headline already names the surface (word overlap), keep it.
        # Otherwise the headline is talking about something the shot doesn't show →
        # use the surface-aligned headline so headline↔UI cohere.
        if not headline or not (hl_words & sf_words):
            headline = surface_hl
    # Last guard: the headline must never echo the address-bar caption / URL.
    if headline and caption and headline.strip().lower() == _decode(caption).strip().lower():
        headline = ""

    # R6 — CROSS-SCENE HEADLINE DEDUP (the Notion miss). When a brand's <title> is
    # identical across pages (Notion home + /product both "The AI workspace that works
    # for you. | Notion") AND the VO distills to the same line, two screenshot scenes
    # derive an IDENTICAL headline (+ identical eyebrow). `_used_headlines` is one shared
    # list threaded by build_props to every screenshot scene (mirrors `_used_supporting`).
    # On a collision, derive a DISTINCT headline from THIS scene's OWN surface
    # (surface-aligned name), else a distinct grounded clause from the brand value-props,
    # else drop the headline so the shot still renders cleanly (never a duplicate).
    used_headlines = d.get("_used_headlines")
    used_headlines = used_headlines if isinstance(used_headlines, list) else None
    if headline and used_headlines is not None:
        used_lower = {h.strip().lower() for h in used_headlines}
        if headline.strip().lower() in used_lower:
            alt = ""
            # 1. The scene's OWN captured surface name (home → "", pricing → "Pricing",
            #    /product → "Product"); distinct from earlier headlines + the wordmark.
            if surface_hl and surface_hl.strip().lower() not in used_lower:
                alt = surface_hl
            # 2. A distinct grounded brand value-prop clause not yet used as a headline.
            if not alt:
                cand = _distinct_tagline(brand, avoid=wordmark)
                if cand and cand.strip().lower() not in used_lower:
                    alt = _clip_to_clause(cand, SCREENSHOT_HEADLINE_LIMIT)
                    if alt and alt.strip().lower() in used_lower:
                        alt = ""
            headline = alt  # "" => the shot renders with no headline (no duplicate)
        if headline:
            used_headlines.append(headline)

    out: Dict[str, Any] = {
        "imageSrc": img,
        "frame": d.get("frame") or "browser",
    }
    if caption:
        out["caption"] = _decode(caption)
    if headline:
        out["headline"] = _decode(headline)

    # --- Split-layout (apple-screenshot v2) fields (spec §2 / .handoff-screenshot-v2) -
    # Newly-built screenshot scenes render the text-LEFT / shot-RIGHT split. This is the
    # GAP closer (Task G): nothing set layout before, so the keystone defaulted to the
    # old centered look. An explicit plan-authored data.layout still wins.
    out["layout"] = d.get("layout") or "split"

    # Eyebrow label — the archetype reads data.kicker via actLabel() and folds the act
    # index into "NN · LABEL". A tracked uppercase eyebrow wants a SHORT label (2-3
    # words), not a full sentence. Source: explicit plan kicker, else a short phrase
    # from the run emphasis (the feature the highlight points at), else the wordmark.
    run_emphasis = str(d.get("_emphasis") or "").strip()
    # R2 coherence: derive the eyebrow from THIS scene's own headline subject first
    # (so two screenshot scenes get DISTINCT eyebrows — "Payments" vs "Dashboard" —
    # each matching its own headline), then the run emphasis, then the wordmark. An
    # explicit plan kicker still wins.
    scene_eyebrow = _short_eyebrow(headline, avoid=wordmark) if headline else ""
    kicker = (str(d.get("kicker") or "").strip()
              or scene_eyebrow
              or _short_eyebrow(_emphasis_phrase(run_emphasis), avoid=wordmark)
              or wordmark)
    if kicker:
        kicker = _decode(kicker)
        out["kicker"] = kicker
        # Also expose the named `eyebrow` field (spec §2). The archetype consumes
        # `kicker`; `eyebrow` mirrors it so either field name resolves the label.
        out["eyebrow"] = kicker

    # Supporting muted secondary line, DISTINCT from the headline AND distinct across
    # scenes (the R1 "Build internet businesses" x3 bug). `_used_supporting` is one
    # shared list threaded by build_props to every screenshot scene.
    used_supporting = d.get("_used_supporting")
    used_supporting = used_supporting if isinstance(used_supporting, list) else None
    supporting = str(d.get("supporting") or "").strip()
    if supporting:
        # ROBUSTNESS — CLAMP an explicit plan-authored supporting line to the same
        # ~90-char ceiling _supporting_line enforces. The split layout's left column
        # renders supporting as a SINGLE muted line (28px, maxWidth leftColW-30 ≈
        # 630px ≈ ~2 lines of room); a dense planner can author a full sentence that
        # overflows. Clause-clip it (never mid-word) so it fits regardless of brain.
        if len(supporting) > _SUPPORTING_MAX_CHARS:
            clamped = _clip_to_clause(supporting, _SUPPORTING_MAX_CHARS)
            if clamped and len(clamped.split()) >= 2:
                supporting = clamped
        # Register an explicit plan-authored line so later scenes don't repeat it.
        if used_supporting is not None and supporting not in used_supporting:
            used_supporting.append(supporting)
    elif headline:
        supporting = _supporting_line(headline, raw_threaded, brief_seed, brand,
                                      used=used_supporting)
    if supporting:
        out["supporting"] = _decode(supporting)

    # punchWord — a salient noun INSIDE the headline (substring contract for the accent
    # split). Honor an explicit plan punchWord only when it is a substring of headline.
    if headline:
        explicit_punch = str(d.get("punchWord") or "").strip()
        decoded_headline = out["headline"]
        if explicit_punch and _decode(explicit_punch) in decoded_headline:
            out["punchWord"] = _decode(explicit_punch)
        else:
            punch = _pick_punch_word(decoded_headline, brand, run_emphasis)
            if punch and punch in decoded_headline:
                out["punchWord"] = punch

    # focus — the card-local NORMALIZED rect from the screenshot manifest (wired onto
    # scene.data.focus by wire_captured_assets). R2 coherence: re-target the rect to the
    # one the HEADLINE names (over the most-prominent CTA), using the labelled candidate
    # rects (_focus_candidates) + the punch word + emphasis. Absent candidates => the
    # captured primary; absent focus => no highlight (plain shot).
    focus = d.get("focus")
    if isinstance(focus, dict):
        chosen = _focus_for_headline(
            focus, d.get("_focus_candidates"),
            out.get("headline", ""), out.get("punchWord", ""), run_emphasis)
        if isinstance(chosen, dict):
            out["focus"] = chosen
    # Optional explicit cursor path / zoom target (plan-authored) pass through too.
    if isinstance(d.get("cursorPath"), list):
        out["cursorPath"] = d.get("cursorPath")
    if isinstance(d.get("zoomTo"), dict):
        out["zoomTo"] = d.get("zoomTo")

    return out


class Style:
    """One curated template. `role_map` classifies a plan scene -> archetype;
    `shapers` builds each archetype's `data`. Adding a style = one instance."""

    def __init__(self, name: str, role_map: Dict[str, str],
                 default_archetype: str,
                 shapers: Dict[str, Callable[[Dict, Dict], Dict]],
                 theme_fn: Callable[[Dict], Dict]):
        self.name = name
        self.role_map = role_map
        self.default_archetype = default_archetype
        self.shapers = shapers
        self.theme_fn = theme_fn

    def archetype_for(self, scene: Dict[str, Any]) -> str:
        arch = self.role_map.get(_scene_role(scene), self.default_archetype)
        # NEVER-BLANK guard for the walkthrough player: a `walkthrough`/`demo`/
        # `cinematic` role only earns the video player when a REAL clip exists.
        # With no clip, fall back to the designed explainer card so a clip-less
        # ($0 / standard, or failed-capture) run is never blank.
        if arch == ARCH_WALKTHROUGH and not _has_walkthrough_clip(scene):
            return self.shapers.get(ARCH_EXPLAINER) and ARCH_EXPLAINER or self.default_archetype
        return arch

    def shape(self, scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
        arch = self.archetype_for(scene)
        return self.shapers[arch](scene, brand)

    def theme(self, brand: Dict[str, Any]) -> Dict[str, Any]:
        return self.theme_fn(brand)


# Theme keys the <Timeline> composition reads (studio/src/timeline/types.ts Theme).
_THEME_PALETTE_KEYS = ("bg", "bgCard", "bgCardRaised", "navy", "navyBright",
                       "accent", "ok", "text", "textMuted", "textDim", "border")
_THEME_FONT_KEYS = ("fontPrimary", "fontMono", "fontDisplay")
# Fallbacks lifted from the Orinovate kinetic-light theme.ts (keeps a thin brand
# fixture from producing an undefined-color render).
_KINETIC_LIGHT_DEFAULTS = {
    "bg": "#ffffff", "bgCard": "#ffffff", "bgCardRaised": "#f9fafc",
    "navy": "#1a3a5c", "navyBright": "#4a7aa8", "accent": "#2563eb",
    "ok": "#10b981", "text": "#0f2338", "textMuted": "#3d4a5c",
    "textDim": "#6b7589", "border": "#e5e9f0",
    "fontPrimary": "Inter, system-ui, -apple-system, sans-serif",
    "fontMono": "ui-monospace, SFMono-Regular, Menlo, monospace",
    "fontDisplay": "Inter, system-ui, sans-serif",
}


# --- Music selection (Task E/F: the music-selection point) ---------------------
# We choose a BGM track by COMPANY STYLE and write the chosen SOURCE path into the
# theme under the key `theme.music`. _stage_audio later copies that file into
# studio/public/ and rewrites the value to a public-relative name so Remotion's
# staticFile() resolves it; Timeline.tsx (Foundation/Task-E agent) reads
# props.theme.music and mounts ONE looped, VO-ducked <Audio>.
#
# The picks come from Dennis's owned, attribution-free Pixabay set. Per
# VIDEO-OVERHAUL-SPEC §4 the Stripe/fintech default is the TapPay promo track
# (51.5s, confident-modern-clean, no loop seam over the ~32-40s arc).
# Repo-relative so the tracks resolve on the Railway worker too (the old absolute
# /Users/dennis/... paths existed only on the dev machine → silent video in prod).
# These mp3s are bundled (git-tracked via the !assets/music exception in .gitignore).
_MUSIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "music")
_MUSIC_TRACKS = {
    # confident, modern, clean — fintech / payments / SaaS (the spec default)
    "fintech": os.path.join(_MUSIC_DIR, "fintech.mp3"),
    # calm / modern, longer bed — generic fallback for non-fintech brands
    "calm":    os.path.join(_MUSIC_DIR, "calm.mp3"),
}
# The default track when nothing brand-specific is known. The spec recommends the
# TapPay/fintech cut for Stripe and as a safe modern-clean default for all brands.
_MUSIC_DEFAULT = _MUSIC_TRACKS["fintech"]

# Brand/industry keywords -> a music style bucket. Matched (case-insensitive)
# against the brand name + tagline + host so a payments/fintech brand picks the
# confident fintech bed and other brands still get a calm modern default.
_FINTECH_HINTS = (
    "payment", "payments", "fintech", "finance", "financial", "bank", "banking",
    "invoice", "billing", "checkout", "transaction", "money", "wallet", "card",
    "stripe", "plaid", "tappay", "ledger", "treasury", "payout", "merchant",
)


def _select_music(brand: Dict[str, Any]) -> str:
    """Return the SOURCE filesystem path of the BGM track for this brand's style.

    Fintech/payments brands get the confident TapPay bed; everything else gets a
    calm modern default. The TapPay/fintech cut is also the spec's safe default for
    Stripe specifically. Returns a path string; _stage_audio stages it into
    studio/public/. The brand may pin `brand.music` to override the auto-pick."""
    # Explicit per-brand override wins (a future data-driven path).
    override = (brand.get("music") or "").strip() if isinstance(brand, dict) else ""
    if override:
        return override
    haystack = " ".join(str(brand.get(k) or "") for k in (
        "name", "brand", "wordmark", "tagline", "host")).lower()
    copy = brand.get("copy") or {}
    if isinstance(copy, dict):
        haystack += " " + " ".join(str(copy.get(k) or "") for k in ("hook", "cta")).lower()
    if any(h in haystack for h in _FINTECH_HINTS):
        return _MUSIC_TRACKS["fintech"]
    # Default: the spec-recommended modern-clean fintech bed reads well for the
    # kinetic-light SaaS genre across brands. (Calm is available for future tuning.)
    return _MUSIC_DEFAULT


def _theme_kinetic_light(brand: Dict[str, Any]) -> Dict[str, Any]:
    """Map a brand_theme.json (palette/fonts/wordmark) -> the Timeline theme block.

    Per-template adapter (spec: "the style-fill contract must normalize" differing
    brand shapes). Accepts BOTH the hand-authored kinetic-light fixture
    (palette.{bg,accent,navy,text,...}, fonts.{fontPrimary,...}) AND brand_extract.py's
    normalized shape (palette.{bg,ink,accent,accent2,success}, fonts.{display,mono}).
    Every composition key resolves to a brand value, then an alias, then a default.
    """
    palette = brand.get("palette") or {}
    fonts = brand.get("fonts") or {}

    def pick(key: str, *aliases: str) -> str:
        for src in (palette.get(key), *(palette.get(a) for a in aliases)):
            if src:
                return src
        return _KINETIC_LIGHT_DEFAULTS[key]

    theme: Dict[str, Any] = {
        "bg": pick("bg"),
        "bgCard": pick("bgCard", "bg"),
        "bgCardRaised": pick("bgCardRaised"),
        "navy": pick("navy", "accent2"),
        "navyBright": pick("navyBright", "accent2"),
        "accent": pick("accent"),
        "ok": pick("ok", "success", "accent2"),
        "text": pick("text", "ink", "fg"),
        "textMuted": pick("textMuted"),
        "textDim": pick("textDim"),
        "border": pick("border"),
    }
    theme["fontPrimary"] = fonts.get("fontPrimary") or fonts.get("display") or _KINETIC_LIGHT_DEFAULTS["fontPrimary"]
    theme["fontMono"] = fonts.get("fontMono") or fonts.get("mono") or _KINETIC_LIGHT_DEFAULTS["fontMono"]
    theme["fontDisplay"] = fonts.get("fontDisplay") or fonts.get("display") or _KINETIC_LIGHT_DEFAULTS["fontDisplay"]
    theme["wordmark"] = brand.get("wordmark") or brand.get("brand") or brand.get("name") or ""

    # Task F: real captured logo (set by brand_extract.apply_captured_logo). When
    # present, bookend archetypes render theme.logoSrc as an <Img>; absent => they
    # fall back to wordmark_svg/wordmark text (honest fallback). _stage_audio copies
    # the source file into studio/public/ and rewrites this to a public-relative name.
    logo_src = brand.get("logo_src") or brand.get("logoSrc")
    if logo_src:
        theme["logoSrc"] = logo_src

    # Task E/F: BGM track chosen by company style. _stage_audio stages this source
    # into studio/public/ and rewrites it to a public-relative name; Timeline.tsx
    # reads props.theme.music for ONE looped, VO-ducked <Audio>. Backward-compatible:
    # a build that drops the source (missing file) keeps no music and still renders.
    music_src = _select_music(brand)
    if music_src:
        theme["music"] = music_src
    return theme


# --- THE REGISTRY -----------------------------------------------------------
# orinovate-kinetic-light: open/close -> HeroTitle, feature/capability -> CardUi.
STYLES: Dict[str, Style] = {
    "orinovate-kinetic-light": Style(
        name="orinovate-kinetic-light",
        role_map={
            "open": ARCH_HERO, "hero": ARCH_HERO, "title": ARCH_HERO,
            "intro": ARCH_HERO, "close": ARCH_HERO, "cta": ARCH_HERO,
            "outro": ARCH_HERO,
            # An animated feature beat ("what/how/why") -> the designed explainer
            # card so it SHOWS the narrated point (title + bullets) instead of
            # falling to a blank hero (the content-empty blank-scenes bug).
            "feature": ARCH_EXPLAINER, "motion_graphic": ARCH_EXPLAINER,
            "motion-graphic": ARCH_EXPLAINER,
            # The explicit brand-grid roles still use the 2x2 CardUi grid.
            "capability": ARCH_CARD, "capabilities": ARCH_CARD,
            "cards": ARCH_CARD, "grid": ARCH_CARD,
            # A walkthrough/demo beat plays its PRODUCED clip inside the branded
            # frame (walkthrough-player) WHEN a real clip exists; archetype_for
            # downgrades to the explainer card when it doesn't (never-blank). A
            # cinematic beat (no UI capture) stays on the designed explainer card.
            "walkthrough": ARCH_WALKTHROUGH, "demo": ARCH_WALKTHROUGH,
            "cinematic": ARCH_EXPLAINER, "explainer": ARCH_EXPLAINER,
            # A screenshot beat shows the REAL captured site inside a branded browser
            # card (apple-screenshot). The captured PNG is wired in by build_props.
            "screenshot": ARCH_SCREENSHOT, "site": ARCH_SCREENSHOT,
        },
        default_archetype=ARCH_HERO,
        shapers={ARCH_HERO: _shape_hero, ARCH_CARD: _shape_cards,
                 ARCH_EXPLAINER: _shape_explainer,
                 ARCH_WALKTHROUGH: _shape_walkthrough,
                 ARCH_SCREENSHOT: _shape_screenshot},
        theme_fn=_theme_kinetic_light,
    ),
}


# ---------------------------------------------------------------------------
# CAPTURED-ASSET WIRING  (screenshots + walkthrough clip -> plan scene data)
# ---------------------------------------------------------------------------
def _manifest_is_real(data: Dict[str, Any]) -> bool:
    """#82: True only when a parsed screenshots manifest is a REAL capture.

    A produce-time capture that flaked writes {"ok": False, "real": False} with
    synthetic shots flagged {"mock": True} (the orange placeholder). Such a manifest
    must NOT be used as the picture source. Treat as real when the manifest is not
    explicitly not-ok / not-real AND it has at least one non-mock shot."""
    if not isinstance(data, dict):
        return False
    if data.get("ok") is False or data.get("real") is False:
        return False
    shots = data.get("shots") or []
    real_shots = [s for s in shots if isinstance(s, dict) and not s.get("mock")]
    return len(real_shots) > 0


def _shots_from_manifest(data: Dict[str, Any], shots_dir: str) -> List[Dict[str, Any]]:
    """Parse a screenshots manifest dict into the ordered [{file,path,url,...}]
    records the stager consumes. Skips synthetic mock shots."""
    shots: List[Dict[str, Any]] = []
    for s in (data.get("shots") or []):
        if not isinstance(s, dict) or s.get("mock"):
            continue
        f = s.get("file") or (os.path.basename(s.get("path")) if s.get("path") else None)
        if not f:
            continue
        rec = {"file": f,
               "path": s.get("path") or os.path.join(shots_dir, f),
               "url": s.get("url") or "",
               # R5: carry the captured page <title> + the capture target
               # label so the headline can NAME the on-screen surface
               # (Shopify bug #2: "Run payments, shipping" over a product
               # list). Absent/empty => the headline stays VO/brand-derived.
               "title": (s.get("title") or "").strip(),
               "label": (s.get("label") or "").strip()}
        # Task F: pass through the card-local focus rect so the
        # apple-screenshot archetype can highlight/zoom the named UI
        # element. Absent => no highlight (plain shot).
        focus = s.get("focus")
        if isinstance(focus, dict):
            rec["focus"] = focus
            # R2 coherence: the focus rect carries extra labelled
            # candidate rects (_candidates) so _shape_screenshot can pick
            # the rect whose LABEL best matches the scene's headline.
            cands = focus.get("_candidates")
            if isinstance(cands, list) and cands:
                rec["focus_candidates"] = cands
        shots.append(rec)
    return shots


def _load_screenshot_manifest(out_dir: str) -> List[Dict[str, Any]]:
    """Return the captured screenshots as an ordered [{file, path, url}] list.

    Source priority (#82 SCREENSHOT FIX): the produce-time capture
    runs/<id>/screenshots/manifest.json is used ONLY when it is a REAL capture
    (not ok=false / real=false / all-mock). When the produce-time capture flaked
    and left a synthetic MOCK manifest, prefer the REAL read-pass capture at
    runs/<id>/screenshots-read/manifest.json (the early brand-read hero shot) so
    the customer sees the REAL homepage instead of the orange synthetic mock.
    Falls back to globbing shot-NN.png in the produce dir, then to [] (the
    screenshot scenes then show their never-blank placeholder)."""
    shots_dir = os.path.join(out_dir, "screenshots")
    manifest_path = os.path.join(shots_dir, "manifest.json")
    # 1) produce-time capture, but ONLY if it is a real (non-mock) capture.
    if os.path.exists(manifest_path):
        try:
            data = _load_json(manifest_path)
            if _manifest_is_real(data):
                shots = _shots_from_manifest(data, shots_dir)
                if shots:
                    return shots
        except (OSError, ValueError):
            pass
    # 2) #82 fallback: the real read-pass capture (screenshots-read/) — this is the
    #    genuine page hero captured early in the run, never a mock.
    read_dir = os.path.join(out_dir, "screenshots-read")
    read_manifest = os.path.join(read_dir, "manifest.json")
    if os.path.exists(read_manifest):
        try:
            data = _load_json(read_manifest)
            if _manifest_is_real(data):
                shots = _shots_from_manifest(data, read_dir)
                if shots:
                    return shots
        except (OSError, ValueError):
            pass
    # 3) glob the produce dir for any real shot-NN.png a manifest-less capture left.
    shots = []
    if os.path.isdir(shots_dir):
        import glob
        for p in sorted(glob.glob(os.path.join(shots_dir, "shot-*.png"))):
            shots.append({"file": os.path.basename(p), "path": p, "url": ""})
    return shots


def _walkthrough_clip_for_run(out_dir: str, scene_id: str) -> str:
    """Locate the produced walkthrough clip for a run, or "" if none.

    Priority: env WS_WALKTHROUGH_CACHE (a cached mp4 path, the $0/no-NIM verify
    path) -> the orchestrator's produced clip at runs/<id>/clips/NN_<scene_id>.mp4.
    Returns an absolute path that _stage_audio stages into studio/public/.
    """
    cache = (os.environ.get("WS_WALKTHROUGH_CACHE") or "").strip()
    if cache and os.path.exists(cache):
        return cache
    clips_dir = os.path.join(out_dir, "clips")
    if os.path.isdir(clips_dir):
        import glob
        # the orchestrator names walkthrough clips NN_<scene_id>.mp4
        cands = sorted(glob.glob(os.path.join(clips_dir, "*_%s.mp4" % scene_id)))
        if cands:
            return cands[0]
    return ""


def wire_captured_assets(plan: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
    """Attach REAL captured assets to the plan's screenshot/walkthrough scenes IN
    PLACE so the existing imageSrc/videoSrc staging (build_props + _stage_audio)
    picks them up:

      - each `screenshot` scene (in order) -> the Nth captured shot-NN.png; sets
        data.imageSrc (the PNG) + data.caption (the captured page URL) when the
        scene has no explicit caption.
      - the `walkthrough` scene -> the produced/cached clip; sets data.videoSrc.

    Mutates + returns `plan`. Idempotent-ish: explicit pre-set imageSrc/videoSrc on a
    scene are never overwritten. No-op for scenes that have no captured asset (they
    keep their never-blank archetype floor)."""
    scenes = [s for s in (plan.get("scenes") or []) if isinstance(s, dict)]
    shots = _load_screenshot_manifest(out_dir)

    shot_i = 0
    for s in scenes:
        stype = str(s.get("type") or "").strip().lower()
        d = dict(s.get("data") or {})
        if stype == "screenshot":
            if not d.get("imageSrc") and shot_i < len(shots):
                shot = shots[shot_i]
                d["imageSrc"] = shot["path"]
                if not d.get("caption") and shot.get("url"):
                    d["caption"] = shot["url"]
                # R5: thread the captured page <title> + capture-target label so the
                # screenshot headline can NAME the surface actually shown (instead of
                # a planner-emphasis phrase unrelated to the captured page). Never
                # overwrite explicit plan-authored hints.
                if not d.get("_shot_title") and shot.get("title"):
                    d["_shot_title"] = shot["title"]
                if not d.get("_shot_label") and shot.get("label"):
                    d["_shot_label"] = shot["label"]
                # Task F: attach the captured focus rect (card-local %) so the
                # archetype's highlight-box / zoom targets the named UI element.
                # Never overwrite an explicit plan-authored focus. Absent => no
                # highlight (byte-identical to a plain shot).
                if not d.get("focus") and isinstance(shot.get("focus"), dict):
                    d["focus"] = shot["focus"]
                    # R2 coherence: carry the labelled candidate rects so the shaper
                    # can re-target the highlight to the rect the HEADLINE names.
                    if isinstance(shot.get("focus_candidates"), list):
                        d["_focus_candidates"] = shot["focus_candidates"]
                shot_i += 1
            s["data"] = d
        elif stype == "walkthrough":
            if not _has_walkthrough_clip(s):
                clip = _walkthrough_clip_for_run(out_dir, str(s.get("id") or ""))
                if clip:
                    d["videoSrc"] = clip
            s["data"] = d
    return plan


# ---------------------------------------------------------------------------
# MERGE + DRIVER  (filled below)
# ---------------------------------------------------------------------------
def build_props(timeline: Dict[str, Any], plan: Dict[str, Any],
                brand: Dict[str, Any], style_name: str) -> Dict[str, Any]:
    """MERGE: timeline (frames + cues) + plan copy + brand theme + style ->
    the exact one-object props the <Timeline> composition consumes.

    timeline.json owns frames/cues; the plan owns copy; the style decides each
    scene's archetype and shapes its `data`; the brand owns palette/fonts/wordmark.
    """
    if style_name not in STYLES:
        raise KeyError(
            f"unknown style {style_name!r}; known: {sorted(STYLES)}")
    style = STYLES[style_name]
    plan_scenes = _plan_scenes(plan)
    by_id = _scene_by_id(plan_scenes)

    # The run's emphasis (user-supplied feature/area). The walkthrough shaper uses
    # this for the overlay title so the title bar stays on the emphasized feature,
    # not whatever flow the planner's free-text VO happened to narrate.
    run_emphasis = str((plan.get("job") or {}).get("emphasis") or "").strip()

    # Per-brand OPENING style (Design-Fit variety): bold/energetic vibe -> animated
    # kinetic-statement opening; enterprise/calm -> clean wordmark; unknown -> tie-break.
    # Read the Design Brief's vibe once before the loop.
    _vibe = (plan.get("design_brief") or {}).get("brand_vibe") or {}
    _open_kinetic = _wants_kinetic_open(
        str(_vibe.get("label") or "").strip().lower(),
        str(_vibe.get("motion") or "").strip().lower(),
        _open_variant_for(brand),
    )

    tl_scenes = timeline.get("scenes", [])
    last_idx = len(tl_scenes) - 1
    feature_counter = 0  # 0-based position among explainer/feature scenes (BUG C)
    used_supporting: List[str] = []  # R2: cross-scene supporting-line dedup
    used_headlines: List[str] = []   # R6: cross-scene screenshot HEADLINE dedup
    scenes: List[Dict[str, Any]] = []
    for idx, tl_scene in enumerate(tl_scenes):
        sid = tl_scene.get("id")
        plan_scene = dict(by_id.get(sid, {"id": sid}))

        # build_timeline threads a non-None `role` and non-empty `text` onto each
        # timeline scene (the blank-scenes fix). Prefer them over re-deriving from
        # the raw plan scene: the role decides the archetype, and the threaded text
        # seeds the shaper's title when the plan scene carries no `data` block.
        tl_role = str(tl_scene.get("role") or "").strip().lower()
        if tl_role:
            plan_scene["role"] = tl_role  # so _scene_role / archetype_for agree
        tl_text = str(tl_scene.get("text") or "").strip()
        d = dict(plan_scene.get("data") or {})
        if tl_text:
            # Seed data.title from the threaded VO/brief text so the shaper builds a
            # real title instead of falling straight to the brand tagline. Explicit
            # plan copy (data.title) still wins inside the shaper.
            d.setdefault("_text", tl_text)

        archetype = style.archetype_for(plan_scene)  # role decides the archetype

        # PER-BRAND OPENING VARIETY (Design-Fit): the opening hero may render as an
        # animated kinetic-statement with a brand badge instead of the clean wordmark
        # lockup. style.shape() dispatches on ROLE, so set role="feature" to run the
        # explainer shaper (which honors data.treatment="kinetic-statement") and mirror
        # the local `archetype`. Content stays the REAL tagline (kinetic derives its
        # lines verbatim from the threaded title).
        if (_open_kinetic and archetype == ARCH_HERO and idx == 0 and last_idx > 0
                and not _is_closing_title(plan_scene)):
            plan_scene["role"] = "feature"
            d["treatment"] = "kinetic-statement"
            d["brandBadge"] = True
            if not str(d.get("eyebrow") or "").strip():
                d["eyebrow"] = str(brand.get("wordmark") or brand.get("name") or "").strip().upper()
            archetype = ARCH_EXPLAINER

        # Thread scene-POSITION hints the shapers use for variety:
        #  - the FINAL title scene is the closing CTA (BUG B), even if its id/role
        #    didn't already mark it close.
        #  - each explainer/feature scene gets its 0-based order among feature scenes
        #    so its bullets rotate to lead with the on-topic capability (BUG C).
        if archetype == ARCH_HERO and idx == last_idx and last_idx > 0:
            d.setdefault("_is_closing", True)
        if archetype == ARCH_EXPLAINER:
            d.setdefault("_feature_index", feature_counter)
            feature_counter += 1
            # Share the SAME cross-scene dedup list screenshots use, so each feature
            # card's beat-derived subtitle is DISTINCT across the set.
            d["_used_supporting"] = used_supporting
            d["_used_headlines"] = used_headlines
        if archetype == ARCH_WALKTHROUGH and run_emphasis:
            # Title bar tracks the emphasized feature, not the planner's VO flow.
            d.setdefault("_emphasis", run_emphasis)
        if archetype == ARCH_SCREENSHOT:
            if run_emphasis:
                # The split-layout eyebrow + punch word track the emphasized feature so
                # the headline accent literally points at the highlighted UI element.
                d.setdefault("_emphasis", run_emphasis)
            # R2 coherence: share one cross-scene "used supporting lines" list so each
            # screenshot scene's secondary line is DISTINCT (no "Build internet
            # businesses" repeated across scenes 1/2/4). _supporting_line consults +
            # appends to it; the same list object threads to every screenshot scene.
            d["_used_supporting"] = used_supporting
            # R6 coherence (the Notion miss): share one cross-scene "used headlines"
            # list so each screenshot scene's HEADLINE (and eyebrow) is DISTINCT. Notion's
            # <title> ("The AI workspace that works for you. | Notion") is identical on
            # home + /product AND the VO distilled to the same line, so scenes 2 & 3 got
            # an IDENTICAL headline+eyebrow. _shape_screenshot consults + appends to this;
            # on a collision it falls to the scene's own surface-aligned headline / next
            # distinct grounded clause (mirrors the supporting-line dedup, one level up).
            d["_used_headlines"] = used_headlines
        plan_scene["data"] = d

        data = style.shape(plan_scene, brand)
        scene_obj: Dict[str, Any] = {
            "id": sid,
            "archetype": archetype,
            "in_frame": tl_scene["in_frame"],
            "out_frame": tl_scene["out_frame"],
            # cues stay ABSOLUTE (Timeline.tsx rebases to scene-local at the seam).
            "cues": tl_scene.get("cues", []),
            "data": data,
        }
        # Per-scene VO audio (the per-beat file) so the voice starts at this
        # scene's in_frame even though scenes are stretched to the planned length.
        audio = tl_scene.get("audio")
        if audio and audio.get("src"):
            scene_obj["audio"] = {"src": audio["src"]}
        scenes.append(scene_obj)

    scenes = _dedupe_cross_scene_secondary(scenes)
    return {
        "fps": timeline.get("fps", 30),
        "total_frames": timeline.get("total_frames", 0),
        "audio_path": timeline.get("audio_path"),
        "lang": timeline.get("lang", "en"),
        "theme": style.theme(brand),
        "scenes": scenes,
    }


STUDIO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "studio")


def _stage_one_asset(src_path: str, out_dir: str, rel: str) -> Optional[str]:
    """Copy one asset (audio OR image) into studio/public/<rel>, resolving src by
    absolute path, by basename under out_dir, by basename under out_dir's
    screenshots/, or as-given. Returns `rel` (public-relative) on a successful
    copy, else None. Remote (http) paths pass through unchanged.

    Remotion serves staticFile()-resolved assets from public/, so both <Audio>
    and the apple-screenshot <Img> need their file copied there with a
    public-relative name."""
    if not src_path:
        return None
    if src_path.startswith("http"):
        return src_path
    cands = [src_path,
             os.path.join(out_dir, os.path.basename(src_path)),
             os.path.join(out_dir, src_path),
             # screenshots land in runs/<id>/screenshots/ — try there too so a
             # bare "shot-01.png" or a screenshots-relative path resolves.
             os.path.join(out_dir, "screenshots", os.path.basename(src_path)),
             os.path.join(out_dir, "screenshots", src_path)]
    src = next((c for c in cands if os.path.exists(c)), None)
    if not src:
        return None
    pub = os.path.join(STUDIO_DIR, "public")
    os.makedirs(pub, exist_ok=True)
    import shutil
    shutil.copyfile(src, os.path.join(pub, rel))
    return rel


# Back-compat alias: the audio path historically called _stage_one_audio.
_stage_one_audio = _stage_one_asset


def _stage_audio(props: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
    """Stage the run's voiceover(s) into studio/public/ and rewrite paths to
    public-relative names. Remotion serves <Audio> via staticFile() under public/;
    an absolute filesystem path gets joined onto the webpack bundle root and 404s.

    Stages BOTH the full continuous track (top-level audio_path, kept as a fallback)
    AND each scene's per-beat VO file (scene.audio.src), so the Timeline can place
    each beat at its own — now stretched — scene start. Run-scoped names so parallel
    runs don't clobber each other. Mutates + returns props."""
    run_tag = os.path.basename(os.path.normpath(out_dir)) or "run"

    # Theme assets: BGM music (Task E/F) + real captured logo (Task F). Both are
    # staged into studio/public/ with run-scoped names and rewritten to public-
    # relative paths so Remotion's staticFile() resolves them. Each DROPS on a
    # missing source so a build with no music/logo still renders (graceful fallback):
    #   - missing music  -> theme.music removed; Timeline.tsx mounts no <Audio>.
    #   - missing logo   -> theme.logoSrc removed; bookends fall to the wordmark.
    theme = props.get("theme")
    if isinstance(theme, dict):
        music_src = theme.get("music")
        if music_src and not str(music_src).startswith("http"):
            mext = os.path.splitext(str(music_src))[1] or ".mp3"
            music_rel = f"music-{run_tag}{mext}"
            staged_music = _stage_one_asset(music_src, out_dir, music_rel)
            if staged_music:
                theme["music"] = staged_music
            else:
                theme.pop("music", None)
        logo_src = theme.get("logoSrc")
        if logo_src and not str(logo_src).startswith("http"):
            lext = os.path.splitext(str(logo_src))[1] or ".svg"
            logo_rel = f"brand-logo-{run_tag}{lext}"
            staged_logo = _stage_one_asset(logo_src, out_dir, logo_rel)
            if staged_logo:
                theme["logoSrc"] = staged_logo
            else:
                theme.pop("logoSrc", None)

    # Full continuous track (fallback path).
    ap = props.get("audio_path")
    if ap and not ap.startswith("http"):
        rel = f"vo-{run_tag}.mp3"
        staged = _stage_one_audio(ap, out_dir, rel)
        # public-relative (no leading slash) -> Timeline.tsx staticFile()s it.
        props["audio_path"] = staged or rel

    # Per-scene beat tracks (authoritative VO placement, one file per voiced scene)
    # AND per-scene screenshot images (apple-screenshot archetype). Both are staged
    # into public/ and rewritten to public-relative names; both DROP on a missing
    # file so the scene is never broken (audio falls back to the full track; the
    # apple-screenshot archetype has its own never-blank floor).
    for i, scene in enumerate(props.get("scenes", [])):
        audio = scene.get("audio")
        if audio and audio.get("src"):
            beat_rel = f"vo-{run_tag}-{scene.get('id', i)}.mp3"
            staged = _stage_one_asset(audio["src"], out_dir, beat_rel)
            if staged:
                audio["src"] = staged
            else:
                scene.pop("audio", None)

        # apple-screenshot image: stage scene.data.imageSrc the same way.
        data = scene.get("data") or {}
        img = data.get("imageSrc")
        if img and not str(img).startswith("http"):
            ext = os.path.splitext(str(img))[1] or ".png"
            img_rel = f"shot-{run_tag}-{scene.get('id', i)}{ext}"
            staged_img = _stage_one_asset(img, out_dir, img_rel)
            if staged_img:
                data["imageSrc"] = staged_img
            else:
                # drop the missing image; the archetype renders its caption/wordmark
                # placeholder rather than a broken <Img>.
                data.pop("imageSrc", None)

        # walkthrough-player clip: stage scene.data.videoSrc the same way. The clip
        # MUST be served from public/ for OffthreadVideo (an absolute fs path 404s
        # against the bundle root). Drop a missing clip so the archetype shows its
        # never-blank placeholder rather than a broken <OffthreadVideo>.
        vid = data.get("videoSrc")
        if vid and not str(vid).startswith("http"):
            vext = os.path.splitext(str(vid))[1] or ".mp4"
            vid_rel = f"walk-{run_tag}-{scene.get('id', i)}{vext}"
            staged_vid = _stage_one_asset(vid, out_dir, vid_rel)
            if staged_vid:
                data["videoSrc"] = staged_vid
            else:
                data.pop("videoSrc", None)
    return props


def run_pipeline(plan_path: str, brand_path: str, style_name: str, out_dir: str,
                 fps: int = 30, tier: str = "free",
                 do_align: bool = True, do_render: bool = False) -> Dict[str, Any]:
    """END-TO-END driver: plan + brand + style -> props.json (+ optional render).

    Chains align_vo -> build_timeline -> style_fill merge. `do_align=False` reuses
    an existing vo_alignment.json (fast deterministic re-merges / tests).
    Returns {props, props_path, timeline_path, alignment_path, montage_path?}.
    """
    os.makedirs(out_dir, exist_ok=True)
    plan = _load_json(plan_path)
    brand = _load_json(brand_path)
    # Task-F logo staging (R2 gap): the brand_theme.json written at brand-resolve
    # time predates screenshot capture, so brand_extract never saw the manifest's
    # captured logo (theme.logoSrc came out None even though brand/logo.svg existed).
    # The manifest DOES exist now (capture ran before style_fill), so inject the
    # captured logo into the brand dict HERE — _theme_kinetic_light reads
    # brand["logo_src"] -> theme.logoSrc and _stage_audio copies it into
    # studio/public/. No-op (graceful) when no logo was captured.
    try:
        import brand_extract
        brand_extract.apply_captured_logo(brand, out_dir)
    except Exception:
        pass  # never block a render on logo staging
    plan_scenes = _plan_scenes(plan)

    # VO<->VISUAL GROUNDING — align each screenshot scene's SPOKEN beat to the page the
    # capture step actually reached, so the narration and the (surface-aligned) on-screen
    # headline tell ONE coherent story (no "billing" VO over a /pricing shot). Runs BEFORE
    # synthesis (the manifest is already on disk — capture precedes run_pipeline) so the
    # grounded line is the audio that gets spoken. Only screenshot beats can change; the
    # bookend (title) + walkthrough beats are never touched. Runs BEFORE the condense pass
    # so the swapped-in surface line is itself length-capped to the pacing budget below.
    try:
        _ground_screenshot_vo_beats(plan, out_dir, brand)
    except Exception:
        pass  # never block a render on the grounding pass; original beats still align fine

    # ROBUSTNESS — copy-length guard. Cap each VO beat to its scene's pacing budget
    # AND the film's target duration BEFORE synthesis, so a DENSE planner (Ultra) does
    # not drive a 33s film off a 30s target and a SPARSE planner (Super) is left
    # untouched. This must run before align_vo so the (shorter) audio drives the
    # (shorter) timeline. plan_scenes already reflects plan["scenes"]; the condense
    # mutates plan["voiceover"].beats in place so cost/console/build all see it.
    try:
        _condense_vo_beats(plan, fps=fps)
    except Exception:
        pass  # never block a render on the condense pass; raw beats still align fine

    # SINGLE SOURCE OF TRUTH — persist the GROUNDED + condensed VO back into the run's
    # plan.json. The two passes above mutate plan["voiceover"].beats IN PLACE, and that
    # grounded copy is what align_vo synthesizes into vo_alignment.json + the audio. But
    # plan.json on disk still held the STALE pre-grounding VO, so anything that reads the
    # script FROM plan.json (e.g. an editor's script panel) would show the OLD mismatched
    # narration even though the rendered video is correct. Write the in-memory (grounded)
    # plan back so plan.json's voiceover.beats MATCH vo_alignment.json. plan_path is the
    # run's own runs/<id>/plan.json (build_runner/orchestrator write it there before this
    # call), so this updates the run artifact in place — never blocks a render on failure.
    try:
        with open(plan_path, "w", encoding="utf-8") as fh:
            json.dump(plan, fh, indent=2)
    except Exception:
        pass  # plan.json sync is advisory; the audio + props are already grounded

    alignment_path = os.path.join(out_dir, "vo_alignment.json")
    if do_align:
        beats = (plan.get("voiceover") or {}).get("beats") or []
        if not beats:
            raise ValueError("plan has no voiceover.beats to align")
        alignment = align_vo.align(beats, out_path=alignment_path, tier=tier,
                                   lang=(plan.get("voiceover") or {}).get("lang", "en"),
                                   voice=(plan.get("voiceover") or {}).get("voice"))
        with open(alignment_path, "w", encoding="utf-8") as fh:
            json.dump(alignment, fh, indent=2)
    else:
        alignment = _load_json(alignment_path)

    brand_fallback = brand.get("tagline") or brand.get("wordmark") \
        or brand.get("brand") or brand.get("name") or ""
    # Honor the planned film length: the scenes HOLD for plan duration_s (never
    # shorter than their VO), and the timeline is padded to job.target_duration_s.
    target_duration_s = (plan.get("job") or {}).get("target_duration_s") \
        if isinstance(plan, dict) else None

    # SCENE-ALIGNED VO DRIVES THE PICTURE LENGTH (the headline fix for the hosted/MCP
    # drift + trailing-silence bug). When align_vo emitted per-beat segments
    # (vo_aligned), each scene plays its OWN beat at its in_frame and must land ==
    # that beat's real speech length. Two plan-side levers otherwise inflate the
    # picture past the (~25s) VO span and re-introduce the bug:
    #   1. honor_plan_durations: each scene is floored to its plan duration_s, and a
    #      curated plan sets those to sum to the ~30s target (3+6+5+5+5+6) — so even
    #      with no grow pass the picture would hold ~30s while the voice is ~25s
    #      (trailing silence + the picture running ahead of the voice = drift).
    #   2. _grow_scenes_to_target: with job.target_duration_s (~30s) the grow pass
    #      inflates the holds to 30s on top of (1).
    # Turning honor_plan_durations OFF makes each VOICED scene exactly
    # max(VO word span, its per-beat mp3 speech length) — its own beat, no plan-hold
    # padding — AND gates the grow/shrink target pass off entirely (it is guarded by
    # `honor_plan_durations and target_duration_s`). Result: total video ~= total VO,
    # zero per-scene drift. The deterministic fallback (vo_aligned False / no per-beat
    # files) keeps the old plan-honoring + job.target_duration_s behavior untouched.
    vo_aligned = bool(isinstance(alignment, dict) and alignment.get("vo_aligned"))
    timeline = build_timeline.build_timeline(plan_scenes, alignment, fps=fps,
                                             brand_fallback=brand_fallback,
                                             target_duration_s=target_duration_s,
                                             honor_plan_durations=not vo_aligned)
    timeline_path = os.path.join(out_dir, "timeline.json")
    with open(timeline_path, "w", encoding="utf-8") as fh:
        json.dump(timeline, fh, indent=2)

    # Wire the REAL captured assets (screenshots + walkthrough clip) onto the plan's
    # screenshot/walkthrough scenes so build_props shapes data.imageSrc/videoSrc and
    # _stage_audio stages them into studio/public/. No-op when nothing was captured.
    wire_captured_assets(plan, out_dir)
    props = build_props(timeline, plan, brand, style_name)

    # BUILD-TIME LOGO STAGING — split-mosaic / logo-wall cards show a grid of REAL
    # company names (data.featureEntities). Fetch each entity's real brand mark and
    # stage it as a self-contained data URI on data.entityLogos[i] (index-aligned)
    # so the headless Remotion worker render needs ZERO render-time network. The
    # finalized treatment + featureEntities exist only HERE, on props["scenes"]
    # (build_props -> _shape_cards writes them), and props.json is written below, so
    # this is the correct (and only) point that sees the final scenes before they
    # persist. Best-effort: a fetch failure degrades each tile to "" (the name) and
    # NEVER fails a render. Scenes without a logo treatment are untouched.
    try:
        import entity_logos
        entity_logos.attach_entity_logos(props.get("scenes"))
    except Exception as e:
        print("[style_fill] entity logo staging skipped: %s" % e, file=sys.stderr)

    _stage_audio(props, out_dir)
    props_path = os.path.join(out_dir, "props.json")
    with open(props_path, "w", encoding="utf-8") as fh:
        json.dump(props, fh, indent=2)

    result = {
        "props": props, "props_path": props_path,
        "timeline_path": timeline_path, "alignment_path": alignment_path,
    }
    print(f"style_fill: wrote {props_path} "
          f"({len(props['scenes'])} scenes, {props['total_frames']} frames @ {props['fps']}fps, "
          f"style={style_name})")

    if do_render:
        result["montage_path"] = render_and_montage(props_path, out_dir)
    return result


def render_and_montage(props_path: str, out_dir: str) -> Optional[str]:
    """Render the Timeline composition with --props, then ffmpeg a tiled montage.

    Foreground + bounded. Returns the montage path (or None on failure)."""
    studio = STUDIO_DIR
    mp4 = os.path.abspath(os.path.join(out_dir, "video.mp4"))
    montage = os.path.abspath(os.path.join(out_dir, "montage.png"))
    abs_props = os.path.abspath(props_path)
    env = dict(os.environ, PATH=os.path.join(studio, "node_modules", ".bin")
               + os.pathsep + os.environ.get("PATH", ""))
    render_cmd = ["remotion", "render", "src/index.ts", "Timeline", mp4,
                  "--codec=h264", "--concurrency=50%", f"--props={abs_props}"]
    print("style_fill: rendering ->", mp4)
    r = subprocess.run(render_cmd, cwd=studio, env=env)
    if r.returncode != 0 or not os.path.exists(mp4):
        print("style_fill: render FAILED", file=sys.stderr)
        return None
    subprocess.run(["ffmpeg", "-y", "-i", mp4,
                    "-vf", "fps=1,scale=480:-1,tile=5x2", "-frames:v", "1", montage],
                   cwd=studio, env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("style_fill: montage ->", montage)
    return montage if os.path.exists(montage) else None


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fill a curated style template and drive the VO render.")
    ap.add_argument("--plan", required=True, help="plan.json (scenes + voiceover.beats)")
    ap.add_argument("--brand", required=True, help="brand_theme.json (palette/fonts/wordmark/features)")
    ap.add_argument("--style", default="orinovate-kinetic-light",
                    choices=sorted(STYLES), help="curated style template")
    ap.add_argument("--out", required=True, help="run output dir (runs/<id>/)")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--tier", default="free", choices=["free", "premium"])
    ap.add_argument("--no-align", action="store_true",
                    help="reuse existing vo_alignment.json in --out (skip synth)")
    ap.add_argument("--render", action="store_true",
                    help="also render the Timeline composition + a tiled montage")
    args = ap.parse_args(argv)

    run_pipeline(args.plan, args.brand, args.style, args.out, fps=args.fps,
                 tier=args.tier, do_align=not args.no_align, do_render=args.render)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# ENGINEERED NIGHT  (docs/references/engineered-night-design-language.md)
# ---------------------------------------------------------------------------
# Dennis's dark one-world style as a second registry entry (2026-07-17). The
# NightTimeline composition consumes the SAME props contract; this block only
# routes scenes to night-* archetypes and shapes their data. Copy honesty is
# inherited: every shaper reads plan/brand data the classic path already
# guards — nothing is invented here.

def _night_accent_split(headline: str) -> List[List[Dict[str, Any]]]:
    """Two headline lines with ONE accent phrase: split at the word midpoint and
    accent the longest content word (>=6 chars) — deterministic, brand-agnostic."""
    words = [w for w in str(headline or "").split() if w]
    if not words:
        return [[{"text": ""}]]
    mid = max(1, round(len(words) / 2))
    lines = [words[:mid], words[mid:]] if len(words) > 3 else [words]
    accent_word = max(words, key=lambda w: len(w.strip(".,!?")))
    if len(accent_word.strip(".,!?")) < 6:
        accent_word = None
    out = []
    for line in lines:
        if not line:
            continue
        parts, buf = [], []
        for w in line:
            if accent_word is not None and w == accent_word:
                if buf:
                    parts.append({"text": " ".join(buf) + " "})
                    buf = []
                parts.append({"text": w, "accent": True})
                accent_word = None  # accent only the first occurrence
                buf = [""]
            else:
                buf.append(w)
        tail = " ".join([b for b in buf if b])
        if tail:
            parts.append({"text": (" " if parts else "") + tail})
        out.append(parts or [{"text": " ".join(line)}])
    return out


def _shape_night_hero(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    base = _shape_hero(scene, brand)
    headline = base.get("title") or base.get("headline") or brand.get("wordmark") or ""
    sub = base.get("subtitle") or base.get("sub") or ""
    if _is_truncated_meta(sub):
        sub = ""
    cta = ((brand.get("copy") or {}).get("cta") or "").strip() or None
    return {
        "eyebrow": base.get("eyebrow") or None,
        "lines": _night_accent_split(headline),
        "sub": sub or None,
        "ctaPrimary": cta,
    }


def _shape_night_panel(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    base = _shape_screenshot(scene, brand)
    # Keep the classic `imageSrc` key so the archetype-agnostic public stager
    # (build_props tail) copies the capture into studio/public and rewrites it.
    return {"imageSrc": base.get("imageSrc"), "caption": base.get("caption") or None}


def _shape_night_quote(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    d = scene.get("data") or {}
    dur = scene.get("duration_s") or 8
    return {
        "quote": d.get("quote") or "",
        "quoteAttribution": d.get("quoteAttribution") or "",
        "holdFrames": int(round(float(dur) * 30)),
    }


def _shape_night_credibility(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    d = scene.get("data") or {}
    stat = d.get("stat") or {}
    raw = str(d.get("_text") or scene.get("brief") or "")
    label = stat.get("label") or _grounded_headline(raw, brand) or ""
    return {"eyebrow": None, "stat": {"value": stat.get("value") or "", "label": label}}


def _shape_night_terminal(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    d = scene.get("data") or {}
    steps = d.get("steps") or []
    lines = []
    for s in steps[:4]:
        text = (s.get("label") or s.get("title") or s.get("text") or "").strip() if isinstance(s, dict) else str(s).strip()
        if text:
            lines.append(text)
    raw = str(d.get("_text") or scene.get("brief") or "")
    title = _grounded_headline(raw, brand) or "How it works"
    # Stash the motif so the close can bookend with the SAME terminal (reference
    # grammar). brand is the per-run mutable dict build_props threads through.
    brand["_night_terminal_lines"] = lines[:2]
    return {"title": title, "lines": lines, "status": None}


def _shape_night_ecosystem(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    d = scene.get("data") or {}
    raw = str(d.get("_text") or scene.get("brief") or "")
    return {
        "headline": _grounded_headline(raw, brand) or None,
        "entities": d.get("featureEntities") or [],
        "logos": d.get("entityLogos") or [],
    }


def _shape_night_ladder(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    d = scene.get("data") or {}
    chips = d.get("featureEntities") or []
    raw = str(d.get("_text") or scene.get("brief") or "")
    return {
        "headline": _grounded_headline(raw, brand) or _title_from_text(raw) or "",
        "chips": chips[:6],
        "activeIndex": 0,
    }


def _shape_night_close(scene: Dict[str, Any], brand: Dict[str, Any]) -> Dict[str, Any]:
    base = _shape_hero(scene, brand)
    tagline = base.get("title") or base.get("headline") or ""
    words = tagline.split()
    accent_word = words[-1] if words else ""
    return {
        "tagline": tagline,
        "accentWord": accent_word,
        "chip": None,
        "terminalLines": brand.get("_night_terminal_lines") or None,
    }


_NIGHT_TREATMENT_ARCH = {
    "pull-quote": "night-quote",
    "split-stat": "night-credibility",
    "split-mosaic": "night-ecosystem",
    "process-pipeline": "night-terminal",
}


class NightStyle(Style):
    """Role routing + DATA-SIGNAL refinement. The classic card-treatment tag is
    honored when present, but it is assigned LATE in the classic flow — at night
    routing time feature beats usually carry only their seeded data. So the
    router inspects the same honest signals the treatment assigner uses:
    a real quote, a real stat, real process steps, a real entity set."""

    def archetype_for(self, scene: Dict[str, Any]) -> str:
        role = _scene_role(scene)
        if role in ("open", "hero", "title", "intro"):
            sid = str(scene.get("id") or "").lower()
            if "clos" in sid or "cta" in sid or "outro" in sid:
                return "night-close"
            return "night-hero"
        if role in ("close", "cta", "outro"):
            return "night-close"
        if role in ("screenshot", "site"):
            return "night-panel"
        d = scene.get("data") or {}
        treatment = str(d.get("treatment") or "").strip().lower()
        if treatment in _NIGHT_TREATMENT_ARCH:
            return _NIGHT_TREATMENT_ARCH[treatment]
        # Data-signal routing (honesty-inherited: these keys only exist when the
        # plan seeded REAL page/enrichment material).
        if str(d.get("quote") or "").strip() and str(d.get("quoteAttribution") or "").strip():
            return "night-quote"
        stat = d.get("stat") or {}
        if str(stat.get("value") or "").strip():
            return "night-credibility"
        steps = d.get("steps") or []
        if isinstance(steps, list) and len(steps) >= 2:
            return "night-terminal"
        entities = d.get("featureEntities") or []
        if isinstance(entities, list) and len(entities) >= 3:
            return "night-ecosystem"
        return "night-ladder"


STYLES["engineered-night"] = NightStyle(
    name="engineered-night",
    role_map={},  # routing is fully computed in archetype_for
    default_archetype="night-ladder",
    shapers={
        "night-hero": _shape_night_hero,
        "night-panel": _shape_night_panel,
        "night-quote": _shape_night_quote,
        "night-credibility": _shape_night_credibility,
        "night-terminal": _shape_night_terminal,
        "night-ecosystem": _shape_night_ecosystem,
        "night-ladder": _shape_night_ladder,
        "night-close": _shape_night_close,
    },
    # The Night composition derives its dark tokens itself; the theme just needs
    # the brand slots (accent, wordmark, logoSrc, music) the light builder fills.
    theme_fn=_theme_kinetic_light,
)
