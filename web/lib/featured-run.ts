// Featured canonical run — the "developer mode" demo that never depends on a live
// build behaving. Every value here is REAL, harvested from the local pipeline runs at
// hermes-video-agent/runs/, not fabricated:
//
//  - Conversion Read   → generated live by the real free-tier Nemotron (super-free) via
//                        analyze.py over real captured stripe.com copy (degraded=false).
//  - Stripe decline + P&L → run `premium-plan` ledger.json (`pnl` + `card` + events):
//                        the agent's own Stripe Issuing card DECLINED scene s2_hero when
//                        it overran budget (99c vs 20c planned) → scene cut, $0 spent.
//  - NemoClaw capture  → real in-sandbox capture PNG (downscaled to public/inside/).
//
// /inside/[runId] renders this fixture when runId === FEATURED_RUN_ID; any other id is
// fetched live from InsForge via the readInsideRun server action.

export const FEATURED_RUN_ID = 'featured-stripe'

export interface ConversionDimension {
  key: 'promise' | 'outcome' | 'proof' | 'show' | 'specificity' | 'cta'
  score: number // 0-5
  finding: string
  evidence: string
  fix: string
}

export interface PriorityFix {
  rank: number
  fix: string
  maps_to: string
}

export interface ConversionRead {
  url: string
  verdict: string
  dimensions: ConversionDimension[]
  priority_fixes: PriorityFix[]
  headline_fix: string
  degraded: boolean
}

export interface StripeDecline {
  /** The scene whose charge the agent's Issuing card declined. */
  scene_id: string
  /** Why the authorization was declined (real Issuing decline reason). */
  reason: string
  /** What the scene would have cost had it been approved (cents). */
  would_have_cost_cents: number
  /** What it was planned/budgeted at (cents). */
  planned_cents: number
  /** The masked Issuing card the agent paid with. */
  card_last4: string
  /** Real Stripe Issuing card id (test mode). */
  card_id: string
  /** Human-readable event line, as the agent logged it. */
  event: string
}

export interface FeaturedRun {
  id: string
  brand: string
  company_url: string
  goal: string
  quality: 'standard' | 'premium'
  status: 'delivered'
  // P&L (cents) — exactly as the ledger recorded it.
  price_cents: number
  cogs_cents: number
  /** Margin as a fraction (0.9077 = 90.8%). formatMargin() normalizes. */
  margin: number
  overage_avoided_cents: number
  gross_profit_cents: number
  conversion_read: ConversionRead
  decline: StripeDecline
  nemoclaw_image: string
}

// REAL Conversion Read — produced by the live free-tier Nemotron (super-free / 120B)
// running analyze.py over real captured stripe.com page copy. degraded=false.
const conversionRead: ConversionRead = {
  url: 'https://stripe.com',
  verdict:
    'The headline and copy are vague and feature-heavy, lacking a clear outcome, proof, or specificity needed to convert visitors quickly.',
  dimensions: [
    {
      key: 'promise',
      score: 2,
      finding:
        "The headline 'Build internet businesses' is abstract and does not instantly clarify what Stripe does or who it's for.",
      evidence: 'Build internet businesses',
      fix: "Clarify the product and audience in the first 5 seconds, e.g., 'Stripe lets developers and businesses accept online payments globally.'",
    },
    {
      key: 'outcome',
      score: 2,
      finding:
        "The copy focuses on features (payments, billing, infrastructure) rather than the buyer's result or transformation.",
      evidence:
        'Online payments, billing, and financial infrastructure for the internet. Enable any billing model.',
      fix: "Lead with the outcome, such as 'Grow revenue faster with seamless global payments and automated billing.'",
    },
    {
      key: 'proof',
      score: 3,
      finding:
        "Mentions 'Millions of companies' but lacks specific, credible proof like logos, metrics, or testimonials.",
      evidence:
        'Millions of companies of all sizes use Stripe to accept payments, send payouts, and manage their businesses online.',
      fix: 'Add specific proof points such as well-known brand logos, uptime statistics, or revenue processed.',
    },
    {
      key: 'show',
      score: 1,
      finding:
        'No demonstration of the product working; all copy is descriptive or abstract.',
      evidence:
        'Online payments, billing, and financial infrastructure for the internet.',
      fix: 'Show a quick demo of a payment flow, dashboard, or integration in action.',
    },
    {
      key: 'specificity',
      score: 2,
      finding:
        "Relies on vague terms like 'backbone of global commerce' and 'financial infrastructure' without concrete details.",
      evidence:
        'Stripe is the backbone of global commerce. Powering businesses of all sizes.',
      fix: "Replace vague claims with specifics, e.g., 'Process payments in 135+ currencies' or 'Handle $1T+ in annual volume.'",
    },
    {
      key: 'cta',
      score: 3,
      finding:
        "CTA is present but weak and duplicated ('Get started. Contact sales.'), lacking a single clear next step.",
      evidence: 'Get started. Contact sales.',
      fix: "Use one strong, outcome-oriented CTA like 'Start accepting payments in minutes' with a clear button.",
    },
  ],
  priority_fixes: [
    {
      rank: 1,
      fix: 'Add a live demo or screenshot showing a payment being processed or dashboard in use',
      maps_to: 'show',
    },
    {
      rank: 2,
      fix: "Replace vague headline with an outcome-led statement like 'Accept global payments and grow revenue faster'",
      maps_to: 'outcome',
    },
    {
      rank: 3,
      fix: 'Include specific proof such as logos of well-known companies or volume processed metrics',
      maps_to: 'proof',
    },
  ],
  headline_fix: 'Accept payments from anywhere and grow your business faster',
  degraded: false,
}

// REAL Stripe Issuing decline — run `premium-plan` ledger.json.
// scene s2_hero production cost 99c vs planned 20c (overrun +79c) → RE-GATE after
// downgrade to gpt_image_2 → DECLINE → scene cut, $0 spent, 99c overage avoided.
const decline: StripeDecline = {
  scene_id: 's2_hero',
  reason: 'spending_controls — over per-scene budget after downgrade',
  would_have_cost_cents: 99,
  planned_cents: 20,
  card_last4: '0054',
  card_id: 'ic_1TldA6Aj3uJtl67Rudk87Mms',
  event:
    "scene 's2_hero' production cost 99c vs planned 20c (overrun +79c) — DECLINED even after downgrade to gpt_image_2; scene cut, $0 spent.",
}

// REAL P&L — run `premium-plan` ledger.json `pnl`.
// price 65c, COGS spent 6c, gross profit 59c, margin 0.9077 (90.8%), overage avoided 99c.
export const FEATURED_RUN: FeaturedRun = {
  id: FEATURED_RUN_ID,
  brand: 'stripe.com',
  company_url: 'https://stripe.com',
  goal: 'A 30-second brand explainer',
  quality: 'premium',
  status: 'delivered',
  price_cents: 65,
  cogs_cents: 6,
  margin: 0.9077,
  overage_avoided_cents: 99,
  gross_profit_cents: 59,
  conversion_read: conversionRead,
  decline,
  nemoclaw_image: '/inside/nemoclaw-capture.jpg',
}
