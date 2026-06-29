// The right-side edit panel. Pure controlled component: it receives `props` and
// an `update(mutator)` callback that applies an immutable change to props state in
// the parent; the parent re-renders the Player on every change -> live preview.
//
// Click-to-select wiring: a `focusField` prop ({ field, nonce }) arrives when an
// element is clicked in the live preview. We map the composition's `data-field`
// to the matching inspector control, scroll it into view, briefly flash it coral,
// and focus the text input where one exists. The `nonce` bumps on every click so
// re-selecting the same field re-triggers the effect.
import React, { useEffect, useRef, useState } from "react";
import { Section, TextField, NumberField, Slider, ColorField, Button, Icon } from "./ui.jsx";

// data-field on the composition element -> how the inspector reflects it.
//   kind "text"  -> the named text input (focus + flash it)
//   kind "geo"   -> the Geometry section (scroll + flash; no single input to focus)
//   kind "list"  -> the Lists section (scroll + flash; the per-item editors live there)
const FIELD_MAP = {
  // text fields — each lands on its named text input
  title: { kind: "text", key: "title" },
  subtitle: { kind: "text", key: "subtitle" },
  kicker: { kind: "text", key: "kicker" },
  heading: { kind: "text", key: "heading" },
  headingAccent: { kind: "text", key: "headingAccent" },
  punchWord: { kind: "text", key: "punchWord" },
  statement: { kind: "text", key: "statement" },
  headline: { kind: "text", key: "headline" },
  caption: { kind: "text", key: "caption" },
  overlayTitle: { kind: "text", key: "overlayTitle" },
  footnote: { kind: "text", key: "footnote" },
  product: { kind: "text", key: "product" },
  // visual / geometry fields — land on the Geometry section
  plate: { kind: "geo" },
  card: { kind: "geo" },
  // list containers — land on the Lists section (per-item rows live there)
  bullets: { kind: "list" },
  cards: { kind: "list" },
  entities: { kind: "list" },
};

// data-field -> the scene.data text key it edits, ONLY for fields that are plain
// single text values (which Inspector field a clicked element maps to, and which
// key writes its text). Derived from FIELD_MAP so it stays in sync.
export const TEXT_KEY_FOR_FIELD = Object.fromEntries(
  Object.entries(FIELD_MAP)
    .filter(([, m]) => m.kind === "text")
    .map(([field, m]) => [field, m.key])
);

// Text fields a scene's `data` may carry; we render an input for each PRESENT key
// (plus a few always-useful ones for hero/statement scenes).
const TEXT_FIELDS = [
  ["title", "Title"],
  ["kicker", "Kicker"],
  ["subtitle", "Subtitle"],
  ["heading", "Heading"],
  ["headingAccent", "Heading accent"],
  ["punchWord", "Punch word"],
  ["statement", "Statement"],
  ["headline", "Headline"],
  ["caption", "Caption"],
  ["overlayTitle", "Overlay title"],
  ["footnote", "Footnote"],
  ["product", "Product"],
];

// Per-archetype geometry sliders. Keys are written to scene.data.geo.<key>.
// A slider is ONLY listed for a (key) the matching archetype actually reads back
// as `data.geo?.<key> ?? <fallback>` (backward-compatible). The fallback here MUST
// equal the archetype's literal so absent-geo renders byte-identical.
const GEO = {
  "hero-title": [
    ["titleFontSize", "Title size", 40, 220, 132],
    ["subtitleFontSize", "Subtitle size", 16, 72, 34],
    ["plateW", "Plate width", 200, 1600, 1200],
    ["plateH", "Plate height", 120, 900, 720],
    // position nudge (px from center) — written by the preview drag (move).
    ["plateOffsetX", "Plate offset X", -600, 600, 0],
    ["plateOffsetY", "Plate offset Y", -400, 400, 0],
  ],
  // apple-hero reads titleFontSize (140) + subtitleFontSize (32). Its product
  // plate is padding-sized (not fixed W/H) so no plateW/plateH slider.
  "apple-hero": [
    ["titleFontSize", "Title size", 40, 220, 140],
    ["subtitleFontSize", "Subtitle size", 16, 72, 32],
  ],
  "apple-screenshot": [
    ["cardW", "Card width", 600, 1860, 1380],
    ["cardRadius", "Card radius", 0, 48, 18],
    ["shotH", "Screenshot height", 300, 1000, 712],
    // position nudge (px) — written by the preview drag (move).
    ["cardOffsetX", "Card offset X", -700, 700, 0],
    ["cardOffsetY", "Card offset Y", -400, 400, 0],
  ],
  // apple-statement reads statementFontSize (116) for the editorial wordmark.
  "apple-statement": [
    ["statementFontSize", "Statement size", 48, 200, 116],
  ],
};

const PRETTY_ARCHETYPE = (a) => (a || "scene").replace(/-/g, " ");

// Text fields each archetype can RENDER (and therefore click-select), even when
// the key is not yet present in scene.data. Used so a click on such an element
// always finds an editable row to focus (e.g. an explainer-card kicker that
// currently falls back to the wordmark, or an empty hero title). Union'd with
// whatever keys are actually present in scene.data.
const ARCHETYPE_TEXT_FIELDS = {
  "hero-title": ["title", "kicker", "subtitle", "punchWord"],
  "card-ui": ["heading", "headingAccent"],
  "explainer-card": ["kicker", "title", "subtitle"],
  "apple-hero": ["kicker", "title", "subtitle", "punchWord", "product"],
  "apple-registry": ["heading"],
  "apple-statement": ["statement", "footnote"],
  "apple-screenshot": ["headline", "caption"],
  "walkthrough-player": ["overlayTitle", "caption"],
};

// Generic list-of-objects editor (cards / entities) and list-of-strings (bullets).
function ListEditor({ label, list, fields, onChange }) {
  const arr = Array.isArray(list) ? list : [];
  const setRow = (i, patch) => onChange(arr.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const setStr = (i, v) => onChange(arr.map((r, j) => (j === i ? v : r)));
  const add = () => onChange([...arr, fields ? Object.fromEntries(fields.map((f) => [f, ""])) : ""]);
  const del = (i) => onChange(arr.filter((_, j) => j !== i));
  const rowCard = {
    background: "var(--field)",
    border: "1px solid var(--line)",
    borderRadius: 9,
    padding: 9,
    marginBottom: 7,
  };
  const cellStyle = {
    background: "var(--panel)",
    border: "1px solid var(--line)",
    borderRadius: 6,
    color: "var(--text)",
    padding: "6px 8px",
    fontSize: 12,
    outline: "none",
  };
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 7 }}>
        <span style={{ fontSize: 10.5, color: "var(--muted)", textTransform: "uppercase", letterSpacing: 1, fontWeight: 700 }}>{label}</span>
        <Button kind="tiny" onClick={add} icon={<Icon.plus />}>Add</Button>
      </div>
      {arr.map((row, i) => (
        <div key={i} style={rowCard}>
          {fields ? (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {fields.map((f) => (
                <input
                  key={f}
                  className="ws-input"
                  value={row?.[f] ?? ""}
                  placeholder={f}
                  onChange={(e) => setRow(i, { [f]: e.target.value })}
                  style={{ ...cellStyle, flex: "1 1 40%", minWidth: 78 }}
                />
              ))}
            </div>
          ) : (
            <input
              className="ws-input"
              value={row ?? ""}
              onChange={(e) => setStr(i, e.target.value)}
              style={{ ...cellStyle, width: "100%" }}
            />
          )}
          <div style={{ textAlign: "right", marginTop: 6 }}>
            <Button kind="danger" onClick={() => del(i)} icon={<Icon.trash />}>Remove</Button>
          </div>
        </div>
      ))}
      {arr.length === 0 ? (
        <div style={{ fontSize: 11, color: "var(--dim)", fontStyle: "italic" }}>No items yet — add one.</div>
      ) : null}
    </div>
  );
}

export function EditPanel({ props, activeIdx, setActiveIdx, update, focusField, musicAssetName }) {
  const scenes = props.scenes || [];
  const scene = scenes[activeIdx];
  const theme = props.theme || {};

  const rootRef = useRef(null);
  const textRefs = useRef({}); // key -> input/textarea node
  const [flashAnchor, setFlashAnchor] = useState(null); // which control flashes coral

  // When the preview reports an element click, reflect it in the inspector:
  // scroll the matching control into view, flash it, and focus the text input.
  useEffect(() => {
    const f = focusField?.field;
    if (!f) return;
    const map = FIELD_MAP[f];
    if (!map) return;
    const root = rootRef.current;

    if (map.kind === "text") {
      setFlashAnchor("text:" + map.key);
      const input = textRefs.current[map.key];
      const node = input || root?.querySelector(`[data-anchor="field-${map.key}"]`);
      node?.scrollIntoView?.({ behavior: "smooth", block: "center" });
      // Focus AFTER the scroll settles so it doesn't fight the smooth scroll.
      if (input) setTimeout(() => input.focus({ preventScroll: true }), 220);
    } else if (map.kind === "geo") {
      setFlashAnchor("sec-geometry");
      root?.querySelector('[data-anchor="sec-geometry"]')?.scrollIntoView?.({
        behavior: "smooth",
        block: "center",
      });
    } else if (map.kind === "list") {
      setFlashAnchor("sec-lists");
      root?.querySelector('[data-anchor="sec-lists"]')?.scrollIntoView?.({
        behavior: "smooth",
        block: "center",
      });
    }
    const t = setTimeout(() => setFlashAnchor(null), 900);
    return () => clearTimeout(t);
    // nonce in focusField guarantees re-fire on repeat clicks of the same field.
  }, [focusField]);

  // Immutable helpers scoped to the active scene.
  const setSceneData = (key, value) =>
    update((p) => {
      const next = structuredClone(p);
      next.scenes[activeIdx].data = { ...next.scenes[activeIdx].data, [key]: value };
      return next;
    });
  const setSceneGeo = (key, value) =>
    update((p) => {
      const next = structuredClone(p);
      const d = next.scenes[activeIdx].data;
      d.geo = { ...(d.geo || {}), [key]: value };
      return next;
    });
  const setSceneField = (key, value) =>
    update((p) => {
      const next = structuredClone(p);
      next.scenes[activeIdx][key] = value;
      return next;
    });
  const setTheme = (key, value) =>
    update((p) => ({ ...p, theme: { ...p.theme, [key]: value } }));

  // ── VOICEOVER: edit the active scene's narration beat (props.voiceover.beats[]).
  // VO text lives in props.voiceover (seeded from plan.voiceover.beats by the page),
  // NOT in scene.data. Editing flips props.voiceover.dirty so Export re-synthesizes.
  const setSceneVo = (text) =>
    update((p) => {
      const next = structuredClone(p);
      const vo = next.voiceover || (next.voiceover = { beats: [], dirty: false });
      if (!Array.isArray(vo.beats)) vo.beats = [];
      const sid = next.scenes[activeIdx]?.id;
      let beat = vo.beats.find((b) => b.scene_id === sid);
      if (!beat) {
        beat = { scene_id: sid, text: "" };
        vo.beats.push(beat);
      }
      beat.text = text;
      vo.dirty = true;
      return next;
    });

  // ── MUSIC: toggle the background bed + set a level (0..1.5). The composition reads
  // theme.music ?? music_path for the source and music_level for the volume scale.
  const setMusicEnabled = (on) =>
    update((p) => {
      const next = structuredClone(p);
      if (on) {
        next.music_path = next.music_path || musicAssetName || null;
        if (next.music_level == null) next.music_level = 1;
      } else {
        next.music_path = null;
        if (next.theme) next.theme.music = null;
      }
      return next;
    });
  const setMusicLevel = (v) =>
    update((p) => ({ ...p, music_level: v }));

  if (!scene) return <div style={{ padding: 20, color: "var(--muted)" }}>No scene selected.</div>;
  const data = scene.data || {};
  const geo = data.geo || {};
  const geoRows = GEO[scene.archetype] || null;
  // Render a text row for every key PRESENT in data, PLUS every key this archetype
  // can render (so click-to-select always lands on an editable input even when the
  // key is absent, e.g. an empty hero title or a wordmark-fallback kicker). Keep
  // TEXT_FIELDS ordering.
  const renderable = new Set(ARCHETYPE_TEXT_FIELDS[scene.archetype] || []);
  const textRows = TEXT_FIELDS.filter(([k]) => k in data || renderable.has(k));
  const hasLists = "bullets" in data || "cards" in data || "entities" in data;

  // VO + music state for the active scene.
  const vo = props.voiceover || null;
  const voBeats = vo && Array.isArray(vo.beats) ? vo.beats : null;
  const voBeat = voBeats ? voBeats.find((b) => b.scene_id === scene.id) : null;
  const voDirty = !!(vo && vo.dirty);
  const musicOn = !!(props.music_path || (props.theme && props.theme.music));
  const musicLevel = typeof props.music_level === "number" ? props.music_level : 1;
  const musicAvailable = !!(props.music_path || (props.theme && props.theme.music) || musicAssetName);

  return (
    <div ref={rootRef} style={{ paddingTop: 0, paddingBottom: 28 }}>
      {/* INSPECTOR header — light sticky header on the white panel */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 9,
          padding: "16px 18px 13px",
          position: "sticky",
          top: 0,
          zIndex: 2,
          background: "linear-gradient(180deg, var(--panel) 0%, var(--panel) 72%, rgba(255,255,255,0))",
          borderBottom: "1px solid var(--line)",
        }}
      >
        <span style={{ color: "var(--accent)", display: "flex" }}><Icon.sliders /></span>
        <span style={{ fontSize: 12, fontWeight: 800, letterSpacing: 0.2, color: "var(--text)" }}>Inspector</span>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 9.5, letterSpacing: 1.2, textTransform: "uppercase", color: "var(--muted)", fontWeight: 700 }}>
          {scenes.length} scene{scenes.length === 1 ? "" : "s"}
        </span>
      </div>

      {/* Active-scene context header — the dashboard's "selected well": a soft
          coral tint + a clean 1px coral border, no glow.
          marginTop:12 gives the card clear air below the sticky Inspector header
          so its full rounded TOP border shows instead of being clipped by the
          header's gradient/border that sits directly above it. */}
      <div
        style={{
          margin: "12px 14px 12px",
          padding: "11px 13px",
          background: "var(--accent-tint)",
          border: "1px solid var(--accent-line)",
          borderRadius: "var(--r-card)",
          display: "flex",
          alignItems: "center",
          gap: 10,
          boxShadow: "0 1px 2px rgba(20,23,28,.04)",
        }}
      >
        <div style={{ width: 32, height: 32, borderRadius: 9, background: "#fff", border: "1px solid var(--accent-line)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--accent)", flex: "0 0 auto" }}>
          <Icon.film />
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ fontSize: 9.5, letterSpacing: 1.4, textTransform: "uppercase", color: "var(--muted)", fontWeight: 700 }}>Editing scene {String(activeIdx + 1).padStart(2, "0")} of {String(scenes.length).padStart(2, "0")}</div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text)", fontFamily: "var(--code)" }}>{PRETTY_ARCHETYPE(scene.archetype)}</div>
        </div>
      </div>

      {/* GEOMETRY — headline feature (and where plate/card element-clicks land) */}
      {geoRows ? (
        <Section
          title="Geometry"
          hint="data.geo"
          icon={<Icon.sliders />}
          anchorId="sec-geometry"
          flash={flashAnchor === "sec-geometry"}
        >
          {geoRows.map(([key, label, min, max, fallback]) => (
            <Slider
              key={key}
              label={label}
              value={geo[key]}
              fallback={fallback}
              min={min}
              max={max}
              onChange={(v) => setSceneGeo(key, v)}
            />
          ))}
        </Section>
      ) : null}

      {/* TEXT (where title/subtitle/kicker element-clicks land) */}
      <Section title="Text" badge={textRows.length || undefined} icon={<Icon.type />}>
        {textRows.map(([k, label]) => (
          <TextField
            key={k}
            ref={(el) => (textRefs.current[k] = el)}
            anchorId={"field-" + k}
            flash={flashAnchor === "text:" + k}
            label={label}
            value={data[k]}
            multiline={k === "statement" || k === "subtitle"}
            onChange={(v) => setSceneData(k, v)}
          />
        ))}
        {textRows.length === 0 ? (
          <div style={{ fontSize: 11, color: "var(--dim)", fontStyle: "italic" }}>This scene carries no editable text.</div>
        ) : null}
      </Section>

      {/* VOICEOVER — the active scene's narration. Editing re-synthesizes on Export. */}
      <Section title="Voiceover" hint="this scene" icon={<Icon.play />}>
        {voBeats ? (
          <>
            <TextField
              label="Narration"
              value={voBeat ? voBeat.text : ""}
              multiline
              onChange={(v) => setSceneVo(v)}
            />
            <div
              style={{
                marginTop: 8,
                padding: "8px 11px",
                borderRadius: 9,
                fontSize: 11,
                lineHeight: 1.45,
                background: voDirty ? "var(--accent-tint)" : "var(--field)",
                border: "1px solid " + (voDirty ? "var(--accent-line)" : "var(--line)"),
                color: voDirty ? "var(--accent)" : "var(--muted)",
              }}
            >
              {voDirty
                ? "VO changed — Export will re-synthesize narration (ElevenLabs/edge-tts) and re-time the scenes before rendering."
                : "Edit the narration above. On Export the voiceover is re-synthesized and the timeline re-aligned to the new audio."}
            </div>
          </>
        ) : (
          <div style={{ fontSize: 11, color: "var(--dim)", fontStyle: "italic" }}>
            No editable voiceover script is available for this run.
          </div>
        )}
      </Section>

      {/* LISTS (where bullets/cards/entities element-clicks land) */}
      {hasLists ? (
        <Section title="Lists" icon={<Icon.list />} anchorId="sec-lists" flash={flashAnchor === "sec-lists"}>
          {"bullets" in data ? (
            <ListEditor label="Bullets" list={data.bullets} onChange={(v) => setSceneData("bullets", v)} />
          ) : null}
          {"cards" in data ? (
            <ListEditor label="Cards" list={data.cards} fields={["label", "value", "sub"]} onChange={(v) => setSceneData("cards", v)} />
          ) : null}
          {"entities" in data ? (
            <ListEditor label="Entities" list={data.entities} fields={["code", "name", "meta", "type"]} onChange={(v) => setSceneData("entities", v)} />
          ) : null}
        </Section>
      ) : null}

      {/* TIMING */}
      <Section title="Timing" hint="this scene" icon={<Icon.clock />}>
        <div style={{ display: "flex", gap: 9, marginBottom: 9 }}>
          <div style={{ flex: 1 }}>
            <NumberField label="In frame" value={scene.in_frame} onChange={(v) => setSceneField("in_frame", v)} min={0} suffix="f" />
          </div>
          <div style={{ flex: 1 }}>
            <NumberField label="Out frame" value={scene.out_frame} onChange={(v) => setSceneField("out_frame", v)} min={1} suffix="f" />
          </div>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "7px 11px",
            background: "var(--field)",
            border: "1px solid var(--line)",
            borderRadius: 9,
          }}
        >
          <span style={{ fontSize: 11, color: "var(--muted)" }}>Duration</span>
          <span style={{ fontSize: 12.5, fontWeight: 700, color: "var(--accent)", fontVariantNumeric: "tabular-nums" }}>
            {Math.max(0, (scene.out_frame || 0) - (scene.in_frame || 0))}f
          </span>
        </div>
      </Section>

      {/* MUSIC (global background bed) */}
      <Section title="Music" hint="whole video" icon={<Icon.film />}>
        <label style={{ display: "flex", alignItems: "center", gap: 9, cursor: musicAvailable ? "pointer" : "default", marginBottom: 10 }}>
          <input
            type="checkbox"
            checked={musicOn}
            disabled={!musicAvailable}
            onChange={(e) => setMusicEnabled(e.target.checked)}
            style={{ width: 16, height: 16, accentColor: "var(--accent)", cursor: musicAvailable ? "pointer" : "default" }}
          />
          <span style={{ fontSize: 12.5, fontWeight: 600, color: musicAvailable ? "var(--text)" : "var(--dim)" }}>
            Background music bed
          </span>
        </label>
        {musicAvailable ? (
          <>
            <Slider
              label="Music level"
              value={musicLevel}
              fallback={1}
              min={0}
              max={1.5}
              step={0.05}
              onChange={(v) => setMusicLevel(v)}
            />
            <div style={{ marginTop: 6, fontSize: 10.5, color: "var(--dim)", lineHeight: 1.4 }}>
              The bed auto-ducks under the voiceover. Level scales the whole curve
              (0 = silent, 1 = default, 1.5 = louder).
            </div>
          </>
        ) : (
          <div style={{ fontSize: 11, color: "var(--dim)", fontStyle: "italic" }}>
            No music bed was staged for this run.
          </div>
        )}
      </Section>

      {/* THEME (global) */}
      <Section title="Theme" hint="whole video" icon={<Icon.palette />}>
        <ColorField label="Accent" value={theme.accent} onChange={(v) => setTheme("accent", v)} />
        <ColorField label="Background" value={theme.bg} onChange={(v) => setTheme("bg", v)} />
        <ColorField label="Text" value={theme.text} onChange={(v) => setTheme("text", v)} />
        <ColorField label="Navy" value={theme.navy} onChange={(v) => setTheme("navy", v)} />
        <div style={{ height: 10 }} />
        <TextField label="Wordmark" value={theme.wordmark} onChange={(v) => setTheme("wordmark", v)} />
        <TextField label="Display font" value={theme.fontDisplay} onChange={(v) => setTheme("fontDisplay", v)} />
      </Section>
    </div>
  );
}
