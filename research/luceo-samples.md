# Luceo Studio sample videos — for embedding on the Walk Studio landing page

_Research pass: 2026-06-25. Read-only inspection (no files moved/converted/deleted)._

## Source of truth

The Luceo brand site already curates a finished, web-ready video portfolio:

- **Videos:** `/Users/dennis/Desktop/Projects/Luceo/luceo-site/public/video/*.mp4` (14 files, all 720p, 1.2–3.9 MB — already web-optimized loops pulled from the published YouTube cuts)
- **Posters:** one `*-thumbnail.jpg` (or `*-poster.jpg`) per video in the **same** folder — ready-made poster frames, use these for `<video poster=…>`
- **Captions:** several have `*.en.vtt` sidecars (orinovate, kuli, trayd, benchling, nanoclaw, ikala)
- **Catalog/metadata (descriptors, YouTube IDs, client-vs-concept):** `/Users/dennis/Desktop/Projects/Luceo/luceo-site/src/data/films.ts`
- **YouTube channel:** `https://www.youtube.com/@luceo-studio` (channel ID `UC3K9B7mewAFcUm7wayT-fRg`) — confirmed in both `films.ts` (`YOUTUBE_CHANNEL_URL`) and memory. Website `https://luceostudio.com`.

> These are the *exact* finished, brand-quality, embeddable samples. No need to re-render anything from the per-project Remotion/HyperFrames source dirs.

## Full inventory (ffprobe)

| File (under `luceo-site/public/video/`) | Duration | Resolution | fps | Size | Theme | What it shows |
|---|---|---|---|---|---|---|
| `orinovate-launch-720.mp4` | 79.4s | 1280×720 | 30 | 2.4M | **Light** | Orinovate 3D-print/CNC quote portal — clean light dashboard, navy sidebar, blue accent (zh UI). Client work. |
| `tappay-launch-720.mp4` | 64.1s | 1280×720 | 30 | 2.1M | **Light** | TapPay payments — warm cream bg, real-time transactions dashboard (NT$ figures), gold accent (zh). Concept. |
| `jgb-launch-720.mp4` | 60.1s | 1280×720 | 30 | 2.4M | **Light** | JGB Property mgmt — white bg, glass dashboard card, red accent, corner brackets (zh). Concept. |
| `smartbase-launch-720.mp4` | 59.0s | 1280×720 | 30 | 1.8M | **Light** | Smartbase mfg AI — "Reads any PO. Even handwritten." → ERP-ready rows; white bg, blue accent (EN). Concept. |
| `hotcake-launch-720.mp4` | 58.2s | 1280×720 | 30 | 1.8M | **Light** | Hotcake salon booking/POS — white bg, weekly calendar grid, pink accent (zh). Concept. |
| `cumie-launch-720.mp4` | 39.6s | **720×1280 (portrait)** | 30 | 3.9M | **Light** | Cumie AI dating assistant — phone mockup, chat opener generator, violet accent (zh). Client work. **Vertical 9:16.** |
| `ikala-launch-720.mp4` | 32.1s | 1280×720 | 30 | 1.5M | **Dark** | iKala Kolr KOL platform — dark navy cinematic, "Know the outcome before you pay" (blue accent). Concept. ⚠️ see note. |
| `nanoclaw-launch-720.mp4` | 31.6s | 1280×720 | 30 | 1.2M | **Light** | NanoClaw "Agents that collaborate" — light gray bg, two chat windows, "Message anywhere. Works everywhere." Concept. |
| `webduino-launch-720.mp4` | 30.1s | 1280×720 | 30 | 1.4M | **Light/split** | Webduino K-12 IoT — light block-coding panel + dark code editor side-by-side, multi-color blocks (zh). Concept. |
| `kuli-launch-720.mp4` | 30.1s | 1280×720 | 30 | 2.0M | **Light** | Kuli AI influencer marketing — soft lavender/peach aurora bg, prompt bar "Describe your ideal creator", purple accent (EN). Concept. |
| `trayd-launch-720.mp4` | 30.1s | 1280×720 | 30 | 1.5M | **Dark-ish** | Trayd construction back-office — muted slate bg, payroll dashboard + phone "$327 cash out", lime accent. Concept. |
| `benchling-launch-720.mp4` | 30.1s | 1280×720 | 30 | 1.3M | **Light** | Benchling biotech R&D cloud — light glass dashboard, colorful timeline/Gantt bars, AI assistant card. Concept. |
| `hero-loop-720.mp4` | 49.0s | 1280×720 | 30 | 1.3M | **Light** | Brand hero montage — stitched highlights across films (Kuli wordmark "Don't filter lists / Describe your ideal creator", etc.). The site's own hero loop. |
| `walk-livestream-720.mp4` | 20.0s | 1280×720 | 30 | 1.3M | (footage) | Real footage clip: Dennis on-camera at **NVIDIA GTC Taipei 2026 developer livestream** (Taipei skyline window, two people at laptops). Not an animated promo — it's the "Also Building" founder clip. |

## Recommendation — feature these on the Walk Studio landing page

The landing page is light-themed, so prefer the **light, landscape, short, visually punchy** promos. Top picks:

1. **`smartbase-launch-720.mp4`** (59s, 1.8M, light, EN) — strongest standalone story for a general audience: "Reads any PO. Even handwritten." → live ERP rows. English copy (no zh barrier), crisp white aesthetic, clear before/after. Best "what the agent makes" demo.
2. **`kuli-launch-720.mp4`** (30s, 2.0M, light, EN) — gorgeous soft-aurora + glass prompt-bar aesthetic, English, tight 30s. Visually the most premium/on-trend; reads instantly.
3. **`benchling-launch-720.mp4`** (30s, 1.3M, light, EN) — recognizable brand, colorful animated timeline, light glass UI, English, smallest file. Great variety vs. the other two.
4. **`hero-loop-720.mp4`** (49s, 1.3M, light) — purpose-built montage; ideal as the autoplaying muted hero/background reel if you want one "sizzle" piece rather than discrete cards.

Strong alternates if you want a 5th/6th or more visual variety:
- **`orinovate-launch-720.mp4`** — real *client* work (credibility), but 79s is long and the UI copy is Chinese; trim or caption if featured.
- **`cumie-launch-720.mp4`** — the only **vertical 9:16** piece; use only if the layout has a phone-shaped slot. Largest file (3.9M).
- **`trayd-launch-720.mp4`** — lime accent matches Walk's brand color; slightly darker/slate bg.

## Notes, sizes & theming flags

- **Size:** every file is **well under 15 MB** (max 3.9M for cumie). No compression needed for web embed. All H.264 MP4 720p30 — universally browser-playable.
- **Light vs dark (matters for a light landing page):** majority are **light** (smartbase, kuli, benchling, jgb, hotcake, hero-loop, orinovate, cumie, nanoclaw, webduino). **Darker** ones to use sparingly on a light page: `ikala` (dark navy), `trayd` (slate). `walk-livestream` is live footage, not a styled promo.
- **Language:** EN copy: smartbase, kuli, benchling, nanoclaw, trayd. zh (Traditional Chinese) UI/copy: orinovate, tappay, jgb, hotcake, cumie, webduino. For a global landing page, the EN ones read more universally.
- **Posters ready:** each video has a matching `*-thumbnail.jpg` (or `-poster.jpg`) in the same folder — wire as the `<video poster>` so the card looks good before play.
- **client vs concept:** per `films.ts`, only **Cumie, Orinovate, Kuli** (and the real Walk/iKala relationships) are tagged "client"; the rest are spec/concept pieces. If the landing copy implies "real client work," lean on Cumie/Orinovate; otherwise all are fair game as portfolio samples.

### Uncertainties / flags
- ⚠️ **`ikala-launch-720.mp4` content vs label:** the sampled frame reads "Know the outcome before you pay" on a dark cinematic bg — that copy is Walk/agent-flavored, not obviously an iKala-KOL-platform scene. The `films.ts` descriptor says "Taiwan KOL discovery and campaign platform." Either the loop opens on a generic dark title before the iKala UI, or this clip is mislabeled. Spot-check the full clip before featuring it as "iKala."
- The `hero-loop` frame I sampled shows Kuli branding because it's a **montage** stitched from multiple films — expected, not an error.
- `walk-livestream-720.mp4` is **real conference footage**, not a produced promo. It's the "Also Building" founder clip on luceostudio.com. Don't feature it as a sample film unless you specifically want a founder/credibility beat.

## Newest video in ~/Downloads
`ls -t ~/Downloads/*.mp4 | head -1` →
**`/Users/dennis/Downloads/ec80612d-00c6-4784-bd14-a3b70920c056_720p_mp4_30_16-9.mp4`** (2.8 MB, modified Jun 25 20:17, 720p 16:9 — UUID-named, looks like a fresh Hera/render export). _Not a Luceo-branded sample; flagged per the task only._

## YouTube handle (confirmed locally)
`@luceo-studio` → `https://www.youtube.com/@luceo-studio` (channel ID `UC3K9B7mewAFcUm7wayT-fRg`).
Confirmed in `luceo-site/src/data/films.ts` (`YOUTUBE_CHANNEL_URL`) and `~/.claude/.../memory/project_luceo_studio.md`. Note: `@LuceoStudio-x` is the **wrong/old** form (404) — do not use it.
