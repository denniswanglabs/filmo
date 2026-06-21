# Hackathon Rules — Verification Findings

_Research pass 2026-06-20 for the **Hermes Agent Accelerated Business Hackathon** (NVIDIA × Stripe ×
Nous Research). Goal: answer the MUST-VERIFY open questions from `COMPETITION-COMPLIANCE-REVIEW.md`
with sourced citations. Method: WebSearch + WebFetch only; no Discord/auth access._

> **Why some cells are UNVERIFIED.** The canonical announcement is a single @NousResearch X post
> (`x.com/NousResearch/status/2066921443548348436`). WebFetch of that URL returns **HTTP 402** (X
> paywalls headless fetches), so I could not read the post body directly. However, the **search index
> has crawled the post**, so its indexed text surfaced verbatim across multiple WebSearch result
> snippets — those are quoted below and treated as "from the official source (indexed)." Anything the
> index never surfaced (eligibility/reuse clause, required-stack mandate, repo/OSI-license requirement,
> exact timezone) is **genuinely not present in any public coverage** and almost certainly lives only
> in the X post tail, the Discord pinned message, or the Typeform — none of which are headlessly
> readable. Those are flagged **UNVERIFIED — Dennis must check Discord/the form.**

---

## Findings table

| # | Question | Answer | Source | Confidence |
|---|---|---|---|---|
| 1 | **Reuse of a prior hackathon-winning project (Walk Agent)** — allowed? any "net-new / built during the event" clause? | **No reuse restriction found in any official source.** No "net-new," "built during the event," or "must be original" language appears anywhere in the indexed X-post text or other coverage. The official framing is open-ended: _"for builders making agents that can earn, spend, and run real operations at any scale"_ — no provenance constraint stated. **Cannot affirmatively confirm reuse is permitted from an official source.** | X post (indexed) `x.com/NousResearch/status/2066921443548348436` | **UNVERIFIED — Dennis must check Discord/the form.** Absence of a rule ≠ permission. Verify against the Discord pinned message + Typeform before relying on reusing Walk Agent IP. |
| 2a | **Required stack — must the entry run on Hermes / Nemotron / NemoClaw?** | Officially **framed as provided integrations, not hard mandates.** Indexed X text: _"Our NVIDIA integrations let your team run agents safely through NemoClaw, quickly…"_ and _"The new Stripe Skills for Hermes let your agent buy what it needs, provision its own SaaS, and pay for the services it uses."_ Wording is enabling ("let your team / let your agent"), never "must use." The event is named the **Hermes** Agent hackathon and Nemotron 3 Super is the documented default model, so use is clearly expected — but **no explicit "must use X" disqualification clause was found.** | X post (indexed); NVIDIA NemoClaw blog (`developer.nvidia.com/blog/deploy-self-evolving-agents-...`) confirms default model `nvidia/nemotron-3-super-120b-a12b` | **MED** for "framed as enabling, not mandated." **UNVERIFIED** on whether a hard mandate exists in the full rules — check Discord/form. |
| 2b | **Stripe — must it be a specific integration (Issuing / Checkout / agentic payments)?** | **No specific Stripe integration is mandated.** Official text describes the *capability*, not a required product: _"let your agent buy what it needs, provision its own SaaS, and pay for the services it uses"_ — i.e. the **Stripe Skills for Hermes** (buy / provision SaaS / pay-per-use). Issuing vs Checkout vs a specific skill is **not specified** as a requirement. | X post (indexed) `x.com/NousResearch/status/2066921443548348436` | **MED** — capability described, no specific-product requirement found. |
| 3a | **Public repo required?** | **Not stated in any official source found.** Submission requirements that ARE stated (see 3c) are: demo video tweet + Discord post + submission form. A code repo / public-repo requirement is **not mentioned** in any indexed coverage. | X post (indexed) | **UNVERIFIED — Dennis must check Discord/the form.** The Typeform likely asks for a repo link; could not read its fields (JS-rendered). |
| 3b | **OSI / open-source LICENSE required?** | **No license requirement found in any official source.** (Hermes Agent itself is open-source, but that is the tool, not a submission rule.) No OSI/license clause in indexed coverage. | X post (indexed) | **UNVERIFIED — Dennis must check Discord/the form.** |
| 3c | **Submission requirements (mechanics)** | **Three steps, confirmed from indexed X text:** (1) _"Tweet a 1–3 minute demo video tagging @NousResearch with a short writeup,"_ (2) _"Drop the link in the submissions channel"_ on the Nous Research Discord (**discord.gg/nousresearch**), and (3) **"Fill out the submission form"** at **`form.typeform.com/to/hpEifIK4`** (title confirmed via fetch: "Nous Research Accelerated Business Hackathon"). | X post (indexed); Typeform title confirmed at `form.typeform.com/to/hpEifIK4` | **HIGH** for the three-step mechanics, video length (1–3 min), @NousResearch tag, Discord channel, and form URL. |
| 3d | **Demo video length / format** | **1–3 minutes**, posted as a tweet (video on X), tagging **@NousResearch**, with a short writeup. No format/codec/resolution constraints stated. | X post (indexed) | **HIGH** on the 1–3 min length + tweet format. |
| 3e | **Deadline + timezone** | **Deadline: EOD Tuesday, June 30, 2026** (confirms the internal assumption). Phrasing surfaced as _"Submissions are due EOD Tuesday, June 30"_ / _"end of day Tuesday, June 30."_ **Timezone is NOT specified** in any indexed source. | X post (indexed) `x.com/NousResearch/status/2066921443548348436` | **HIGH** on the date (June 30, 2026). **UNVERIFIED** on timezone — "EOD" TZ unstated; assume the strictest plausible (PT) and confirm on Discord. |
| 4 | **Judging criteria + weights** | **Criteria confirmed: usefulness, viability, and presentation** (matches the internal assumption). Surfaced phrasing: _"judged by Nous Research, NVIDIA, and Stripe on usefulness, viability, and presentation."_ **No weights/percentages** are stated for the three axes, and **no sponsor-specific sub-criteria** (e.g. Stripe weighting real spend) were found. | X post (indexed) `x.com/NousResearch/status/2066921443548348436` | **HIGH** on the three criteria + the three judging orgs. **UNVERIFIED** on any weighting/sub-criteria — none published. |

---

## Cross-cutting confirmations (high confidence, from official/indexed sources)

- **Event name & framing:** "The Hermes Agent Accelerated Business Hackathon presented by @NVIDIAAI ×
  @stripe × @NousResearch … for builders making agents that can **earn, spend, and run real operations
  at any scale**." (X post, indexed.)
- **Teams allowed:** the official wording is "let **your team** run agents…" — implies solo or team
  participation is fine. (X post, indexed.) Exact team-size limits: not stated → UNVERIFIED.
- **Prizes (matches the compliance review):** 1st $10k + DGX Spark + $5k Stripe credits; 2nd $5k + DGX
  Spark + $3k; 3rd $2.5k + DGX Spark + $1k. (Multiple indexed sources.)
- **Judges:** Nous Research, NVIDIA, and Stripe. (X post, indexed.)
- **Default model:** `nvidia/nemotron-3-super-120b-a12b` ("NVIDIA Nemotron 3 Super"), per the NVIDIA
  NemoClaw technical blog — the exact model the compliance review already uses. (NVIDIA blog.)

## Confirmed NOT a match (disambiguation)

- The **DEV Community "Hermes Agent Challenge"** (`dev.to/.../join-the-hermes-agent-challenge-1000-in-prizes`,
  May 15–31, $1,000 prizes, DEV-post submissions, Build/Write tracks) is a **different, earlier event** —
  not this hackathon. Do not use its rules.

## Gaps I could NOT close from any official source (Dennis must verify on Discord + the Typeform)

1. **Reuse / net-new / "built during the event" eligibility** — no rule found either way. **The single
   highest-stakes open question for reusing Walk Agent.** Check the Discord pinned message + the Typeform.
2. **Hard "must use" mandate** for Hermes runtime / NemoClaw / a specific Stripe product — official text
   reads as enabling, not mandatory, but the full rules weren't readable. This directly affects the
   compliance review's HIGH-severity "Hermes doesn't drive the run" risk: if a Hermes-runtime mandate
   exists, that risk is disqualifying, not just weak.
3. **Public-repo requirement** and **OSI/open-source LICENSE requirement** — not stated publicly; the
   Typeform likely asks for a repo link (couldn't read its fields).
4. **Deadline timezone** — date is June 30, 2026; "EOD" timezone unstated.
5. **Judging weights / sponsor sub-criteria** — three axes confirmed; no weighting published.
6. **Eligibility fine print** — region, age, team size, prize/IP/tax terms — none published.

**How to close them fast:** open `form.typeform.com/to/hpEifIK4` in a real browser (its fields are the
canonical rules surface), and read the **pinned message in the submissions channel** at
`discord.gg/nousresearch`. Both require interactive/auth access this research pass did not have.

---

## Sources

- [Nous Research — Hermes Agent Accelerated Business Hackathon announcement (X)](https://x.com/NousResearch/status/2066921443548348436) — primary; body 402 to headless fetch, text recovered via search-index snippets.
- [Submission Typeform — "Nous Research Accelerated Business Hackathon"](https://form.typeform.com/to/hpEifIK4) — title confirmed; fields JS-rendered, not readable headlessly.
- [Nous Research Discord (submissions channel)](https://discord.gg/nousresearch) — not readable without auth.
- [NVIDIA Technical Blog — Deploy Self-Evolving Agents with a Hermes Agent and NVIDIA NemoClaw](https://developer.nvidia.com/blog/deploy-self-evolving-agents-for-faster-more-secure-research-with-a-hermes-agent-and-nvidia-nemoclaw/) — confirms default model; no hackathon rules.
- [DEV Community — "Hermes Agent Challenge" ($1,000)](https://dev.to/devteam/join-the-hermes-agent-challenge-1000-in-prizes-13cd) — a DIFFERENT, earlier event; disambiguation only.
