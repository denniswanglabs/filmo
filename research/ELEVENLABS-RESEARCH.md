# ElevenLabs Research for Walk Studio (June 2026)

Research date: 2026-06-21. Audience: Walk Studio producer brain (`producer.py`) +
Stripe agentic-commerce story for the Hermes hackathon (NVIDIA x Stripe x Nous).

Two goals:
1. Add ElevenLabs as a **premium VO option** over the free `edge-tts` baseline.
2. Find ElevenLabs capabilities Walk Studio can **charge customers extra for**
   (agentic commerce / "the agent earns money" is a scored axis).

---

## 0. HEADLINE FINDING — word/character-level timestamps: YES

**ElevenLabs returns per-character timestamps together with the synthesized audio
in a single call.** This is the key that makes the Walk Studio timeline
VO-driven: every visual beat can be choreographed to the exact spoken word.

- **Endpoint:** `POST https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps`
- **Granularity:** per-**character** (not per-word). Word timings are trivially
  derived by grouping characters on whitespace boundaries.
- **Units:** seconds (floating point, e.g. `0.1`).
- **Response JSON** (three top-level fields):
  - `audio_base64` (string) — the MP3 audio, base64.
  - `alignment` (object) — timing for the original text:
    - `characters`: `["H","e","l","l","o", ...]`
    - `character_start_times_seconds`: `[0.0, 0.05, ...]`
    - `character_end_times_seconds`: `[0.05, 0.09, ...]`
  - `normalized_alignment` (object) — same shape, for the *normalized* text (after
    number/abbreviation expansion). Use this when your script has "$5" / "Dr." etc.

  Source: [Create speech with timing — ElevenLabs Docs](https://elevenlabs.io/docs/api-reference/text-to-speech/convert-with-timestamps)

- **Streaming variant** also exists: `/v1/text-to-speech/{voice_id}/stream/with-timestamps`
  streams audio chunks plus alignment as it generates (lower time-to-first-byte).
- **Forced Alignment** (the inverse, for audio you already have): `POST /v1/forced-alignment`
  takes an audio file (up to 3 GB / 10 h) + a plain-text transcript (up to 675k
  chars) and returns a time-aligned transcript with word- and character-level
  timestamps. Billed at the Speech-to-Text rate. Use only if VO is recorded
  outside ElevenLabs; the `with-timestamps` TTS path is the primary one for us.
  Sources: [Forced Alignment](https://elevenlabs.io/docs/overview/capabilities/forced-alignment),
  [Eleven v3 Timing — WaveSpeedAI](https://wavespeed.ai/models/elevenlabs/eleven-v3/timing)

**Why this matters for Walk Studio:** treat the returned alignment (in seconds)
as the single source of truth for scene/caption timing. The producer emits a VO
track once, reads `character_end_times_seconds`, and snaps every cut, caption,
and lower-third to a real spoken-word boundary. This is also a premium-tier
*differentiator* we can sell (word-synced captions / kinetic typography).

---

## 1. Capability matrix

| Capability | What it is (June 2026) | Endpoint / model | Relevance to Walk Studio |
|---|---|---|---|
| **TTS — Eleven v3** | Most expressive model, GA 2026-03-14. 70+ languages, Audio Tags for emotion, 68% fewer complex-text errors. Higher latency (not real-time). | `eleven_v3` via `/v1/text-to-speech/{voice_id}` | **Primary premium VO.** Non-real-time is fine — we render offline. |
| **TTS — Flash v2.5** | Ultra-low latency (~75 ms), 32 languages, 0.5 credits/char. | `eleven_flash_v2_5` | Cheap bulk fallback; cuts VO COGS in half. |
| **TTS — Multilingual v2** | Long-standing high-quality model, 29 languages, 1 credit/char. | `eleven_multilingual_v2` | Reliable default if v3 too hot. |
| **with-timestamps** | Per-character timestamps + audio in one response. | `/v1/text-to-speech/{voice_id}/with-timestamps` | **THE alignment feature** (see §0). |
| **Instant Voice Cloning (IVC)** | Clone a voice from 1–2 min clean audio; ready in seconds; 32+ languages. | `/v1/voices/add` (clone) | Founder/brand voice as an upsell. Needs Starter+ for commercial. |
| **Professional Voice Cloning (PVC)** | ~30 min (ideally 2–3 h) audio; ~3–4 week training; far higher fidelity & emotional range. Creator plan+. | PVC pipeline | Recurring "brand voice" product; premium. |
| **Voice Design / synthetic voices** | Generate a brand-new synthetic voice from a text prompt (no source audio). | Voice Design API | Custom voice without recording the founder. |
| **Dubbing v2** | Automatic dub of a video/audio into another language, voice-preserving. Billed per **source minute**, **per target language** (3 languages = 3x minutes). | `/v1/dubbing` | Direct basis for the multilingual upsell. |
| **Sound Effects (Text-to-SFX v2)** | Generate cinematic SFX from a text prompt, 0.5–30 s, loopable. | `POST /v1/sound-generation` (`eleven_text_to_sound_v2`) | AI sound-design upsell. |
| **Eleven Music v2** | Studio-grade music generation from NL prompts (May 2026): stems, lyrics, full tracks, seamless looping, any length. | Music API | Custom-scored soundtrack upsell (licensing TBD — verify before reselling). |
| **Scribe v2 (STT)** | Launched Jan 2026, realtime (<150 ms) + batch (up to 48 speakers), 90+ languages, WER as low as 3.3% EN. | `/v1/speech-to-text` | Caption/transcript generation; powers forced alignment for external audio. |
| **Conversational AI / Agents** | Full voice-agent platform (per-minute billed). | Agents API | Not core to a render pipeline — note only. |
| **Auth & SDK** | REST; header `xi-api-key: <key>`. Official **Python** (`pip install elevenlabs`) and TypeScript SDKs. API included on all plans (incl. free); usage draws the same credit pool. | — | Drop-in; store key in `.env` / shell rc, never in chat. |

Sources: [Models](https://elevenlabs.io/docs/overview/models),
[Eleven v3 blog](https://elevenlabs.io/blog/eleven-v3),
[Text to Speech capability](https://elevenlabs.io/docs/overview/capabilities/text-to-speech),
[Latency](https://elevenlabs.io/docs/eleven-api/concepts/latency),
[Voice cloning concepts](https://elevenlabs.io/docs/eleven-api/concepts/voice-cloning),
[Professional Voice Cloning](https://elevenlabs.io/docs/eleven-creative/voices/voice-cloning/professional-voice-cloning),
[Dubbing](https://elevenlabs.io/docs/overview/capabilities/dubbing),
[Sound Effects API](https://elevenlabs.io/docs/api-reference/text-to-sound-effects/convert),
[ElevenLabs in 2026: v3, Agents, Music, Scribe](https://medium.com/the-ai-entrepreneurs/elevenlabs-in-2026-the-complete-guide-to-v3-agents-music-and-scribe-7f3c3bdfd201).

---

## 2. Pricing table (June 2026)

| Plan | $/mo | Credits/mo | $/1000 chars (effective) | Commercial license? | Notable unlocks |
|---|---|---|---|---|---|
| Free | $0 | 10,000 | n/a (no resale) | **No** — attribution required, cannot monetize | API access, but not for paid work |
| Starter | $5 | 30,000 | ~$0.167 | **Yes** (entry point) | Instant Voice Cloning |
| Creator | $22 | 100,000 | ~$0.22 | Yes | **Professional Voice Cloning**, 192 kbps, ~50 dub-min |
| Pro | $99 | 500,000 | ~$0.198 | Yes | ~250 dub-min, $0.24/dub-min overage |
| Scale | $330 | 2,000,000 | ~$0.165 | Yes | volume |
| Business | $1,320 | 11,000,000 | ~$0.12 | Yes | lowest unit cost |
| Enterprise | custom | custom | custom | Yes | SLAs, zero-retention |

Credit mechanics:
- **Multilingual v2 / v3:** 1 credit = 1 character.
- **Flash / Turbo v2.5:** 0.5 credits = 1 character (half cost).
- **Sound effects:** ~20 credits/sec when you set duration (max 30 s), ~100
  credits/generation when AI picks duration. (One help-doc section quotes
  40 credits/sec / 200 per gen — treat 20/sec as the planning floor and verify
  live before relying on it.)
- **Dubbing:** separate quota pool from TTS, billed **per source minute, per
  target language**. Pro overage $0.24/min, Creator overage $0.60/min.

**Commercial / resale:** any **paid** plan (Starter $5+) grants commercial rights
to generated audio, which covers reselling the finished video to Walk Studio
customers. The **Free** plan does **not** — so Walk Studio must run on at least
Starter, and realistically Creator ($22) to unlock Professional Voice Cloning for
the brand-voice product. Music licensing for resale is less clear-cut than
TTS/SFX — **verify the Eleven Music commercial terms before selling generated
soundtracks.**

Sources: [BIGVU 2026 pricing](https://bigvu.tv/blog/elevenlabs-pricing-2026-plans-credits-commercial-rights-api-costs/),
[ElevenLabs pricing](https://elevenlabs.io/pricing),
[Cekura pricing breakdown](https://www.cekura.ai/blogs/elevenlabs-pricing),
[Flexprice overage guide](https://flexprice.io/blog/elevenlabs-pricing-breakdown),
[SFX cost help article](https://help.elevenlabs.io/hc/en-us/articles/25735337678481-How-much-does-it-cost-to-generate-sound-effects),
[Geckodub dubbing pricing](https://blog.geckodub.com/elevenlabs-ai-dubbing-pricing).

### What a typical ~150-word VO actually costs us

150 words ≈ 900 characters (incl. spaces) ≈ ~60 s of speech.

- **v3 / Multilingual v2:** 900 credits. At ~$0.000167–0.00022/credit that is
  **~$0.15–0.20** of underlying ElevenLabs cost.
- **Flash v2.5:** 450 credits → **~$0.08–0.10**.

So the real COGS of a premium ElevenLabs VO on a short promo is **under 20 cents**.
The producer's current `ELEVENLABS_PER_1K_CHARS_CENTS = 30` (≈$0.30/1k chars) is
a *conservative* estimate that slightly over-prices COGS — keep it as a safe
upper bound, or split into v3 vs flash constants (see §4).

---

## 3. THE MONETIZATION QUESTION — ranked chargeable upsells

Walk Studio's lever: ElevenLabs COGS per video is **cents**, but the *perceived
value* (human-grade narration, a localized version, the founder's own voice) is
worth **tens of dollars** to a brand. Every line below feeds the existing
`producer.py` model: it raises `total_cogs_cents` by a known amount, and the
add-on's own price flows into `suggested_price_cents` via the margin formula. The
margins are extreme (90%+), which is exactly the agentic-commerce story for the
Stripe judges: **the agent quotes, charges, and pockets margin autonomously.**

Ranked best-first by (margin x demand x ease-of-integration):

### #1 — Multilingual versions ("dub into N languages") — BEST
- **What:** ship the same video in N languages. Each extra language is a fresh VO
  pass (v3 supports 70+) or a Dubbing v2 run, plus re-rendered captions (the
  alignment timestamps make caption re-timing automatic).
- **EL cost per language:** VO path ≈ **$0.15–0.20** (same as base VO). Dubbing
  path ≈ **$0.24–0.60 per source minute** (so ~$0.24–0.60 for a 1-min promo).
- **Customer price:** **$29–49 per added language** (roughly the base VO upsell
  price each — "~Nx the price" as Dennis framed it).
- **Margin:** ~$0.20 cost on a $39 add-on = **>99%**.
- **producer.py slot:** add one `voiceover`-type cost line per language to the
  scene list; `total_cogs += vo_cents * num_languages`; the per-language add-on
  price lifts `suggested_price_cents`. Naturally multiplies revenue with near-zero
  marginal cost — the single strongest agentic-commerce demo.

### #2 — Premium human-grade VO tier (v3) vs free edge-tts — FOUNDATION
- **What:** the default tier uses free `edge-tts` (en-US-AndrewNeural, robotic-ish);
  the premium tier swaps in ElevenLabs v3 with Audio Tags for emotional, broadcast-
  grade narration. This is the upsell every other one builds on.
- **EL cost:** **~$0.15–0.20** per ~150-word VO (see §2).
- **Customer price:** **$25–39** flat upgrade per video.
- **Margin:** ~$0.18 cost on a $29 upgrade = **~99%**.
- **producer.py slot:** make VO a tiered line item — `voiceover.tier in {free, premium}`.
  `free` → 0 cents COGS (edge-tts). `premium` → ElevenLabs cents via the existing
  `estimate_voiceover_cents`. The tier's surcharge raises the suggested price.
  Lowest-effort change, unlocks #1 and #3.

### #3 — Custom brand voice (clone the founder) — HIGHEST TICKET / RECURRING
- **What:** clone the founder's (or a chosen brand) voice once, then narrate every
  future video in it. IVC for fast/cheap; PVC for premium fidelity.
- **EL cost:** **$0** marginal (cloning draws no extra credits beyond a plan that
  already exists; PVC needs Creator $22/mo, amortized across all customers). Per-
  video VO with the clone costs the same ~$0.15–0.20 as #2.
- **Customer price:** **$199–499 one-time setup** + **$19–39/mo retainer** to keep
  the voice on file and generate ongoing videos.
- **Margin:** setup is almost pure margin (one-time labor + a few cents); the
  retainer is **>95%** after the $22 plan share. Recurring revenue = the cleanest
  Stripe subscription demo.
- **producer.py slot:** model the setup as a one-off `addons` line (fixed cents)
  and the retainer as a subscription handled by Stripe, not per-job COGS. Per
  video, the clone is just `voiceover.voice = <clone_id>` with the same premium
  VO cost. Licensing: Starter+ commercial rights cover reselling clone audio;
  IVC needs consent/ownership of the source voice.

### #4 — AI sound design / SFX pack
- **What:** generate scene-matched SFX (whooshes, UI clicks, ambience, stingers)
  via Text-to-SFX v2 to lift production value.
- **EL cost:** ~20 credits/sec. A pack of 10 cues x ~2 s = ~400 credits ≈
  **$0.07–0.09**.
- **Customer price:** **$15–25** per video as a "sound design" add-on.
- **Margin:** ~$0.08 cost on a $19 add-on = **>99%**.
- **producer.py slot:** new PAID line type `sfx` with cents = `seconds * 20 *
  cents_per_credit`; add to `total_cogs`. Cheap to build; modest demand on short
  promos, higher on cinematic pieces.

### #5 — Localized **regional** voices / accents
- **What:** not just another language — the *right* regional voice (e.g. zh-TW vs
  zh-CN, en-GB vs en-US, Latin-American vs Castilian Spanish) via voice selection
  or Voice Design. Sells to brands with specific target markets (e.g. Dennis's
  Taiwan outreach list).
- **EL cost:** same as a VO pass, **~$0.15–0.20**.
- **Customer price:** **$19–29** per regional variant (or bundled into #1).
- **Margin:** **>99%**.
- **producer.py slot:** a voice-selection parameter on the premium VO line; price
  as a small surcharge or fold into the per-language multiplier in #1.

### #6 (note, lower priority) — Custom soundtrack via Eleven Music
- **What:** generate an original branded music bed instead of stock library music.
- **EL cost:** per-generation credit cost (verify); likely **<$1** for a short cue.
- **Customer price:** **$25–49**.
- **Margin:** high, BUT **resale licensing for generated music is not as clearly
  granted as for TTS/SFX** — confirm Eleven Music commercial terms before
  selling. Until then, keep using royalty-free libraries (Pixabay) for the base
  tier and treat this as experimental.

### Upsell economics summary

| Rank | Upsell | EL cost (approx) | Customer price | Margin |
|---|---|---|---|---|
| 1 | Each added language | $0.20–0.60 | $29–49 / language | >99% |
| 2 | Premium v3 VO tier | $0.15–0.20 | $25–39 | ~99% |
| 3 | Custom brand voice | ~$0 + $0.20/vid | $199–499 + $19–39/mo | >95% |
| 4 | AI sound design pack | $0.07–0.09 | $15–25 | >99% |
| 5 | Regional voice/accent | $0.15–0.20 | $19–29 | >99% |
| 6 | Custom soundtrack | <$1 (verify license) | $25–49 | high, license risk |

---

## 4. Recommended VO integration into producer.py

1. **Keep `edge-tts` as the free base tier** (0 cents COGS). Add ElevenLabs v3 as
   the **premium** tier.
2. **Make VO a tiered line item.** In the `voiceover` object support
   `tier: "free" | "premium"`, `voice`, and `languages: [..]`.
   - `free` → return `(0, "edge-tts free baseline")`.
   - `premium` → existing `estimate_voiceover_cents` path.
3. **Split the rate constant by model** instead of one blunt 30c/1k:
   - `ELEVENLABS_V3_PER_1K_CHARS_CENTS = 20` (≈$0.20/1k, matches real v3 cost),
   - `ELEVENLABS_FLASH_PER_1K_CHARS_CENTS = 10` (half, for bulk/cheap mode).
   The current single `30` constant stays valid as a conservative upper bound if
   you'd rather not split yet.
4. **Multilingual = multiply the VO line.** `total_cogs += vo_cents * len(languages)`
   and surface one cost line per language so the gate/budget logic and the Stripe
   invoice both itemize them. This is the money-shot for the agentic-commerce axis.
5. **Add-on lines for SFX and brand-voice setup** as new PAID item types feeding
   `total_cogs`; their customer-facing surcharges raise `suggested_price_cents`
   through the unchanged `total_cogs / (1 - target_margin)` formula.
6. **Per-VO cost to budget against:** **~$0.20** (20 cents) for a ~150-word v3
   narration. Use 20c as the planning number; the existing 30c constant is a safe
   ceiling.

**Recommended default premium VO:** model `eleven_v3`, voice e.g. a polished
preset, called via `/v1/text-to-speech/{voice_id}/with-timestamps` so we get the
audio AND the per-character alignment in one shot — feeding the VO-driven
timeline at no extra API cost.
